"""CLI commands for conflict detection and resolution."""

import json
import sys
from datetime import datetime
from typing import Optional

import typer

from dmm.core.constants import get_conflicts_db_path, get_embeddings_db_path


app = typer.Typer(
    name="conflicts",
    help="Conflict detection and resolution commands.",
    no_args_is_help=True,
)


def _get_components(base_path=None):
    """Initialize conflict detection components."""
    from pathlib import Path
    from dmm.conflicts.store import ConflictStore
    from dmm.conflicts.merger import ConflictMerger
    from dmm.conflicts.resolver import ConflictResolver
    from dmm.conflicts.detector import ConflictDetector, ConflictConfig
    from dmm.conflicts.scanner import ConflictScanner, ScanConfig
    from dmm.indexer.store import MemoryStore
    from dmm.indexer.embedder import MemoryEmbedder
    
    base = Path(base_path) if base_path else Path.cwd()
    
    memory_store = MemoryStore(get_embeddings_db_path(base))
    conflict_store = ConflictStore(base)
    conflict_store.initialize()
    
    embedder = MemoryEmbedder()
    merger = ConflictMerger(conflict_store)
    
    config = ConflictConfig()
    detector = ConflictDetector(
        memory_store=memory_store,
        conflict_store=conflict_store,
        embedder=embedder,
        merger=merger,
        config=config,
    )
    
    resolver = ConflictResolver(
        conflict_store=conflict_store,
        memory_store=memory_store,
    )
    
    scan_config = ScanConfig()
    scanner = ConflictScanner(detector, scan_config)
    
    return {
        "memory_store": memory_store,
        "conflict_store": conflict_store,
        "detector": detector,
        "resolver": resolver,
        "scanner": scanner,
        "merger": merger,
    }


@app.command("scan")
def scan_conflicts(
    full: bool = typer.Option(False, "--full", help="Run full scan (default is incremental)"),
    methods: Optional[str] = typer.Option(
        None, "--methods", help="Comma-separated methods: tag,semantic,supersession,rule"
    ),
    include_rule_extraction: bool = typer.Option(
        False, "--include-rule-extraction", help="Include LLM rule extraction (slower)"
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Run a conflict detection scan."""
    import asyncio
    from dmm.models.conflict import DetectionMethod
    
    components = _get_components()
    scanner = components["scanner"]
    
    method_list = None
    if methods:
        method_map = {
            "tag": DetectionMethod.TAG_OVERLAP,
            "semantic": DetectionMethod.SEMANTIC_SIMILARITY,
            "supersession": DetectionMethod.SUPERSESSION_CHAIN,
            "rule": DetectionMethod.RULE_EXTRACTION,
        }
        method_list = []
        for m in methods.split(","):
            m = m.strip().lower()
            if m in method_map:
                method_list.append(method_map[m])
    
    typer.echo("Scanning for conflicts...")
    
    result = asyncio.run(scanner.trigger_full_scan(
        methods=method_list,
        include_rule_extraction=include_rule_extraction,
    ))
    
    if output_json:
        typer.echo(json.dumps(result.to_dict(), indent=2))
    else:
        typer.echo("")
        typer.echo(f"Methods: {', '.join(result.methods_used)}")
        typer.echo(f"Memories scanned: {result.memories_scanned}")
        typer.echo("")
        typer.echo("Results:")
        typer.echo(f"  Scan completed in {result.duration_ms}ms")
        typer.echo("")
        typer.echo(f"  Conflicts detected: {result.conflicts_detected}")
        typer.echo(f"  - New: {result.conflicts_new}")
        typer.echo(f"  - Existing: {result.conflicts_existing}")
        
        if result.by_type:
            typer.echo("")
            typer.echo("  By type:")
            for ctype, count in result.by_type.items():
                typer.echo(f"  - {ctype}: {count}")
        
        if result.by_method:
            typer.echo("")
            typer.echo("  By method:")
            for method, count in result.by_method.items():
                typer.echo(f"  - {method}: {count}")
        
        if result.errors:
            typer.echo("")
            typer.echo("  Errors:")
            for err in result.errors:
                typer.echo(f"  - {err}")
        
        typer.echo("")
        typer.echo("Use 'dmm conflicts list' to view conflicts.")


@app.command("list")
def list_conflicts(
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status"),
    conflict_type: Optional[str] = typer.Option(None, "--type", help="Filter by type"),
    memory: Optional[str] = typer.Option(None, "--memory", help="Filter by memory ID"),
    min_confidence: float = typer.Option(0.0, "--min-confidence", help="Minimum confidence"),
    limit: int = typer.Option(50, "--limit", help="Maximum results"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List detected conflicts."""
    from dmm.models.conflict import ConflictStatus, ConflictType
    
    components = _get_components()
    store = components["conflict_store"]
    
    if memory:
        conflicts = store.get_by_memory(memory)
    elif status:
        try:
            status_enum = ConflictStatus(status)
            conflicts = store.get_by_status(status_enum, limit)
        except ValueError:
            typer.echo(f"Invalid status: {status}", err=True)
            raise typer.Exit(1)
    elif conflict_type:
        try:
            type_enum = ConflictType(conflict_type)
            conflicts = store.get_by_type(type_enum, limit)
        except ValueError:
            typer.echo(f"Invalid type: {conflict_type}", err=True)
            raise typer.Exit(1)
    else:
        conflicts = store.get_unresolved(limit, min_confidence)
    
    if output_json:
        typer.echo(json.dumps([c.to_dict() for c in conflicts], indent=2))
    else:
        if not conflicts:
            typer.echo("No conflicts found.")
            return
        
        typer.echo(f"{'ID':<28} {'Type':<14} {'Confidence':<11} {'Memories'}")
        typer.echo("-" * 90)
        
        for conflict in conflicts:
            mem_paths = [m.path for m in conflict.memories[:2]]
            mem_str = "\n".join([f"{' ' * 55}{p}" for p in mem_paths])
            
            typer.echo(
                f"{conflict.conflict_id:<28} "
                f"{conflict.conflict_type.value:<14} "
                f"{conflict.confidence:<11.2f} "
                f"{conflict.memories[0].path if conflict.memories else ''}"
            )
            if len(conflict.memories) > 1:
                typer.echo(f"{' ' * 55}{conflict.memories[1].path}")
        
        stats = store.get_stats()
        typer.echo("")
        typer.echo(
            f"Unresolved: {stats.unresolved} | "
            f"In Progress: {stats.in_progress} | "
            f"Resolved: {stats.resolved} | "
            f"Dismissed: {stats.dismissed}"
        )


@app.command("show")
def show_conflict(
    conflict_id: str = typer.Argument(..., help="Conflict ID"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show conflict details."""
    components = _get_components()
    store = components["conflict_store"]
    
    conflict = store.get(conflict_id)
    if conflict is None:
        typer.echo(f"Conflict not found: {conflict_id}", err=True)
        raise typer.Exit(1)
    
    if output_json:
        typer.echo(json.dumps(conflict.to_dict(), indent=2))
    else:
        typer.echo("")
        typer.echo(f"Conflict: {conflict.conflict_id}")
        typer.echo("-" * 50)
        typer.echo("")
        typer.echo(f"Type:        {conflict.conflict_type.value}")
        typer.echo(f"Confidence:  {conflict.confidence:.2f}")
        typer.echo(f"Status:      {conflict.status.value}")
        typer.echo(f"Detected:    {conflict.detected_at}")
        typer.echo("")
        typer.echo("Memories:")
        for i, mem in enumerate(conflict.memories, 1):
            typer.echo(f"  {i}. {mem.path} ({mem.role})")
            typer.echo(f"     Title: \"{mem.title}\"")
            typer.echo(f"     Scope: {mem.scope} | Priority: {mem.priority}")
            typer.echo("")
        
        typer.echo(f"Evidence: {conflict.evidence[:200]}..." if len(conflict.evidence) > 200 else f"Evidence: {conflict.evidence}")
        typer.echo("")
        typer.echo(f"Description: {conflict.description}")
        
        if conflict.resolution_action:
            typer.echo("")
            typer.echo("Resolution:")
            typer.echo(f"  Action: {conflict.resolution_action.value}")
            typer.echo(f"  Target: {conflict.resolution_target}")
            typer.echo(f"  Reason: {conflict.resolution_reason}")
            typer.echo(f"  Resolved by: {conflict.resolved_by}")
            typer.echo(f"  Resolved at: {conflict.resolved_at}")


@app.command("resolve")
def resolve_conflict(
    conflict_id: str = typer.Argument(..., help="Conflict ID"),
    action: str = typer.Option(..., "--action", help="Action: deprecate|merge|clarify|dismiss"),
    target: Optional[str] = typer.Option(None, "--target", help="Target memory ID (for deprecate)"),
    content: Optional[str] = typer.Option(None, "--content", help="Merged content (for merge)"),
    reason: str = typer.Option("", "--reason", help="Resolution reason"),
) -> None:
    """Resolve a conflict."""
    from dmm.models.conflict import ResolutionAction, ResolutionRequest
    
    try:
        action_enum = ResolutionAction(action)
    except ValueError:
        typer.echo(f"Invalid action: {action}", err=True)
        typer.echo("Valid actions: deprecate, merge, clarify, dismiss, defer")
        raise typer.Exit(1)
    
    components = _get_components()
    resolver = components["resolver"]
    
    request = ResolutionRequest(
        conflict_id=conflict_id,
        action=action_enum,
        target_memory_id=target,
        merged_content=content,
        reason=reason,
        resolved_by="cli",
    )
    
    typer.echo(f"Resolving {conflict_id}...")
    
    try:
        result = resolver.resolve(request)
        
        if result.success:
            typer.echo("")
            typer.echo("Actions taken:")
            if result.memories_deprecated:
                for mid in result.memories_deprecated:
                    typer.echo(f"  - Deprecated: {mid}")
            if result.memories_modified:
                for mid in result.memories_modified:
                    typer.echo(f"  - Modified: {mid}")
            if result.memories_created:
                for mid in result.memories_created:
                    typer.echo(f"  - Created: {mid}")
            typer.echo("")
            typer.echo("Resolution recorded.")
        else:
            typer.echo(f"Resolution failed: {result.error}", err=True)
            raise typer.Exit(1)
            
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command("dismiss")
def dismiss_conflict(
    conflict_id: str = typer.Argument(..., help="Conflict ID"),
    reason: str = typer.Option("", "--reason", help="Dismissal reason"),
) -> None:
    """Dismiss a conflict as false positive."""
    from dmm.models.conflict import ResolutionAction, ResolutionRequest
    
    components = _get_components()
    resolver = components["resolver"]
    
    request = ResolutionRequest(
        conflict_id=conflict_id,
        action=ResolutionAction.DISMISS,
        dismiss_reason=reason or "Marked as false positive",
        resolved_by="cli",
        reason=reason or "Marked as false positive",
    )
    
    try:
        result = resolver.resolve(request)
        
        if result.success:
            typer.echo(f"Dismissed conflict: {conflict_id}")
        else:
            typer.echo(f"Failed to dismiss: {result.error}", err=True)
            raise typer.Exit(1)
            
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command("flag")
def flag_conflict(
    memories: str = typer.Option(..., "--memories", help="Comma-separated memory IDs (2)"),
    description: str = typer.Option(..., "--description", help="Conflict description"),
    conflict_type: str = typer.Option("contradictory", "--type", help="Conflict type"),
) -> None:
    """Manually flag a conflict between memories."""
    from dmm.models.conflict import (
        Conflict, ConflictMemory, ConflictStatus, ConflictType, DetectionMethod
    )
    import secrets
    
    memory_ids = [m.strip() for m in memories.split(",")]
    if len(memory_ids) != 2:
        typer.echo("Must specify exactly 2 memory IDs", err=True)
        raise typer.Exit(1)
    
    try:
        type_enum = ConflictType(conflict_type)
    except ValueError:
        typer.echo(f"Invalid type: {conflict_type}", err=True)
        raise typer.Exit(1)
    
    components = _get_components()
    memory_store = components["memory_store"]
    conflict_store = components["conflict_store"]
    
    mems = []
    for mid in memory_ids:
        mem = memory_store.get_memory(mid)
        if mem is None:
            typer.echo(f"Memory not found: {mid}", err=True)
            raise typer.Exit(1)
        mems.append(mem)
    
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    conflict_id = f"conflict_{timestamp}_{secrets.token_hex(4)}"
    
    conflict = Conflict(
        conflict_id=conflict_id,
        memories=[
            ConflictMemory(
                memory_id=mems[0].id,
                path=mems[0].path,
                title=mems[0].title,
                summary=mems[0].body[:200] if mems[0].body else "",
                scope=str(mems[0].scope),
                priority=mems[0].priority,
                role="primary",
            ),
            ConflictMemory(
                memory_id=mems[1].id,
                path=mems[1].path,
                title=mems[1].title,
                summary=mems[1].body[:200] if mems[1].body else "",
                scope=str(mems[1].scope),
                priority=mems[1].priority,
                role="secondary",
            ),
        ],
        conflict_type=type_enum,
        detection_method=DetectionMethod.MANUAL,
        confidence=1.0,
        description=description,
        evidence="Manually flagged",
        status=ConflictStatus.UNRESOLVED,
    )
    
    try:
        conflict_store.create(conflict)
        typer.echo(f"Created conflict: {conflict_id}")
    except Exception as e:
        typer.echo(f"Failed to create conflict: {e}", err=True)
        raise typer.Exit(1)


@app.command("check")
def check_memories(
    memories: str = typer.Option(..., "--memories", help="Comma-separated memory IDs"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Check if specific memories have conflicts."""
    memory_ids = [m.strip() for m in memories.split(",")]
    
    components = _get_components()
    conflict_store = components["conflict_store"]
    
    conflicts = conflict_store.get_conflicts_among(memory_ids)
    
    if output_json:
        typer.echo(json.dumps({
            "has_conflicts": len(conflicts) > 0,
            "conflicts": [c.to_dict() for c in conflicts],
        }, indent=2))
    else:
        typer.echo(f"Checking {len(memory_ids)} memories for conflicts...")
        typer.echo("")
        
        if not conflicts:
            typer.echo("No conflicts found among these memories.")
        else:
            typer.echo(f"Found {len(conflicts)} conflict(s):")
            for conflict in conflicts:
                typer.echo(
                    f"  {conflict.conflict_id} (confidence: {conflict.confidence:.2f})"
                )
                typer.echo(f"  Type: {conflict.conflict_type.value}")
                mem_ids = " <-> ".join([m.memory_id for m in conflict.memories])
                typer.echo(f"  Memories: {mem_ids}")
                typer.echo("")


@app.command("stats")
def show_stats(
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show conflict statistics."""
    components = _get_components()
    store = components["conflict_store"]
    
    stats = store.get_stats()
    
    if output_json:
        typer.echo(json.dumps(stats.to_dict(), indent=2))
    else:
        typer.echo("")
        typer.echo("Conflict Statistics")
        typer.echo("-" * 50)
        typer.echo("")
        typer.echo(f"Total conflicts:     {stats.total}")
        typer.echo(f"  - Unresolved:      {stats.unresolved}")
        typer.echo(f"  - In Progress:     {stats.in_progress}")
        typer.echo(f"  - Resolved:        {stats.resolved}")
        typer.echo(f"  - Dismissed:       {stats.dismissed}")
        
        if stats.by_type:
            typer.echo("")
            typer.echo("By Type:")
            total = stats.total or 1
            for ctype, count in stats.by_type.items():
                pct = (count / total) * 100
                typer.echo(f"  - {ctype}: {count} ({pct:.0f}%)")
        
        if stats.by_method:
            typer.echo("")
            typer.echo("By Detection Method:")
            total = stats.total or 1
            for method, count in stats.by_method.items():
                pct = (count / total) * 100
                typer.echo(f"  - {method}: {count} ({pct:.0f}%)")
        
        typer.echo("")
        typer.echo(f"Average confidence:  {stats.avg_confidence:.2f}")
        if stats.oldest_unresolved:
            typer.echo(f"Oldest unresolved:   {stats.oldest_unresolved}")


@app.command("history")
def show_scan_history(
    limit: int = typer.Option(10, "--limit", help="Number of scans to show"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show conflict scan history."""
    components = _get_components()
    scanner = components["scanner"]
    
    history = scanner.get_scan_history(limit)
    
    if output_json:
        typer.echo(json.dumps(history, indent=2))
    else:
        if not history:
            typer.echo("No scan history found.")
            return
        
        typer.echo("")
        typer.echo("Scan History")
        typer.echo("-" * 80)
        
        for scan in history:
            typer.echo("")
            typer.echo(f"Scan: {scan['scan_id']}")
            typer.echo(f"  Type: {scan['scan_type']} | Status: {scan['status']}")
            typer.echo(f"  Started: {scan['started_at']}")
            typer.echo(f"  Duration: {scan['duration_ms']}ms | Memories: {scan['memories_scanned']}")
            typer.echo(
                f"  Conflicts: {scan['conflicts_detected']} "
                f"(new: {scan['conflicts_new']}, existing: {scan['conflicts_existing']})"
            )
            if scan['errors']:
                typer.echo(f"  Errors: {len(scan['errors'])}")
