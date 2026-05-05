from collections.abc import Iterator
from pathlib import Path


def is_task_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    return (
        (path / "instructions.md").exists()
        or (path / "task.yaml").exists()
        or (path / "subtasks").is_dir()
    )


def iter_subtask_dirs(path: Path) -> Iterator[Path]:
    subtasks = path / "subtasks"
    if not subtasks.is_dir():
        return
    for child in sorted(subtasks.iterdir()):
        if is_task_dir(child):
            yield child
