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


# =============================================================================
# Phase 5.2: Advanced Knowledge Graph Commands
# =============================================================================


@app.command("extract")
def extract_relationships(
    base_path: Annotated[
        Optional[Path],
        typer.Option("--path", "-p", help="Project base path"),
    ] = None,
    memory_id: Annotated[
        Optional[str],
        typer.Option("--memory", "-m", help="Extract for specific memory ID"),
    ] = None,
    extractors: Annotated[
        Optional[str],
        typer.Option("--extractors", "-e", help="Comma-separated extractors: tag,semantic,temporal,llm"),
    ] = "tag,temporal",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be extracted without saving"),
    ] = False,
    min_weight: Annotated[
        float,
        typer.Option("--min-weight", "-w", help="Minimum edge weight to keep"),
    ] = 0.3,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
) -> None:
    """Extract relationships between memories using configured extractors.
    
    Extractors available:
    - tag: Find relationships based on shared tags
    - semantic: Find relationships based on embedding similarity
    - temporal: Find version chains and temporal proximity
    - llm: Use LLM for deep semantic analysis (requires API)
    
    Examples:
        dmm graph extract                    # Extract with defaults (tag, temporal)
        dmm graph extract -e tag,semantic    # Use tag and semantic extractors
        dmm graph extract -m mem_123 -n      # Dry run for specific memory
    """
    from dmm.graph.extractors import (
        ExtractionOrchestrator,
        OrchestratorConfig,
        TagExtractionConfig,
        SemanticExtractionConfig,
        TemporalExtractionConfig,
    )
    
    store = get_graph_store(base_path)
    
    try:
        # Parse extractor list
        enabled = set(e.strip().lower() for e in extractors.split(","))
        
        config = OrchestratorConfig(
            enable_tag_extraction="tag" in enabled,
            enable_semantic_extraction="semantic" in enabled,
            enable_temporal_extraction="temporal" in enabled,
            enable_llm_extraction="llm" in enabled,
            min_edge_weight=min_weight,
            tag_config=TagExtractionConfig(min_overlap_count=2),
            semantic_config=SemanticExtractionConfig(relates_threshold=0.75),
            temporal_config=TemporalExtractionConfig(proximity_days=7),
        )
        
        orchestrator = ExtractionOrchestrator(config)
        
        # Get memories to process
        memories = store.get_all_memory_nodes()
        
        if not memories:
            console.print("[yellow]No memories found in graph[/yellow]")
            return
        
        if memory_id:
            memories = [m for m in memories if m.id == memory_id]
            if not memories:
                console.print(f"[red]Memory not found: {memory_id}[/red]")
                raise typer.Exit(1)
        
        total_edges = 0
        all_results = []
        
        with console.status("[bold green]Extracting relationships...") as status:
            for i, memory in enumerate(memories):
                status.update(f"[bold green]Processing {i+1}/{len(memories)}: {memory.id[:20]}...")
                
                result = orchestrator.extract(memory, memories)
                all_results.append(result)
                total_edges += result.final_count
                
                if not dry_run:
                    # Save edges to graph
                    for edge in result.edges:
                        try:
                            store.create_edge(
                                edge.edge_type,
                                edge.from_id,
                                edge.to_id,
                                edge.to_cypher_params(),
                            )
                        except Exception as e:
                            console.print(f"[yellow]Failed to create edge: {e}[/yellow]")
        
        if json_output:
            import json
            output = {
                "memories_processed": len(memories),
                "total_edges_extracted": total_edges,
                "dry_run": dry_run,
                "extractors_used": list(enabled),
                "results": [r.to_dict() for r in all_results],
            }
            console.print(json.dumps(output, indent=2))
            return
        
        # Summary table
        table = Table(title="Extraction Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")
        
        table.add_row("Memories Processed", str(len(memories)))
        table.add_row("Total Edges Extracted", str(total_edges))
        table.add_row("Extractors Used", ", ".join(sorted(enabled)))
        table.add_row("Min Weight Threshold", f"{min_weight:.2f}")
        table.add_row("Dry Run", "Yes" if dry_run else "No")
        
        console.print(table)
        
        if dry_run:
            console.print("\n[yellow]Dry run - no edges were saved[/yellow]")
        else:
            console.print(f"\n[green]✓ Extracted and saved {total_edges} edges[/green]")
        
    finally:
        store.close()


@app.command("infer")
def infer_relationships(
    base_path: Annotated[
        Optional[Path],
        typer.Option("--path", "-p", help="Project base path"),
    ] = None,
    mode: Annotated[
        str,
        typer.Option("--mode", "-m", help="Inference mode: transitive, clusters, gaps, all"),
    ] = "all",
    apply: Annotated[
        bool,
        typer.Option("--apply", "-a", help="Apply inferred edges to graph"),
    ] = False,
    min_confidence: Annotated[
        float,
        typer.Option("--min-confidence", "-c", help="Minimum confidence for inferred edges"),
    ] = 0.5,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
) -> None:
    """Run inference to discover implicit relationships.
    
    Modes:
    - transitive: Find transitive relationships (A->B->C implies A->C)
    - clusters: Detect clusters of related memories
    - gaps: Find potential missing relationships
    - all: Run all inference modes
    
    Examples:
        dmm graph infer                      # Run all inference
        dmm graph infer -m transitive -a     # Find and apply transitive edges
        dmm graph infer -m clusters          # Detect memory clusters
    """
    from dmm.graph.inference import (
        TransitiveInferenceEngine,
        TransitiveConfig,
        ClusterDetector,
        ClusterConfig,
    )
    
    store = get_graph_store(base_path)
    
    try:
        modes = set(mode.lower().split(","))
        if "all" in modes:
            modes = {"transitive", "clusters", "gaps"}
        
        results = {}
        
        # Transitive inference
        if "transitive" in modes:
            with console.status("[bold green]Running transitive inference..."):
                config = TransitiveConfig(
                    min_confidence=min_confidence,
                    max_path_length=3,
                )
                engine = TransitiveInferenceEngine(store, config)
                trans_result = engine.infer_all()
                results["transitive"] = trans_result
                
                if apply and trans_result.inferred_edges:
                    applied, skipped = engine.apply_inferred_edges(
                        trans_result.inferred_edges,
                        min_confidence=min_confidence,
                    )
                    results["transitive_applied"] = applied
                    results["transitive_skipped"] = skipped
        
        # Cluster detection
        if "clusters" in modes or "gaps" in modes:
            with console.status("[bold green]Detecting clusters..."):
                config = ClusterConfig(
                    min_cluster_size=3,
                    detect_knowledge_gaps="gaps" in modes,
                )
                detector = ClusterDetector(store, config)
                cluster_result = detector.detect_clusters()
                results["clusters"] = cluster_result
        
        if json_output:
            import json
            output = {
                "modes": list(modes),
                "apply": apply,
                "min_confidence": min_confidence,
            }
            if "transitive" in results:
                output["transitive"] = results["transitive"].to_dict()
                if "transitive_applied" in results:
                    output["transitive_applied"] = results["transitive_applied"]
            if "clusters" in results:
                output["clusters"] = results["clusters"].to_dict()
            console.print(json.dumps(output, indent=2))
            return
        
        # Display results
        if "transitive" in results:
            trans = results["transitive"]
            table = Table(title="Transitive Inference Results")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green", justify="right")
            
            table.add_row("Nodes Processed", str(trans.nodes_processed))
            table.add_row("Paths Evaluated", str(trans.paths_evaluated))
            table.add_row("Edges Inferred", str(trans.total_inferred))
            table.add_row("Skipped (existing)", str(trans.skipped_existing))
            table.add_row("Skipped (low conf)", str(trans.skipped_low_confidence))
            table.add_row("Duration (ms)", f"{trans.duration_ms:.1f}")
            
            if trans.edges_by_type:
                for edge_type, count in trans.edges_by_type.items():
                    table.add_row(f"  {edge_type}", str(count))
            
            console.print(table)
            
            if apply and "transitive_applied" in results:
                console.print(f"\n[green]✓ Applied {results['transitive_applied']} inferred edges[/green]")
        
        if "clusters" in results:
            cluster_res = results["clusters"]
            
            table = Table(title="Cluster Detection Results")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green", justify="right")
            
            table.add_row("Total Memories", str(cluster_res.total_memories))
            table.add_row("Clusters Found", str(cluster_res.cluster_count))
            table.add_row("Clustered Memories", str(cluster_res.clustered_memories))
            table.add_row("Singletons", str(cluster_res.singleton_count))
            table.add_row("Largest Cluster", str(cluster_res.largest_cluster_size))
            table.add_row("Avg Cluster Size", f"{cluster_res.avg_cluster_size:.1f}")
            
            console.print(table)
            
            # Show top clusters
            if cluster_res.clusters:
                cluster_table = Table(title="Top Clusters")
                cluster_table.add_column("Cluster", style="cyan")
                cluster_table.add_column("Size", justify="right")
                cluster_table.add_column("Density", justify="right")
                cluster_table.add_column("Common Tags")
                
                for cluster in cluster_res.clusters[:5]:
                    cluster_table.add_row(
                        cluster.cluster_id,
                        str(cluster.size),
                        f"{cluster.density:.2f}",
                        ", ".join(cluster.common_tags[:3]) or "-",
                    )
                
                console.print(cluster_table)
            
            # Show knowledge gaps
            if cluster_res.knowledge_gaps:
                gap_table = Table(title="Knowledge Gaps (Potential Missing Relationships)")
                gap_table.add_column("Memory 1", style="cyan")
                gap_table.add_column("Memory 2", style="cyan")
                gap_table.add_column("Similarity", justify="right")
                gap_table.add_column("Shared Tags")
                
                for gap in cluster_res.knowledge_gaps[:10]:
                    gap_table.add_row(
                        gap.memory_id_1[:20],
                        gap.memory_id_2[:20],
                        f"{gap.similarity_score:.2f}",
                        ", ".join(gap.shared_tags[:3]),
                    )
                
                console.print(gap_table)
        
    finally:
        store.close()


@app.command("viz")
def visualize_graph(
    base_path: Annotated[
        Optional[Path],
        typer.Option("--path", "-p", help="Project base path"),
    ] = None,
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output file path"),
    ] = Path("graph.html"),
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: html, json, dot, mermaid"),
    ] = "html",
    scope: Annotated[
        Optional[str],
        typer.Option("--scope", "-s", help="Filter by scope(s), comma-separated"),
    ] = None,
    edge_types: Annotated[
        Optional[str],
        typer.Option("--edges", "-e", help="Filter by edge type(s), comma-separated"),
    ] = None,
    include_clusters: Annotated[
        bool,
        typer.Option("--clusters", "-c", help="Highlight detected clusters"),
    ] = False,
) -> None:
    """Generate a visualization of the knowledge graph.
    
    Formats:
    - html: Interactive D3.js force-directed graph (default)
    - json: Raw graph data for custom tools
    - dot: Graphviz DOT format for static diagrams
    - mermaid: Mermaid syntax for documentation
    
    Examples:
        dmm graph viz                        # Generate HTML visualization
        dmm graph viz -f mermaid -o graph.md # Generate Mermaid diagram
        dmm graph viz -s global,project      # Only show specific scopes
        dmm graph viz -c                     # Highlight clusters
    """
    from dmm.graph.visualization import GraphRenderer, RenderConfig
    from dmm.graph.inference import ClusterDetector, ClusterConfig
    
    store = get_graph_store(base_path)
    
    try:
        # Parse filters
        scope_filter = tuple(s.strip() for s in scope.split(",")) if scope else None
        edge_filter = tuple(e.strip().upper() for e in edge_types.split(",")) if edge_types else None
        
        config = RenderConfig(
            output_format=format.lower(),
            filter_scopes=scope_filter,
            filter_edge_types=edge_filter,
            highlight_clusters=include_clusters,
            include_edge_labels=True,
            include_weights=True,
            color_by_scope=True,
            color_edges_by_type=True,
        )
        
        renderer = GraphRenderer(store, config)
        
        # Get clusters if requested
        if include_clusters:
            with console.status("[bold green]Detecting clusters..."):
                cluster_config = ClusterConfig(min_cluster_size=2)
                detector = ClusterDetector(store, cluster_config)
                cluster_result = detector.detect_clusters()
                renderer.set_clusters(cluster_result.clusters)
        
        with console.status(f"[bold green]Generating {format} visualization..."):
            result = renderer.render()
        
        # Save to file
        result.save(str(output))
        
        console.print(f"\n[green]✓ Visualization saved to {output}[/green]")
        console.print(f"  Nodes: {result.node_count}")
        console.print(f"  Edges: {result.edge_count}")
        console.print(f"  Format: {result.format}")
        
        if result.warnings:
            for warning in result.warnings:
                console.print(f"  [yellow]Warning: {warning}[/yellow]")
        
        # Hint for HTML
        if format.lower() == "html":
            console.print(f"\n[dim]Open {output} in a browser to view the interactive graph[/dim]")
        
    finally:
        store.close()


@app.command("extract-stats")
def extraction_stats(
    base_path: Annotated[
        Optional[Path],
        typer.Option("--path", "-p", help="Project base path"),
    ] = None,
) -> None:
    """Show statistics about extracted relationships."""
    store = get_graph_store(base_path)
    
    try:
        stats = store.get_stats()
        
        table = Table(title="Relationship Extraction Statistics")
        table.add_column("Relationship Type", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_column("Description")
        
        descriptions = {
            "RELATES_TO": "General topical relationship",
            "SUPPORTS": "Evidence/reinforcement relationship",
            "CONTRADICTS": "Conflicting information",
            "DEPENDS_ON": "Prerequisite knowledge",
            "SUPERSEDES": "Version replacement",
            "HAS_TAG": "Memory-to-tag relationship",
            "IN_SCOPE": "Memory-to-scope relationship",
        }
        
        for rel_type, count in sorted(stats.relationship_counts.items()):
            desc = descriptions.get(rel_type, "")
            table.add_row(rel_type, str(count), desc)
        
        console.print(table)
        
        # Summary
        semantic_rels = sum(
            count for rel_type, count in stats.relationship_counts.items()
            if rel_type in {"RELATES_TO", "SUPPORTS", "CONTRADICTS", "DEPENDS_ON", "SUPERSEDES"}
        )
        console.print(f"\n[dim]Semantic relationships: {semantic_rels}[/dim]")
        
    finally:
        store.close()
