from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    module: str
    model: str | None = None
    temperature: float | None = None
    api_key_env: str | None = None
    base_url: str | None = None


class ProvidersBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    default: str | None = None
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _collect_providers(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out: dict[str, Any] = {"default": data.get("default")}
        providers: dict[str, Any] = {}
        for key, value in data.items():
            if key == "default":
                continue
            if key == "providers" and isinstance(value, dict):
                providers.update(value)
                continue
            if isinstance(value, dict) and "module" in value:
                providers[key] = value
        out["providers"] = providers
        return out


class AgentBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    provider: str | None = None
    model: str | None = None
    temperature: float | None = None


class Settings(BaseModel):
    max_retries: int = 3
    timeout: float = 300.0
    parallel_workers: int = 4


class IOBlock(BaseModel):
    required: list[str] = Field(default_factory=list)
    optional: list[str] = Field(default_factory=list)


class SubtasksBlock(BaseModel):
    execution_type: Literal["sequential", "parallel", "graph", "loop", "priority_groups"] = "parallel"
    order: list[str] | None = None
    on_error: Literal["fail", "continue", "ignore"] = "fail"
    until: str | None = None
    max_iterations: int | None = None
    iteration_timeout: float | None = None
    on_max_iterations: Literal["fail", "succeed_with_last"] = "fail"


class ToolsBlock(BaseModel):
    use_shared: list[str] = Field(default_factory=list)


class ConditionsBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    skip_if: str | None = None
    retry_on: list[str] = Field(default_factory=list)


class TaskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    priority: int = 50
    enabled: bool = True

    settings: Settings | None = None
    agent: AgentBlock | None = None
    providers: ProvidersBlock | None = None

    input: IOBlock | None = None
    output: list[str] | None = None

    subtasks: SubtasksBlock | None = None
    tools: ToolsBlock | None = None

    inherit_tools: list[str] | bool | None = None
    exclude_tools: list[str] = Field(default_factory=list)
    block_tools: list[str] = Field(default_factory=list)
    inherit_tools_depth: int = -1

    conditions: ConditionsBlock | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    on_failure: Literal["fail", "skip", "use_default"] = "fail"
    default_output: dict[str, Any] = Field(default_factory=dict)
