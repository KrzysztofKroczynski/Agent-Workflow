class AgentflowError(Exception):
    pass


class TaskNotFoundError(AgentflowError):
    pass


class ToolError(AgentflowError):
    pass


class ConfigError(AgentflowError):
    pass


class ProviderError(AgentflowError):
    pass


class TaskTimeoutError(AgentflowError):
    pass
