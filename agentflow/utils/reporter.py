from __future__ import annotations

import json
import time
from typing import Any

from rich.console import Console
from rich.panel import Panel

_console = Console()
_INDENT = "  "


def _depth(task: Any) -> int:
    d, cur = 0, task.parent
    while cur is not None:
        d += 1
        cur = cur.parent
    return d


class RunReporter:
    """
    Default: task start/done lines with timing.
    verbose=True: also prints instructions, input, LLM response, and tool calls.
    """

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose
        self._starts: dict[str, float] = {}

    def task_start(self, task: Any) -> None:
        self._starts[task.name] = time.monotonic()
        ind = _INDENT * _depth(task)
        _console.print(f"{ind}[dim]>[/dim] {task.name}...")

    def task_done(self, task: Any, status: str = "ok") -> None:
        elapsed = time.monotonic() - self._starts.pop(task.name, time.monotonic())
        ind = _INDENT * _depth(task)
        if status == "ok":
            _console.print(f"{ind}[green]✓[/green] {task.name}  [dim]{elapsed:.1f}s[/dim]")
        else:
            _console.print(f"{ind}[red]✗[/red] {task.name}  [dim]{elapsed:.1f}s[/dim]")

    # ── verbose helpers ───────────────────────────────────────────────────────

    def agent_call(
        self,
        task: Any,
        instructions: str,
        messages: list[dict[str, Any]],
        tools: list[Any],
    ) -> None:
        if not self.verbose:
            return
        ind = _INDENT * (_depth(task) + 1)
        _console.rule(f"[cyan]{task.name} · LLM call[/cyan]", style="dim cyan")
        _console.print(f"{ind}[bold cyan]instructions[/bold cyan]")
        _console.print(Panel(instructions.strip(), border_style="dim"))
        user_msgs = [m for m in messages if m.get("role") == "user"]
        if user_msgs:
            _console.print(f"{ind}[bold cyan]input[/bold cyan]")
            _console.print(Panel(user_msgs[-1].get("content", ""), border_style="dim"))
        if tools:
            names = ", ".join(t.name for t in tools)
            _console.print(f"{ind}[dim]tools: {names}[/dim]")

    def agent_response(self, task: Any, text: str, has_tool_calls: bool) -> None:
        if not self.verbose:
            return
        ind = _INDENT * (_depth(task) + 1)
        if text:
            _console.print(f"{ind}[bold cyan]response[/bold cyan]")
            _console.print(Panel(text.strip(), border_style="dim green"))
        if has_tool_calls:
            _console.print(f"{ind}[dim]v tool calls[/dim]")

    def tool_call(
        self,
        task: Any,
        name: str,
        arguments: dict[str, Any],
        result: Any,
    ) -> None:
        if not self.verbose:
            return
        ind = _INDENT * (_depth(task) + 1)
        args_str = json.dumps(arguments, default=str)
        result_str = json.dumps(result, default=str) if not isinstance(result, str) else result
        if len(result_str) > 400:
            result_str = result_str[:397] + "..."
        _console.print(f"{ind}[yellow]->[/yellow] [bold]{name}[/bold]({args_str})")
        _console.print(f"{ind}[yellow]<-[/yellow] {result_str}")
