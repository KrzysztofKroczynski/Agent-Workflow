from pathlib import Path

import pytest

from agentflow.core.tool import (
    ToolContext,
    ToolRegistry,
    parse_tools_md,
    tool,
)
from agentflow.exceptions import ToolError


TOOLS_MD = """\
## search_api
> type: python

Search the API.

```python
def search_api(query: str, limit: int = 10) -> dict:
    return {"q": query, "limit": limit}
```

## echo_shell
> type: shell

Echo a value.

```bash
echo $MSG
```

## browser
> type: reference

Browse the web.

## scoped_tool
> type: python
> scope: local

Local-only tool.

```python
def scoped_tool() -> str:
    return "local"
```
"""


def test_parse_tools_md(tmp_path: Path):
    p = tmp_path / "tools.md"
    p.write_text(TOOLS_MD)
    specs = parse_tools_md(p)
    by_name = {s.name: s for s in specs}
    assert set(by_name) == {"search_api", "echo_shell", "browser", "scoped_tool"}
    assert by_name["search_api"].type == "python"
    assert by_name["search_api"].parameters["properties"]["query"]["type"] == "string"
    assert by_name["search_api"].parameters["properties"]["limit"]["type"] == "integer"
    assert by_name["search_api"].parameters["required"] == ["query"]
    assert by_name["echo_shell"].type == "shell"
    assert "echo $MSG" in by_name["echo_shell"].impl
    assert by_name["browser"].type == "reference"
    assert by_name["scoped_tool"].scope == "local"


def test_tool_decorator_schema():
    @tool(description="search")
    def search_api(ctx, query: str, limit: int = 10) -> dict:
        return {"q": query}

    spec = search_api._tool_spec
    assert spec.name == "search_api"
    assert spec.description == "search"
    assert spec.parameters["properties"]["query"]["type"] == "string"
    assert "ctx" not in spec.parameters["properties"]
    assert spec.parameters["required"] == ["query"]


def test_invoke_python_tool(tmp_path: Path):
    @tool()
    def add(a: int, b: int) -> int:
        return a + b

    registry = ToolRegistry()
    registry.register(add._tool_spec, tmp_path)
    ctx = ToolContext(workflow_root=tmp_path, task_path=tmp_path, state={}, logger=None)
    result = registry.invoke(add._tool_spec, ctx, a=2, b=3)
    assert result == 5


def test_invoke_reference_tool_errors(tmp_path: Path):
    p = tmp_path / "tools.md"
    p.write_text(TOOLS_MD)
    specs = parse_tools_md(p)
    spec = next(s for s in specs if s.type == "reference")
    registry = ToolRegistry()
    registry.register(spec, tmp_path)
    ctx = ToolContext(workflow_root=tmp_path, task_path=tmp_path, state={}, logger=None)
    with pytest.raises(ToolError):
        registry.invoke(spec, ctx)
