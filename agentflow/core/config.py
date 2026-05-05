from __future__ import annotations

from typing import Any

from agentflow.exceptions import ConfigError
from agentflow.schemas.task_schema import Settings


def merge_config(parent: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    """§5.0: scalars → child wins, lists → child replaces, dicts → deep-merge."""
    out: dict[str, Any] = dict(parent)
    for key, child_val in child.items():
        if key in out and isinstance(out[key], dict) and isinstance(child_val, dict):
            out[key] = merge_config(out[key], child_val)
        else:
            out[key] = child_val
    return out


def _walk_to_root(task: Any) -> list[Any]:
    chain = []
    cur = task
    while cur is not None:
        chain.append(cur)
        cur = cur.parent
    return chain


def resolve_settings(task: Any) -> Settings:
    merged: dict[str, Any] = {}
    for ancestor in reversed(_walk_to_root(task)):
        if ancestor.config.settings is not None:
            merged = merge_config(
                merged, ancestor.config.settings.model_dump(exclude_unset=True)
            )
    return Settings(**merged) if merged else Settings()


def resolve_provider(task: Any) -> tuple[str, dict[str, Any]]:
    """Returns (provider_name, settings) per §6.4."""
    chain = _walk_to_root(task)

    provider_name: str | None = None
    for ancestor in chain:
        if ancestor.config.agent and ancestor.config.agent.provider:
            provider_name = ancestor.config.agent.provider
            break
    if provider_name is None:
        root = chain[-1]
        if root.config.providers and root.config.providers.default:
            provider_name = root.config.providers.default

    if provider_name is None:
        raise ConfigError(
            "No LLM provider configured. Add a `providers` block to your root task.yaml."
        )

    root = chain[-1]
    base_settings: dict[str, Any] = {}
    if root.config.providers and provider_name in root.config.providers.providers:
        pcfg = root.config.providers.providers[provider_name]
        base_settings = pcfg.model_dump(exclude_none=True)
    base_settings.pop("module", None)

    # Cascade agent overrides root → leaf
    merged = base_settings
    for ancestor in reversed(chain):
        if ancestor.config.agent is None:
            continue
        agent_overrides = ancestor.config.agent.model_dump(exclude_none=True)
        agent_overrides.pop("provider", None)
        if agent_overrides:
            merged = merge_config(merged, agent_overrides)

    return provider_name, merged


def resolve_provider_module(task: Any, provider_name: str) -> str:
    chain = _walk_to_root(task)
    root = chain[-1]
    if root.config.providers and provider_name in root.config.providers.providers:
        return root.config.providers.providers[provider_name].module
    raise ConfigError(f"Provider '{provider_name}' not declared in root task.yaml.")
