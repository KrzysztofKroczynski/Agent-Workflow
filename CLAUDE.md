# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (uv recommended)
uv sync

# Run tests
uv run pytest

# Run a single test file
uv run pytest tests/test_executor.py

# Run a single test by name
uv run pytest tests/test_executor.py::test_name

# Run the CLI
uv run agentflow run ./examples/hello_world
uv run agentflow validate ./examples/hello_world
uv run agentflow tree ./examples/hello_world
```

## Architecture

**Core concept:** every unit of work is a folder (task). A minimal task is just `instructions.md`. A root task with `subtasks/` children IS the pipeline — no separate pipeline concept.

### Key components (`agentflow/core/`)

| File | Responsibility |
|---|---|
| `loader.py` | `TaskLoader` — scans folder tree, builds `Task` dataclass tree. `TaskLoader.load(path)` is the entry point. |
| `executor.py` | `TaskExecutor` — async engine; runs pre-hooks, invokes agent, dispatches subtasks (parallel via `asyncio.gather` or sequential), runs post-hooks. `run(path)` is the convenience entry point. |
| `tool.py` | `ToolRegistry` + `ToolSpec` + `@tool` decorator. Parses `tools.md`, imports `tools/*.py`, resolves inheritance per §2.10 of design doc. |
| `context.py` | `ContextManager` — shared state dict flowing through the tree; captures output; produces audit trail. |
| `agent.py` | `AgentProvider` ABC + `ProviderRegistry`. All LLM providers implement `configure()`, `call()`, `supports_tool_calling()`. |
| `config.py` | Cascading config resolution — merges `task.yaml` settings from root → child. |
| `templating.py` | Resolves `{% include "name" %}` in `instructions.md` from `shared/instructions/`. |

### Data flow

```
TaskLoader.load(path) → Task tree
TaskExecutor.run() → for each task:
    1. Pre-hook (hooks/pre_run.py)
    2. AgentProvider.call(instructions, tools, context) [if instructions.md exists]
    3. Run subtasks (parallel default, or sequential/graph)
    4. Final agent pass [if task has BOTH instructions AND subtasks]
    5. Post-hook (hooks/post_run.py)
    6. ContextManager.capture_output(task, response)
```

Context flows **vertically** only: parent → children → back to parent. Siblings never communicate directly.

### Tool resolution order (§2.10)

Own tools > shared tools (`use_shared`) > inherited ancestor tools. `scope: local` blocks inheritance. `block_tools` in a task prevents propagation to its children. `inherit_tools: false` disables inheritance entirely.

### Provider system

`ProviderRegistry.get(name, module_path, settings)` lazy-loads providers by module path. Only the `ollama` extra is wired in `pyproject.toml`; `claude` and `openai` providers are documented in the design but not yet implemented. `FakeProvider` (`agentflow/providers/fake.py`) is the test double — use it for all tests.

### Testing patterns

Tests use `tmp_workflow` fixture (from `conftest.py`) to materialize a folder layout from a dict, and `FixedRegistry` / `fake_registry` to inject `FakeProvider`. No real LLM calls in tests.

```python
async def test_something(tmp_workflow, fixed_registry):
    root_path = tmp_workflow({"instructions.md": "do the thing"})
    provider = FakeProvider()
    provider.configure(script=[AgentResponse(text="done", finish_reason="end_turn")])
    registry = fixed_registry(provider)
    loader = TaskLoader()
    root = loader.load(root_path)
    executor = TaskExecutor(root, registry, loader.registry)
    result = await executor.run()
```

### task.yaml schema

Defined as Pydantic models in `agentflow/schemas/task_schema.py`. Key fields: `name`, `priority` (default 50, use multiples of 10), `enabled`, `agent`, `settings` (max_retries, timeout), `input`, `output`, `subtasks.execution_type` (`parallel`|`sequential`|`graph`), `conditions.skip_if`, `inherit_tools`, `exclude_tools`, `block_tools`, `inherit_tools_depth`.
