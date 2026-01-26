"""
Quick remember command for DMM.

Provides a fast way to create memories without the full proposal workflow.
Automatically generates proper frontmatter and validates content.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel

from dmm.cli.utils.daemon_manager import ensure_daemon_running
from dmm.core.constants import DEFAULT_HOST, DEFAULT_PORT, Scope

console = Console()
err_console = Console(stderr=True)


def _generate_memory_id() -> str:
    """Generate a unique memory ID based on timestamp."""
    now = datetime.now()
    date_part = now.strftime("%Y_%m_%d")
    
    # Use time-based sequence for uniqueness within the day
    time_seq = int(now.strftime("%H%M%S")) % 1000
    return f"mem_{date_part}_{time_seq:03d}"


def _extract_title(content: str) -> str:
    """Extract or generate a title from content."""
    # Check for markdown header
    header_match = re.match(r'^#\s+(.+)$', content, re.MULTILINE)
    if header_match:
        return header_match.group(1).strip()
    
    # Use first line or truncate
    first_line = content.split('\n')[0].strip()
    if len(first_line) <= 60:
        return first_line
    return first_line[:57] + "..."


def _extract_tags(content: str, title: str) -> list[str]:
    """Extract tags from content using simple keyword analysis."""
    # Combine title and content for analysis
    text = f"{title} {content}".lower()
    
    # Common technical keywords to detect
    keyword_tags = {
        "api": ["api", "endpoint", "rest", "graphql"],
        "database": ["database", "sql", "query", "schema", "table"],
        "authentication": ["auth", "login", "password", "token", "jwt"],
        "testing": ["test", "spec", "unittest", "pytest"],
        "configuration": ["config", "setting", "environment", "env"],
        "deployment": ["deploy", "docker", "kubernetes", "ci/cd"],
        "security": ["security", "vulnerability", "encryption"],
        "performance": ["performance", "optimization", "cache", "speed"],
        "error-handling": ["error", "exception", "catch", "handling"],
        "architecture": ["architecture", "design", "pattern", "structure"],
        "documentation": ["documentation", "readme", "docs"],
        "refactoring": ["refactor", "cleanup", "improvement"],
    }
    
    tags = []
    for tag, keywords in keyword_tags.items():
        if any(kw in text for kw in keywords):
            tags.append(tag)
    
    # Limit to 5 tags
    if not tags:
        tags = ["note"]
    
    return tags[:5]


def _sanitize_filename(title: str) -> str:
    """Convert title to valid filename."""
    # Remove special characters, replace spaces with underscores
    filename = re.sub(r'[^\w\s-]', '', title.lower())
    filename = re.sub(r'[\s-]+', '_', filename)
    filename = filename.strip('_')
    
    # Limit length
    if len(filename) > 50:
        filename = filename[:50].rstrip('_')
    
    return filename or "memory"


def _count_tokens(text: str) -> int:
    """Estimate token count (rough approximation)."""
    # Simple approximation: ~4 characters per token for English
    return len(text) // 4


def remember_command(
    content: Annotated[
        str,
        typer.Argument(help="Memory content or text to remember"),
    ],
    scope: Annotated[
        str,
        typer.Option("--scope", "-s", help="Memory scope"),
    ] = "project",
    category: Annotated[
        Optional[str],
        typer.Option("--category", "-c", help="Category subdirectory"),
    ] = None,
    title: Annotated[
        Optional[str],
        typer.Option("--title", "-t", help="Memory title (auto-generated if not provided)"),
    ] = None,
    tags: Annotated[
        Optional[str],
        typer.Option("--tags", help="Comma-separated tags"),
    ] = None,
    priority: Annotated[
        float,
        typer.Option("--priority", "-p", help="Priority (0.0-1.0)"),
    ] = 0.6,
    confidence: Annotated[
        str,
        typer.Option("--confidence", help="Confidence level"),
    ] = "active",
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
        typer.Option("--dry-run", help="Preview without creating file"),
    ] = False,
    no_daemon: Annotated[
        bool,
        typer.Option("--no-daemon", help="Skip daemon check"),
    ] = False,
) -> None:
    """
    Quickly create a memory from text.

    This is a streamlined alternative to the full write proposal workflow.
    The memory is created directly without review.

    Examples:
        dmm remember "We use Redis for caching with 15-minute TTL"
        dmm remember "API versioning uses /v1/ prefix" --scope project --category decisions
        dmm remember "Always validate user input" --tags "security,validation" --priority 0.8
    """
    # Validate scope
    valid_scopes = ["baseline", "global", "agent", "project", "ephemeral"]
    if scope not in valid_scopes:
        err_console.print(f"[red]Invalid scope: {scope}[/red]")
        err_console.print(f"Valid scopes: {', '.join(valid_scopes)}")
        raise typer.Exit(1)

    # Validate confidence
    valid_confidences = ["experimental", "active", "stable"]
    if confidence not in valid_confidences:
        err_console.print(f"[red]Invalid confidence: {confidence}[/red]")
        err_console.print(f"Valid values: {', '.join(valid_confidences)}")
        raise typer.Exit(1)

    # Validate priority
    if not 0.0 <= priority <= 1.0:
        err_console.print("[red]Priority must be between 0.0 and 1.0[/red]")
        raise typer.Exit(1)

    # Baseline requires extra confirmation
    if scope == "baseline":
        err_console.print("[yellow]Warning: baseline scope requires human review[/yellow]")
        err_console.print("Consider using 'dmm write propose' for baseline memories")
        if not typer.confirm("Continue with baseline scope?"):
            raise typer.Exit(0)

    # Ensure daemon is running for reindexing
    if not no_daemon:
        if not ensure_daemon_running(host=host, port=port, quiet=True):
            err_console.print("[yellow]Warning: Daemon not running. Memory will be indexed on next daemon start.[/yellow]")

    # Generate or use provided title
    memory_title = title or _extract_title(content)

    # Generate or parse tags
    if tags:
        memory_tags = [t.strip() for t in tags.split(",")]
    else:
        memory_tags = _extract_tags(content, memory_title)

    # Generate memory ID
    memory_id = _generate_memory_id()

    # Build frontmatter
    today = datetime.now().strftime("%Y-%m-%d")
    frontmatter = f'''---
id: {memory_id}
tags: [{", ".join(memory_tags)}]
scope: {scope}
priority: {priority}
confidence: {confidence}
status: active
created: {today}
last_used: {today}
usage_count: 0
---'''

    # Build full content
    # Add title as H1 if not already present
    if not content.strip().startswith('#'):
        full_content = f"{frontmatter}\n\n# {memory_title}\n\n{content}"
    else:
        full_content = f"{frontmatter}\n\n{content}"

    # Check token count
    token_count = _count_tokens(full_content)
    if token_count < 300:
        err_console.print(f"[yellow]Warning: Content is short ({token_count} estimated tokens, minimum 300)[/yellow]")
    elif token_count > 800:
        err_console.print(f"[yellow]Warning: Content is long ({token_count} estimated tokens, maximum 800)[/yellow]")
        err_console.print("Consider splitting into multiple memories")

    # Determine file path
    from dmm.core.constants import get_memory_root
    
    memory_root = get_memory_root()
    if category:
        file_dir = memory_root / scope / category
    else:
        file_dir = memory_root / scope

    filename = f"{_sanitize_filename(memory_title)}.md"
    file_path = file_dir / filename

    # Handle existing file
    if file_path.exists():
        # Add sequence number
        base_name = _sanitize_filename(memory_title)
        seq = 1
        while file_path.exists():
            filename = f"{base_name}_{seq:02d}.md"
            file_path = file_dir / filename
            seq += 1

    if dry_run:
        console.print(Panel(
            f"[bold]Dry Run - Memory Preview[/bold]\n\n"
            f"[cyan]Path:[/cyan] {file_path}\n"
            f"[cyan]Tokens:[/cyan] ~{token_count}\n\n"
            f"[dim]{'-' * 40}[/dim]\n"
            f"{full_content}",
            expand=False,
        ))
        return

    # Create directory if needed
    file_dir.mkdir(parents=True, exist_ok=True)

    # Write file
    file_path.write_text(full_content)

    console.print(f"[green]Memory created:[/green] {file_path}")
    console.print(f"  ID: {memory_id}")
    console.print(f"  Scope: {scope}")
    console.print(f"  Tags: {', '.join(memory_tags)}")
    console.print(f"  Tokens: ~{token_count}")

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
