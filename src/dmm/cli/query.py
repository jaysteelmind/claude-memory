"""CLI command for querying memory."""

from pathlib import Path
from typing import Annotated, Optional

import httpx
import typer
from rich.console import Console
from rich.panel import Panel

from dmm.core.constants import (
    DEFAULT_BASELINE_BUDGET,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_TOTAL_BUDGET,
    Scope,
)

console = Console()
err_console = Console(stderr=True)


def query_command(
    query: Annotated[str, typer.Argument(help="Task or question to query for")],
    budget: Annotated[
        int, typer.Option("--budget", "-b", help="Total token budget")
    ] = DEFAULT_TOTAL_BUDGET,
    baseline_budget: Annotated[
        int, typer.Option("--baseline-budget", help="Baseline token budget")
    ] = DEFAULT_BASELINE_BUDGET,
    scope: Annotated[
        Optional[str], typer.Option("--scope", "-s", help="Filter by scope")
    ] = None,
    exclude_ephemeral: Annotated[
        bool, typer.Option("--exclude-ephemeral", help="Exclude ephemeral memories")
    ] = False,
    include_deprecated: Annotated[
        bool, typer.Option("--include-deprecated", help="Include deprecated memories")
    ] = False,
    output: Annotated[
        Optional[Path], typer.Option("--output", "-o", help="Save pack to file")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Include scores and stats")
    ] = False,
    host: Annotated[str, typer.Option("--host", help="Daemon host")] = DEFAULT_HOST,
    port: Annotated[int, typer.Option("--port", help="Daemon port")] = DEFAULT_PORT,
    raw: Annotated[
        bool, typer.Option("--raw", help="Output raw markdown without formatting")
    ] = False,
) -> None:
    """Query the memory system for relevant context."""
    # Validate scope if provided
    if scope:
        try:
            Scope(scope)
        except ValueError:
            valid_scopes = ", ".join(s.value for s in Scope)
            err_console.print(f"[red]Invalid scope: {scope}[/red]")
            err_console.print(f"Valid scopes: {valid_scopes}")
            raise typer.Exit(1)

    # Build request
    request_data = {
        "query": query,
        "budget": budget,
        "baseline_budget": baseline_budget,
        "scope_filter": scope,
        "exclude_ephemeral": exclude_ephemeral,
        "include_deprecated": include_deprecated,
        "verbose": verbose,
    }

    # Send request to daemon
    url = f"http://{host}:{port}/query"

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, json=request_data)
            response.raise_for_status()
            data = response.json()

    except httpx.ConnectError:
        err_console.print("[red]Error: Cannot connect to daemon[/red]")
        err_console.print(f"Is the daemon running? Try: dmm daemon start")
        raise typer.Exit(1)
    except httpx.HTTPStatusError as e:
        err_console.print(f"[red]Error: {e.response.status_code}[/red]")
        try:
            detail = e.response.json().get("detail", str(e))
            err_console.print(f"Detail: {detail}")
        except Exception:
            err_console.print(f"Detail: {e}")
        raise typer.Exit(1)
    except httpx.RequestError as e:
        err_console.print(f"[red]Request error: {e}[/red]")
        raise typer.Exit(1)

    # Handle response
    if not data.get("success", False):
        err_console.print(f"[red]Query failed: {data.get('error', 'Unknown error')}[/red]")
        raise typer.Exit(1)

    pack_markdown = data.get("pack_markdown", "")

    # Output
    if output:
        output.write_text(pack_markdown)
        console.print(f"[green]Pack saved to: {output}[/green]")
    elif raw:
        console.print(pack_markdown)
    else:
        console.print(Panel(pack_markdown, title="DMM Memory Pack", border_style="blue"))

    # Show stats if verbose
    if verbose:
        stats = data.get("stats", {})
        console.print()
        console.print("[bold]Query Statistics:[/bold]")
        console.print(f"  Query time: {stats.get('query_time_ms', 0):.1f}ms")
        console.print(f"  Embedding time: {stats.get('embedding_time_ms', 0):.1f}ms")
        console.print(f"  Retrieval time: {stats.get('retrieval_time_ms', 0):.1f}ms")
        console.print(f"  Assembly time: {stats.get('assembly_time_ms', 0):.1f}ms")
        console.print(f"  Directories searched: {stats.get('directories_searched', [])}")
        console.print(f"  Candidates considered: {stats.get('candidates_considered', 0)}")
        console.print(f"  Baseline files: {stats.get('baseline_files', 0)}")
        console.print(f"  Retrieved files: {stats.get('retrieved_files', 0)}")
        console.print(f"  Excluded files: {stats.get('excluded_files', 0)}")
