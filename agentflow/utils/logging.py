"""Logging setup for AgentFlow.

All framework loggers live under the ``agentflow`` namespace so they can be
controlled as a group.

Usage
-----
From any framework module::

    from agentflow.utils.logging import get_logger
    logger = get_logger(__name__)

From a tool that accepts ``ctx``::

    def my_tool(ctx, arg: str) -> str:
        ctx.logger.info("doing thing with %s", arg)
        ...

Log level
---------
Set ``AGENTFLOW_LOG_LEVEL`` env var (default: ``INFO``).
``DEBUG`` enables per-tool invocation traces (args, return values, errors).
"""
import logging
import os

from rich.logging import RichHandler

_configured = False


def get_logger(name: str) -> logging.Logger:
    global _configured
    if not _configured:
        # Silence root so third-party libs (httpx, ollama, etc.) stay quiet.
        logging.getLogger().setLevel(logging.WARNING)

        level = os.environ.get("AGENTFLOW_LOG_LEVEL", "INFO").upper()
        handler = RichHandler(rich_tracebacks=True, show_path=False)
        handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))
        af = logging.getLogger("agentflow")
        af.setLevel(level)
        af.addHandler(handler)
        af.propagate = False

        _configured = True
    return logging.getLogger(name)
