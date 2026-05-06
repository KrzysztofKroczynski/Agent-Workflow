from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from agentflow.core.agent import AgentResponse, ProviderRegistry, ToolCall
from agentflow.core.config import (
    resolve_provider,
    resolve_provider_module,
    resolve_settings,
)
from agentflow.core.context import ContextManager, WorkflowResult
from agentflow.core.loader import Task
from agentflow.core.templating import render_instructions
from agentflow.core.tool import ToolContext, ToolRegistry, ToolSpec
from agentflow.exceptions import AgentflowError, TaskTimeoutError, ToolError
from agentflow.hooks.base import load_hook
from agentflow.utils.logging import get_logger
from agentflow.utils.reporter import RunReporter

logger = get_logger(__name__)


class TaskExecutor:
    def __init__(
        self,
        root: Task,
        provider_registry: ProviderRegistry,
        tool_registry: ToolRegistry,
        context: ContextManager | None = None,
        reporter: RunReporter | None = None,
    ) -> None:
        self.root = root
        self.providers = provider_registry
        self.tools = tool_registry
        self.context = context or ContextManager()
        self.reporter = reporter

    async def run(self) -> WorkflowResult:
        await self._run_task(self.root)
        return WorkflowResult(context=self.context.data, audit=self.context.audit)

    async def _run_task(self, task: Task) -> None:
        self.context.cascade_global_context(task)

        if task.config.conditions and task.config.conditions.skip_if:
            try:
                if eval(  # noqa: S307 - intentional, sandbox-ish
                    task.config.conditions.skip_if,
                    {"__builtins__": {}},
                    {"context": self.context.data},
                ):
                    logger.info("Skipping task '%s' (skip_if matched).", task.name)
                    return
            except Exception as e:
                raise AgentflowError(
                    f"skip_if evaluation failed for task '{task.name}': {e}"
                ) from e

        if not task.config.enabled:
            logger.info("Task '%s' is disabled — skipping.", task.name)
            return

        if self.reporter:
            self.reporter.task_start(task)

        audit = self.context.start_audit(task)
        try:
            self._run_hook(task, "pre_run")
            settings = resolve_settings(task)

            response_text = ""
            if task.has_instructions:
                response_text = await self._invoke_agent(task, settings)

            if task.is_branch:
                await self._run_subtasks(task)
                if task.has_instructions:
                    # Final pass to assemble child outputs (§2.6 "Both")
                    response_text = await self._invoke_agent(task, settings, final_pass=True)

            self._run_hook(task, "post_run")
            self.context.capture_output(task, response_text)
            self.context.finish_audit(audit, "ok")
            if self.reporter:
                self.reporter.task_done(task, "ok")
        except Exception:
            self.context.finish_audit(audit, "error")
            if self.reporter:
                self.reporter.task_done(task, "error")
            raise

    def _run_hook(self, task: Task, kind: str) -> None:
        hook_path = task.path / "hooks" / f"{kind}.py"
        fn = load_hook(hook_path)
        if fn is None:
            return
        ctx = ToolContext(
            workflow_root=task.workflow_root.path if task.workflow_root else task.path,
            task_path=task.path,
            state=self.context.data,
            logger=logger,
        )
        fn(ctx, task)

    async def _run_subtasks(self, task: Task) -> None:
        execution_type = (
            task.config.subtasks.execution_type if task.config.subtasks else "parallel"
        )
        if execution_type == "sequential":
            await self._run_sequential(task)
        elif execution_type == "loop":
            await self._run_loop(task)
        elif execution_type == "priority_groups":
            await self._run_priority_groups(task)
        else:
            await self._run_parallel(task)

    def _get_on_error(self, task: Task) -> str:
        if task.config.subtasks:
            return task.config.subtasks.on_error
        return "fail"

    async def _run_child(self, child: Task, on_error: str, iteration: int | None = None) -> bool:
        """Run one child task applying on_failure then on_error policy. Returns False on non-fatal failure."""
        on_failure = child.config.on_failure if child.config else "fail"
        try:
            await self._run_task(child)
            return True
        except Exception as exc:
            if on_failure == "skip":
                self.context.record_error(child.name, exc, iteration)
                logger.warning("Task '%s' failed and was skipped: %s", child.name, exc)
                return False
            if on_failure == "use_default":
                self.context.record_error(child.name, exc, iteration)
                default = child.config.default_output if child.config else {}
                self.context.data.update(default)
                logger.warning("Task '%s' failed; using default output.", child.name)
                return False
            # on_failure == "fail" — group policy decides
            if on_error in ("continue", "ignore"):
                self.context.record_error(child.name, exc, iteration)
                logger.warning("Task '%s' failed (%s): %s", child.name, on_error, exc)
                return False
            raise

    async def _run_sequential(self, task: Task) -> None:
        on_error = self._get_on_error(task)
        any_failed = False
        for child in task.subtasks:
            success = await self._run_child(child, on_error)
            if not success:
                any_failed = True
        if any_failed and on_error == "continue":
            raise AgentflowError(f"One or more subtasks of '{task.name}' failed.")

    async def _run_parallel(self, task: Task) -> None:
        on_error = self._get_on_error(task)
        results = await asyncio.gather(*(self._run_child(c, on_error) for c in task.subtasks))
        if not all(results) and on_error == "continue":
            raise AgentflowError(f"One or more subtasks of '{task.name}' failed.")

    async def _run_loop(self, task: Task) -> None:
        cfg = task.config.subtasks
        until = cfg.until if cfg else None
        max_iterations = cfg.max_iterations if cfg else None
        iteration_timeout = cfg.iteration_timeout if cfg else None
        on_max_iterations = cfg.on_max_iterations if cfg else "fail"
        on_error = self._get_on_error(task)

        if max_iterations is None:
            raise AgentflowError(f"Loop task '{task.name}' requires max_iterations.")

        for i in range(max_iterations):
            snap = self.context.snapshot()
            try:
                coro = self._run_loop_iteration(task, i)
                if iteration_timeout:
                    await asyncio.wait_for(coro, timeout=iteration_timeout)
                else:
                    await coro
            except asyncio.TimeoutError as exc:
                if on_error in ("continue", "ignore"):
                    self.context.restore(snap)
                    self.context.record_error(task.name, TaskTimeoutError(f"iteration {i} timed out"), i)
                    continue
                raise TaskTimeoutError(
                    f"Loop '{task.name}' iteration {i} timed out after {iteration_timeout}s."
                ) from exc
            except Exception as exc:
                if on_error in ("continue", "ignore"):
                    self.context.restore(snap)
                    self.context.record_error(task.name, exc, i)
                    continue
                raise

            if until:
                try:
                    if eval(until, {"__builtins__": {}}, {"context": self.context.data}):  # noqa: S307
                        logger.info("Loop '%s' condition met after %d iteration(s).", task.name, i + 1)
                        return
                except Exception as e:
                    raise AgentflowError(f"Loop 'until' eval failed in '{task.name}': {e}") from e

        if until:
            if on_max_iterations == "fail":
                raise AgentflowError(
                    f"Loop '{task.name}' reached max_iterations ({max_iterations}) without condition being met."
                )
            logger.warning("Loop '%s' hit max_iterations; proceeding with last result.", task.name)

    async def _run_loop_iteration(self, task: Task, iteration: int) -> None:
        for child in task.subtasks:
            await self._run_child(child, "fail", iteration)

    async def _run_priority_groups(self, task: Task) -> None:
        on_error = self._get_on_error(task)
        groups: dict[int, list[Task]] = {}
        for child in task.subtasks:
            m = re.match(r"^(\d+)_", child.name)
            pri = int(m.group(1)) if m else (child.config.priority if child.config else 50)
            groups.setdefault(pri, []).append(child)

        any_failed = False
        for group_tasks in (groups[k] for k in sorted(groups)):
            results = await asyncio.gather(*(self._run_child(c, on_error) for c in group_tasks))
            if not all(results):
                any_failed = True

        if any_failed and on_error == "continue":
            raise AgentflowError(f"One or more subtasks of '{task.name}' failed.")

    def _build_output_injection(self, task: Task) -> str:
        output = task.config.output
        if not output:
            return ""
        template = {key: f"<{type_hint}>" if type_hint else "..." for key, type_hint in output.items()}
        template_str = json.dumps(template, indent=2)
        return (
            "After completing all tool calls, respond with ONLY a JSON code block "
            "containing exactly these keys:\n"
            f"```json\n{template_str}\n```"
        )

    async def _invoke_agent(
        self, task: Task, settings: Any, final_pass: bool = False
    ) -> str:
        provider_name, provider_settings = resolve_provider(task)
        module_path = resolve_provider_module(task, provider_name)
        provider = self.providers.get(provider_name, module_path, provider_settings)

        shared_dir = (
            task.workflow_root.path / "shared"
            if task.workflow_root and (task.workflow_root.path / "shared").is_dir()
            else None
        )
        instructions = render_instructions(task.instructions or "", shared_dir)

        if task.config.output and "```json" not in instructions:
            injection = self._build_output_injection(task)
            instructions = f"{instructions}\n\n{injection}"

        visible = self.tools.resolve_for_task(task)
        tool_list = list(visible.values())

        # Build user message including input context (and child outputs on final pass)
        input_ctx = self.context.prepare_input(task)
        user_payload: dict[str, Any] = {"input": input_ctx}
        if final_pass and task.subtasks:
            user_payload["child_outputs"] = {
                child.name: self.context.data.get(child.name)
                for child in task.subtasks
            }
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": json.dumps(user_payload, default=str)}
        ]

        attempts_remaining = max(1, settings.max_retries)
        last_error: Exception | None = None
        while attempts_remaining > 0:
            attempts_remaining -= 1
            try:
                return await asyncio.wait_for(
                    self._agent_loop(provider, instructions, tool_list, messages, task, visible),
                    timeout=settings.timeout,
                )
            except asyncio.TimeoutError as e:
                last_error = TaskTimeoutError(
                    f"Task '{task.name}' timed out after {settings.timeout}s."
                )
                if attempts_remaining == 0:
                    raise last_error from e
            except Exception as e:
                last_error = e
                if attempts_remaining == 0:
                    raise
                logger.warning("Task '%s' failed (%s); retrying.", task.name, e)
        raise last_error or AgentflowError("agent loop exhausted retries")

    async def _agent_loop(
        self,
        provider: Any,
        instructions: str,
        tool_list: list[ToolSpec],
        messages: list[dict[str, Any]],
        task: Task,
        visible: dict[str, ToolSpec],
    ) -> str:
        last_text = ""
        for _ in range(20):  # hard cap on tool-use turns
            if self.reporter:
                self.reporter.agent_call(task, instructions, messages, tool_list)
            response: AgentResponse = provider.call(instructions, tool_list, messages)
            last_text = response.text or last_text
            if self.reporter:
                self.reporter.agent_response(task, response.text or "", bool(response.tool_calls))
            if not response.tool_calls:
                return response.text or last_text
            messages.append(
                {
                    "role": "assistant",
                    "content": response.text or "",
                    "tool_calls": [tc.__dict__ for tc in response.tool_calls],
                }
            )
            for call in response.tool_calls:
                spec = visible.get(call.name)
                if spec is None:
                    raise ToolError(
                        f"Agent tried to call unknown tool '{call.name}' in task '{task.name}'."
                    )
                ctx = ToolContext(
                    workflow_root=task.workflow_root.path if task.workflow_root else task.path,
                    task_path=task.path,
                    state=self.context.data,
                    logger=logger,
                )
                result = self.tools.invoke(spec, ctx, **call.arguments)
                if self.reporter:
                    self.reporter.tool_call(task, call.name, call.arguments, result)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": json.dumps(result, default=str),
                    }
                )
        return last_text


async def _run_async(root: Task, provider_registry: ProviderRegistry, tool_registry: ToolRegistry) -> WorkflowResult:
    executor = TaskExecutor(root, provider_registry, tool_registry)
    return await executor.run()


def run(path: str, provider_registry: ProviderRegistry | None = None) -> WorkflowResult:
    """Convenience entry point. Loads the task tree and runs it synchronously."""
    from pathlib import Path

    from agentflow.core.loader import TaskLoader

    loader = TaskLoader()
    root = loader.load(Path(path))
    registry = provider_registry or ProviderRegistry()
    return asyncio.run(_run_async(root, registry, loader.registry))
