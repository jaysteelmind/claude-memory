"""API routes for conflict detection and resolution."""

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from dmm.models.conflict import (
    ConflictStatus,
    ConflictType,
    DetectionMethod,
    ResolutionAction,
)


router = APIRouter(prefix="/conflicts", tags=["conflicts"])


class ScanRequestModel(BaseModel):
    """Request model for conflict scan."""
    
    scan_type: str = Field(default="full", description="Scan type: full, incremental, targeted")
    target_memory_id: Optional[str] = Field(default=None, description="Target memory for targeted scan")
    methods: Optional[list[str]] = Field(default=None, description="Detection methods to use")
    include_rule_extraction: bool = Field(default=False, description="Include LLM rule extraction")


class ResolutionRequestModel(BaseModel):
    """Request model for conflict resolution."""
    
    action: str = Field(..., description="Resolution action: deprecate, merge, clarify, dismiss, defer")
    target_memory_id: Optional[str] = Field(default=None, description="Target memory ID for deprecate")
    merged_content: Optional[str] = Field(default=None, description="Merged content for merge action")
    clarification: Optional[str] = Field(default=None, description="Clarification text")
    reason: str = Field(default="", description="Resolution reason")
    resolved_by: str = Field(default="api", description="Who is resolving")


class FlagRequestModel(BaseModel):
    """Request model for manually flagging a conflict."""
    
    memory_ids: list[str] = Field(..., description="Two memory IDs")
    description: str = Field(..., description="Conflict description")
    conflict_type: str = Field(default="contradictory", description="Conflict type")


class DismissRequestModel(BaseModel):
    """Request model for dismissing a conflict."""
    
    reason: str = Field(default="", description="Dismissal reason")


class CheckRequestModel(BaseModel):
    """Request model for checking memories for conflicts."""
    
    memory_ids: list[str] = Field(..., description="Memory IDs to check")


class CheckContentRequestModel(BaseModel):
    """Request model for checking proposed content."""
    
    content: str = Field(..., description="Proposed memory content")
    path: str = Field(..., description="Proposed memory path")
    tags: list[str] = Field(default_factory=list, description="Proposed tags")


def _get_components():
    """Get conflict detection components from app state."""
    from pathlib import Path
    from dmm.core.constants import get_embeddings_db_path
    from dmm.conflicts.store import ConflictStore
    from dmm.conflicts.merger import ConflictMerger
    from dmm.conflicts.resolver import ConflictResolver
    from dmm.conflicts.detector import ConflictDetector, ConflictConfig
    from dmm.conflicts.scanner import ConflictScanner, ScanConfig
    from dmm.indexer.store import MemoryStore
    from dmm.indexer.embedder import MemoryEmbedder
    
    base = Path.cwd()
    
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
    }


@router.get("")
async def list_conflicts(
    status: Optional[str] = Query(None, description="Filter by status"),
    conflict_type: Optional[str] = Query(None, alias="type", description="Filter by type"),
    memory_id: Optional[str] = Query(None, description="Filter by memory ID"),
    min_confidence: float = Query(0.0, description="Minimum confidence"),
    limit: int = Query(50, description="Maximum results"),
):
    """List conflicts with optional filters."""
    components = _get_components()
    store = components["conflict_store"]
    
    try:
        if memory_id:
            conflicts = store.get_by_memory(memory_id)
        elif status:
            status_enum = ConflictStatus(status)
            conflicts = store.get_by_status(status_enum, limit)
        elif conflict_type:
            type_enum = ConflictType(conflict_type)
            conflicts = store.get_by_type(type_enum, limit)
        else:
            conflicts = store.get_unresolved(limit, min_confidence)
        
        stats = store.get_stats()
        
        return {
            "conflicts": [c.to_dict() for c in conflicts],
            "total": len(conflicts),
            "stats": stats.to_dict(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_stats():
    """Get conflict statistics."""
    components = _get_components()
    store = components["conflict_store"]
    
    try:
        stats = store.get_stats()
        return stats.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scans")
async def get_scan_history(
    limit: int = Query(20, description="Maximum scans to return"),
):
    """Get conflict scan history."""
    components = _get_components()
    scanner = components["scanner"]
    
    try:
        history = scanner.get_scan_history(limit)
        return {
            "scans": history,
            "total": len(history),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{conflict_id}")
async def get_conflict(conflict_id: str):
    """Get a specific conflict by ID."""
    components = _get_components()
    store = components["conflict_store"]
    
    conflict = store.get(conflict_id)
    if conflict is None:
        raise HTTPException(status_code=404, detail=f"Conflict not found: {conflict_id}")
    
    return conflict.to_dict()


@router.get("/memory/{memory_id}")
async def get_conflicts_for_memory(memory_id: str):
    """Get all conflicts involving a specific memory."""
    components = _get_components()
    store = components["conflict_store"]
    
    try:
        conflicts = store.get_by_memory(memory_id)
        return {
            "conflicts": [c.to_dict() for c in conflicts],
            "total": len(conflicts),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scan")
async def run_scan(request: ScanRequestModel):
    """Run a conflict detection scan."""
    from dmm.models.conflict import ScanRequest
    
    components = _get_components()
    scanner = components["scanner"]
    
    method_map = {
        "tag": DetectionMethod.TAG_OVERLAP,
        "tag_overlap": DetectionMethod.TAG_OVERLAP,
        "semantic": DetectionMethod.SEMANTIC_SIMILARITY,
        "semantic_similarity": DetectionMethod.SEMANTIC_SIMILARITY,
        "supersession": DetectionMethod.SUPERSESSION_CHAIN,
        "supersession_chain": DetectionMethod.SUPERSESSION_CHAIN,
        "rule": DetectionMethod.RULE_EXTRACTION,
        "rule_extraction": DetectionMethod.RULE_EXTRACTION,
    }
    
    methods = None
    if request.methods:
        methods = []
        for m in request.methods:
            m_lower = m.lower()
            if m_lower in method_map:
                methods.append(method_map[m_lower])
    
    try:
        result = await scanner.trigger_full_scan(
            methods=methods,
            include_rule_extraction=request.include_rule_extraction,
        )
        return result.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{conflict_id}/resolve")
async def resolve_conflict(conflict_id: str, request: ResolutionRequestModel):
    """Resolve a conflict."""
    from dmm.models.conflict import ResolutionRequest
    
    components = _get_components()
    resolver = components["resolver"]
    
    try:
        action_enum = ResolutionAction(request.action)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action: {request.action}. Valid: deprecate, merge, clarify, dismiss, defer"
        )
    
    resolution_request = ResolutionRequest(
        conflict_id=conflict_id,
        action=action_enum,
        target_memory_id=request.target_memory_id,
        merged_content=request.merged_content,
        clarification=request.clarification,
        reason=request.reason,
        resolved_by=request.resolved_by,
    )
    
    try:
        result = resolver.resolve(resolution_request)
        return result.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{conflict_id}/dismiss")
async def dismiss_conflict(conflict_id: str, request: DismissRequestModel):
    """Dismiss a conflict as false positive."""
    from dmm.models.conflict import ResolutionRequest
    
    components = _get_components()
    resolver = components["resolver"]
    
    resolution_request = ResolutionRequest(
        conflict_id=conflict_id,
        action=ResolutionAction.DISMISS,
        dismiss_reason=request.reason or "Marked as false positive",
        resolved_by="api",
        reason=request.reason or "Marked as false positive",
    )
    
    try:
        result = resolver.resolve(resolution_request)
        return result.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/flag")
async def flag_conflict(request: FlagRequestModel):
    """Manually flag a conflict between memories."""
    from datetime import datetime
    import secrets
    from dmm.models.conflict import (
        Conflict, ConflictMemory, ConflictStatus, DetectionMethod
    )
    
    if len(request.memory_ids) != 2:
        raise HTTPException(status_code=400, detail="Must specify exactly 2 memory IDs")
    
    try:
        type_enum = ConflictType(request.conflict_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid type: {request.conflict_type}")
    
    components = _get_components()
    memory_store = components["memory_store"]
    conflict_store = components["conflict_store"]
    
    mems = []
    for mid in request.memory_ids:
        mem = memory_store.get_memory(mid)
        if mem is None:
            raise HTTPException(status_code=404, detail=f"Memory not found: {mid}")
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
        description=request.description,
        evidence="Manually flagged",
        status=ConflictStatus.UNRESOLVED,
    )
    
    try:
        conflict_store.create(conflict)
        return {
            "conflict_id": conflict_id,
            "created": True,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check")
async def check_memories(request: CheckRequestModel):
    """Check if specific memories have conflicts among them."""
    components = _get_components()
    conflict_store = components["conflict_store"]
    
    try:
        conflicts = conflict_store.get_conflicts_among(request.memory_ids)
        return {
            "has_conflicts": len(conflicts) > 0,
            "conflicts": [c.to_dict() for c in conflicts],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check-content")
async def check_content(request: CheckContentRequestModel):
    """Check if proposed content would conflict with existing memories."""
    components = _get_components()
    detector = components["detector"]
    
    try:
        candidates = await detector.check_proposal(
            content=request.content,
            path=request.path,
            tags=request.tags,
        )
        
        return {
            "potential_conflicts": [c.to_dict() for c in candidates],
            "similar_memories": [
                {"memory_id": c.memory_ids[1], "score": c.raw_score}
                for c in candidates
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{conflict_id}/history")
async def get_conflict_history(conflict_id: str):
    """Get resolution history for a conflict."""
    components = _get_components()
    resolver = components["resolver"]
    
    try:
        history = resolver.get_resolution_history(conflict_id)
        return {
            "conflict_id": conflict_id,
            "history": history,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
