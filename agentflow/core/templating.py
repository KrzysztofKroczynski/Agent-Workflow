from __future__ import annotations

import re
from pathlib import Path

from agentflow.exceptions import ConfigError

_INCLUDE_RE = re.compile(r'\{\%\s*include\s+"([^"]+)"\s*\%\}')


def render_instructions(text: str, shared_dir: Path | None) -> str:
    return _render(text, shared_dir, set())


def _render(text: str, shared_dir: Path | None, visiting: set[str]) -> str:
    def replace(match: re.Match) -> str:
        name = match.group(1)
        if shared_dir is None:
            raise ConfigError(
                f"Instruction tries to include '{name}' but no shared/ directory exists."
            )
        if name in visiting:
            raise ConfigError(f"Cyclic include of snippet '{name}'.")
        path = shared_dir / "instructions" / f"{name}.md"
        if not path.exists():
            raise ConfigError(f"Shared instruction snippet '{name}' not found at {path}.")
        snippet = path.read_text()
        return _render(snippet, shared_dir, visiting | {name})

    return _INCLUDE_RE.sub(replace, text)
