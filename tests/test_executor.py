from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from agentflow.core.agent import AgentResponse, ProviderRegistry
from agentflow.core.context import ContextManager
from agentflow.core.executor import TaskExecutor
from agentflow.core.loader import TaskLoader
from agentflow.providers.fake import FakeProvider


PROVIDERS_BLOCK = """
providers:
  default: fake
  fake:
    module: agentflow.providers.fake
"""


class FixedRegistry(ProviderRegistry):
    def __init__(self, provider: FakeProvider) -> None:
        super().__init__()
        self._provider = provider

    def get(self, name: str, module_path: str, settings: dict[str, Any]) -> FakeProvider:  # type: ignore[override]
        return self._provider


@pytest.mark.asyncio
async def test_leaf_task_runs(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": f"name: root\n{PROVIDERS_BLOCK}",
            "instructions.md": "say hi",
        }
    )
    loader = TaskLoader()
    task = loader.load(root)
    fake = FakeProvider()
    fake.configure(script=[AgentResponse(text="hello")])
    executor = TaskExecutor(task, FixedRegistry(fake), loader.registry, ContextManager())
    result = await executor.run()
    assert result.context["root"] == "hello"


@pytest.mark.asyncio
async def test_three_task_pipeline(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": f"name: pipe\n{PROVIDERS_BLOCK}\n",
            "subtasks": {
                "fetch": {
                    "task.yaml": "priority: 10\noutput: [raw_data]\n",
                    "instructions.md": "fetch",
                },
                "process": {
                    "task.yaml": "priority: 20\noutput: [processed]\n",
                    "instructions.md": "process",
                },
                "report": {
                    "task.yaml": "priority: 30\n",
                    "instructions.md": "report",
                },
            },
        }
    )
    loader = TaskLoader()
    task = loader.load(root)
    # parallel by default — order of fake responses keyed by call sequence,
    # but FakeProvider returns same response if list is shorter; use callable.
    responses = {
        "fetch": AgentResponse(text='```json\n{"raw_data": [1, 2]}\n```'),
        "process": AgentResponse(text='```json\n{"processed": "ok"}\n```'),
        "report": AgentResponse(text="all done"),
    }

    def script(instructions, tools, messages):
        for key, resp in responses.items():
            if key in instructions:
                return resp
        return AgentResponse(text="?")

    fake = FakeProvider()
    fake.configure(script=script)
    executor = TaskExecutor(task, FixedRegistry(fake), loader.registry, ContextManager())
    result = await executor.run()
    assert result.context["raw_data"] == [1, 2]
    assert result.context["processed"] == "ok"
    assert result.context["report"] == "all done"


@pytest.mark.asyncio
async def test_skip_if_short_circuits(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": f"name: root\n{PROVIDERS_BLOCK}\n",
            "instructions.md": "go",
            "subtasks": {
                "skipme": {
                    "task.yaml": "conditions:\n  skip_if: \"context.get('flag') == True\"\n",
                    "instructions.md": "x",
                }
            },
        }
    )
    loader = TaskLoader()
    task = loader.load(root)
    fake = FakeProvider()
    fake.configure(script=[AgentResponse(text="parent")])
    cm = ContextManager({"flag": True})
    executor = TaskExecutor(task, FixedRegistry(fake), loader.registry, cm)
    result = await executor.run()
    assert "skipme" not in result.context


@pytest.mark.asyncio
async def test_tool_call_loop(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": f"name: root\n{PROVIDERS_BLOCK}\n",
            "tools.md": (
                "## add\n> type: python\n\nAdd two numbers.\n\n"
                "```python\ndef add(a: int, b: int) -> int:\n    return a + b\n```\n"
            ),
            "instructions.md": "compute",
        }
    )
    loader = TaskLoader()
    task = loader.load(root)
    from agentflow.core.agent import ToolCall

    call_count = [0]

    def script(instructions, tools, messages):
        call_count[0] += 1
        if call_count[0] == 1:
            return AgentResponse(
                text="",
                tool_calls=[ToolCall(id="1", name="add", arguments={"a": 2, "b": 3})],
                finish_reason="tool_use",
            )
        # Confirm tool result was appended
        last = messages[-1]
        assert last["role"] == "tool"
        assert json.loads(last["content"]) == 5
        return AgentResponse(text="result is 5")

    fake = FakeProvider()
    fake.configure(script=script)
    executor = TaskExecutor(task, FixedRegistry(fake), loader.registry, ContextManager())
    result = await executor.run()
    assert result.context["root"] == "result is 5"
    assert call_count[0] == 2


@pytest.mark.asyncio
async def test_sequential_subtasks_in_order(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": (
                f"name: root\n{PROVIDERS_BLOCK}\n"
                "subtasks:\n  execution_type: sequential\n  order: [first, second]\n"
            ),
            "subtasks": {
                "first": {"instructions.md": "1"},
                "second": {"instructions.md": "2"},
            },
        }
    )
    loader = TaskLoader()
    task = loader.load(root)
    seen = []

    def script(instructions, tools, messages):
        # The user message contains JSON-serialized input — peek at the audit instead
        return AgentResponse(text=f"r{len(seen)+1}")

    def wrapped(instructions, tools, messages):
        seen.append(messages[0]["content"])
        return script(instructions, tools, messages)

    fake = FakeProvider()
    fake.configure(script=wrapped)
    executor = TaskExecutor(task, FixedRegistry(fake), loader.registry, ContextManager())
    result = await executor.run()
    audit_names = [a.task_name for a in result.audit if a.task_name in ("first", "second")]
    assert audit_names == ["first", "second"]


@pytest.mark.asyncio
async def test_on_failure_skip(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": f"name: root\n{PROVIDERS_BLOCK}\nsubtasks:\n  execution_type: sequential\n",
            "subtasks": {
                "bad": {
                    "task.yaml": "on_failure: skip\n",
                    "instructions.md": "fail_me",
                },
                "good": {"instructions.md": "ok"},
            },
        }
    )
    loader = TaskLoader()
    task = loader.load(root)

    def script(instructions, tools, messages):
        if "fail_me" in instructions:
            raise RuntimeError("deliberate")
        return AgentResponse(text="done")

    fake = FakeProvider()
    fake.configure(script=script)
    executor = TaskExecutor(task, FixedRegistry(fake), loader.registry, ContextManager())
    result = await executor.run()
    assert result.context["good"] == "done"
    assert any(e["task"] == "bad" for e in result.context["_errors"])


@pytest.mark.asyncio
async def test_on_failure_use_default(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": f"name: root\n{PROVIDERS_BLOCK}\nsubtasks:\n  execution_type: sequential\n",
            "subtasks": {
                "fetcher": {
                    "task.yaml": (
                        "on_failure: use_default\n"
                        "default_output:\n  raw_data: []\n"
                    ),
                    "instructions.md": "fail_me",
                },
            },
        }
    )
    loader = TaskLoader()
    task = loader.load(root)

    def script(instructions, tools, messages):
        if "fail_me" in instructions:
            raise RuntimeError("deliberate")
        return AgentResponse(text="ok")

    fake = FakeProvider()
    fake.configure(script=script)
    executor = TaskExecutor(task, FixedRegistry(fake), loader.registry, ContextManager())
    result = await executor.run()
    assert result.context["raw_data"] == []
    assert any(e["task"] == "fetcher" for e in result.context["_errors"])


@pytest.mark.asyncio
async def test_on_error_continue_sequential(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": (
                f"name: root\n{PROVIDERS_BLOCK}\n"
                "subtasks:\n  execution_type: sequential\n  on_error: continue\n"
            ),
            "subtasks": {
                "first": {"instructions.md": "fail_me"},
                "second": {"instructions.md": "ok"},
            },
        }
    )
    loader = TaskLoader()
    task = loader.load(root)
    ran = []

    def script(instructions, tools, messages):
        if "fail_me" in instructions:
            raise RuntimeError("deliberate")
        ran.append("second")
        return AgentResponse(text="done")

    fake = FakeProvider()
    fake.configure(script=script)
    executor = TaskExecutor(task, FixedRegistry(fake), loader.registry, ContextManager())
    with pytest.raises(Exception):
        await executor.run()
    assert "second" in ran
    assert any(e["task"] == "first" for e in executor.context.data.get("_errors", []))


@pytest.mark.asyncio
async def test_on_error_ignore_parallel(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": (
                f"name: root\n{PROVIDERS_BLOCK}\n"
                "subtasks:\n  on_error: ignore\n"
            ),
            "subtasks": {
                "bad": {"instructions.md": "fail_me"},
                "good": {"instructions.md": "ok"},
            },
        }
    )
    loader = TaskLoader()
    task = loader.load(root)

    def script(instructions, tools, messages):
        if "fail_me" in instructions:
            raise RuntimeError("deliberate")
        return AgentResponse(text="success")

    fake = FakeProvider()
    fake.configure(script=script)
    executor = TaskExecutor(task, FixedRegistry(fake), loader.registry, ContextManager())
    result = await executor.run()
    assert result.context["good"] == "success"
    assert any(e["task"] == "bad" for e in result.context["_errors"])


@pytest.mark.asyncio
async def test_loop_runs_until_condition(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": (
                f"name: root\n{PROVIDERS_BLOCK}\n"
                "subtasks:\n"
                "  execution_type: loop\n"
                "  max_iterations: 5\n"
                "  until: \"context.get('approved') == True\"\n"
            ),
            "subtasks": {
                "reviewer": {
                    "task.yaml": "output: [approved]\n",
                    "instructions.md": "review",
                },
            },
        }
    )
    loader = TaskLoader()
    task = loader.load(root)
    call_count = [0]

    def script(instructions, tools, messages):
        call_count[0] += 1
        approved = call_count[0] >= 3
        return AgentResponse(text=f'```json\n{{"approved": {str(approved).lower()}}}\n```')

    fake = FakeProvider()
    fake.configure(script=script)
    executor = TaskExecutor(task, FixedRegistry(fake), loader.registry, ContextManager())
    result = await executor.run()
    assert result.context["approved"] is True
    assert call_count[0] == 3


@pytest.mark.asyncio
async def test_loop_fails_on_max_iterations(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": (
                f"name: root\n{PROVIDERS_BLOCK}\n"
                "subtasks:\n"
                "  execution_type: loop\n"
                "  max_iterations: 3\n"
                "  until: \"context.get('approved') == True\"\n"
                "  on_max_iterations: fail\n"
            ),
            "subtasks": {
                "reviewer": {
                    "task.yaml": "output: [approved]\n",
                    "instructions.md": "review",
                },
            },
        }
    )
    loader = TaskLoader()
    task = loader.load(root)
    fake = FakeProvider()
    fake.configure(script=[AgentResponse(text='```json\n{"approved": false}\n```')])
    executor = TaskExecutor(task, FixedRegistry(fake), loader.registry, ContextManager())
    with pytest.raises(Exception, match="max_iterations"):
        await executor.run()


@pytest.mark.asyncio
async def test_priority_groups_order(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": (
                f"name: root\n{PROVIDERS_BLOCK}\n"
                "subtasks:\n  execution_type: priority_groups\n"
            ),
            "subtasks": {
                "10_fetch_a": {"instructions.md": "fetch_a"},
                "10_fetch_b": {"instructions.md": "fetch_b"},
                "20_process": {"instructions.md": "process"},
            },
        }
    )
    loader = TaskLoader()
    task = loader.load(root)
    finished: list[str] = []

    def script(instructions, tools, messages):
        finished.append(instructions.strip())
        return AgentResponse(text="ok")

    fake = FakeProvider()
    fake.configure(script=script)
    executor = TaskExecutor(task, FixedRegistry(fake), loader.registry, ContextManager())
    await executor.run()
    assert finished.index("process") > finished.index("fetch_a")
    assert finished.index("process") > finished.index("fetch_b")


@pytest.mark.asyncio
async def test_output_injection_appended_when_no_json_block(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": f"name: root\n{PROVIDERS_BLOCK}\noutput: [greeting]\n",
            "instructions.md": "say hello",
        }
    )
    loader = TaskLoader()
    task = loader.load(root)
    seen_instructions = []

    def script(instructions, tools, messages):
        seen_instructions.append(instructions)
        return AgentResponse(text='```json\n{"greeting": "hi"}\n```')

    fake = FakeProvider()
    fake.configure(script=script)
    executor = TaskExecutor(task, FixedRegistry(fake), loader.registry, ContextManager())
    result = await executor.run()
    assert result.context["greeting"] == "hi"
    assert "exactly these keys" in seen_instructions[0]
    assert "greeting" in seen_instructions[0]


@pytest.mark.asyncio
async def test_output_injection_skipped_when_json_block_present(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": f"name: root\n{PROVIDERS_BLOCK}\noutput: [greeting]\n",
            "instructions.md": 'say hello\n\n```json\n{"greeting": "value"}\n```\n',
        }
    )
    loader = TaskLoader()
    task = loader.load(root)
    seen_instructions = []

    def script(instructions, tools, messages):
        seen_instructions.append(instructions)
        return AgentResponse(text='```json\n{"greeting": "hi"}\n```')

    fake = FakeProvider()
    fake.configure(script=script)
    executor = TaskExecutor(task, FixedRegistry(fake), loader.registry, ContextManager())
    await executor.run()
    assert "exactly these keys" not in seen_instructions[0]


@pytest.mark.asyncio
async def test_output_dict_form_with_types(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": (
                f"name: root\n{PROVIDERS_BLOCK}\n"
                "output:\n  score: int\n  label: str\n"
            ),
            "instructions.md": "classify",
        }
    )
    loader = TaskLoader()
    task = loader.load(root)
    seen_instructions = []

    def script(instructions, tools, messages):
        seen_instructions.append(instructions)
        return AgentResponse(text='```json\n{"score": 42, "label": "good"}\n```')

    fake = FakeProvider()
    fake.configure(script=script)
    executor = TaskExecutor(task, FixedRegistry(fake), loader.registry, ContextManager())
    result = await executor.run()
    assert result.context["score"] == 42
    assert result.context["label"] == "good"
    assert "<int>" in seen_instructions[0]
    assert "<str>" in seen_instructions[0]
