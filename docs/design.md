# Agentic Workflow Framework - Design Document

## 1. Vision

A Python framework for building agentic AI workflows where **each task is a folder** on the filesystem. Folders contain instructions, tools, configuration, and can nest subtasks as subfolders. The framework orchestrates execution, manages context, and routes control flow between tasks.

## 2. Core Concepts

### 2.1 Task (Folder)

A **task** is a directory that represents a unit of work. Everything is a task — including what would traditionally be called a "pipeline." A root task with children IS the pipeline.

**Minimal task** — just one file:

```
my_task/
    instructions.md
```

Name inferred from folder. All defaults apply. That's it.

**Full task** — all optional features:

```
my_task/
    task.yaml          # Config overrides, input/output, metadata (optional)
    instructions.md    # Natural language instructions for the agent
    tools.md           # Tool definitions — python, shell, http, mcp, reference (optional)
    tools/             # Complex Python tools needing multiple files (optional, merged with tools.md)
        search.py
        transform.py
    hooks/             # Pre/post execution hooks (optional)
        pre_run.py
        post_run.py
    subtasks/          # Nested child tasks (auto-discovered)
        subtask_a/
        subtask_b/
```

### 2.2 Everything is a Task

There is no separate "pipeline" concept. A root task with children IS the pipeline:

```
my_workflow/
    task.yaml              # Root task config (providers, global settings)
    instructions.md        # Root-level instructions
    subtasks/
        fetch_data/
            instructions.md
        process/
            instructions.md
            tools/
                transform.py
        generate_report/
            instructions.md
            subtasks/       # Nesting works at any depth
                charts/
                    instructions.md
                summary/
                    instructions.md
```

This means the same rules (discovery, config cascade, execution) apply uniformly at every level.

### 2.3 Tool

A **tool** is a callable capability the agent can invoke during task execution. Tools can be Python functions, shell commands, HTTP endpoints, MCP server references, or plain descriptions.

Tools are defined in `tools.md` (one file, multiple tools) or as Python modules in `tools/` (for complex cases). Both are auto-discovered. A task has access to its own tools plus all tools inherited from ancestors.

### 2.4 Context

A shared state object that flows between tasks. Each task receives input context and produces output context. The framework manages serialization and passing of context between tasks.

**Output rules:**
- If `task.yaml` declares `output` keys, those keys are extracted from the agent's response and placed into context
- If no `output` is declared (including minimal tasks), the agent's full response is stored under the task's name (e.g., `context["fetch_data"] = agent_response`)
- This means minimal tasks always contribute to context — no output is ever lost

### 2.5 Task Identity

A folder is recognized as a task if it contains at least one of:
- `instructions.md` — agent instructions (can run as a leaf task)
- `task.yaml` — configuration (can be a pure orchestrator with no instructions)
- `subtasks/` — child tasks (implicit: this is a parent task)

A folder with none of these is ignored by discovery.

### 2.6 Leaf vs Branch Tasks

A task can be a **leaf** (no children), a **branch** (has children), or **both** (has instructions AND children):

- **Leaf task:** Agent runs with instructions + tools, produces output. Most common case.
- **Branch task (no instructions):** Pure orchestrator. Dispatches children, merges their outputs. No agent invocation.
- **Both:** Agent runs first (can reason, set up context), then children execute, then agent gets a final pass to assemble results. Useful for tasks that need to coordinate child outputs.

### 2.7 Task Discovery (Hybrid)

Tasks are discovered using a hybrid approach — auto-discovery by default, explicit config as optional override:

- **Auto-discovery:** If a `subtasks/` directory exists, the framework scans it for child folders and registers them as children. No parent config needed.
- **Explicit override:** If the parent's `task.yaml` has a `subtasks.order` list, that takes precedence over auto-discovery.
- **Ordering:** Each child declares `priority` in its own `task.yaml` (default: `50`). Recommended convention is multiples of 10 (`10`, `20`, `30`...) so new tasks can be inserted between existing ones without renumbering (e.g., `15` between `10` and `20`).
- **Toggling:** Children can set `enabled: false` in their `task.yaml` to be skipped without deleting the folder.
- **Default execution:** Auto-discovered children run in `parallel` by default (aligns with vertical data flow — siblings are independent). Parent can override via `subtasks.execution_type`.

### 2.8 Tool Discovery

Tools are auto-discovered from three sources:

- **`tools.md`** — parsed for tool definitions (H2 heading = tool name, blockquote = metadata, code block = implementation)
- **`tools/`** — scanned for `.py` files with `@tool`-decorated functions (complex tools needing multiple files/imports)
- **`shared/tools.md`** — workflow-level shared tools, pulled explicitly via `use_shared` in task.yaml
- If `tools.md` and `tools/` both exist, they are merged. On name conflict, `tools/` takes precedence.
- Inherited ancestor tools are added according to scoping rules (see 2.10)
- No config required for own tools — just add a `tools.md` or drop a `.py` file in `tools/`

### 2.9 Shared Resources

A workflow can have a `shared/` directory at the root level for reusable tools and instruction snippets:

```
my_workflow/
    shared/
        tools.md               # Shared tool definitions
        instructions/          # Reusable instruction snippets
            formatting.md
            error_handling.md
    subtasks/
        task_a/
            instructions.md
            task.yaml
        task_b/
            instructions.md
```

**Shared tools** — tasks explicitly pull what they need:

```yaml
# task_a/task.yaml
tools:
  use_shared: [search_api, format_results]
```

Shared tools are NOT auto-inherited. A task must declare `use_shared` to access them. This keeps tools explicit and avoids polluting tasks with irrelevant capabilities.

**Shared instructions** — reusable snippets included via template syntax:

```markdown
# instructions.md
Perform the analysis.

{% include "formatting" %}
{% include "error_handling" %}
```

Snippet name maps to `shared/instructions/{name}.md`. Resolved at load time before sending to the LLM.

### 2.10 Tool Inheritance & Scoping

By default, a task inherits all tools from its ancestors. Multiple strategies can limit this — they combine in a defined order.

**Control from the tool side (tool author decides):**

In `tools.md`:
```markdown
## dangerous_delete
> type: python
> scope: local

Delete records from database. Only for this task.
```

`scope` values:
- `shared` (default) — propagates to all descendants
- `local` — stays in the declaring task, never inherited

**Control from the task side (task author decides):**

In `task.yaml`:
```yaml
# Whitelist — only inherit these specific tools from ancestors
inherit_tools: [search_api, format_results]

# OR blacklist — inherit all except these
exclude_tools: [dangerous_delete]

# OR disable inheritance entirely
inherit_tools: false

# Limit inheritance depth (how many ancestor levels to look up)
inherit_tools_depth: 1     # 1 = parent only, 2 = parent + grandparent, -1 = unlimited (default)

# Block propagation — I can use these, but my children cannot inherit them from me
block_tools: [admin_api, dangerous_delete]
```

**Resolution order** (evaluated for each task):

0. **Collect own tools** — from task's `tools.md` and `tools/`
0. **Add shared tools** — from `use_shared` list in task.yaml
0. **Gather ancestor tools** — walk up the tree, at each ancestor:
   - Skip tools with `scope: local`
   - Skip tools listed in any intermediate ancestor's `block_tools`
0. **Apply depth limit** — stop walking ancestors beyond `inherit_tools_depth`
0. **Apply whitelist** — if `inherit_tools` is a list, keep only named tools from inherited set
0. **Apply blacklist** — remove any tools in `exclude_tools` from inherited set
0. **Merge** — on name conflict: own tools > shared tools > inherited tools

**Example — blocking propagation:**

```
root/
    tools.md              # defines: admin_api (scope: shared)
    subtasks/
        manager/
            task.yaml     # block_tools: [admin_api]  ← manager CAN use it
            subtasks/
                worker/   # worker CANNOT see admin_api (blocked by manager)
```

Manager has `admin_api` in its tool set. But because it lists `admin_api` in `block_tools`, its children (worker) will not inherit it. Worker can still define its own tool with that name if needed.

## 3. Data Flow Philosophy

Data flows **vertically** through the task tree, not horizontally between siblings.

**Rules:**
- A parent task provides input context to its children
- Children produce output that flows back up to the parent
- The parent assembles/merges child outputs into its own output
- Siblings never read each other's output directly — the parent mediates

**Why:** This keeps tasks self-contained and composable. Adding a new subtask means: create a folder, declare input/output, done. No need to rewire other tasks. Removing a task doesn't break siblings.

**Escape hatch:** Graph-based `depends_on` between siblings is supported for cases where vertical-only flow is genuinely impractical (e.g., a merge step that must wait for N parallel siblings). Use sparingly — it couples siblings and makes reordering harder.

## 4. Architecture

### 4.1 High-Level Architecture

```
+------------------------------------------------------------------+
|                       Root Task (folder)                          |
|         (mediates context between children, same as any task)     |
+------------------------------------------------------------------+
        |               |                |
        v               v                v
  +-----------+   +-----------+    +-----------+
  |  Task A   |   |  Task B   |    |  Task C   |
  | (folder)  |   | (folder)  |    | (folder)  |
  +-----------+   +-----------+    +-----------+
        |
        v  (parent provides input, collects output)
  +---------------------+
  | Subtask A.1 (folder)|
  +---------------------+
```

Context flows: Root -> Task A -> (output) -> Root -> Task B -> ...
Not: Task A -> Task B directly.

### 4.2 Component Breakdown

#### TaskExecutor
- Core engine — executes any task, whether root or deeply nested
- Loads task config, instructions, tools
- Provides the agent with: instructions, tools, input context
- Captures output context
- Runs pre/post hooks if `hooks/` exists
- Dispatches subtasks sequentially, in parallel, or as a DAG based on `execution_type`
- Parallel subtasks run concurrently via `asyncio.gather`, results merged on completion
- Recursively invokes itself for child tasks

#### TaskLoader
- Auto-discovers child tasks by scanning `subtasks/` for folders
- Falls back to explicit `subtasks.order` if defined in parent
- Sorts discovered children by `priority` field (default `50`, recommended multiples of 10)
- Skips children with `enabled: false`
- Loads `task.yaml` if present, otherwise applies defaults (name from folder)
- Discovers and registers tools from `tools/` directory
- Recursively loads subtasks

#### ToolRegistry
- Auto-discovers tools from `tools/` directories
- Handles tool inheritance (child sees parent's tools + its own)
- Validates tool signatures against expected schemas
- Provides tool discovery for the agent

#### ContextManager
- Manages the shared state flowing through the task tree
- Serializes/deserializes context between tasks
- Supports scoped views (task sees only what it needs)
- Maintains execution history and audit trail

#### AgentInterface (Provider-Agnostic)
- Abstract base class defining the LLM contract
- Concrete implementations per provider: Claude, OpenAI, Ollama, etc.
- Sends instructions + tools + context to the agent
- Parses agent responses and tool calls
- Manages conversation loop within a task
- Provider selected per-root or overridden per-task

#### ProviderRegistry
- Registers available LLM providers at startup
- Auto-discovers installed provider packages (e.g., `anthropic`, `openai`, `ollama`)
- Resolves provider by name from config
- Validates provider-specific settings (API keys, base URLs, model names)

## 5. Configuration Schemas

### 5.0 Configuration Hierarchy

Settings cascade with deeper levels overriding shallower ones:

```
root task.yaml (defaults)
  -> child task.yaml (overrides)
    -> grandchild task.yaml (overrides)
```

**Merge rules:**
- Scalar values (timeout, max_retries): child wins
- Lists (retry_on): child replaces entirely
- Dicts (agent settings): deep-merged, child keys win

This means a long-running task can set `timeout: 600` while root default is `120`, and a lightweight subtask inside it can set `timeout: 30`.

### 5.1 task.yaml (root level)

A root task typically configures providers and global defaults:

```yaml
name: "data_processing_workflow"
description: "Fetches, processes, and reports on data"

# LLM provider configuration
providers:
  default: "claude"     # Which provider to use by default

  claude:
    module: "agentflow.providers.claude"
    model: "claude-sonnet-4-20250514"
    temperature: 0.0
    api_key_env: "ANTHROPIC_API_KEY"

  openai:
    module: "agentflow.providers.openai"
    model: "gpt-4o"
    temperature: 0.0
    api_key_env: "OPENAI_API_KEY"

  ollama:
    module: "agentflow.providers.ollama"
    model: "llama3.1:70b"
    base_url: "http://localhost:11434"

# Global settings (defaults for all descendant tasks)
settings:
  max_retries: 3
  timeout: 300
  parallel_workers: 4

# Global context (available to all tasks)
context:
  api_base_url: "https://api.example.com"
  output_dir: "./output"
```

### 5.2 task.yaml (child level)

Children only declare what they need. Everything else is inherited or defaulted:

```yaml
name: "fetch_data"
description: "Fetches raw data from external API"
priority: 20            # Ordering among siblings (default: 50, use multiples of 10)
enabled: true           # Set to false to skip without deleting (default: true)

# Task-level settings (override parent defaults)
settings:
  max_retries: 5
  timeout: 120

# Override LLM provider for this task (optional)
agent:
  provider: "claude"
  model: "claude-sonnet-4-20250514"
  temperature: 0.2

# Input/output declarations
input:
  required:
    - api_base_url
  optional:
    - filter_params
output:
  - raw_data
  - fetch_metadata

# Subtask execution (optional — if omitted, subtasks/ is auto-discovered)
# subtasks:
#   execution_type: "parallel"  # sequential | parallel | graph (default: parallel)

# Conditions for execution
conditions:
  skip_if: "context.raw_data is not None"  # Python expression
  retry_on:
    - ConnectionError
    - TimeoutError
```

**Remember: `task.yaml` itself is optional.** A folder with just `instructions.md` is a valid task.

## 6. Provider System

### 6.1 Provider Interface

All LLM providers implement the same abstract base class:

```python
from abc import ABC, abstractmethod
from agentflow.core.tool import ToolSpec

class AgentProvider(ABC):
    """Base class all LLM providers must implement."""

    @abstractmethod
    def configure(self, **kwargs) -> None:
        """Initialize with provider-specific settings (model, API key, etc.)."""

    @abstractmethod
    def call(
        self,
        instructions: str,
        tools: list[ToolSpec],
        messages: list[dict],
    ) -> AgentResponse:
        """Send a request to the LLM. Returns structured response with text + tool calls."""

    @abstractmethod
    def supports_tool_calling(self) -> bool:
        """Whether this provider supports native tool/function calling."""
```

### 6.2 Built-in Providers

| Provider | Module | Tool calling | Notes |
|---|---|---|---|
| Claude (Anthropic) | `agentflow.providers.claude` | Native | Default provider |
| OpenAI | `agentflow.providers.openai` | Native | GPT-4o, o1, etc. |
| Ollama | `agentflow.providers.ollama` | Via prompt engineering | Local models, no API key |

Each provider is an **optional dependency**. Only the provider you use needs to be installed.

### 6.3 Custom Providers

Register custom providers by pointing to a module with an `AgentProvider` subclass:

```yaml
providers:
  default: "my_custom"
  my_custom:
    module: "my_package.my_provider"
    model: "my-model-v1"
    custom_param: "value"
```

### 6.4 Provider Resolution Order

When TaskExecutor needs a provider for a task:

0. Check `task.yaml` -> `agent.provider` (task-level override)
0. Check parent task's `agent.provider` (inherited from parent)
0. Walk up to root task's `providers.default`
0. If no provider found anywhere in the tree, error with clear message: "No LLM provider configured. Add a `providers` block to your root task.yaml."

Settings within the chosen provider also cascade: root provider config -> task-level `agent` overrides (deep-merged).

## 7. Tool Definition

### 7.1 tools.md (Primary — Simple Tools)

Define tools in a single markdown file. Each H2 heading is a tool:

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

## generate_chart
> type: shell

Generate a PNG chart from CSV data.

```bash
gnuplot -e "set terminal png; set output '$OUTPUT'; plot '$INPUT' with lines"
```

## get_weather
> type: http
> method: GET
> url: https://api.weather.com/v1/forecast
> headers: {"Authorization": "Bearer ${WEATHER_API_KEY}"}

Get weather forecast for a location.

**Parameters:**
- location (str): City name or coordinates
- days (int, default=3): Forecast days

## slack_notify
> type: mcp
> server: slack-mcp
> tool: send_message

Send a message to a Slack channel.

## web_browser
> type: reference

Browse the web to find information. Agent already has browser access.
~~~

**Format rules:**
- `## heading` = tool name
- `> type:` blockquote = tool type (default: `python` if omitted)
- Extra metadata in blockquotes varies by type (`method`, `url`, `server`, etc.)
- Text before code block = description shown to the LLM
- Code block = implementation (interpreted based on type)

### 7.2 Tool Types

| Type | Implementation | Use case |
|---|---|---|
| `python` | Inline function in code block. Type hints → JSON schema for LLM. | Most tools |
| `shell` | Command in code block. Stdin/env for input, stdout captured. | CLI tools, scripts |
| `http` | Endpoint defined in metadata. Parameters map to query/body. | External APIs |
| `mcp` | Reference to MCP server + tool name. Schema from MCP. | MCP integrations |
| `reference` | No implementation. Just a description for the LLM. | Agent-native capabilities |

**Common metadata** (applies to all types):
- `> scope: local | shared` — controls inheritance (default: `shared`). See section 2.10.

### 7.3 tools/ Directory (Complex Tools)

For tools that need multiple files, heavy imports, or test coverage, use the `tools/` directory with `@tool`-decorated Python functions:

```python
# tools/search.py
from agentflow import tool, ToolContext

@tool(name="search_api", description="Search the external API for records matching a query")
def search_api(ctx: ToolContext, query: str, limit: int = 10) -> dict:
    response = ctx.http.get(
        f"{ctx.get('api_base_url')}/search",
        params={"q": query, "limit": limit}
    )
    return response.json()
```

The `@tool` decorator:
- Registers the function in the ToolRegistry
- Auto-generates JSON schema from type hints for the agent
- Handles serialization of inputs/outputs
- Provides `ToolContext` with access to shared state and utilities

## 8. Execution Flow

0. TaskExecutor loads root task config
0. TaskLoader discovers all child tasks (auto-discovery or explicit)
0. For each child task in execution order:
   0. TaskLoader loads task config (or applies defaults if no `task.yaml`)
   0. ContextManager prepares input context for task
   0. TaskExecutor runs pre-hooks (if `hooks/` exists)
   0. If `instructions.md` exists, invoke AgentInterface with:
      - instructions.md content
      - registered tools
      - input context
   0. Agent reasons, calls tools, produces output into context
   0. If subtasks exist, dispatch children:
      - sequential: run subtasks one by one, passing context forward
      - parallel: run all subtasks concurrently (asyncio.gather), merge outputs
      - graph: resolve dependency DAG, run independent subtasks in parallel,
        wait for dependencies before starting dependent subtasks
   0. If task has both instructions AND subtasks, agent gets a final pass to assemble child outputs
   0. TaskExecutor runs post-hooks (if `hooks/` exists)
   0. ContextManager merges output context (explicit `output` keys, or full response under task name)
0. Root task collects final context as workflow output

## 9. Error Handling & Recovery

| Scenario | Strategy |
|---|---|
| Tool raises exception | Retry up to `max_retries`, then surface to agent for reasoning |
| Agent fails to produce output | Re-prompt with error context, escalate after retries |
| Task timeout | Kill task, run error hooks, skip or fail per config |
| Subtask failure | Bubble up to parent task, parent decides to retry/skip/fail |
| Root-level failure | Save checkpoint, allow resume from last successful task |

### Checkpointing

The framework saves execution state after each successful task:

```
my_workflow/
    .agentflow/
        checkpoints/
            fetch_data.json
            process.json
        run_history/
            2026-05-04T12-00-00/
```

This enables resuming failed workflows from the last checkpoint.

## 10. Package Structure

```
agentflow/
    __init__.py
    core/
        __init__.py
        executor.py         # TaskExecutor
        loader.py           # TaskLoader
        context.py          # ContextManager
        tool.py             # @tool decorator, ToolRegistry
        agent.py            # AgentProvider base class, ProviderRegistry
        config.py           # Config hierarchy resolution & merging
    providers/
        __init__.py
        claude.py           # Anthropic Claude provider
        openai.py           # OpenAI provider
        ollama.py           # Ollama (local models) provider
    schemas/
        __init__.py
        task_schema.py      # Pydantic models for task.yaml
    hooks/
        __init__.py
        base.py             # Hook base class
    utils/
        __init__.py
        discovery.py        # Folder/file discovery utilities
        serialization.py    # Context serialization
        logging.py          # Structured logging
    cli/
        __init__.py
        main.py             # CLI entry point
    exceptions.py           # Custom exceptions
```

## 11. CLI Interface

```bash
# Run a workflow (root task)
agentflow run ./my_workflow

# Run a single task (useful for development)
agentflow run-task ./my_workflow/subtasks/fetch_data --context '{"api_base_url": "..."}'

# Validate task tree structure
agentflow validate ./my_workflow

# Resume from checkpoint
agentflow resume ./my_workflow --from process

# Create new task from template
agentflow init ./new_workflow
agentflow init ./new_workflow/subtasks/new_task

# List tasks and their status
agentflow status ./my_workflow

# Visualize task tree
agentflow tree ./my_workflow
```

## 12. Key Design Decisions

| Decision | Rationale |
|---|---|
| Folders as tasks | Human-readable, version-controllable, easy to inspect/edit. Each task is self-contained. |
| Everything is a task | No separate pipeline concept. Uniform rules at every level. Simpler mental model. |
| Minimal task = one file | Just `instructions.md`. No yaml needed for simple cases. Lowest possible barrier. |
| YAML for config | Widely understood, supports comments, clean syntax for hierarchical config. |
| Markdown for instructions | Natural format for agent prompts. Easy to write and maintain. |
| Pydantic for schemas | Strong validation, auto-serialization, good Python ecosystem integration. |
| tools.md as universal registry | One markdown file defines tools of any type (python, shell, http, mcp, reference). `tools/` directory for complex cases. Both merge. |
| Auto-discovery everywhere | Tools, subtasks, hooks — all discovered from folder structure. Config only when overriding defaults. |
| Vertical data flow | Siblings don't depend on each other. Parent mediates. Adding/removing a task never breaks other tasks at the same level. |
| Hybrid task discovery | Auto-discover by default, explicit config as override. Drop a folder in = new task. Priority multiples of 10 for easy insertion. |
| Cascading config hierarchy | Root defaults -> task overrides -> subtask overrides. Each task controls its own behavior (timeout, retries, provider, model). |
| Provider-agnostic design | Abstract base class + registry. Swap LLM by changing one config line. No vendor lock-in. |
| Optional provider deps | Only install what you use. `pip install agentflow[claude]` or `agentflow[ollama]`. |

## 13. Dependencies

**Core (always installed):**
- **Python >= 3.11**
- **pydantic** - Config validation and schemas
- **pyyaml** - YAML parsing
- **click** - CLI framework
- **rich** - Terminal output formatting

**Provider extras (install only what you need):**
- `agentflow[claude]` -> **anthropic**
- `agentflow[openai]` -> **openai**
- `agentflow[ollama]` -> **ollama**
- `agentflow[all]` -> all providers

**Optional:**
- **networkx** - Graph-based execution ordering

## 14. Future Considerations

- **Parallel task execution** with async/await
- **Streaming output** from agent during task execution
- **Web UI** for workflow monitoring and visualization
- **Plugin system** for custom TaskExecutors
- **Shared tool libraries** that multiple tasks can reference
- **Template marketplace** for common workflow patterns
