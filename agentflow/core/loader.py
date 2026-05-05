from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from agentflow.core.tool import (
    ToolRegistry,
    ToolSpec,
    load_tools_dir,
    parse_tools_md,
)
from agentflow.exceptions import ConfigError, TaskNotFoundError
from agentflow.schemas.task_schema import TaskConfig
from agentflow.utils.discovery import is_task_dir, iter_subtask_dirs

if TYPE_CHECKING:
    pass


@dataclass
class Task:
    name: str
    path: Path
    config: TaskConfig
    instructions: str | None = None
    tools: list[ToolSpec] = field(default_factory=list)
    subtasks: list["Task"] = field(default_factory=list)
    parent: "Task | None" = None
    workflow_root: "Task | None" = None  # Set after second pass

    @property
    def has_instructions(self) -> bool:
        return self.instructions is not None and self.instructions.strip() != ""

    @property
    def is_branch(self) -> bool:
        return bool(self.subtasks)


def _load_task_yaml(path: Path) -> TaskConfig:
    yaml_path = path / "task.yaml"
    if not yaml_path.exists():
        return TaskConfig()
    raw = yaml.safe_load(yaml_path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"task.yaml at {yaml_path} did not parse to a dict.")
    return TaskConfig(**raw)


class TaskLoader:
    def __init__(self) -> None:
        self.registry = ToolRegistry()

    def load(self, path: Path) -> Task:
        path = path.resolve()
        if not is_task_dir(path):
            raise TaskNotFoundError(f"Path {path} is not a task directory.")
        root = self._load_one(path)
        # Second pass: parent/workflow_root refs
        self._set_refs(root, parent=None, workflow_root=root)
        # Shared tools at the workflow root
        shared_dir = root.path / "shared"
        if (shared_dir / "tools.md").exists():
            for spec in parse_tools_md(shared_dir / "tools.md"):
                self.registry.register(spec, shared_dir)
        return root

    def _load_one(self, path: Path) -> Task:
        config = _load_task_yaml(path)
        name = config.name or path.name

        instructions: str | None = None
        if (path / "instructions.md").exists():
            instructions = (path / "instructions.md").read_text()

        tools: dict[str, ToolSpec] = {}
        if (path / "tools.md").exists():
            for spec in parse_tools_md(path / "tools.md"):
                tools[spec.name] = spec
        if (path / "tools").is_dir():
            for spec in load_tools_dir(path / "tools"):
                tools[spec.name] = spec  # tools/ wins on conflict

        for spec in tools.values():
            self.registry.register(spec, path)

        subtasks: list[Task] = []
        if (path / "subtasks").is_dir():
            ordered: list[Path]
            if config.subtasks and config.subtasks.order:
                ordered = []
                for child_name in config.subtasks.order:
                    candidate = path / "subtasks" / child_name
                    if not is_task_dir(candidate):
                        raise ConfigError(
                            f"subtasks.order references '{child_name}' but that's not a task dir under {path}."
                        )
                    ordered.append(candidate)
            else:
                ordered = list(iter_subtask_dirs(path))
            loaded_children = [self._load_one(p) for p in ordered]
            if not (config.subtasks and config.subtasks.order):
                loaded_children.sort(key=lambda c: (c.config.priority, c.name))
            loaded_children = [c for c in loaded_children if c.config.enabled]
            subtasks = loaded_children

        return Task(
            name=name,
            path=path,
            config=config,
            instructions=instructions,
            tools=list(tools.values()),
            subtasks=subtasks,
        )

    def _set_refs(self, task: Task, parent: Task | None, workflow_root: Task) -> None:
        task.parent = parent
        task.workflow_root = workflow_root
        for child in task.subtasks:
            self._set_refs(child, parent=task, workflow_root=workflow_root)
