"""Review API endpoints for the daemon."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from dmm.core.constants import get_embeddings_db_path
from dmm.core.exceptions import CommitError, ReviewError
from dmm.indexer.embedder import MemoryEmbedder
from dmm.indexer.store import MemoryStore
from dmm.models.proposal import ProposalStatus, ReviewDecision
from dmm.reviewer.agent import ReviewerAgent
from dmm.writeback.queue import ReviewQueue

router = APIRouter(prefix="/review", tags=["review"])


class ProcessRequest(BaseModel):
    """Request body for processing a proposal."""
    
    force: bool = Field(False, description="Skip auto-approve threshold")


class ProcessResponse(BaseModel):
    """Response for proposal processing."""
    
    proposal_id: str
    decision: str
    confidence: float
    schema_valid: bool
    quality_valid: bool
    duplicate_check_passed: bool
    issues: list[dict[str, Any]] = []
    notes: str | None = None
    committed: bool = False
    commit_result: dict[str, Any] | None = None


class BatchProcessRequest(BaseModel):
    """Request body for batch processing."""
    
    limit: int = Field(10, description="Maximum proposals to process")
    force: bool = Field(False, description="Skip auto-approve threshold")


class BatchProcessResponse(BaseModel):
    """Response for batch processing."""
    
    processed: int
    results: list[dict[str, Any]]


class ApproveRequest(BaseModel):
    """Request body for manual approval."""
    
    bypass_reviewer: bool = Field(False, description="Skip reviewer validation")
    reason: str | None = Field(None, description="Approval reason")


class RejectRequest(BaseModel):
    """Request body for manual rejection."""
    
    reason: str = Field(..., description="Rejection reason")


class QueueResponse(BaseModel):
    """Response for queue status."""
    
    pending: list[dict[str, Any]]
    stats: dict[str, Any]


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


@router.post("/process/{proposal_id}", response_model=ProcessResponse)
async def process_proposal(
    proposal_id: str,
    request: ProcessRequest | None = None,
) -> ProcessResponse:
    """Review and optionally commit a specific proposal."""
    reviewer, queue, store, _ = get_components()
    
    proposal = queue.get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Proposal not found: {proposal_id}")
    
    try:
        result = reviewer.review(proposal)
        
        response = ProcessResponse(
            proposal_id=proposal_id,
            decision=result.decision.value,
            confidence=result.confidence,
            schema_valid=result.schema_valid,
            quality_valid=result.quality_valid,
            duplicate_check_passed=result.duplicate_check_passed,
            issues=[i.to_dict() for i in result.issues],
            notes=result.notes,
        )
        
        if result.decision == ReviewDecision.APPROVE and reviewer.can_auto_commit(result):
            commit_result = _do_commit(proposal_id, queue)
            response.committed = commit_result.get("success", False)
            response.commit_result = commit_result
        
        return response
        
    except ReviewError as e:
        raise HTTPException(status_code=500, detail=e.message)


@router.post("/process-batch", response_model=BatchProcessResponse)
async def process_batch(request: BatchProcessRequest) -> BatchProcessResponse:
    """Review multiple pending proposals."""
    reviewer, queue, _, _ = get_components()
    
    pending = queue.get_pending(request.limit)
    results = []
    
    for proposal in pending:
        try:
            result = reviewer.review(proposal)
            
            result_dict = {
                "proposal_id": proposal.proposal_id,
                "decision": result.decision.value,
                "confidence": result.confidence,
                "committed": False,
            }
            
            if result.decision == ReviewDecision.APPROVE and reviewer.can_auto_commit(result):
                commit_result = _do_commit(proposal.proposal_id, queue)
                result_dict["committed"] = commit_result.get("success", False)
            
            results.append(result_dict)
            
        except ReviewError as e:
            results.append({
                "proposal_id": proposal.proposal_id,
                "decision": "error",
                "error": e.message,
            })
    
    return BatchProcessResponse(
        processed=len(results),
        results=results,
    )


@router.post("/approve/{proposal_id}")
async def approve_proposal(
    proposal_id: str,
    request: ApproveRequest,
) -> dict[str, Any]:
    """Manually approve a proposal."""
    _, queue, _, _ = get_components()
    
    proposal = queue.get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Proposal not found: {proposal_id}")
    
    if proposal.status not in (ProposalStatus.PENDING, ProposalStatus.DEFERRED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve proposal with status '{proposal.status.value}'",
        )
    
    queue.update_status(
        proposal_id,
        ProposalStatus.APPROVED,
        notes=request.reason or "Manually approved",
    )
    
    commit_result = _do_commit(proposal_id, queue)
    
    return {
        "success": True,
        "proposal_id": proposal_id,
        "committed": commit_result.get("success", False),
        "commit_result": commit_result,
    }


@router.post("/reject/{proposal_id}")
async def reject_proposal(
    proposal_id: str,
    request: RejectRequest,
) -> dict[str, Any]:
    """Manually reject a proposal."""
    _, queue, _, _ = get_components()
    
    proposal = queue.get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Proposal not found: {proposal_id}")
    
    if proposal.status not in (
        ProposalStatus.PENDING,
        ProposalStatus.DEFERRED,
        ProposalStatus.IN_REVIEW,
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject proposal with status '{proposal.status.value}'",
        )
    
    queue.update_status(
        proposal_id,
        ProposalStatus.REJECTED,
        notes=request.reason,
    )
    
    return {
        "success": True,
        "proposal_id": proposal_id,
        "message": f"Proposal rejected: {request.reason}",
    }


@router.get("/queue", response_model=QueueResponse)
async def get_queue() -> QueueResponse:
    """Get the review queue status."""
    _, queue, _, _ = get_components()
    
    pending = queue.get_pending(100)
    stats = queue.get_stats()
    
    return QueueResponse(
        pending=[p.to_dict() for p in pending],
        stats=stats,
    )


@router.get("/history/{proposal_id}")
async def get_history(proposal_id: str) -> dict[str, Any]:
    """Get review history for a proposal."""
    _, queue, _, _ = get_components()
    
    proposal = queue.get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Proposal not found: {proposal_id}")
    
    history = queue.get_history(proposal_id)
    
    return {
        "proposal_id": proposal_id,
        "history": history,
    }


def _do_commit(proposal_id: str, queue: ReviewQueue) -> dict[str, Any]:
    """Internal function to commit an approved proposal."""
    from dmm.core.config import DMMConfig
    from dmm.indexer.indexer import Indexer
    from dmm.writeback.commit import CommitEngine
    
    base = Path.cwd()
    
    proposal = queue.get(proposal_id)
    if not proposal:
        return {"success": False, "error": "Proposal not found"}
    
    if proposal.status not in (ProposalStatus.APPROVED, ProposalStatus.MODIFIED):
        return {"success": False, "error": f"Invalid status: {proposal.status.value}"}
    
    try:
        config = DMMConfig.load(base)
        indexer = Indexer(config, base)
        
        commit_engine = CommitEngine(queue, indexer, base)
        result = commit_engine.commit(proposal)
        
        return {
            "success": result.success,
            "memory_id": result.memory_id,
            "memory_path": result.memory_path,
            "error": result.error,
            "commit_duration_ms": result.commit_duration_ms,
        }
        
    except CommitError as e:
        return {"success": False, "error": e.message}
    except Exception as e:
        return {"success": False, "error": str(e)}
