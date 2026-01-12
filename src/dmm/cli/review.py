"""CLI commands for review operations."""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from dmm.core.constants import get_embeddings_db_path
from dmm.core.exceptions import ReviewError, CommitError
from dmm.indexer.embedder import MemoryEmbedder
from dmm.indexer.store import MemoryStore
from dmm.models.proposal import ProposalStatus, ReviewDecision
from dmm.reviewer.agent import ReviewerAgent
from dmm.writeback.queue import ReviewQueue

app = typer.Typer(help="Review operations for write proposals")
console = Console()


def get_components(base_path: Path | None = None):
    """Get review components."""
    base = base_path or Path.cwd()
    
    queue = ReviewQueue(base)
    queue.initialize()
    
    store = MemoryStore(get_embeddings_db_path(base))
    store.initialize()
    
    embedder = MemoryEmbedder()
    
    reviewer = ReviewerAgent(queue, store, embedder, base)
    
    return reviewer, queue, store, embedder


@app.command("list")
def list_pending(
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum number to show"),
) -> None:
    """List proposals pending review."""
    _, queue, _, _ = get_components()
    
    proposals = queue.get_pending(limit)
    
    if not proposals:
        console.print("[yellow]No pending proposals[/yellow]")
        return
    
    table = Table(title="Pending Reviews")
    table.add_column("ID", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Path", style="blue")
    table.add_column("Reason")
    table.add_column("Created")
    
    for p in proposals:
        table.add_row(
            p.proposal_id[:20] + "...",
            p.type.value,
            p.target_path[:25] + ("..." if len(p.target_path) > 25 else ""),
            p.reason[:30] + ("..." if len(p.reason) > 30 else ""),
            p.created_at.strftime("%Y-%m-%d %H:%M"),
        )
    
    console.print(table)


@app.command("process")
def process_proposal(
    proposal_id: str = typer.Argument(..., help="Proposal ID to review"),
    auto_commit: bool = typer.Option(False, "--commit", "-c", help="Auto-commit if approved"),
) -> None:
    """Review and optionally commit a specific proposal."""
    reviewer, queue, store, embedder = get_components()
    
    proposal = queue.get(proposal_id)
    if not proposal:
        console.print(f"[red]Error:[/red] Proposal not found: {proposal_id}")
        raise typer.Exit(1)
    
    if proposal.status != ProposalStatus.PENDING:
        console.print(f"[yellow]Warning:[/yellow] Proposal status is '{proposal.status.value}', not 'pending'")
    
    console.print(f"[cyan]Reviewing proposal {proposal_id}...[/cyan]")
    
    try:
        result = reviewer.review(proposal)
        
        decision_color = {
            ReviewDecision.APPROVE: "green",
            ReviewDecision.REJECT: "red",
            ReviewDecision.MODIFY: "yellow",
            ReviewDecision.DEFER: "blue",
        }.get(result.decision, "white")
        
        console.print(Panel(
            f"[{decision_color}]Decision: {result.decision.value.upper()}[/{decision_color}]\n"
            f"Confidence: {result.confidence:.1%}\n\n"
            f"Schema Valid: {'Yes' if result.schema_valid else 'No'}\n"
            f"Quality Valid: {'Yes' if result.quality_valid else 'No'}\n"
            f"Duplicate Check: {'Passed' if result.duplicate_check_passed else 'Failed'}\n\n"
            f"Notes: {result.notes or 'None'}",
            title="Review Result",
        ))
        
        if result.issues:
            console.print("\n[cyan]Issues Found:[/cyan]")
            for issue in result.issues:
                severity_color = {
                    "error": "red",
                    "warning": "yellow",
                    "info": "blue",
                }.get(issue.severity, "white")
                console.print(f"  [{severity_color}][{issue.severity.upper()}][/{severity_color}] {issue.message}")
                if issue.suggestion:
                    console.print(f"    Suggestion: {issue.suggestion}")
        
        if result.duplicates:
            console.print("\n[cyan]Duplicate Matches:[/cyan]")
            for dup in result.duplicates[:5]:
                console.print(f"  - {dup.memory_path} ({dup.similarity:.1%} {dup.match_type})")
        
        if auto_commit and result.decision == ReviewDecision.APPROVE:
            console.print("\n[cyan]Committing approved proposal...[/cyan]")
            _commit_proposal(proposal_id)
        
    except ReviewError as e:
        console.print(f"[red]Review Error:[/red] {e.message}")
        raise typer.Exit(1)


@app.command("batch")
def batch_review(
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum proposals to review"),
    auto_commit: bool = typer.Option(False, "--commit", "-c", help="Auto-commit approved proposals"),
) -> None:
    """Review multiple pending proposals."""
    reviewer, queue, _, _ = get_components()
    
    pending = queue.get_pending(limit)
    
    if not pending:
        console.print("[yellow]No pending proposals to review[/yellow]")
        return
    
    console.print(f"[cyan]Reviewing {len(pending)} proposal(s)...[/cyan]\n")
    
    results = {
        "approved": 0,
        "rejected": 0,
        "deferred": 0,
        "modified": 0,
        "errors": 0,
    }
    
    for proposal in pending:
        try:
            result = reviewer.review(proposal)
            
            decision_color = {
                ReviewDecision.APPROVE: "green",
                ReviewDecision.REJECT: "red",
                ReviewDecision.MODIFY: "yellow",
                ReviewDecision.DEFER: "blue",
            }.get(result.decision, "white")
            
            console.print(
                f"  [{decision_color}]{result.decision.value.upper()}[/{decision_color}] "
                f"{proposal.proposal_id[:20]}... - {proposal.target_path}"
            )
            
            if result.decision == ReviewDecision.APPROVE:
                results["approved"] += 1
                if auto_commit:
                    try:
                        _commit_proposal(proposal.proposal_id, quiet=True)
                        console.print(f"    [green]Committed[/green]")
                    except Exception as e:
                        console.print(f"    [red]Commit failed: {e}[/red]")
            elif result.decision == ReviewDecision.REJECT:
                results["rejected"] += 1
            elif result.decision == ReviewDecision.DEFER:
                results["deferred"] += 1
            elif result.decision == ReviewDecision.MODIFY:
                results["modified"] += 1
                
        except ReviewError as e:
            console.print(f"  [red]ERROR[/red] {proposal.proposal_id[:20]}... - {e.message}")
            results["errors"] += 1
    
    console.print(Panel(
        f"[green]Approved:[/green] {results['approved']}\n"
        f"[red]Rejected:[/red] {results['rejected']}\n"
        f"[blue]Deferred:[/blue] {results['deferred']}\n"
        f"[yellow]Modified:[/yellow] {results['modified']}\n"
        f"[red]Errors:[/red] {results['errors']}",
        title="Batch Review Summary",
    ))


@app.command("commit")
def commit_approved(
    proposal_id: str = typer.Argument(..., help="Proposal ID to commit"),
) -> None:
    """Commit an approved proposal."""
    _commit_proposal(proposal_id)


def _commit_proposal(proposal_id: str, quiet: bool = False) -> None:
    """Internal function to commit a proposal."""
    from dmm.indexer.indexer import Indexer
    from dmm.core.config import DMMConfig
    from dmm.writeback.commit import CommitEngine
    
    base = Path.cwd()
    
    queue = ReviewQueue(base)
    queue.initialize()
    
    proposal = queue.get(proposal_id)
    if not proposal:
        if not quiet:
            console.print(f"[red]Error:[/red] Proposal not found: {proposal_id}")
        raise typer.Exit(1)
    
    if proposal.status not in (ProposalStatus.APPROVED, ProposalStatus.MODIFIED):
        if not quiet:
            console.print(f"[red]Error:[/red] Proposal status is '{proposal.status.value}', must be 'approved' or 'modified'")
        raise typer.Exit(1)
    
    config = DMMConfig.load(base)
    indexer = Indexer(config, base)
    
    commit_engine = CommitEngine(queue, indexer, base)
    
    try:
        result = commit_engine.commit(proposal)
        
        if result.success:
            if not quiet:
                console.print(Panel(
                    f"[green]Commit successful[/green]\n\n"
                    f"Memory ID: {result.memory_id}\n"
                    f"Path: {result.memory_path}\n"
                    f"Commit time: {result.commit_duration_ms:.1f}ms\n"
                    f"Reindex time: {result.reindex_duration_ms:.1f}ms",
                    title="Commit Result",
                ))
        else:
            if not quiet:
                console.print(f"[red]Commit failed:[/red] {result.error}")
                if result.rollback_performed:
                    status = "successful" if result.rollback_success else "failed"
                    console.print(f"  Rollback: {status}")
            raise typer.Exit(1)
            
    except CommitError as e:
        if not quiet:
            console.print(f"[red]Commit Error:[/red] {e.message}")
        raise typer.Exit(1)


@app.command("approve")
def manual_approve(
    proposal_id: str = typer.Argument(..., help="Proposal ID to approve"),
    notes: str = typer.Option("", "--notes", "-n", help="Approval notes"),
    commit: bool = typer.Option(False, "--commit", "-c", help="Also commit after approval"),
) -> None:
    """Manually approve a proposal (for deferred proposals)."""
    _, queue, _, _ = get_components()
    
    proposal = queue.get(proposal_id)
    if not proposal:
        console.print(f"[red]Error:[/red] Proposal not found: {proposal_id}")
        raise typer.Exit(1)
    
    if proposal.status not in (ProposalStatus.PENDING, ProposalStatus.DEFERRED):
        console.print(f"[red]Error:[/red] Can only approve pending or deferred proposals")
        raise typer.Exit(1)
    
    queue.update_status(
        proposal_id,
        ProposalStatus.APPROVED,
        notes=notes or "Manually approved",
    )
    
    console.print(f"[green]Proposal {proposal_id} approved[/green]")
    
    if commit:
        _commit_proposal(proposal_id)


@app.command("reject")
def manual_reject(
    proposal_id: str = typer.Argument(..., help="Proposal ID to reject"),
    reason: str = typer.Option(..., "--reason", "-r", help="Rejection reason"),
) -> None:
    """Manually reject a proposal."""
    _, queue, _, _ = get_components()
    
    proposal = queue.get(proposal_id)
    if not proposal:
        console.print(f"[red]Error:[/red] Proposal not found: {proposal_id}")
        raise typer.Exit(1)
    
    if proposal.status not in (ProposalStatus.PENDING, ProposalStatus.DEFERRED, ProposalStatus.IN_REVIEW):
        console.print(f"[red]Error:[/red] Cannot reject proposal with status '{proposal.status.value}'")
        raise typer.Exit(1)
    
    queue.update_status(
        proposal_id,
        ProposalStatus.REJECTED,
        notes=reason,
    )
    
    console.print(f"[green]Proposal {proposal_id} rejected[/green]")


@app.command("history")
def show_history(
    proposal_id: str = typer.Argument(..., help="Proposal ID"),
) -> None:
    """Show review history for a proposal."""
    _, queue, _, _ = get_components()
    
    proposal = queue.get(proposal_id)
    if not proposal:
        console.print(f"[red]Error:[/red] Proposal not found: {proposal_id}")
        raise typer.Exit(1)
    
    history = queue.get_history(proposal_id)
    
    if not history:
        console.print("[yellow]No history found[/yellow]")
        return
    
    table = Table(title=f"History for {proposal_id[:20]}...")
    table.add_column("Time", style="cyan")
    table.add_column("Action", style="green")
    table.add_column("From")
    table.add_column("To")
    table.add_column("Notes")
    
    for entry in history:
        table.add_row(
            entry.get("timestamp", "")[:19],
            entry.get("action", ""),
            entry.get("from_status") or "-",
            entry.get("to_status") or "-",
            (entry.get("notes") or "")[:30],
        )
    
    console.print(table)
