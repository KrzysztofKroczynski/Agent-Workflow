from pathlib import Path

from agentflow.core.loader import TaskLoader


def test_minimal_task(tmp_workflow):
    root = tmp_workflow({"instructions.md": "do the thing"})
    task = TaskLoader().load(root)
    assert task.has_instructions
    assert task.subtasks == []


def test_priority_sorting(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": "name: root\n",
            "subtasks": {
                "b": {"task.yaml": "priority: 10\n", "instructions.md": "b"},
                "a": {"task.yaml": "priority: 30\n", "instructions.md": "a"},
                "c": {"task.yaml": "priority: 20\n", "instructions.md": "c"},
            },
        }
    )
    task = TaskLoader().load(root)
    assert [c.name for c in task.subtasks] == ["b", "c", "a"]


def test_disabled_skipped(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": "name: root\n",
            "subtasks": {
                "active": {"instructions.md": "go"},
                "off": {"task.yaml": "enabled: false\n", "instructions.md": "no"},
            },
        }
    )
    task = TaskLoader().load(root)
    assert [c.name for c in task.subtasks] == ["active"]


def test_explicit_order(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": "name: root\nsubtasks:\n  order: [c, a, b]\n",
            "subtasks": {
                "a": {"instructions.md": "a"},
                "b": {"instructions.md": "b"},
                "c": {"instructions.md": "c"},
            },
        }
    )
    task = TaskLoader().load(root)
    assert [c.name for c in task.subtasks] == ["c", "a", "b"]


def test_ignores_non_task_folders(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": "name: root\n",
            "subtasks": {
                "real": {"instructions.md": "yes"},
                "junk": {"random.txt": "ignored"},
            },
        }
    )
    task = TaskLoader().load(root)
    assert [c.name for c in task.subtasks] == ["real"]


def test_tools_dir_overrides_tools_md(tmp_workflow):
    tools_md = """## echo
> type: python

Echo.

```python
def echo() -> str:
    return "from md"
```
"""
    tools_py = """\
from agentflow import tool

@tool()
def echo() -> str:
    return "from dir"
"""
    root = tmp_workflow(
        {
            "instructions.md": "go",
            "tools.md": tools_md,
            "tools": {"echo.py": tools_py},
        }
    )
    loader = TaskLoader()
    task = loader.load(root)
    own = loader.registry.for_owner(task.path)
    assert own["echo"].impl() == "from dir"
