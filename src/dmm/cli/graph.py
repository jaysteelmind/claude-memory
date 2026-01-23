"""CLI commands for knowledge graph operations.

This module provides the `dmm graph` command group with subcommands for:
- status: Show graph statistics
- migrate: Migrate existing memories to graph
- show: Display a memory with its relationships
- related: Find memories related to a given memory
- contradictions: List all contradicting memory pairs
- path: Find shortest path between two memories
- query: Execute raw Cypher queries
"""

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from dmm.core.constants import get_knowledge_graph_path, get_embeddings_db_path
from dmm.graph.store import KnowledgeGraphStore
from dmm.graph.migration import GraphMigration
from dmm.graph.queries import (
    find_related_memories_weighted,
    compute_memory_centrality,
    get_scope_summary,
)

app = typer.Typer(
    name="graph",
    help="Knowledge graph operations for memory relationships.",
    no_args_is_help=True,
)
console = Console()


def get_graph_store(base_path: Optional[Path] = None) -> KnowledgeGraphStore:
    """Get an initialized graph store.

    Args:
        base_path: Optional project base path.

    Returns:
        Initialized KnowledgeGraphStore instance.
    """
    base = base_path or Path.cwd()
    store = KnowledgeGraphStore(get_knowledge_graph_path(base))
    store.initialize()
    return store


@app.command("status")
def graph_status(
    base_path: Annotated[
        Optional[Path],
        typer.Option("--path", "-p", help="Project base path"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
) -> None:
    """Show knowledge graph status and statistics."""
    store = get_graph_store(base_path)

    try:
        stats = store.get_stats()

        if json_output:
            import json
            output = {
                "memory_count": stats.memory_count,
                "tag_count": stats.tag_count,
                "scope_count": stats.scope_count,
                "concept_count": stats.concept_count,
                "edge_count": stats.edge_count,
                "relationship_counts": stats.relationship_counts,
            }
            console.print(json.dumps(output, indent=2))
            return

        # Node counts table
        table = Table(title="Knowledge Graph Status")
        table.add_column("Node Type", style="cyan")
        table.add_column("Count", style="green", justify="right")

        table.add_row("Memory Nodes", str(stats.memory_count))
        table.add_row("Tag Nodes", str(stats.tag_count))
        table.add_row("Scope Nodes", str(stats.scope_count))
        table.add_row("Concept Nodes", str(stats.concept_count))
        table.add_row("Total Edges", str(stats.edge_count))

        console.print(table)

        # Relationship counts table
        if stats.relationship_counts:
            rel_table = Table(title="Relationships by Type")
            rel_table.add_column("Type", style="cyan")
            rel_table.add_column("Count", style="green", justify="right")

            for rel_type, count in sorted(stats.relationship_counts.items()):
                rel_table.add_row(rel_type, str(count))

            console.print(rel_table)

        # Scope summary
        scope_summary = get_scope_summary(store)
        if scope_summary:
            scope_table = Table(title="Scope Summary")
            scope_table.add_column("Scope", style="cyan")
            scope_table.add_column("Memories", justify="right")
            scope_table.add_column("Tokens", justify="right")

            for scope in scope_summary:
                scope_table.add_row(
                    scope["name"],
                    str(scope["memory_count"]),
                    str(scope["token_total"]),
                )

            console.print(scope_table)

    finally:
        store.close()


@app.command("migrate")
def migrate_to_graph(
    base_path: Annotated[
        Optional[Path],
        typer.Option("--path", "-p", help="Project base path"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Force re-migration even if data exists"),
    ] = False,
) -> None:
    """Migrate existing memories to the knowledge graph."""
    base = base_path or Path.cwd()

    graph_path = get_knowledge_graph_path(base)
    embeddings_path = get_embeddings_db_path(base)

    # Check if embeddings database exists
    if not embeddings_path.exists():
        console.print(
            f"[red]Embeddings database not found at {embeddings_path}[/red]"
        )
        console.print("Run 'dmm reindex' first to index your memories.")
        raise typer.Exit(1)

    graph_store = KnowledgeGraphStore(graph_path)
    graph_store.initialize()

    try:
        # Check if already migrated
        stats = graph_store.get_stats()
        if stats.memory_count > 0 and not force:
            console.print(
                f"[yellow]Graph already contains {stats.memory_count} memories.[/yellow]"
            )
            console.print("Use --force to re-migrate.")
            return

        console.print("Migrating memories to knowledge graph...")

        # Import memory store
        from dmm.indexer.store import MemoryStore

        memory_store = MemoryStore(embeddings_path)
        memory_store.initialize()

        try:
            migration = GraphMigration(graph_store, memory_store)

            # Progress callback
            def on_progress(step: str, current: int, total: int) -> None:
                if total > 0:
                    console.print(f"  {step}: {current}/{total}", end="\r")

            result = migration.migrate(progress_callback=on_progress)
            console.print()  # Clear progress line

            # Display results
            console.print(Panel(
                f"[green]Migration complete![/green]\n\n"
                f"Memories: {result.memories}\n"
                f"Tags: {result.tags}\n"
                f"Scopes: {result.scopes}\n"
                f"HAS_TAG edges: {result.has_tag_edges}\n"
                f"IN_SCOPE edges: {result.in_scope_edges}\n"
                f"RELATES_TO edges: {result.relates_to_edges}\n"
                f"SUPERSEDES edges: {result.supersedes_edges}\n"
                f"TAG_COOCCURS edges: {result.tag_cooccurs_edges}\n"
                f"Duration: {result.duration_ms}ms",
                title="Migration Results",
            ))

            if result.errors:
                console.print("[yellow]Warnings/Errors:[/yellow]")
                for error in result.errors[:10]:  # Show first 10
                    console.print(f"  - {error}")
                if len(result.errors) > 10:
                    console.print(f"  ... and {len(result.errors) - 10} more")

        finally:
            memory_store.close()

    finally:
        graph_store.close()


@app.command("show")
def show_memory_graph(
    memory_id: Annotated[
        str,
        typer.Argument(help="Memory ID to display"),
    ],
    depth: Annotated[
        int,
        typer.Option("--depth", "-d", help="Relationship traversal depth"),
    ] = 1,
    base_path: Annotated[
        Optional[Path],
        typer.Option("--path", "-p", help="Project base path"),
    ] = None,
) -> None:
    """Show a memory and its graph relationships."""
    store = get_graph_store(base_path)

    try:
        memory = store.get_memory_node(memory_id)
        if not memory:
            console.print(f"[red]Memory not found: {memory_id}[/red]")
            raise typer.Exit(1)

        # Build tree visualization
        tree = Tree(f"[bold cyan]{memory.title}[/bold cyan] ({memory_id})")

        # Memory properties
        props_branch = tree.add("[dim]Properties[/dim]")
        props_branch.add(f"Path: {memory.path}")
        props_branch.add(f"Scope: {memory.scope}")
        props_branch.add(f"Priority: {memory.priority}")
        props_branch.add(f"Confidence: {memory.confidence}")
        props_branch.add(f"Status: {memory.status}")
        props_branch.add(f"Tokens: {memory.token_count}")

        # Outgoing relationships
        outgoing = store.get_edges_from(memory_id)
        memory_outgoing = [
            e for e in outgoing
            if e["type"] in ("RELATES_TO", "SUPERSEDES", "CONTRADICTS", "SUPPORTS", "DEPENDS_ON")
        ]
        if memory_outgoing:
            out_branch = tree.add("[yellow]Outgoing Relationships[/yellow]")
            for edge in memory_outgoing:
                weight_str = f" ({edge.get('weight', '')})" if edge.get("weight") else ""
                out_branch.add(f"--[{edge['type']}]--> {edge['to_id']}{weight_str}")

        # Incoming relationships
        incoming = store.get_edges_to(memory_id)
        memory_incoming = [
            e for e in incoming
            if e["type"] in ("RELATES_TO", "SUPERSEDES", "CONTRADICTS", "SUPPORTS", "DEPENDS_ON")
        ]
        if memory_incoming:
            in_branch = tree.add("[yellow]Incoming Relationships[/yellow]")
            for edge in memory_incoming:
                weight_str = f" ({edge.get('weight', '')})" if edge.get("weight") else ""
                in_branch.add(f"<--[{edge['type']}]-- {edge['from_id']}{weight_str}")

        # Tags
        tags = store.get_tags_for_memory(memory_id)
        if tags:
            tag_branch = tree.add("[green]Tags[/green]")
            for tag in tags:
                tag_branch.add(tag.name)

        # Centrality metrics
        centrality = compute_memory_centrality(store, memory_id)
        metrics_branch = tree.add("[dim]Centrality[/dim]")
        metrics_branch.add(f"Degree: {centrality['degree']}")
        metrics_branch.add(f"In-degree: {centrality['in_degree']}")
        metrics_branch.add(f"Out-degree: {centrality['out_degree']}")

        console.print(tree)

    finally:
        store.close()


@app.command("related")
def find_related(
    memory_id: Annotated[
        str,
        typer.Argument(help="Memory ID to find relationships for"),
    ],
    depth: Annotated[
        int,
        typer.Option("--depth", "-d", help="Maximum traversal depth"),
    ] = 2,
    edge_type: Annotated[
        Optional[str],
        typer.Option("--type", "-t", help="Filter by edge type"),
    ] = None,
    min_weight: Annotated[
        float,
        typer.Option("--min-weight", "-w", help="Minimum relationship weight"),
    ] = 0.0,
    base_path: Annotated[
        Optional[Path],
        typer.Option("--path", "-p", help="Project base path"),
    ] = None,
) -> None:
    """Find memories related to a given memory."""
    store = get_graph_store(base_path)

    try:
        # Check if memory exists
        memory = store.get_memory_node(memory_id)
        if not memory:
            console.print(f"[red]Memory not found: {memory_id}[/red]")
            raise typer.Exit(1)

        related = find_related_memories_weighted(
            store,
            memory_id,
            max_depth=depth,
            min_weight=min_weight,
        )

        # Filter by edge type if specified
        if edge_type:
            related = [r for r in related if r.relationship_type == edge_type.upper()]

        if not related:
            console.print("[yellow]No related memories found[/yellow]")
            return

        table = Table(title=f"Memories Related to {memory_id}")
        table.add_column("ID", style="cyan")
        table.add_column("Title")
        table.add_column("Type", style="yellow")
        table.add_column("Weight", justify="right")
        table.add_column("Depth", justify="right")

        for result in related:
            title = result.memory.title
            if len(title) > 40:
                title = title[:37] + "..."
            table.add_row(
                result.memory.id,
                title,
                result.relationship_type,
                f"{result.weight:.2f}",
                str(result.path_length),
            )

        console.print(table)

    finally:
        store.close()


@app.command("contradictions")
def list_contradictions(
    base_path: Annotated[
        Optional[Path],
        typer.Option("--path", "-p", help="Project base path"),
    ] = None,
) -> None:
    """List all contradicting memory pairs."""
    store = get_graph_store(base_path)

    try:
        pairs = store.get_contradiction_pairs()

        if not pairs:
            console.print("[green]No contradictions found[/green]")
            return

        table = Table(title="Contradicting Memories")
        table.add_column("Memory 1", style="cyan")
        table.add_column("Memory 2", style="cyan")
        table.add_column("Description")

        for m1, m2, description in pairs:
            table.add_row(
                m1.id,
                m2.id,
                description[:50] + "..." if len(description) > 50 else description,
            )

        console.print(table)
        console.print(f"\n[yellow]Total: {len(pairs)} contradictions[/yellow]")

    finally:
        store.close()


@app.command("path")
def find_path(
    from_id: Annotated[
        str,
        typer.Argument(help="Source memory ID"),
    ],
    to_id: Annotated[
        str,
        typer.Argument(help="Target memory ID"),
    ],
    max_depth: Annotated[
        int,
        typer.Option("--max-depth", "-d", help="Maximum path length"),
    ] = 5,
    base_path: Annotated[
        Optional[Path],
        typer.Option("--path", "-p", help="Project base path"),
    ] = None,
) -> None:
    """Find shortest path between two memories."""
    store = get_graph_store(base_path)

    try:
        # Verify both memories exist
        from_memory = store.get_memory_node(from_id)
        if not from_memory:
            console.print(f"[red]Source memory not found: {from_id}[/red]")
            raise typer.Exit(1)

        to_memory = store.get_memory_node(to_id)
        if not to_memory:
            console.print(f"[red]Target memory not found: {to_id}[/red]")
            raise typer.Exit(1)

        path = store.find_path(from_id, to_id, max_depth)

        if not path:
            console.print(
                f"[yellow]No path found between {from_id} and {to_id} "
                f"within {max_depth} hops[/yellow]"
            )
            return

        console.print(f"[green]Path found ({len(path) - 1} hops):[/green]")
        console.print()

        for i, node_id in enumerate(path):
            memory = store.get_memory_node(node_id)
            title = memory.title if memory else "Unknown"

            if i == 0:
                prefix = "[bold cyan]START[/bold cyan] "
            elif i == len(path) - 1:
                prefix = "  " * i + "[bold green]END[/bold green]   "
            else:
                prefix = "  " * i + "      "

            connector = " --> " if i < len(path) - 1 else ""
            console.print(f"{prefix}{node_id}: {title}{connector}")

    finally:
        store.close()


@app.command("query")
def execute_query(
    cypher: Annotated[
        str,
        typer.Argument(help="Cypher query to execute"),
    ],
    base_path: Annotated[
        Optional[Path],
        typer.Option("--path", "-p", help="Project base path"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum rows to display"),
    ] = 100,
) -> None:
    """Execute a raw Cypher query against the knowledge graph."""
    store = get_graph_store(base_path)

    try:
        results = store.execute_cypher(cypher)

        if not results:
            console.print("[yellow]No results[/yellow]")
            return

        # Limit results
        display_results = results[:limit]

        # Create table with dynamic columns
        table = Table(title=f"Query Results ({len(results)} rows)")

        # Get columns from first result
        if display_results:
            columns = list(display_results[0].keys())
            for col in columns:
                table.add_column(col, style="cyan")

            for row in display_results:
                values = []
                for col in columns:
                    val = row.get(col, "")
                    val_str = str(val) if val is not None else ""
                    if len(val_str) > 50:
                        val_str = val_str[:47] + "..."
                    values.append(val_str)
                table.add_row(*values)

        console.print(table)

        if len(results) > limit:
            console.print(f"\n[dim]Showing {limit} of {len(results)} results[/dim]")

    except Exception as e:
        console.print(f"[red]Query error: {e}[/red]")
        raise typer.Exit(1)

    finally:
        store.close()


@app.command("tags")
def list_tags(
    base_path: Annotated[
        Optional[Path],
        typer.Option("--path", "-p", help="Project base path"),
    ] = None,
    min_usage: Annotated[
        int,
        typer.Option("--min-usage", "-m", help="Minimum usage count to show"),
    ] = 0,
) -> None:
    """List all tags in the knowledge graph."""
    store = get_graph_store(base_path)

    try:
        tags = store.get_all_tag_nodes()

        # Filter by minimum usage
        tags = [t for t in tags if t.usage_count >= min_usage]

        if not tags:
            console.print("[yellow]No tags found[/yellow]")
            return

        # Sort by usage count descending
        tags.sort(key=lambda t: t.usage_count, reverse=True)

        table = Table(title="Tags in Knowledge Graph")
        table.add_column("Tag", style="cyan")
        table.add_column("Usage Count", justify="right")

        for tag in tags:
            table.add_row(tag.name, str(tag.usage_count))

        console.print(table)
        console.print(f"\n[dim]Total: {len(tags)} tags[/dim]")

    finally:
        store.close()
