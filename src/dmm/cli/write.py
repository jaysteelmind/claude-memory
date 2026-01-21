"""CLI commands for write operations."""

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from dmm.core.constants import get_memory_root
from dmm.core.exceptions import ProposalError
from dmm.indexer.embedder import MemoryEmbedder
from dmm.indexer.store import MemoryStore
from dmm.models.proposal import ProposalStatus, ProposalType
from dmm.writeback.proposal import ProposalHandler
from dmm.writeback.queue import ReviewQueue

app = typer.Typer(help="Write operations for memory management")
console = Console()


def get_components(base_path: Path | None = None):
    """Get write components."""
    base = base_path or Path.cwd()
    
    from dmm.core.constants import get_embeddings_db_path
    from dmm.indexer.embedder import MemoryEmbedder
    
    queue = ReviewQueue(base)
    queue.initialize()
    
    store = MemoryStore(get_embeddings_db_path(base))
    store.initialize()
    
    embedder = MemoryEmbedder()
    
    handler = ProposalHandler(queue, store, base)
    
    return handler, queue, base, store, embedder


@app.command("propose")
def propose_create(
    path: str = typer.Argument(..., help="Target path relative to memory root (e.g., project/my_memory.md)"),
    content_file: Path = typer.Option(None, "--file", "-f", help="File containing memory content"),
    reason: str = typer.Option(..., "--reason", "-r", help="Reason for creating this memory"),
    proposed_by: str = typer.Option("cli", "--by", help="Proposer identifier"),
    auto_commit: bool = typer.Option(True, "--auto-commit/--no-auto-commit", help="Auto-approve and commit (default: True)"),
) -> None:
    """Propose a new memory creation. Auto-commits by default."""
    handler, queue, base, store, embedder = get_components()
    
    if content_file:
        if not content_file.exists():
            console.print(f"[red]Error:[/red] File not found: {content_file}")
            raise typer.Exit(1)
        content = content_file.read_text(encoding="utf-8")
    else:
        console.print("[yellow]Enter memory content (Ctrl+D to finish):[/yellow]")
        content = sys.stdin.read()
    
    if not content.strip():
        console.print("[red]Error:[/red] No content provided")
        raise typer.Exit(1)
    
    try:
        proposal = handler.propose_create(
            target_path=path,
            content=content,
            reason=reason,
            proposed_by=proposed_by,
        )
        
        console.print(Panel(
            f"[green]Proposal created successfully[/green]\n\n"
            f"ID: {proposal.proposal_id}\n"
            f"Type: {proposal.type.value}\n"
            f"Path: {proposal.target_path}\n"
            f"Status: {proposal.status.value}",
            title="Write Proposal",
        ))
        
        if auto_commit:
            from dmm.models.proposal import ProposalStatus
            from dmm.writeback.commit import CommitEngine
            from dmm.indexer.indexer import Indexer
            from dmm.core.config import DMMConfig
            
            # Update status in database
            queue.update_status(
                proposal.proposal_id,
                ProposalStatus.APPROVED,
                notes="Auto-approved"
            )
            
            # Update the proposal object's status so commit() accepts it
            proposal.status = ProposalStatus.APPROVED
            
            config = DMMConfig.load(base)
            indexer = Indexer(config, base)
            commit_engine = CommitEngine(queue, indexer, base)
            
            try:
                result = commit_engine.commit(proposal)
                if result.success:
                    console.print(f"[green]Memory committed:[/green] {result.memory_path}")
                else:
                    console.print(f"[yellow]Warning: Commit failed:[/yellow] {result.error}")
            except Exception as e:
                console.print(f"[yellow]Warning: Auto-commit failed:[/yellow] {e}")
                console.print("Use 'dmm review approve <id>' to commit manually")
        
    except ProposalError as e:
        console.print(f"[red]Error:[/red] {e.message}")
        if e.details:
            for key, value in e.details.items():
                console.print(f"  {key}: {value}")
        raise typer.Exit(1)


@app.command("update")
def propose_update(
    memory_id: str = typer.Argument(..., help="ID of the memory to update"),
    content_file: Path = typer.Option(None, "--file", "-f", help="File containing new content"),
    reason: str = typer.Option(..., "--reason", "-r", help="Reason for the update"),
    proposed_by: str = typer.Option("cli", "--by", help="Proposer identifier"),
) -> None:
    """Propose an update to an existing memory."""
    handler, queue, base, store, embedder = get_components()
    
    if content_file:
        if not content_file.exists():
            console.print(f"[red]Error:[/red] File not found: {content_file}")
            raise typer.Exit(1)
        content = content_file.read_text(encoding="utf-8")
    else:
        console.print("[yellow]Enter new content (Ctrl+D to finish):[/yellow]")
        content = sys.stdin.read()
    
    if not content.strip():
        console.print("[red]Error:[/red] No content provided")
        raise typer.Exit(1)
    
    try:
        proposal = handler.propose_update(
            memory_id=memory_id,
            content=content,
            reason=reason,
            proposed_by=proposed_by,
        )
        
        console.print(Panel(
            f"[green]Update proposal created successfully[/green]\n\n"
            f"ID: {proposal.proposal_id}\n"
            f"Memory: {proposal.memory_id}\n"
            f"Path: {proposal.target_path}\n"
            f"Status: {proposal.status.value}",
            title="Update Proposal",
        ))
        
    except ProposalError as e:
        console.print(f"[red]Error:[/red] {e.message}")
        raise typer.Exit(1)


@app.command("deprecate")
def propose_deprecate(
    memory_id: str = typer.Argument(..., help="ID of the memory to deprecate"),
    reason: str = typer.Option(..., "--reason", "-r", help="Reason for deprecation"),
    proposed_by: str = typer.Option("cli", "--by", help="Proposer identifier"),
) -> None:
    """Propose deprecation of a memory."""
    handler, queue, base, store, embedder = get_components()
    
    try:
        proposal = handler.propose_deprecate(
            memory_id=memory_id,
            reason=reason,
            proposed_by=proposed_by,
        )
        
        console.print(Panel(
            f"[green]Deprecation proposal created successfully[/green]\n\n"
            f"ID: {proposal.proposal_id}\n"
            f"Memory: {proposal.memory_id}\n"
            f"Reason: {proposal.deprecation_reason}\n"
            f"Status: {proposal.status.value}",
            title="Deprecation Proposal",
        ))
        
    except ProposalError as e:
        console.print(f"[red]Error:[/red] {e.message}")
        raise typer.Exit(1)


@app.command("promote")
def propose_promote(
    memory_id: str = typer.Argument(..., help="ID of the memory to promote"),
    new_scope: str = typer.Option(..., "--scope", "-s", help="New scope (global, project, etc.)"),
    reason: str = typer.Option(..., "--reason", "-r", help="Reason for promotion"),
    proposed_by: str = typer.Option("cli", "--by", help="Proposer identifier"),
) -> None:
    """Propose promoting a memory to a different scope."""
    handler, queue, base, store, embedder = get_components()
    
    try:
        proposal = handler.propose_promote(
            memory_id=memory_id,
            new_scope=new_scope,
            reason=reason,
            proposed_by=proposed_by,
        )
        
        console.print(Panel(
            f"[green]Promotion proposal created successfully[/green]\n\n"
            f"ID: {proposal.proposal_id}\n"
            f"Memory: {proposal.memory_id}\n"
            f"From: {proposal.source_scope}\n"
            f"To: {proposal.new_scope}\n"
            f"Status: {proposal.status.value}",
            title="Promotion Proposal",
        ))
        
    except ProposalError as e:
        console.print(f"[red]Error:[/red] {e.message}")
        raise typer.Exit(1)


@app.command("list")
def list_proposals(
    status: str = typer.Option(None, "--status", "-s", help="Filter by status"),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum number to show"),
) -> None:
    """List write proposals."""
    _, queue, _ = get_components()
    
    if status:
        try:
            proposal_status = ProposalStatus(status)
            proposals = queue.get_by_status(proposal_status, limit)
        except ValueError:
            console.print(f"[red]Error:[/red] Invalid status: {status}")
            console.print(f"Valid statuses: {', '.join(s.value for s in ProposalStatus)}")
            raise typer.Exit(1)
    else:
        proposals = queue.get_pending(limit)
    
    if not proposals:
        console.print("[yellow]No proposals found[/yellow]")
        return
    
    table = Table(title="Write Proposals")
    table.add_column("ID", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Path", style="blue")
    table.add_column("Status", style="yellow")
    table.add_column("Created")
    
    for p in proposals:
        table.add_row(
            p.proposal_id[:20] + "...",
            p.type.value,
            p.target_path[:30] + ("..." if len(p.target_path) > 30 else ""),
            p.status.value,
            p.created_at.strftime("%Y-%m-%d %H:%M"),
        )
    
    console.print(table)


@app.command("show")
def show_proposal(
    proposal_id: str = typer.Argument(..., help="Proposal ID to show"),
) -> None:
    """Show details of a specific proposal."""
    _, queue, _ = get_components()
    
    proposal = queue.get(proposal_id)
    if not proposal:
        console.print(f"[red]Error:[/red] Proposal not found: {proposal_id}")
        raise typer.Exit(1)
    
    console.print(Panel(
        f"[cyan]ID:[/cyan] {proposal.proposal_id}\n"
        f"[cyan]Type:[/cyan] {proposal.type.value}\n"
        f"[cyan]Path:[/cyan] {proposal.target_path}\n"
        f"[cyan]Status:[/cyan] {proposal.status.value}\n"
        f"[cyan]Reason:[/cyan] {proposal.reason}\n"
        f"[cyan]Proposed By:[/cyan] {proposal.proposed_by}\n"
        f"[cyan]Created:[/cyan] {proposal.created_at}\n"
        f"[cyan]Reviewed:[/cyan] {proposal.reviewed_at or 'Not yet'}\n"
        f"[cyan]Notes:[/cyan] {proposal.reviewer_notes or 'None'}",
        title=f"Proposal: {proposal.proposal_id}",
    ))
    
    if proposal.content:
        console.print("\n[cyan]Content Preview:[/cyan]")
        preview = proposal.content[:500]
        if len(proposal.content) > 500:
            preview += "\n... (truncated)"
        console.print(preview)


@app.command("cancel")
def cancel_proposal(
    proposal_id: str = typer.Argument(..., help="Proposal ID to cancel"),
) -> None:
    """Cancel a pending proposal."""
    handler, queue, base, store, embedder = get_components()
    
    if handler.cancel_proposal(proposal_id):
        console.print(f"[green]Proposal {proposal_id} cancelled[/green]")
    else:
        console.print(f"[red]Error:[/red] Could not cancel proposal (not found or not cancellable)")
        raise typer.Exit(1)


@app.command("stats")
def show_stats() -> None:
    """Show write proposal statistics."""
    _, queue, _ = get_components()
    
    stats = queue.get_stats()
    
    console.print(Panel(
        f"[cyan]Total Proposals:[/cyan] {stats.get('total', 0)}\n\n"
        f"[cyan]By Status:[/cyan]\n" +
        "\n".join(f"  {k}: {v}" for k, v in stats.get('by_status', {}).items()) +
        f"\n\n[cyan]By Type:[/cyan]\n" +
        "\n".join(f"  {k}: {v}" for k, v in stats.get('by_type', {}).items()),
        title="Proposal Statistics",
    ))
