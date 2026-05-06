# AgentFlow

> **Agentic AI workflows where each task is a folder.**

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Status: MVP](https://img.shields.io/badge/status-MVP-orange)]()

Build multi-step AI workflows by organizing folders on your filesystem. Each folder is a task — it holds instructions, tools, config, and can nest subtasks. The framework handles orchestration, context passing, and LLM routing. No separate "pipeline" concept: a root task with children **is** the pipeline.

---

## Why folders?

| Property | Benefit |
|---|---|
| Human-readable | Browse and edit tasks like any code |
| Version-controllable | Diff instructions, review tool changes in git |
| Self-contained | Each task has everything it needs, no wiring |
| Uniform at every depth | Same rules for root tasks, subtasks, and sub-subtasks |
| Zero config to start | Just `instructions.md` — no YAML required |

---

## Quickstart

**Minimal task** — one file:

```
my_task/
└── instructions.md
```

That's it. Name inferred from folder. All defaults applied.

**Full task** — all optional features:

```
my_task/
├── task.yaml           # config, input/output, metadata
├── instructions.md     # agent prompt (natural language)
├── tools.md            # tool definitions (python/shell/http/mcp/reference)
├── tools/              # complex Python tools (merged with tools.md)
│   └── transform.py
├── hooks/              # pre/post execution hooks
│   ├── pre_run.py
│   └── post_run.py
└── subtasks/           # nested children (auto-discovered)
    ├── child_a/
    └── child_b/
```

A folder is recognized as a task if it contains `instructions.md`, `task.yaml`, or `subtasks/`. Anything else is ignored.

---

## Workflow example

```
my_workflow/
├── task.yaml                   # providers, global settings
├── shared/
│   └── tools.md                # reusable tools (opt-in via use_shared)
└── subtasks/
    ├── fetch_data/
    │   └── instructions.md
    ├── process/
    │   ├── instructions.md
    │   └── tools/
    │       └── transform.py
    └── generate_report/
        └── subtasks/
            ├── charts/
            └── summary/
```

---

## Core concepts

### Tasks

A task can be a **leaf** (runs agent), a **branch** (orchestrates children), or **both** (agent runs, then children, then agent assembles results).

### Data flow

Data flows **vertically** — parent provides input context to children, children return output to parent. Siblings never communicate directly. Parent mediates. This keeps tasks composable: adding or removing a subtask never breaks siblings.

```
Root Task
  ├─── Task A  ──outputs──► Root
  ├─── Task B  ──outputs──► Root
  └─── Task C
         └─── Task C.1 ──outputs──► Task C ──outputs──► Root
```

> Need sibling dependencies? Use `depends_on` for DAG-style execution — but use it sparingly.

### Tools

Tools are callable capabilities defined in `tools.md` (one file, any type) or `tools/*.py` (complex cases). Both are auto-discovered and merged. Children inherit ancestor tools; scoping rules give fine-grained control:

| Control | Where | How |
|---|---|---|
| `scope: local` | tool side (`tools.md`) | tool stays in declaring task only |
| `inherit_tools` | task side (`task.yaml`) | whitelist or disable inheritance |
| `exclude_tools` | task side | blacklist specific tools |
| `block_tools` | task side | prevent propagation to children |
| `inherit_tools_depth` | task side | limit ancestor walk depth |

### Discovery & ordering

Subtasks are **auto-discovered** from `subtasks/`. Explicit `subtasks.order` in `task.yaml` overrides. Children sort by `priority` (default `50`, use multiples of 10 — insert `15` between `10` and `20` without renumbering). Set `enabled: false` to skip without deleting.

### Config cascade

```
root task.yaml  →  child task.yaml  →  grandchild task.yaml
```

Scalars: child wins. Lists: child replaces. Dicts: deep-merged. Each task controls its own timeout, retries, and provider without affecting siblings.

---

## Providers

Provider-agnostic via abstract `AgentProvider`. Select globally or override per-task. Only install what you use.

| Provider | Install extra | Status |
|---|---|---|
| Ollama (local models) | `.[ollama]` | ✅ shipped |
| Claude (Anthropic) | `.[claude]` | planned |
| OpenAI | `.[openai]` | planned |
| Custom | point `module:` at your `AgentProvider` subclass | supported |

---

## Installation

```bash
# Core
pip install -e .

# With local model support (Ollama)
pip install -e ".[ollama]"

# Development
pip install -e ".[dev]"
```

Requires **Python 3.11+**.

---

## Configuration

**Root `task.yaml`** — providers and global defaults:

```yaml
providers:
  default: "ollama"
  ollama:
    module: "agentflow.providers.ollama"
    model: "llama3.1:70b"
    base_url: "http://localhost:11434"

settings:
  max_retries: 3
  timeout: 300
  parallel_workers: 4
```

**Child `task.yaml`** — only what differs:

```yaml
name: "fetch_data"
priority: 20
settings:
  timeout: 120
input:
  required: [api_base_url]
output: [raw_data]
dependencies:
  - requests>=2      # pip packages needed by this task's tools or hooks
```

---

## Defining tools

`tools.md` — H2 heading = tool name, blockquote = metadata, code block = implementation:

~~~markdown
## search_api
> type: python

Search the external API for records matching a query.

```python
def search_api(ctx: ToolContext, query: str, limit: int = 10) -> dict:
    return ctx.http.get(
        f"{ctx.get('api_base_url')}/search",
        params={"q": query, "limit": limit}
    ).json()
```

## run_script
> type: shell

Run a data processing script.

```bash
python scripts/process.py --input "$INPUT" --output "$OUTPUT"
```
~~~

**Tool types:** `python` · `shell` · `http` · `mcp` · `reference`

For tools that need multiple files or heavy imports, use `@tool`-decorated functions in `tools/*.py`:

```python
# tools/search.py
from agentflow import tool, ToolContext

@tool(description="Search the external API for records matching a query")
def search_api(ctx: ToolContext, query: str, limit: int = 10) -> dict:
    ...
```

---

## CLI

```bash
# Run a full workflow
agentflow run ./my_workflow

# Run a single task (useful during development)
agentflow run-task ./my_workflow/subtasks/fetch_data --context '{"api_base_url": "..."}'

# Validate task tree structure
agentflow validate ./my_workflow

# Resume a failed workflow from last checkpoint
agentflow resume ./my_workflow --from process

# Scaffold a new task
agentflow init ./new_workflow
agentflow init ./new_workflow/subtasks/new_task

# Inspect workflow state
agentflow status ./my_workflow
agentflow tree ./my_workflow
```

---

## Execution model

```
1. Load root config
2. Discover children (auto or explicit)
3. For each child (in priority order):
   a. Prepare input context
   b. Run pre-hooks
   c. Invoke agent with instructions + tools + context  [if instructions.md]
   d. Dispatch subtasks  [sequential | parallel | graph | loop | priority_groups]
   e. Final agent pass to assemble child outputs  [if both instructions + subtasks]
   f. Run post-hooks
   g. Merge output into context
4. Return final context
```

### Execution types

| Type | Behaviour |
|---|---|
| `parallel` | All subtasks run concurrently (default) |
| `sequential` | Subtasks run one by one in priority order |
| `graph` | DAG via `depends_on` — independent tasks run in parallel, dependents wait |
| `loop` | Re-runs the subtask group as one iteration until an `until` condition is met or `max_iterations` is reached |
| `priority_groups` | Tasks grouped by `N_name` prefix — groups run sequentially, tasks within a group run in parallel |

**Loop example** — generate-review cycle:

```yaml
# cv_pipeline/task.yaml
subtasks:
  execution_type: loop
  until: "context.get('approved') == True"
  max_iterations: 5
  iteration_timeout: 120   # seconds per iteration
  on_max_iterations: fail  # fail | succeed_with_last
```

**Priority groups example** — zero config, name-driven:

```
subtasks/
    10_fetch_a/    ─┐ parallel
    10_fetch_b/    ─┘
    20_process/    ── waits for group 10
    30_report/     ── waits for group 20
```

```yaml
subtasks:
  execution_type: priority_groups
```

Execution state is checkpointed after each task under `.agentflow/checkpoints/` — failed workflows can resume from the last successful step.

---

## Error handling

Two levels of control:

**Task-level `on_failure`** — how this task's own failure is treated:

```yaml
on_failure: skip        # swallow error, continue pipeline
# or
on_failure: use_default
default_output:
  result: ""            # injected into context as if task succeeded
```

**Group-level `on_error`** — what the executor does when any child fails:

```yaml
subtasks:
  on_error: continue    # run all, fail at end
  # or
  on_error: ignore      # run all, pipeline succeeds regardless
```

`on_failure` takes precedence over `on_error`. Failed non-fatal tasks append to `context._errors` — downstream tasks and agent passes can inspect it:

```yaml
conditions:
  skip_if: "not any(e['task'] == 'fetch_data' for e in context.get('_errors', []))"
```

---

## Status

MVP. Core framework is working end-to-end:

- [x] Task executor, loader, config hierarchy
- [x] Context management
- [x] Tool registry, `@tool` decorator, inheritance & scoping
- [x] Instruction templating (`{% include %}`)
- [x] Ollama provider
- [x] CLI (`run`, `validate`, `tree`, `status`)
- [x] Test suite
- [x] Loop execution type (`until`, `max_iterations`, `iteration_timeout`)
- [x] Priority groups execution type (`N_name` prefix convention)
- [x] Error handling — `on_failure`, `on_error`, `context._errors`
- [ ] Claude provider
- [ ] OpenAI provider
- [ ] Streaming output
- [ ] Web UI

See [`docs/design.md`](docs/design.md) for full architecture and design decisions.

---

## License

MIT
