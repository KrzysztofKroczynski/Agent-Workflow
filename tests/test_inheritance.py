from agentflow.core.loader import TaskLoader


SHARED_TOOL = """## helper
> type: python

A shared helper.

```python
def helper() -> str:
    return "shared"
```
"""

ROOT_TOOLS = """## ancestor_tool
> type: python

```python
def ancestor_tool() -> str:
    return "from-root"
```

## local_only
> type: python
> scope: local

```python
def local_only() -> str:
    return "local"
```

## blocked_tool
> type: python

```python
def blocked_tool() -> str:
    return "blocked"
```
"""


def _build(tmp_workflow, child_yaml: str = ""):
    return tmp_workflow(
        {
            "task.yaml": "name: root\n",
            "tools.md": ROOT_TOOLS,
            "shared": {"tools.md": SHARED_TOOL},
            "subtasks": {
                "child": {
                    "task.yaml": "name: child\n" + child_yaml,
                    "instructions.md": "go",
                }
            },
        }
    )


def test_basic_inheritance(tmp_workflow):
    root = _build(tmp_workflow)
    loader = TaskLoader()
    task = loader.load(root)
    child = task.subtasks[0]
    visible = loader.registry.resolve_for_task(child)
    assert "ancestor_tool" in visible
    assert "blocked_tool" in visible


def test_local_scope_not_inherited(tmp_workflow):
    root = _build(tmp_workflow)
    loader = TaskLoader()
    task = loader.load(root)
    child = task.subtasks[0]
    visible = loader.registry.resolve_for_task(child)
    assert "local_only" not in visible


def test_use_shared_pulls_in(tmp_workflow):
    root = _build(tmp_workflow, "tools:\n  use_shared: [helper]\n")
    loader = TaskLoader()
    task = loader.load(root)
    child = task.subtasks[0]
    visible = loader.registry.resolve_for_task(child)
    assert "helper" in visible


def test_inherit_tools_whitelist(tmp_workflow):
    root = _build(tmp_workflow, "inherit_tools: [ancestor_tool]\n")
    loader = TaskLoader()
    task = loader.load(root)
    child = task.subtasks[0]
    visible = loader.registry.resolve_for_task(child)
    assert visible.keys() == {"ancestor_tool"}


def test_exclude_tools(tmp_workflow):
    root = _build(tmp_workflow, "exclude_tools: [blocked_tool]\n")
    loader = TaskLoader()
    task = loader.load(root)
    child = task.subtasks[0]
    visible = loader.registry.resolve_for_task(child)
    assert "blocked_tool" not in visible
    assert "ancestor_tool" in visible


def test_inherit_tools_false(tmp_workflow):
    root = _build(tmp_workflow, "inherit_tools: false\n")
    loader = TaskLoader()
    task = loader.load(root)
    child = task.subtasks[0]
    visible = loader.registry.resolve_for_task(child)
    assert "ancestor_tool" not in visible


def test_inherit_tools_depth(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": "name: root\n",
            "tools.md": ROOT_TOOLS,
            "subtasks": {
                "mid": {
                    "task.yaml": "name: mid\n",
                    "subtasks": {
                        "leaf": {
                            "task.yaml": "name: leaf\ninherit_tools_depth: 1\n",
                            "instructions.md": "go",
                        }
                    },
                }
            },
        }
    )
    loader = TaskLoader()
    task = loader.load(root)
    leaf = task.subtasks[0].subtasks[0]
    visible = loader.registry.resolve_for_task(leaf)
    # Depth 1 means parent only, root tools should not be visible
    assert "ancestor_tool" not in visible


def test_block_tools_blocks_grandchildren(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": "name: root\n",
            "tools.md": ROOT_TOOLS,
            "subtasks": {
                "mid": {
                    "task.yaml": "name: mid\nblock_tools: [ancestor_tool]\n",
                    "subtasks": {
                        "leaf": {
                            "task.yaml": "name: leaf\n",
                            "instructions.md": "go",
                        }
                    },
                }
            },
        }
    )
    loader = TaskLoader()
    task = loader.load(root)
    mid = task.subtasks[0]
    leaf = mid.subtasks[0]

    mid_visible = loader.registry.resolve_for_task(mid)
    leaf_visible = loader.registry.resolve_for_task(leaf)

    # mid CAN use it, leaf CANNOT
    assert "ancestor_tool" in mid_visible
    assert "ancestor_tool" not in leaf_visible


def test_own_overrides_inherited(tmp_workflow):
    own_tools = """## ancestor_tool
> type: python

```python
def ancestor_tool() -> str:
    return "overridden"
```
"""
    root = tmp_workflow(
        {
            "task.yaml": "name: root\n",
            "tools.md": ROOT_TOOLS,
            "subtasks": {
                "child": {
                    "task.yaml": "name: child\n",
                    "tools.md": own_tools,
                    "instructions.md": "go",
                }
            },
        }
    )
    loader = TaskLoader()
    task = loader.load(root)
    child = task.subtasks[0]
    visible = loader.registry.resolve_for_task(child)
    assert visible["ancestor_tool"].impl() == "overridden"
