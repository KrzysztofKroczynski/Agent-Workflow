from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.tree import Tree

from agentflow.core.agent import ProviderRegistry
from agentflow.core.context import ContextManager
from agentflow.core.executor import TaskExecutor
from agentflow.core.loader import Task, TaskLoader
from agentflow.exceptions import AgentflowError

console = Console()


def _collect_and_install_dependencies(root_task: Task) -> None:
    packages: list[str] = []

    def _walk(task: Task) -> None:
        packages.extend(task.config.dependencies)
        for child in task.subtasks:
            _walk(child)

    _walk(root_task)
    if not packages:
        return
    seen: set[str] = set()
    unique = [p for p in packages if not (p in seen or seen.add(p))]  # type: ignore[func-returns-value]
    console.print(f"[dim]Installing pipeline dependencies: {', '.join(unique)}[/dim]")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", *unique],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        console.print(f"[red]Dependency install failed:[/red]\n{result.stderr.strip()}")
        sys.exit(1)


@click.group()
def cli() -> None:
    """agentflow — agentic workflow framework."""


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False))
@click.option("--context", "context_json", default=None, help="Initial context as JSON.")
@click.option("--verbose", is_flag=True, help="Verbose audit output.")
def run(path: str, context_json: str | None, verbose: bool) -> None:
    """Run a workflow rooted at PATH."""
    initial = json.loads(context_json) if context_json else {}
    loader = TaskLoader()
    try:
        root = loader.load(Path(path))
    except AgentflowError as e:
        console.print(f"[red]Failed to load workflow:[/red] {e}")
        sys.exit(1)
    _collect_and_install_dependencies(root)
    cm = ContextManager(initial)
    executor = TaskExecutor(root, ProviderRegistry(), loader.registry, cm)
    try:
        result = asyncio.run(executor.run())
    except AgentflowError as e:
        console.print(f"[red]Workflow failed:[/red] {e}")
        sys.exit(1)
    console.print_json(json.dumps(result.context, default=str))
    if verbose:
        console.print("\n[bold]Audit trail:[/bold]")
        for entry in result.audit:
            console.print(
                f"  {entry.task_name}: {entry.status} ({entry.started_at} → {entry.finished_at})"
            )


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False))
def validate(path: str) -> None:
    """Validate a workflow's structure and configuration."""
    loader = TaskLoader()
    try:
        root = loader.load(Path(path))
    except AgentflowError as e:
        console.print(f"[red]Validation failed:[/red] {e}")
        sys.exit(1)

    errors: list[str] = []

    def check(task: Task) -> None:
        if task.config.tools and task.config.tools.use_shared:
            shared = loader.registry.shared_tools(root.path)
            for name in task.config.tools.use_shared:
                if name not in shared:
                    errors.append(
                        f"Task '{task.name}' references shared tool '{name}' that is not defined."
                    )
        for child in task.subtasks:
            check(child)

    check(root)

    if errors:
        for err in errors:
            console.print(f"[red]✗[/red] {err}")
        sys.exit(1)
    console.print("[green]✓[/green] Workflow valid.")
    _print_tree(root)


@cli.command(name="tree")
@click.argument("path", type=click.Path(exists=True, file_okay=False))
def tree_cmd(path: str) -> None:
    """Print the task tree."""
    loader = TaskLoader()
    try:
        root = loader.load(Path(path))
    except AgentflowError as e:
        console.print(f"[red]Failed to load workflow:[/red] {e}")
        sys.exit(1)
    _print_tree(root)


def _print_tree(root: Task) -> None:
    def label(task: Task) -> str:
        bits = [f"[bold]{task.name}[/bold]"]
        bits.append(f"priority={task.config.priority}")
        if task.tools:
            bits.append(f"tools={len(task.tools)}")
        if task.is_branch:
            mode = (
                task.config.subtasks.execution_type
                if task.config.subtasks
                else "parallel"
            )
            bits.append(f"children={len(task.subtasks)} ({mode})")
        if not task.config.enabled:
            bits.append("[dim]disabled[/dim]")
        return " ".join(bits)

    tree = Tree(label(root))

    def add(node: Tree, task: Task) -> None:
        for child in task.subtasks:
            sub = node.add(label(child))
            add(sub, child)

    add(tree, root)
    console.print(tree)


if __name__ == "__main__":
    cli()
