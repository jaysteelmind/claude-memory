"""
Bootstrap command for DMM.

Provides programmatic project initialization and setup,
replacing manual execution of start.md instructions.
"""

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel

from dmm.cli.utils.daemon_manager import DaemonManager, DaemonManagerConfig
from dmm.core.constants import DEFAULT_HOST, DEFAULT_PORT

console = Console()
err_console = Console(stderr=True)

# Create bootstrap app
bootstrap_app = typer.Typer(
    name="bootstrap",
    help="Bootstrap DMM in a project",
    no_args_is_help=False,
)


@bootstrap_app.callback(invoke_without_command=True)
def bootstrap(
    ctx: typer.Context,
    project_dir: Annotated[
        Optional[Path],
        typer.Option("--project", "-p", help="Project directory (default: current)"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Force re-initialization"),
    ] = False,
    no_daemon: Annotated[
        bool,
        typer.Option("--no-daemon", help="Skip daemon startup"),
    ] = False,
    no_claude_md: Annotated[
        bool,
        typer.Option("--no-claude-md", help="Skip CLAUDE.md generation"),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Minimal output"),
    ] = False,
) -> None:
    """
    Bootstrap DMM in a project directory.

    This command:
    1. Initializes .dmm directory if needed
    2. Starts the daemon if not running
    3. Generates/updates CLAUDE.md for Claude Code integration
    4. Verifies system health

    Example:
        dmm bootstrap
        dmm bootstrap --project /path/to/project
        dmm bootstrap --force
    """
    if ctx.invoked_subcommand is not None:
        return

    project_path = (project_dir or Path.cwd()).resolve()

    if not quiet:
        console.print(
            Panel(
                "[bold blue]DMM Bootstrap[/bold blue]\n"
                f"Project: {project_path}",
                expand=False,
            )
        )

    # Step 1: Check/Initialize .dmm directory
    dmm_dir = project_path / ".dmm"
    if not _initialize_dmm(dmm_dir, force, quiet):
        raise typer.Exit(1)

    # Step 2: Start daemon if needed
    if not no_daemon:
        if not _start_daemon(quiet):
            err_console.print("[yellow]Warning: Daemon failed to start[/yellow]")

    # Step 3: Generate CLAUDE.md
    if not no_claude_md:
        _generate_claude_md(project_path, quiet)

    # Step 4: Archive start.md if present
    _archive_start_md(project_path, quiet)

    # Step 5: Verify and report
    _report_status(project_path, quiet)


def _initialize_dmm(dmm_dir: Path, force: bool, quiet: bool) -> bool:
    """Initialize .dmm directory structure."""
    if not quiet:
        console.print("\n[bold]Step 1:[/bold] Checking DMM initialization...")

    if dmm_dir.exists() and not force:
        if not quiet:
            console.print("  [green]Already initialized[/green]")
        return True

    if dmm_dir.exists() and force:
        if not quiet:
            console.print("  [yellow]Force re-initialization...[/yellow]")
        # Keep memory files, reinitialize structure
        _backup_memories(dmm_dir)

    # Create directory structure
    directories = [
        dmm_dir / "memory" / "baseline",
        dmm_dir / "memory" / "global",
        dmm_dir / "memory" / "agent",
        dmm_dir / "memory" / "project",
        dmm_dir / "memory" / "ephemeral",
        dmm_dir / "memory" / "deprecated",
        dmm_dir / "index",
        dmm_dir / "packs",
        dmm_dir / "skills" / "core",
        dmm_dir / "skills" / "custom",
        dmm_dir / "tools" / "cli",
        dmm_dir / "tools" / "api",
        dmm_dir / "tools" / "mcp",
        dmm_dir / "tools" / "function",
        dmm_dir / "agents",
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

    # Create BOOT.md if not exists
    boot_md = dmm_dir / "BOOT.md"
    if not boot_md.exists():
        _create_boot_md(boot_md)

    # Create policy.md if not exists
    policy_md = dmm_dir / "policy.md"
    if not policy_md.exists():
        _create_policy_md(policy_md)

    # Create daemon.config.json if not exists
    config_file = dmm_dir / "daemon.config.json"
    if not config_file.exists():
        _create_daemon_config(config_file)

    if not quiet:
        console.print("  [green]Initialized .dmm directory[/green]")

    return True


def _backup_memories(dmm_dir: Path) -> None:
    """Backup existing memory files before re-initialization."""
    memory_dir = dmm_dir / "memory"
    if memory_dir.exists():
        backup_dir = dmm_dir.parent / f".dmm-backup-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        shutil.copytree(memory_dir, backup_dir / "memory", dirs_exist_ok=True)


def _start_daemon(quiet: bool) -> bool:
    """Start the DMM daemon."""
    if not quiet:
        console.print("\n[bold]Step 2:[/bold] Starting daemon...")

    manager = DaemonManager(DaemonManagerConfig(quiet=quiet))

    if manager.is_running():
        if not quiet:
            console.print("  [green]Daemon already running[/green]")
        return True

    success = manager.start(wait=True)

    if success:
        if not quiet:
            console.print("  [green]Daemon started[/green]")
    else:
        if not quiet:
            console.print("  [red]Failed to start daemon[/red]")

    return success


def _generate_claude_md(project_path: Path, quiet: bool) -> None:
    """Generate CLAUDE.md from template."""
    if not quiet:
        console.print("\n[bold]Step 3:[/bold] Generating CLAUDE.md...")

    claude_md = project_path / "CLAUDE.md"
    
    # Find template
    template_locations = [
        Path(__file__).parent.parent.parent.parent.parent / "templates" / "CLAUDE.md.template",
        Path.home() / ".dmm-system" / "templates" / "CLAUDE.md.template",
        project_path / "templates" / "CLAUDE.md.template",
    ]

    template_path = None
    for loc in template_locations:
        if loc.exists():
            template_path = loc
            break

    if template_path:
        content = template_path.read_text()
        content = content.replace("{{TIMESTAMP}}", datetime.now().isoformat())
        
        # Backup existing CLAUDE.md
        if claude_md.exists():
            backup_path = project_path / f"CLAUDE.md.backup.{datetime.now().strftime('%Y%m%d%H%M%S')}"
            shutil.copy(claude_md, backup_path)
            if not quiet:
                console.print(f"  [yellow]Backed up existing CLAUDE.md to {backup_path.name}[/yellow]")

        claude_md.write_text(content)
        if not quiet:
            console.print("  [green]Generated CLAUDE.md from template[/green]")
    else:
        if not quiet:
            console.print("  [yellow]Template not found, skipping CLAUDE.md generation[/yellow]")


def _archive_start_md(project_path: Path, quiet: bool) -> None:
    """Archive start.md if present."""
    start_md = project_path / "start.md"
    if start_md.exists():
        archive_path = project_path / "start.md.done"
        shutil.move(str(start_md), str(archive_path))
        if not quiet:
            console.print("\n[bold]Step 4:[/bold] Archived start.md -> start.md.done")


def _report_status(project_path: Path, quiet: bool) -> None:
    """Report final bootstrap status."""
    if quiet:
        return

    console.print("\n" + "=" * 50)
    console.print("[bold green]DMM Bootstrap Complete[/bold green]")
    console.print("=" * 50)

    dmm_dir = project_path / ".dmm"
    console.print(f"\nProject:     {project_path}")
    console.print(f"DMM Dir:     {dmm_dir}")

    # Check daemon
    manager = DaemonManager()
    if manager.is_running():
        console.print("Daemon:      [green]running[/green]")
    else:
        console.print("Daemon:      [yellow]not running[/yellow]")

    # Count memories
    memory_count = 0
    memory_dir = dmm_dir / "memory"
    if memory_dir.exists():
        for scope_dir in memory_dir.iterdir():
            if scope_dir.is_dir() and scope_dir.name != "deprecated":
                memory_count += len(list(scope_dir.glob("*.md")))

    console.print(f"Memories:    {memory_count}")

    console.print("\n[bold]Next steps:[/bold]")
    console.print("  1. Query memories:  dmm query \"your task\"")
    console.print("  2. Check status:    dmm status")
    console.print("  3. Read guidelines: cat .dmm/BOOT.md")


def _create_boot_md(path: Path) -> None:
    """Create default BOOT.md file."""
    content = '''# DMM Boot Instructions

**Read this file at the start of every session.**

## Core Principle

You have access to a semantic memory system. Query it before making assumptions.

## Essential Commands
```bash
# Get relevant context for your task
dmm query "your task description" --budget 1500

# Check system status
dmm status

# Quick memory creation
dmm remember "important information to save"
```

## Memory Scopes

- **baseline**: Always loaded (identity, hard constraints)
- **project**: Project-specific decisions and patterns
- **agent**: Your behavioral rules
- **ephemeral**: Temporary findings (may expire)

## Rules

1. **Query before assuming** - Check memory for existing decisions
2. **Write when learning** - Capture important discoveries
3. **Respect constraints** - Baseline memories are non-negotiable
4. **Flag conflicts** - Report contradictory memories, do not resolve silently

## Token Budget

Default budget is 1500 tokens. Baseline uses ~800 tokens automatically.
Remaining budget is filled with relevant memories.
'''
    path.write_text(content)


def _create_policy_md(path: Path) -> None:
    """Create default policy.md file."""
    content = '''# DMM Policies

## Write Policy

- Memories must be 300-800 tokens
- One concept per memory file
- Include rationale for decisions
- Use clear, descriptive titles

## Retrieval Policy

- Baseline is always included
- Query returns most relevant memories within budget
- Higher priority memories are preferred

## Conflict Policy

- Contradictions must be flagged
- Do not silently choose between conflicting memories
- Escalate to human for resolution
'''
    path.write_text(content)


def _create_daemon_config(path: Path) -> None:
    """Create default daemon.config.json file."""
    import json
    
    config = {
        "daemon": {
            "host": DEFAULT_HOST,
            "port": DEFAULT_PORT,
        },
        "indexer": {
            "watch_interval_ms": 1000,
            "embedding_model": "all-MiniLM-L6-v2",
        },
        "retrieval": {
            "top_k_directories": 3,
            "max_candidates": 50,
            "default_budget": 2000,
        },
        "validation": {
            "min_tokens": 300,
            "max_tokens": 800,
        },
        "reviewer": {
            "duplicate_threshold": 0.92,
            "auto_approve_threshold": 0.95,
        },
        "conflicts": {
            "semantic_similarity_threshold": 0.80,
            "periodic_scan_interval_hours": 24,
        },
    }
    
    path.write_text(json.dumps(config, indent=2))
