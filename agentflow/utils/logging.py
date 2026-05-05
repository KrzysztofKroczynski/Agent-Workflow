import logging
import os

from rich.logging import RichHandler

_configured = False


def get_logger(name: str) -> logging.Logger:
    global _configured
    if not _configured:
        level = os.environ.get("AGENTFLOW_LOG_LEVEL", "INFO").upper()
        logging.basicConfig(
            level=level,
            format="%(message)s",
            datefmt="[%X]",
            handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
        )
        _configured = True
    return logging.getLogger(name)
