from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agentflow.core.agent import AgentProvider, AgentResponse
from agentflow.core.tool import ToolSpec
from agentflow.exceptions import ProviderError


class FakeProvider(AgentProvider):
    """Deterministic provider for tests.

    `script` is either a list of `AgentResponse` objects (consumed in order, last
    repeats) or a callable receiving `(instructions, tools, messages)` and
    returning an `AgentResponse`.
    """

    def __init__(self) -> None:
        self._script: list[AgentResponse] | Callable[..., AgentResponse] | None = None
        self._cursor = 0
        self.calls: list[dict[str, Any]] = []

    def configure(
        self,
        script: list[AgentResponse] | Callable[..., AgentResponse] | None = None,
        **_: Any,
    ) -> None:
        if script is None:
            self._script = [AgentResponse(text="", finish_reason="end_turn")]
        else:
            self._script = script
        self._cursor = 0

    def call(
        self,
        instructions: str,
        tools: list[ToolSpec],
        messages: list[dict[str, Any]],
    ) -> AgentResponse:
        if self._script is None:
            raise ProviderError("FakeProvider not configured.")
        self.calls.append(
            {"instructions": instructions, "tools": tools, "messages": list(messages)}
        )
        if callable(self._script):
            return self._script(instructions, tools, messages)
        idx = min(self._cursor, len(self._script) - 1)
        self._cursor += 1
        return self._script[idx]

    def supports_tool_calling(self) -> bool:
        return True
