from __future__ import annotations

import asyncio
import json
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
        execution_type = "parallel"
        if task.config.subtasks and task.config.subtasks.execution_type:
            execution_type = task.config.subtasks.execution_type

        if execution_type == "sequential":
            for child in task.subtasks:
                await self._run_task(child)
        else:
            await asyncio.gather(*(self._run_task(c) for c in task.subtasks))

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
