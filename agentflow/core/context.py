from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from agentflow.core.config import merge_config
from agentflow.utils.logging import get_logger

logger = get_logger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n(\{.*?\}|\[.*?\])\s*\n```", re.DOTALL)


@dataclass
class AuditEntry:
    task_name: str
    started_at: datetime
    finished_at: datetime | None = None
    status: str = "running"


@dataclass
class WorkflowResult:
    context: dict[str, Any]
    audit: list[AuditEntry] = field(default_factory=list)


class ContextManager:
    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = dict(initial or {})
        self.audit: list[AuditEntry] = []

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    def cascade_global_context(self, task: Any) -> None:
        """Merge `context:` blocks from root → task into the live state."""
        chain = []
        cur = task
        while cur is not None:
            chain.append(cur)
            cur = cur.parent
        merged: dict[str, Any] = {}
        for ancestor in reversed(chain):
            if ancestor.config.context:
                merged = merge_config(merged, ancestor.config.context)
        for k, v in merged.items():
            self._data.setdefault(k, v)

    def prepare_input(self, task: Any) -> dict[str, Any]:
        if task.config.input is None:
            return dict(self._data)
        out: dict[str, Any] = {}
        missing: list[str] = []
        for key in task.config.input.required:
            if key not in self._data:
                missing.append(key)
            else:
                out[key] = self._data[key]
        if missing:
            raise KeyError(
                f"Task '{task.name}' is missing required input keys: {missing}"
            )
        for key in task.config.input.optional:
            if key in self._data:
                out[key] = self._data[key]
        return out

    def capture_output(self, task: Any, response_text: str) -> None:
        declared = task.config.output
        if not declared:
            self._data[task.name] = response_text
            return

        parsed: dict[str, Any] | None = None
        match = _JSON_BLOCK_RE.search(response_text or "")
        if match:
            try:
                parsed = json.loads(match.group(1))
            except json.JSONDecodeError:
                parsed = None
        if parsed is None:
            stripped = (response_text or "").strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError:
                    parsed = None
        if not isinstance(parsed, dict):
            logger.warning(
                "Task '%s' declared output keys %s but response had no JSON; storing raw text under each key.",
                task.name,
                declared,
            )
            for key in declared:
                self._data[key] = response_text
            return
        for key in declared:
            if key in parsed:
                self._data[key] = parsed[key]

    def start_audit(self, task: Any) -> AuditEntry:
        entry = AuditEntry(task_name=task.name, started_at=datetime.now())
        self.audit.append(entry)
        return entry

    def finish_audit(self, entry: AuditEntry, status: str) -> None:
        entry.finished_at = datetime.now()
        entry.status = status
