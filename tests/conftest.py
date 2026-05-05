from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agentflow.core.agent import AgentResponse, ProviderRegistry
from agentflow.providers.fake import FakeProvider


def materialize(root: Path, layout: dict[str, Any]) -> None:
    for name, value in layout.items():
        target = root / name
        if isinstance(value, dict):
            target.mkdir(parents=True, exist_ok=True)
            materialize(target, value)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value)


@pytest.fixture
def tmp_workflow(tmp_path: Path) -> Callable[[dict[str, Any]], Path]:
    def _factory(layout: dict[str, Any]) -> Path:
        materialize(tmp_path, layout)
        return tmp_path

    return _factory


@pytest.fixture
def fake_registry() -> tuple[ProviderRegistry, FakeProvider]:
    registry = ProviderRegistry()
    instance = FakeProvider()
    instance.configure(script=[AgentResponse(text="ok", finish_reason="end_turn")])

    class _Wrapper:
        def get(self, name: str, module_path: str, settings: dict[str, Any]) -> FakeProvider:
            instance.configure(**settings) if settings.get("script") else None
            return instance

        def register(self, *_a, **_k):
            pass

        def load(self, *_a, **_k):
            return type(instance)

    return _Wrapper(), instance  # type: ignore[return-value]


@pytest.fixture
def make_provider() -> Callable[[Any], FakeProvider]:
    def _make(script: Any) -> FakeProvider:
        p = FakeProvider()
        p.configure(script=script)
        return p

    return _make


class FixedRegistry(ProviderRegistry):
    """ProviderRegistry that always returns a single configured FakeProvider."""

    def __init__(self, provider: FakeProvider) -> None:
        super().__init__()
        self._provider = provider

    def get(self, name: str, module_path: str, settings: dict[str, Any]) -> FakeProvider:  # type: ignore[override]
        return self._provider


@pytest.fixture
def fixed_registry() -> Callable[[FakeProvider], FixedRegistry]:
    return FixedRegistry
