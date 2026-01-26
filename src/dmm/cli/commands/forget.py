"""
Quick forget command for DMM.

Provides a fast way to deprecate memories without the full proposal workflow.
Moves memory to deprecated scope and updates status.
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel

from dmm.cli.utils.daemon_manager import ensure_daemon_running
from dmm.core.constants import DEFAULT_HOST, DEFAULT_PORT

console = Console()
err_console = Console(stderr=True)


def _find_memory_by_id(memory_root: Path, memory_id: str) -> Optional[Path]:
    """Find a memory file by its ID."""
    scopes = ["baseline", "global", "agent", "project", "ephemeral"]
    
    for scope in scopes:
        scope_dir = memory_root / scope
        if not scope_dir.exists():
            continue
        
        # Search recursively in scope
        for md_file in scope_dir.rglob("*.md"):
            try:
                content = md_file.read_text()
                if f"id: {memory_id}" in content:
                    return md_file
            except Exception:
                continue
    
    return None


def _find_memory_by_path(memory_root: Path, path_hint: str) -> Optional[Path]:
    """Find a memory file by path or partial path."""
    # Try as absolute path
    path = Path(path_hint)
    if path.exists() and path.suffix == ".md":
        return path
    
    # Try relative to memory root
    relative_path = memory_root / path_hint
    if relative_path.exists():
        return relative_path
    
    # Try with .md extension
    if not path_hint.endswith(".md"):
        relative_path = memory_root / f"{path_hint}.md"
        if relative_path.exists():
            return relative_path
    
    # Search by filename
    filename = Path(path_hint).name
    if not filename.endswith(".md"):
        filename = f"{filename}.md"
    
    for md_file in memory_root.rglob(filename):
        return md_file
    
    return None


def _update_memory_status(file_path: Path) -> str:
    """Update memory frontmatter to deprecated status."""
    content = file_path.read_text()
    
    # Update status
    if "status: active" in content:
        content = content.replace("status: active", "status: deprecated")
    elif "status:" not in content:
        # Add status after confidence line
        content = content.replace(
            "confidence:",
            "confidence:",
        )
    
    # Add deprecated date
    today = datetime.now().strftime("%Y-%m-%d")
    if "deprecated_at:" not in content:
        # Insert after status line
        content = content.replace(
            "status: deprecated",
            f"status: deprecated\ndeprecated_at: {today}",
        )
    
    return content


def forget_command(
    identifier: Annotated[
        str,
        typer.Argument(help="Memory ID (mem_YYYY_MM_DD_NNN) or file path"),
    ],
    reason: Annotated[
        Optional[str],
        typer.Option("--reason", "-r", help="Reason for deprecation"),
    ] = None,
    hard_delete: Annotated[
        bool,
        typer.Option("--hard-delete", help="Permanently delete instead of deprecating"),
    ] = False,
    host: Annotated[
        str,
        typer.Option("--host", help="Daemon host"),
    ] = DEFAULT_HOST,
    port: Annotated[
        int,
        typer.Option("--port", help="Daemon port"),
    ] = DEFAULT_PORT,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview without making changes"),
    ] = False,
    no_daemon: Annotated[
        bool,
        typer.Option("--no-daemon", help="Skip daemon check"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation"),
    ] = False,
) -> None:
    """
    Deprecate or delete a memory.

    By default, moves the memory to the deprecated scope.
    Use --hard-delete to permanently remove the file.

    Examples:
        dmm forget mem_2025_01_20_001
        dmm forget mem_2025_01_20_001 --reason "Superseded by new policy"
        dmm forget project/decisions/old_api.md
        dmm forget mem_2025_01_20_001 --hard-delete
    """
    from dmm.core.constants import get_memory_root
    
    memory_root = get_memory_root()

    # Find the memory file
    memory_path = None
    
    # Try as memory ID first
    if identifier.startswith("mem_"):
        memory_path = _find_memory_by_id(memory_root, identifier)
    
    # Try as path
    if memory_path is None:
        memory_path = _find_memory_by_path(memory_root, identifier)

    if memory_path is None:
        err_console.print(f"[red]Memory not found: {identifier}[/red]")
        err_console.print("\nSearch locations:")
        err_console.print(f"  - Memory root: {memory_root}")
        err_console.print("\nTry:")
        err_console.print("  dmm forget mem_YYYY_MM_DD_NNN")
        err_console.print("  dmm forget project/category/filename.md")
        raise typer.Exit(1)

    # Check if already deprecated
    if "deprecated" in str(memory_path):
        err_console.print(f"[yellow]Memory is already deprecated: {memory_path}[/yellow]")
        if not hard_delete:
            raise typer.Exit(0)

    # Check if baseline (requires extra confirmation)
    if "baseline" in str(memory_path):
        err_console.print("[yellow]Warning: This is a baseline memory[/yellow]")
        err_console.print("Baseline memories are critical and should rarely be deprecated.")
        if not force and not typer.confirm("Are you sure you want to deprecate this baseline memory?"):
            raise typer.Exit(0)

    # Preview
    console.print(Panel(
        f"[bold]Memory to {'delete' if hard_delete else 'deprecate'}:[/bold]\n\n"
        f"[cyan]Path:[/cyan] {memory_path}\n"
        f"[cyan]Action:[/cyan] {'Permanent deletion' if hard_delete else 'Move to deprecated'}",
        expand=False,
    ))

    if reason:
        console.print(f"[cyan]Reason:[/cyan] {reason}")

    if dry_run:
        console.print("\n[yellow]Dry run - no changes made[/yellow]")
        return

    # Confirm unless forced
    if not force:
        action = "permanently delete" if hard_delete else "deprecate"
        if not typer.confirm(f"\n{action.capitalize()} this memory?"):
            console.print("[dim]Cancelled[/dim]")
            raise typer.Exit(0)

    # Ensure daemon is running for reindexing
    if not no_daemon:
        if not ensure_daemon_running(host=host, port=port, quiet=True):
            err_console.print("[yellow]Warning: Daemon not running. Index will update on next daemon start.[/yellow]")

    if hard_delete:
        # Permanently delete
        memory_path.unlink()
        console.print(f"[green]Deleted:[/green] {memory_path}")
    else:
        # Move to deprecated
        deprecated_dir = memory_root / "deprecated"
        deprecated_dir.mkdir(parents=True, exist_ok=True)

        # Preserve relative path structure
        relative_to_scope = memory_path.relative_to(memory_root)
        scope_name = relative_to_scope.parts[0]
        rest_of_path = Path(*relative_to_scope.parts[1:]) if len(relative_to_scope.parts) > 1 else Path(relative_to_scope.name)

        # Create subdirectory in deprecated matching original scope
        dest_dir = deprecated_dir / scope_name
        if len(rest_of_path.parts) > 1:
            dest_dir = dest_dir / rest_of_path.parent
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest_path = dest_dir / memory_path.name

        # Handle name collision
        if dest_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            dest_path = dest_dir / f"{memory_path.stem}_{timestamp}{memory_path.suffix}"

        # Update content and move
        updated_content = _update_memory_status(memory_path)
        
        # Add deprecation reason if provided
        if reason:
            # Insert reason after deprecated_at
            if "deprecated_at:" in updated_content:
                updated_content = updated_content.replace(
                    "deprecated_at:",
                    f"deprecation_reason: \"{reason}\"\ndeprecated_at:",
                )

        # Write to new location
        dest_path.write_text(updated_content)
        
        # Remove original
        memory_path.unlink()

        console.print(f"[green]Deprecated:[/green] {memory_path.name}")
        console.print(f"[dim]Moved to: {dest_path}[/dim]")

    # Trigger reindex if daemon is running
    if not no_daemon:
        try:
            import httpx
            with httpx.Client(timeout=5.0) as client:
                response = client.post(f"http://{host}:{port}/reindex")
                if response.status_code == 200:
                    console.print("[dim]Reindex triggered[/dim]")
        except Exception:
            pass
