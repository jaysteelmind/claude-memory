"""Write API endpoints for the daemon."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from dmm.core.constants import get_embeddings_db_path
from dmm.core.exceptions import ProposalError
from dmm.indexer.store import MemoryStore
from dmm.models.proposal import ProposalStatus, ProposalType
from dmm.writeback.proposal import ProposalHandler
from dmm.writeback.queue import ReviewQueue

router = APIRouter(prefix="/write", tags=["write"])


class ProposeRequest(BaseModel):
    """Request body for proposal creation."""
    
    type: str = Field(..., description="Proposal type: create, update, deprecate, promote")
    path: str = Field(..., description="Target path relative to memory root")
    reason: str = Field(..., description="Reason for the proposal")
    content: str | None = Field(None, description="Content for create/update")
    memory_id: str | None = Field(None, description="Memory ID for update/deprecate/promote")
    new_scope: str | None = Field(None, description="New scope for promote")
    proposed_by: str = Field("agent", description="Proposer identifier")


class ProposeResponse(BaseModel):
    """Response for proposal creation."""
    
    success: bool
    proposal_id: str | None = None
    precheck_passed: bool = False
    precheck_warnings: list[str] = []
    precheck_errors: list[str] = []
    message: str = ""


class ProposalResponse(BaseModel):
    """Response containing a single proposal."""
    
    proposal_id: str
    type: str
    target_path: str
    reason: str
    status: str
    proposed_by: str
    created_at: str
    content: str | None = None
    memory_id: str | None = None
    new_scope: str | None = None
    reviewer_notes: str | None = None


class ProposalsListResponse(BaseModel):
    """Response containing multiple proposals."""
    
    proposals: list[dict[str, Any]]
    total: int
    stats: dict[str, Any]


def get_components(base_path: Path | None = None):
    """Get write components."""
    base = base_path or Path.cwd()
    
    queue = ReviewQueue(base)
    queue.initialize()
    
    store = MemoryStore(get_embeddings_db_path(base))
    store.initialize()
    
    handler = ProposalHandler(queue, store, base)
    
    return handler, queue, store


@router.post("/propose", response_model=ProposeResponse)
async def propose(request: ProposeRequest) -> ProposeResponse:
    """Create a write proposal."""
    handler, queue, _ = get_components()
    
    try:
        proposal_type = request.type.lower()
        
        if proposal_type == "create":
            if not request.content:
                return ProposeResponse(
                    success=False,
                    precheck_passed=False,
                    precheck_errors=["Content is required for create proposals"],
                    message="Missing content",
                )
            
            proposal = handler.propose_create(
                target_path=request.path,
                content=request.content,
                reason=request.reason,
                proposed_by=request.proposed_by,
            )
            
        elif proposal_type == "update":
            if not request.memory_id:
                return ProposeResponse(
                    success=False,
                    precheck_passed=False,
                    precheck_errors=["memory_id is required for update proposals"],
                    message="Missing memory_id",
                )
            if not request.content:
                return ProposeResponse(
                    success=False,
                    precheck_passed=False,
                    precheck_errors=["Content is required for update proposals"],
                    message="Missing content",
                )
            
            proposal = handler.propose_update(
                memory_id=request.memory_id,
                content=request.content,
                reason=request.reason,
                proposed_by=request.proposed_by,
            )
            
        elif proposal_type == "deprecate":
            if not request.memory_id:
                return ProposeResponse(
                    success=False,
                    precheck_passed=False,
                    precheck_errors=["memory_id is required for deprecate proposals"],
                    message="Missing memory_id",
                )
            
            proposal = handler.propose_deprecate(
                memory_id=request.memory_id,
                reason=request.reason,
                proposed_by=request.proposed_by,
            )
            
        elif proposal_type == "promote":
            if not request.memory_id:
                return ProposeResponse(
                    success=False,
                    precheck_passed=False,
                    precheck_errors=["memory_id is required for promote proposals"],
                    message="Missing memory_id",
                )
            if not request.new_scope:
                return ProposeResponse(
                    success=False,
                    precheck_passed=False,
                    precheck_errors=["new_scope is required for promote proposals"],
                    message="Missing new_scope",
                )
            
            proposal = handler.propose_promote(
                memory_id=request.memory_id,
                new_scope=request.new_scope,
                reason=request.reason,
                proposed_by=request.proposed_by,
            )
            
        else:
            return ProposeResponse(
                success=False,
                precheck_passed=False,
                precheck_errors=[f"Invalid proposal type: {request.type}"],
                message="Invalid type",
            )
        
        return ProposeResponse(
            success=True,
            proposal_id=proposal.proposal_id,
            precheck_passed=True,
            message=f"Proposal {proposal.proposal_id} created successfully",
        )
        
    except ProposalError as e:
        errors = []
        if e.details and "issues" in e.details:
            for issue in e.details["issues"]:
                errors.append(issue.get("message", str(issue)))
        else:
            errors.append(e.message)
        
        return ProposeResponse(
            success=False,
            precheck_passed=False,
            precheck_errors=errors,
            message=e.message,
        )


@router.get("/proposal/{proposal_id}", response_model=ProposalResponse)
async def get_proposal(proposal_id: str) -> ProposalResponse:
    """Get a specific proposal by ID."""
    _, queue, _ = get_components()
    
    proposal = queue.get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Proposal not found: {proposal_id}")
    
    return ProposalResponse(
        proposal_id=proposal.proposal_id,
        type=proposal.type.value,
        target_path=proposal.target_path,
        reason=proposal.reason,
        status=proposal.status.value,
        proposed_by=proposal.proposed_by,
        created_at=proposal.created_at.isoformat(),
        content=proposal.content,
        memory_id=proposal.memory_id,
        new_scope=proposal.new_scope,
        reviewer_notes=proposal.reviewer_notes,
    )


@router.get("/proposals", response_model=ProposalsListResponse)
async def list_proposals(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> ProposalsListResponse:
    """List proposals with optional filtering."""
    _, queue, _ = get_components()
    
    if status:
        try:
            proposal_status = ProposalStatus(status)
            proposals = queue.get_by_status(proposal_status, limit)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}",
            )
    else:
        proposals = queue.get_pending(limit)
    
    stats = queue.get_stats()
    
    return ProposalsListResponse(
        proposals=[p.to_dict() for p in proposals],
        total=len(proposals),
        stats=stats,
    )


@router.delete("/proposal/{proposal_id}")
async def cancel_proposal(proposal_id: str) -> dict[str, Any]:
    """Cancel a pending proposal."""
    handler, _, _ = get_components()
    
    if handler.cancel_proposal(proposal_id):
        return {"success": True, "message": f"Proposal {proposal_id} cancelled"}
    else:
        raise HTTPException(
            status_code=400,
            detail="Could not cancel proposal (not found or not cancellable)",
        )
