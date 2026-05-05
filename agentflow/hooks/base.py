from __future__ import annotations

import importlib.util
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any


class Hook(ABC):
    @abstractmethod
    def run(self, ctx: Any, task: Any) -> None: ...


def load_hook(path: Path) -> Callable[[Any, Any], None] | None:
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(f"agentflow_hook_{path.stem}", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for attr in vars(module).values():
        if isinstance(attr, type) and issubclass(attr, Hook) and attr is not Hook:
            instance = attr()
            return instance.run
    fn = getattr(module, "run", None)
    if callable(fn):
        return fn
    return None
