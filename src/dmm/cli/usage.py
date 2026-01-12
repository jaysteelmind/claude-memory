"""CLI commands for usage tracking operations."""

from datetime import datetime, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from dmm.writeback.usage import UsageTracker

app = typer.Typer(help="Usage tracking and analytics")
console = Console()


def get_tracker(base_path: Path | None = None) -> UsageTracker:
    """Get usage tracker."""
    base = base_path or Path.cwd()
    tracker = UsageTracker(base)
    tracker.initialize()
    return tracker


@app.command("stats")
def show_stats(
    days: int = typer.Option(30, "--days", "-d", help="Number of days to include"),
) -> None:
    """Show usage statistics."""
    tracker = get_tracker()
    
    stats = tracker.get_stats(days)
    
    console.print(Panel(
        f"[cyan]Period:[/cyan] {stats.period_start.strftime('%Y-%m-%d')} to {stats.period_end.strftime('%Y-%m-%d')}\n\n"
        f"[cyan]Total Queries:[/cyan] {stats.total_queries}\n"
        f"[cyan]Avg Query Time:[/cyan] {stats.avg_query_time_ms:.1f}ms\n"
        f"[cyan]Avg Tokens/Query:[/cyan] {stats.avg_tokens_per_query:.0f}\n\n"
        f"[cyan]Total Retrievals:[/cyan] {stats.total_memories_retrieved}\n"
        f"[cyan]Unique Memories:[/cyan] {stats.unique_memories_retrieved}",
        title="Usage Statistics",
    ))
    
    if stats.most_retrieved:
        console.print("\n[cyan]Most Retrieved Memories:[/cyan]")
        for memory_id, count in stats.most_retrieved[:5]:
            console.print(f"  {memory_id}: {count} times")
    
    if stats.least_retrieved:
        console.print("\n[cyan]Least Retrieved Memories:[/cyan]")
        for memory_id, count in stats.least_retrieved[:5]:
            console.print(f"  {memory_id}: {count} times")


@app.command("top")
def show_top(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of results"),
) -> None:
    """Show most frequently retrieved memories."""
    tracker = get_tracker()
    
    records = tracker.get_most_retrieved(limit)
    
    if not records:
        console.print("[yellow]No usage data found[/yellow]")
        return
    
    table = Table(title="Most Retrieved Memories")
    table.add_column("Memory ID", style="cyan")
    table.add_column("Path", style="blue")
    table.add_column("Total", justify="right")
    table.add_column("Baseline", justify="right")
    table.add_column("Query", justify="right")
    table.add_column("Last Used")
    
    for r in records:
        table.add_row(
            r.memory_id[:20] + ("..." if len(r.memory_id) > 20 else ""),
            r.memory_path[:25] + ("..." if len(r.memory_path) > 25 else ""),
            str(r.total_retrievals),
            str(r.baseline_retrievals),
            str(r.query_retrievals),
            r.last_used.strftime("%Y-%m-%d") if r.last_used else "-",
        )
    
    console.print(table)


@app.command("stale")
def show_stale(
    days: int = typer.Option(30, "--days", "-d", help="Days threshold for staleness"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of results"),
) -> None:
    """Show memories that haven't been retrieved recently."""
    tracker = get_tracker()
    
    records = tracker.get_stale_memories(days, limit)
    
    if not records:
        console.print(f"[green]No stale memories found (threshold: {days} days)[/green]")
        return
    
    table = Table(title=f"Stale Memories (not used in {days} days)")
    table.add_column("Memory ID", style="cyan")
    table.add_column("Path", style="blue")
    table.add_column("Total Uses", justify="right")
    table.add_column("Last Used")
    
    for r in records:
        table.add_row(
            r.memory_id[:20] + ("..." if len(r.memory_id) > 20 else ""),
            r.memory_path[:30] + ("..." if len(r.memory_path) > 30 else ""),
            str(r.total_retrievals),
            r.last_used.strftime("%Y-%m-%d") if r.last_used else "Never",
        )
    
    console.print(table)


@app.command("memory")
def show_memory_usage(
    memory_id: str = typer.Argument(..., help="Memory ID to check"),
) -> None:
    """Show usage details for a specific memory."""
    tracker = get_tracker()
    
    record = tracker.get_memory_usage(memory_id)
    
    if not record:
        console.print(f"[yellow]No usage data for memory: {memory_id}[/yellow]")
        return
    
    console.print(Panel(
        f"[cyan]Memory ID:[/cyan] {record.memory_id}\n"
        f"[cyan]Path:[/cyan] {record.memory_path}\n\n"
        f"[cyan]Total Retrievals:[/cyan] {record.total_retrievals}\n"
        f"[cyan]Baseline Retrievals:[/cyan] {record.baseline_retrievals}\n"
        f"[cyan]Query Retrievals:[/cyan] {record.query_retrievals}\n\n"
        f"[cyan]First Used:[/cyan] {record.first_used.strftime('%Y-%m-%d %H:%M') if record.first_used else 'Never'}\n"
        f"[cyan]Last Used:[/cyan] {record.last_used.strftime('%Y-%m-%d %H:%M') if record.last_used else 'Never'}",
        title=f"Usage: {memory_id}",
    ))
    
    if record.co_occurred_with:
        console.print("\n[cyan]Frequently Co-occurs With:[/cyan]")
        sorted_co = sorted(record.co_occurred_with.items(), key=lambda x: x[1], reverse=True)
        for other_id, count in sorted_co[:5]:
            console.print(f"  {other_id}: {count} times")


@app.command("health")
def show_health(
    stale_days: int = typer.Option(30, "--stale-days", help="Days threshold for staleness"),
    hot_count: int = typer.Option(10, "--hot-count", help="Retrieval count for hot memories"),
) -> None:
    """Generate a health report for memory usage."""
    tracker = get_tracker()
    
    report = tracker.generate_health_report(stale_days, hot_count)
    
    console.print(Panel(
        f"[cyan]Generated:[/cyan] {report.generated_at.strftime('%Y-%m-%d %H:%M')}\n\n"
        f"[cyan]Stale Memories:[/cyan] {len(report.stale_memories)} (>{stale_days} days unused)\n"
        f"[cyan]Hot Memories:[/cyan] {len(report.hot_memories)} (>={hot_count} retrievals)\n"
        f"[cyan]Deprecation Candidates:[/cyan] {len(report.deprecation_candidates)}",
        title="Memory Health Report",
    ))
    
    if report.hot_memories:
        console.print("\n[green]Hot Memories (frequently used):[/green]")
        for m in report.hot_memories[:5]:
            console.print(f"  - {m.get('memory_id', 'unknown')}: {m.get('total_retrievals', 0)} uses")
    
    if report.deprecation_candidates:
        console.print("\n[yellow]Deprecation Candidates (rarely used):[/yellow]")
        for m in report.deprecation_candidates[:5]:
            console.print(f"  - {m.get('memory_id', 'unknown')}: {m.get('total_retrievals', 0)} uses")


@app.command("cleanup")
def cleanup_logs(
    days: int = typer.Option(90, "--days", "-d", help="Delete logs older than this many days"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Clean up old query logs."""
    tracker = get_tracker()
    
    if not confirm:
        console.print(f"[yellow]This will delete query logs older than {days} days.[/yellow]")
        response = typer.confirm("Continue?")
        if not response:
            console.print("Aborted.")
            raise typer.Exit(0)
    
    deleted = tracker.clear_old_logs(days)
    console.print(f"[green]Deleted {deleted} old log entries[/green]")
