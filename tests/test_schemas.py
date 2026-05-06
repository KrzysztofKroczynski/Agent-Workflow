import pytest
import yaml

from agentflow.schemas.task_schema import Settings, TaskConfig

ROOT_YAML = """
name: data_workflow
description: Test
providers:
  default: claude
  claude:
    module: agentflow.providers.claude
    model: claude-sonnet-4
    api_key_env: ANTHROPIC_API_KEY
settings:
  max_retries: 3
  timeout: 120
context:
  api_base_url: https://api.example.com
"""

CHILD_YAML = """
name: fetch_data
priority: 20
enabled: true
settings:
  max_retries: 5
agent:
  provider: claude
  temperature: 0.2
input:
  required: [api_base_url]
output: [raw_data]
"""


def test_root_yaml_parses():
    cfg = TaskConfig(**yaml.safe_load(ROOT_YAML))
    assert cfg.name == "data_workflow"
    assert cfg.providers is not None
    assert cfg.providers.default == "claude"
    assert "claude" in cfg.providers.providers
    assert cfg.providers.providers["claude"].module == "agentflow.providers.claude"
    assert cfg.settings is not None
    assert cfg.settings.max_retries == 3
    assert cfg.context["api_base_url"] == "https://api.example.com"


def test_child_yaml_parses():
    cfg = TaskConfig(**yaml.safe_load(CHILD_YAML))
    assert cfg.priority == 20
    assert cfg.settings.max_retries == 5
    assert cfg.agent.provider == "claude"
    assert cfg.agent.temperature == 0.2
    assert cfg.input.required == ["api_base_url"]
    assert cfg.output == {"raw_data": None}


def test_defaults():
    cfg = TaskConfig()
    assert cfg.priority == 50
    assert cfg.enabled is True
    assert cfg.exclude_tools == []
    assert cfg.inherit_tools_depth == -1


def test_unknown_top_level_rejected():
    with pytest.raises(Exception):
        TaskConfig(**yaml.safe_load("totally_made_up: 42"))


def test_settings_defaults():
    s = Settings()
    assert s.max_retries == 3
    assert s.timeout == 300.0
    assert s.parallel_workers == 4
