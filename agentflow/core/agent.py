from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from agentflow.core.tool import ToolSpec
from agentflow.exceptions import ProviderError


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class AgentResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "end_turn"


class AgentProvider(ABC):
    @abstractmethod
    def configure(self, **kwargs: Any) -> None: ...

    @abstractmethod
    def call(
        self,
        instructions: str,
        tools: list[ToolSpec],
        messages: list[dict[str, Any]],
    ) -> AgentResponse: ...

    @abstractmethod
    def supports_tool_calling(self) -> bool: ...


class ProviderRegistry:
    def __init__(self) -> None:
        self._classes: dict[str, type[AgentProvider]] = {}
        self._instances: dict[str, AgentProvider] = {}

    def register(self, name: str, cls: type[AgentProvider]) -> None:
        self._classes[name] = cls

    def load(self, name: str, module_path: str) -> type[AgentProvider]:
        if name in self._classes:
            return self._classes[name]
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            raise ProviderError(
                f"Could not import provider module '{module_path}': {e}"
            ) from e
        for attr in vars(module).values():
            if (
                isinstance(attr, type)
                and issubclass(attr, AgentProvider)
                and attr is not AgentProvider
            ):
                self._classes[name] = attr
                return attr
        raise ProviderError(
            f"No AgentProvider subclass found in module '{module_path}'."
        )

    def get(self, name: str, module_path: str, settings: dict[str, Any]) -> AgentProvider:
        cache_key = f"{name}|{sorted(settings.items())}"
        if cache_key in self._instances:
            return self._instances[cache_key]
        cls = self.load(name, module_path)
        instance = cls()
        instance.configure(**settings)
        self._instances[cache_key] = instance
        return instance
