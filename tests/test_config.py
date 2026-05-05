from agentflow.core.config import (
    merge_config,
    resolve_provider,
    resolve_settings,
)
from agentflow.core.loader import TaskLoader


def test_merge_scalars_child_wins():
    assert merge_config({"a": 1}, {"a": 2}) == {"a": 2}


def test_merge_lists_child_replaces():
    assert merge_config({"l": [1, 2, 3]}, {"l": [9]}) == {"l": [9]}


def test_merge_dicts_deep_merged():
    out = merge_config(
        {"a": {"x": 1, "y": 2}},
        {"a": {"y": 99, "z": 3}},
    )
    assert out == {"a": {"x": 1, "y": 99, "z": 3}}


def test_resolve_settings_cascade(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": "name: root\nsettings:\n  max_retries: 3\n  timeout: 600\n",
            "subtasks": {
                "child": {
                    "task.yaml": "settings:\n  max_retries: 5\n",
                    "instructions.md": "go",
                }
            },
        }
    )
    task = TaskLoader().load(root)
    child = task.subtasks[0]
    s = resolve_settings(child)
    assert s.max_retries == 5
    assert s.timeout == 600


def test_resolve_provider_walks_up(tmp_workflow):
    root = tmp_workflow(
        {
            "task.yaml": (
                "name: root\n"
                "providers:\n"
                "  default: claude\n"
                "  claude:\n"
                "    module: agentflow.providers.fake\n"
                "    model: claude-sonnet-4\n"
                "    temperature: 0.0\n"
            ),
            "subtasks": {
                "child": {
                    "task.yaml": "agent:\n  temperature: 0.5\n",
                    "instructions.md": "go",
                }
            },
        }
    )
    task = TaskLoader().load(root)
    child = task.subtasks[0]
    name, settings = resolve_provider(child)
    assert name == "claude"
    assert settings["model"] == "claude-sonnet-4"
    assert settings["temperature"] == 0.5
