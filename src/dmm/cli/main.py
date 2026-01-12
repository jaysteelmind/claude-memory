"""Main CLI entrypoint for DMM."""

import json
from pathlib import Path
from typing import Annotated, Optional

import httpx
import typer
from rich.console import Console
from rich.table import Table

from dmm.cli.daemon import daemon_app
from dmm.cli.query import query_command
from dmm.cli.review import app as review_app
from dmm.cli.usage import app as usage_app
from dmm.cli.write import app as write_app
from dmm.core.constants import DEFAULT_HOST, DEFAULT_PORT, get_memory_root

console = Console()
err_console = Console(stderr=True)

# Create main app
app = typer.Typer(
    name="dmm",
    help="Dynamic Markdown Memory - AI agent memory system",
    no_args_is_help=True,
)

# Add subcommands
app.add_typer(daemon_app, name="daemon")
app.command("query")(query_command)

# Phase 2: Write-back commands
app.add_typer(write_app, name="write")
app.add_typer(review_app, name="review")
app.add_typer(usage_app, name="usage")


@app.command("status")
def status_command(
    host: Annotated[str, typer.Option("--host", help="Daemon host")] = DEFAULT_HOST,
    port: Annotated[int, typer.Option("--port", help="Daemon port")] = DEFAULT_PORT,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON")
    ] = False,
) -> None:
    """Show system status."""
    url = f"http://{host}:{port}/status"

    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.json()

    except httpx.ConnectError:
        if json_output:
            console.print(json.dumps({"daemon_running": False}))
        else:
            console.print("[yellow]DMM Status[/yellow]")
            console.print("-" * 30)
            console.print("Daemon:          [red]not running[/red]")
            console.print(f"Memory root:     {get_memory_root()}")
        return

    except httpx.RequestError as e:
        err_console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if json_output:
        console.print(json.dumps(data, indent=2))
        return

    # Pretty print status
    console.print("[bold]DMM Status[/bold]")
    console.print("-" * 30)
    console.print(f"Daemon:          [green]running[/green] (PID: {data.get('daemon_pid', 'unknown')})")
    console.print(f"Memory root:     {data.get('memory_root', 'unknown')}")
    console.print(f"Indexed:         {data.get('indexed_memories', 0)} memories")
    console.print(f"Baseline:        {data.get('baseline_files', 0)} files, {data.get('baseline_tokens', 0)} tokens")

    last_reindex = data.get("last_reindex")
    if last_reindex:
        console.print(f"Last reindex:    {last_reindex}")
    else:
        console.print("Last reindex:    never")

    watcher = "active" if data.get("watcher_active") else "inactive"
    watcher_color = "green" if data.get("watcher_active") else "yellow"
    console.print(f"Watcher:         [{watcher_color}]{watcher}[/{watcher_color}]")


@app.command("reindex")
def reindex_command(
    full: Annotated[
        bool, typer.Option("--full", help="Force full reindex")
    ] = True,
    host: Annotated[str, typer.Option("--host", help="Daemon host")] = DEFAULT_HOST,
    port: Annotated[int, typer.Option("--port", help="Daemon port")] = DEFAULT_PORT,
) -> None:
    """Trigger reindexing of memory files."""
    url = f"http://{host}:{port}/reindex"

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, json={"full": full})
            response.raise_for_status()
            data = response.json()

    except httpx.ConnectError:
        err_console.print("[red]Error: Cannot connect to daemon[/red]")
        err_console.print("Is the daemon running? Try: dmm daemon start")
        raise typer.Exit(1)
    except httpx.RequestError as e:
        err_console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Reindexed {data.get('reindexed', 0)} memories[/green]")
    console.print(f"Duration: {data.get('duration_ms', 0):.1f}ms")

    errors = data.get("errors", 0)
    if errors > 0:
        console.print(f"[yellow]Errors: {errors}[/yellow]")
        for err in data.get("error_details", []):
            console.print(f"  - {err.get('path', 'unknown')}: {err.get('error', 'unknown')}")


@app.command("validate")
def validate_command(
    fix: Annotated[
        bool, typer.Option("--fix", help="Auto-fix where possible")
    ] = False,
    path: Annotated[
        Optional[Path], typer.Option("--path", help="Validate specific file")
    ] = None,
) -> None:
    """Validate memory files."""
    from dmm.core.config import DMMConfig
    from dmm.indexer.parser import MemoryParser, TokenCounter

    memory_root = get_memory_root()

    if not memory_root.exists():
        err_console.print(f"[red]Memory root not found: {memory_root}[/red]")
        raise typer.Exit(1)

    config = DMMConfig.load()
    parser = MemoryParser(
        token_counter=TokenCounter(),
        min_tokens=config.validation.min_tokens,
        max_tokens=config.validation.max_tokens,
    )

    # Collect files to validate
    if path:
        if not path.exists():
            err_console.print(f"[red]File not found: {path}[/red]")
            raise typer.Exit(1)
        files = [path]
    else:
        files = list(memory_root.rglob("*.md"))
        # Exclude deprecated
        files = [f for f in files if "/deprecated/" not in str(f)]

    console.print(f"Validating {len(files)} files in {memory_root}...")

    valid_count = 0
    warning_count = 0
    error_count = 0
    all_warnings: list[tuple[Path, str]] = []
    all_errors: list[tuple[Path, str]] = []

    for file_path in files:
        result = parser.parse(file_path)

        if result.error:
            error_count += 1
            all_errors.append((file_path, str(result.error)))
        else:
            valid_count += 1
            for warning in result.warnings:
                warning_count += 1
                all_warnings.append((file_path, str(warning)))

    # Summary
    console.print()
    console.print(f"[green]{valid_count} files valid[/green]")

    if warning_count > 0:
        console.print(f"[yellow]{warning_count} warnings:[/yellow]")
        for file_path, msg in all_warnings:
            relative = file_path.relative_to(memory_root) if memory_root in file_path.parents else file_path
            console.print(f"  - {relative}: {msg}")

    if error_count > 0:
        console.print(f"[red]{error_count} errors:[/red]")
        for file_path, msg in all_errors:
            relative = file_path.relative_to(memory_root) if memory_root in file_path.parents else file_path
            console.print(f"  - {relative}: {msg}")
        raise typer.Exit(1)


@app.command("init")
def init_command(
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing files")
    ] = False,
) -> None:
    """Initialize DMM in the current directory."""
    from dmm.core.config import DMMConfig
    from dmm.core.constants import get_dmm_root

    dmm_root = get_dmm_root()

    if dmm_root.exists() and not force:
        console.print(f"[yellow]DMM already initialized at {dmm_root}[/yellow]")
        console.print("Use --force to reinitialize")
        return

    # Create directory structure
    directories = [
        dmm_root / "index",
        dmm_root / "memory" / "baseline",
        dmm_root / "memory" / "global",
        dmm_root / "memory" / "agent",
        dmm_root / "memory" / "project",
        dmm_root / "memory" / "ephemeral",
        dmm_root / "memory" / "deprecated",
        dmm_root / "packs",
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

    # Create default config
    config = DMMConfig()
    config.save()

    # Initialize Phase 2 databases
    from dmm.writeback.queue import ReviewQueue
    from dmm.writeback.usage import UsageTracker
    from dmm.writeback.conflicts import initialize_conflicts_db
    
    # Review queue
    queue = ReviewQueue(dmm_root.parent)
    queue.initialize()
    queue.close()
    
    # Usage tracker
    tracker = UsageTracker(dmm_root.parent)
    tracker.initialize()
    tracker.close()
    
    # Conflicts database (Phase 3 preparation)
    initialize_conflicts_db(dmm_root.parent)

    # Create BOOT.md with Phase 2 updates
    boot_content = """# DMM Boot Instructions

You have access to a Dynamic Markdown Memory (DMM) system that provides
relevant context for your tasks without loading everything into context.

## What You Always Have

Every Memory Pack includes the **Baseline Pack** - critical context that applies
to all tasks. This is automatically included; you do not need to query for it.

## How to Retrieve Memory

When you need context beyond baseline, request a Memory Pack:

    dmm query "<describe your task or question>" --budget 1200

## How to Write Memory (Phase 2)

To propose a new memory:

    dmm write propose <path> --file <content.md> --reason "why this memory"

To update an existing memory:

    dmm write update <memory_id> --file <content.md> --reason "update reason"

To deprecate a memory:

    dmm write deprecate <memory_id> --reason "deprecation reason"

To promote a memory to a different scope:

    dmm write promote <memory_id> --scope global --reason "promotion reason"

## Review Process

All write proposals go through review:

    dmm review list           # See pending proposals
    dmm review process <id>   # Review a proposal
    dmm review batch          # Review all pending

## When to Retrieve

Request a Memory Pack:
- At task start (if baseline is insufficient)
- When switching to a different domain
- After encountering a failure or contradiction
- Before producing final deliverables

## When to Write

Propose a new memory when:
- You discover a project constraint or decision
- A pattern emerges that should be documented
- You find information that would help future tasks
- Temporary findings need to be preserved (ephemeral)

## Memory Quality Guidelines

Good memories are:
- **Atomic**: One concept per file (300-800 tokens)
- **Self-contained**: No undefined references
- **Actionable**: Clear what to do with the information
- **Justified**: Include rationale for decisions
- **Appropriately scoped**: baseline < global < project < ephemeral
"""
    (dmm_root / "BOOT.md").write_text(boot_content)

    # Create policy.md with Phase 2 updates
    policy_content = """# DMM Policy

## Memory Retrieval Policy

### Retrieval Triggers
Retrieve a Memory Pack when:
1. Starting a new task (if baseline is insufficient)
2. Switching to a different domain or subsystem
3. Encountering unexpected behavior or failures
4. Before producing final deliverables

### Token Budget Guidelines

| Task Type | Recommended Budget |
|-----------|-------------------|
| Quick question | 1000 |
| Standard task | 1500 |
| Complex task | 2000 |
| Multi-domain | 2500 |

Baseline always uses 800 tokens (reserved).

## Scope Meanings

| Scope | Meaning |
|-------|---------|
| baseline | Critical, always-relevant (human review required) |
| global | Stable, cross-project truths |
| agent | Behavioral rules for the agent |
| project | Project-specific context |
| ephemeral | Temporary findings (auto-expire) |
| deprecated | Outdated memories (excluded by default) |

## Write Policy (Phase 2)

### What to Write
- Architectural decisions with rationale
- Project constraints and their reasons
- Behavioral guidelines for the agent
- Patterns discovered during development
- Temporary findings (as ephemeral)

### What NOT to Write
- Transient chat context
- Raw logs (store elsewhere)
- Sensitive information not intended for repo
- One-off solutions unlikely to recur

### Review Requirements
- All writes require review before commit
- Baseline modifications always require human review
- Auto-approve threshold: 95% confidence
- Rejected proposals include actionable feedback

### Conflict Handling
If two memories conflict:
- Do NOT silently choose one
- Flag the conflict for review
- Continue with the more recent or higher-confidence memory
- Note the conflict in your response to the user
"""
    (dmm_root / "policy.md").write_text(policy_content)

    # Create example baseline memory
    example_identity = """---
id: mem_2025_01_01_001
tags: [identity, role]
scope: baseline
priority: 1.0
confidence: stable
status: active
created: 2025-01-01
---

# Agent Identity

You are an AI assistant working on this project. Your role is to help
with development tasks while respecting the constraints and conventions
documented in the memory system.

## Core Responsibilities

- Follow project conventions
- Respect documented constraints
- Query memory when context is needed
- Propose memory updates when new patterns emerge
"""
    (dmm_root / "memory" / "baseline" / "identity.md").write_text(example_identity)

    console.print(f"[green]DMM initialized at {dmm_root}[/green]")
    console.print()
    console.print("Next steps:")
    console.print("  1. Add baseline memories to .dmm/memory/baseline/")
    console.print("  2. Start the daemon: dmm daemon start")
    console.print("  3. Query memory: dmm query 'your task'")
    console.print("  4. Propose new memory: dmm write propose <path> --file <file> --reason 'reason'")


@app.command("dirs")
def dirs_command(
    host: Annotated[str, typer.Option("--host", help="Daemon host")] = DEFAULT_HOST,
    port: Annotated[int, typer.Option("--port", help="Daemon port")] = DEFAULT_PORT,
) -> None:
    """List memory directories."""
    url = f"http://{host}:{port}/stats"

    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.json()

    except httpx.ConnectError:
        # Fallback to local filesystem
        memory_root = get_memory_root()
        if not memory_root.exists():
            err_console.print(f"[red]Memory root not found: {memory_root}[/red]")
            raise typer.Exit(1)

        table = Table(title="Memory Directories")
        table.add_column("Directory", style="cyan")
        table.add_column("Files", justify="right")

        for scope_dir in sorted(memory_root.iterdir()):
            if scope_dir.is_dir():
                file_count = len(list(scope_dir.rglob("*.md")))
                table.add_row(scope_dir.name, str(file_count))

        console.print(table)
        return

    except httpx.RequestError as e:
        err_console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    # Parse from stats
    indexer_stats = data.get("indexer", {})
    console.print("[bold]Memory Directories[/bold]")
    console.print(f"Total indexed: {indexer_stats.get('memory_count', 0)}")


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
