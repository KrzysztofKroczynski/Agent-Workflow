from __future__ import annotations

import fnmatch
import json
import re
from typing import Any

from agentflow.core.agent import AgentProvider, AgentResponse, ToolCall
from agentflow.core.tool import ToolSpec
from agentflow.exceptions import ProviderError

NATIVE_TOOL_CALL_MODELS = (
    "llama3.1*",
    "llama3.2*",
    "llama3.3*",
    "qwen2.5*",
    "qwen3*",
    "mistral-nemo*",
    "mistral-small*",
)


def _supports_native(model: str) -> bool:
    return any(fnmatch.fnmatch(model, pat) for pat in NATIVE_TOOL_CALL_MODELS)


_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*\n(\{.*?\})\s*\n```", re.DOTALL)


class OllamaProvider(AgentProvider):
    def __init__(self) -> None:
        self._client: Any = None
        self._model: str | None = None
        self._base_url = "http://localhost:11434"
        self._temperature = 0.0
        self._tool_calling_mode: str | None = None  # "native" | "prompt" | None=auto

    def configure(
        self,
        model: str | None = None,
        base_url: str = "http://localhost:11434",
        temperature: float = 0.0,
        tool_calling: str | None = None,
        **_: Any,
    ) -> None:
        if not model:
            raise ProviderError("OllamaProvider requires a `model` setting.")
        self._model = model
        self._base_url = base_url
        self._temperature = temperature
        self._tool_calling_mode = tool_calling
        try:
            import ollama  # type: ignore
        except ImportError as e:
            raise ProviderError(
                "The `ollama` package is required for OllamaProvider. "
                "Install with `uv sync --extra ollama`."
            ) from e
        self._client = ollama.Client(host=base_url)

    def supports_tool_calling(self) -> bool:
        if self._tool_calling_mode == "native":
            return True
        if self._tool_calling_mode == "prompt":
            return False
        return _supports_native(self._model or "")

    def _tools_payload(self, tools: list[ToolSpec]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    def call(
        self,
        instructions: str,
        tools: list[ToolSpec],
        messages: list[dict[str, Any]],
    ) -> AgentResponse:
        if self._client is None:
            raise ProviderError("OllamaProvider.configure() was not called.")
        full_messages = [{"role": "system", "content": instructions}, *messages]
        if self.supports_tool_calling() and tools:
            response = self._client.chat(
                model=self._model,
                messages=full_messages,
                tools=self._tools_payload(tools),
                options={"temperature": self._temperature},
            )
            msg = response.get("message", {}) if isinstance(response, dict) else response.message
            text = (msg.get("content") if isinstance(msg, dict) else msg.content) or ""
            raw_calls = (
                msg.get("tool_calls") if isinstance(msg, dict) else getattr(msg, "tool_calls", None)
            ) or []
            calls = []
            for i, c in enumerate(raw_calls):
                fn = c["function"] if isinstance(c, dict) else c.function
                name = fn["name"] if isinstance(fn, dict) else fn.name
                args = fn.get("arguments") if isinstance(fn, dict) else fn.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                calls.append(ToolCall(id=str(i), name=name, arguments=args or {}))
            return AgentResponse(
                text=text,
                tool_calls=calls,
                finish_reason="tool_use" if calls else "end_turn",
            )

        # Prompt-engineered fallback
        tool_brief = "\n".join(
            f"- {t.name}: {t.description}\n  params: {json.dumps(t.parameters)}" for t in tools
        )
        if tool_brief:
            full_messages[0]["content"] += (
                "\n\nAvailable tools:\n"
                + tool_brief
                + "\n\nTo call a tool, reply with a JSON object: "
                '{"tool": "<name>", "arguments": {...}}.'
            )
        response = self._client.chat(
            model=self._model,
            messages=full_messages,
            options={"temperature": self._temperature},
        )
        msg = response.get("message", {}) if isinstance(response, dict) else response.message
        text = (msg.get("content") if isinstance(msg, dict) else msg.content) or ""
        calls = []
        m = _FENCED_JSON_RE.search(text)
        candidate = m.group(1) if m else (text.strip() if text.strip().startswith("{") else None)
        if candidate:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict) and "tool" in parsed:
                    calls.append(
                        ToolCall(
                            id="0",
                            name=parsed["tool"],
                            arguments=parsed.get("arguments", {}) or {},
                        )
                    )
            except json.JSONDecodeError:
                pass
        return AgentResponse(
            text=text,
            tool_calls=calls,
            finish_reason="tool_use" if calls else "end_turn",
        )
