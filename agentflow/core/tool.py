from __future__ import annotations

import inspect
import logging
import re
import subprocess
import typing
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from agentflow.exceptions import ToolError

ToolType = Literal["python", "shell", "reference", "http", "mcp"]
SUPPORTED_TYPES: set[str] = {"python", "shell", "reference"}


@dataclass
class ToolSpec:
    name: str
    description: str
    type: ToolType
    parameters: dict[str, Any]
    impl: Any
    scope: Literal["shared", "local"] = "shared"
    owner_path: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolContext:
    workflow_root: Path
    task_path: Path
    state: dict[str, Any]
    logger: logging.Logger

    def get(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.state[key] = value


_PYTHON_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _build_parameters_schema(func: Callable) -> dict[str, Any]:
    sig = inspect.signature(func)
    try:
        hints = typing.get_type_hints(func)
    except Exception:
        hints = {}

    properties: dict[str, Any] = {}
    required: list[str] = []
    for pname, param in sig.parameters.items():
        if pname == "ctx" or pname == "self":
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        annotation = hints.get(pname, str)
        origin = typing.get_origin(annotation)
        base = origin if origin is not None else annotation
        json_type = _PYTHON_TYPE_MAP.get(base, "string")
        prop: dict[str, Any] = {"type": json_type}
        if param.default is inspect.Parameter.empty:
            required.append(pname)
        else:
            prop["default"] = param.default
        properties[pname] = prop
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def tool(
    name: str | None = None,
    description: str | None = None,
    scope: Literal["shared", "local"] = "shared",
) -> Callable:
    def decorator(func: Callable) -> Callable:
        spec = ToolSpec(
            name=name or func.__name__,
            description=description or (func.__doc__ or "").strip(),
            type="python",
            parameters=_build_parameters_schema(func),
            impl=func,
            scope=scope,
        )
        func._tool_spec = spec  # type: ignore[attr-defined]
        return func

    return decorator


_HEADING_RE = re.compile(r"^##\s+(\S.*?)\s*$")
_BLOCKQUOTE_RE = re.compile(r"^>\s*(.*?)\s*$")
_FENCE_RE = re.compile(r"^```(\w+)?\s*$")


def _parse_metadata_line(line: str) -> tuple[str, str] | None:
    if ":" not in line:
        return None
    key, _, value = line.partition(":")
    return key.strip(), value.strip()


def parse_tools_md(path: Path) -> list[ToolSpec]:
    text = path.read_text()
    lines = text.splitlines()
    specs: list[ToolSpec] = []
    i = 0
    while i < len(lines):
        m = _HEADING_RE.match(lines[i])
        if not m:
            i += 1
            continue
        name = m.group(1).strip()
        i += 1
        metadata: dict[str, str] = {}
        description_lines: list[str] = []
        code_lang: str | None = None
        code_lines: list[str] = []
        # Walk forward until next heading
        while i < len(lines):
            line = lines[i]
            if _HEADING_RE.match(line):
                break
            if line.startswith("# "):
                break
            bq = _BLOCKQUOTE_RE.match(line)
            if bq and not code_lines and code_lang is None:
                kv = _parse_metadata_line(bq.group(1))
                if kv:
                    metadata[kv[0]] = kv[1]
                i += 1
                continue
            fence = _FENCE_RE.match(line)
            if fence and not code_lines and code_lang is None:
                code_lang = fence.group(1) or ""
                i += 1
                while i < len(lines):
                    end = _FENCE_RE.match(lines[i])
                    if end:
                        i += 1
                        break
                    code_lines.append(lines[i])
                    i += 1
                continue
            if not code_lines and code_lang is None:
                description_lines.append(line)
            i += 1
        ttype = metadata.pop("type", "python")
        if ttype not in SUPPORTED_TYPES:
            raise ToolError(
                f"Tool type '{ttype}' is not supported in this MVP (tool '{name}')."
            )
        scope = metadata.pop("scope", "shared")
        if scope not in ("shared", "local"):
            raise ToolError(f"Invalid scope '{scope}' for tool '{name}'.")
        description = "\n".join(description_lines).strip()
        impl: Any
        parameters: dict[str, Any] = {"type": "object", "properties": {}}
        if ttype == "python":
            namespace: dict[str, Any] = {}
            exec("\n".join(code_lines), namespace)
            func = namespace.get(name)
            if not callable(func):
                raise ToolError(
                    f"tools.md python tool '{name}' did not define a function called '{name}'."
                )
            impl = func
            parameters = _build_parameters_schema(func)
        elif ttype == "shell":
            impl = "\n".join(code_lines)
        elif ttype == "reference":
            impl = None
        else:  # pragma: no cover
            raise ToolError(f"Unhandled tool type {ttype}")
        specs.append(
            ToolSpec(
                name=name,
                description=description,
                type=ttype,  # type: ignore[arg-type]
                parameters=parameters,
                impl=impl,
                scope=scope,  # type: ignore[arg-type]
                metadata=metadata,
            )
        )
    return specs


def load_tools_dir(path: Path) -> list[ToolSpec]:
    """Import every .py file under `path` and return any @tool-decorated specs."""
    if not path.is_dir():
        return []
    import importlib.util

    specs: list[ToolSpec] = []
    for py in sorted(path.glob("*.py")):
        if py.name.startswith("_"):
            continue
        spec_obj = importlib.util.spec_from_file_location(
            f"agentflow_tools_{py.stem}_{abs(hash(py))}", py
        )
        if spec_obj is None or spec_obj.loader is None:
            continue
        module = importlib.util.module_from_spec(spec_obj)
        spec_obj.loader.exec_module(module)
        for attr in vars(module).values():
            ts = getattr(attr, "_tool_spec", None)
            if isinstance(ts, ToolSpec):
                specs.append(ts)
    return specs


class ToolRegistry:
    """Stores tool specs keyed by their owning task path."""

    def __init__(self) -> None:
        self._by_owner: dict[Path, dict[str, ToolSpec]] = {}

    def register(self, spec: ToolSpec, owner_path: Path) -> None:
        spec.owner_path = owner_path
        self._by_owner.setdefault(owner_path, {})[spec.name] = spec

    def for_owner(self, owner_path: Path) -> dict[str, ToolSpec]:
        return dict(self._by_owner.get(owner_path, {}))

    def shared_tools(self, workflow_root: Path) -> dict[str, ToolSpec]:
        return dict(self._by_owner.get(workflow_root / "shared", {}))

    def resolve_for_task(self, task: Any) -> dict[str, ToolSpec]:
        """Return the tools visible to `task` per design.md §2.10."""
        own = self.for_owner(task.path)

        shared_pool = self.shared_tools(task.workflow_root.path)
        use_shared: list[str] = []
        if task.config.tools is not None:
            use_shared = list(task.config.tools.use_shared)
        shared = {n: shared_pool[n] for n in use_shared if n in shared_pool}

        # Walk ancestors
        depth_limit = task.config.inherit_tools_depth
        inherit_setting = task.config.inherit_tools

        if inherit_setting is False:
            inherited: dict[str, ToolSpec] = {}
        else:
            inherited = {}
            ancestor = task.parent
            depth = 0
            blocked: set[str] = set()
            while ancestor is not None:
                if 0 <= depth_limit <= depth:
                    break
                # Tools owned by ancestor
                for tname, tspec in self.for_owner(ancestor.path).items():
                    if tspec.scope == "local":
                        continue
                    if tname in blocked:
                        continue
                    if tname in inherited:
                        continue
                    inherited[tname] = tspec
                # After collecting, this ancestor's block_tools applies to further-up ancestors
                blocked.update(ancestor.config.block_tools)
                ancestor = ancestor.parent
                depth += 1

            if isinstance(inherit_setting, list):
                inherited = {n: s for n, s in inherited.items() if n in inherit_setting}
            for name in task.config.exclude_tools:
                inherited.pop(name, None)

        merged: dict[str, ToolSpec] = {}
        merged.update(inherited)
        merged.update(shared)
        merged.update(own)
        return merged

    def invoke(self, spec: ToolSpec, ctx: ToolContext, **kwargs: Any) -> Any:
        if spec.type == "python":
            func = spec.impl
            sig = inspect.signature(func)
            if "ctx" in sig.parameters:
                return func(ctx, **kwargs)
            return func(**kwargs)
        if spec.type == "shell":
            env = {k: str(v) for k, v in kwargs.items()}
            result = subprocess.run(
                spec.impl,
                shell=True,
                capture_output=True,
                text=True,
                env={**__import__("os").environ, **env},
            )
            if result.returncode != 0:
                raise ToolError(
                    f"shell tool '{spec.name}' failed (exit {result.returncode}): {result.stderr.strip()}"
                )
            return result.stdout
        if spec.type == "reference":
            raise ToolError(
                f"Tool '{spec.name}' is a reference tool — the agent should call its native capability, not the framework."
            )
        raise ToolError(f"Cannot invoke tool of type {spec.type}")
