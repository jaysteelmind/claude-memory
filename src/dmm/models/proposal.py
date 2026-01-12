"""Data models for write proposals and review decisions."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ProposalType(str, Enum):
    """Type of write proposal."""

    CREATE = "create"
    UPDATE = "update"
    DEPRECATE = "deprecate"
    PROMOTE = "promote"


class ProposalStatus(str, Enum):
    """Status of a write proposal in the review queue."""

    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    COMMITTED = "committed"
    REJECTED = "rejected"
    MODIFIED = "modified"
    DEFERRED = "deferred"
    FAILED = "failed"


class ReviewDecision(str, Enum):
    """Decision made by the reviewer agent."""

    APPROVE = "approve"
    REJECT = "reject"
    MODIFY = "modify"
    DEFER = "defer"


class RejectionReason(str, Enum):
    """Standardized rejection reasons."""

    SCHEMA_INVALID = "schema_invalid"
    DUPLICATE_EXACT = "duplicate_exact"
    DUPLICATE_SEMANTIC = "duplicate_semantic"
    TOKEN_COUNT_LOW = "token_count_low"
    TOKEN_COUNT_HIGH = "token_count_high"
    MULTIPLE_CONCEPTS = "multiple_concepts"
    MISSING_RATIONALE = "missing_rationale"
    INCOHERENT_CONTENT = "incoherent_content"
    INVALID_SCOPE = "invalid_scope"
    INVALID_PATH = "invalid_path"
    BASELINE_PROTECTED = "baseline_protected"
    QUALITY_FAILED = "quality_failed"


@dataclass
class WriteProposal:
    """A proposed write operation to the memory system."""

    # Identity
    proposal_id: str

    # Proposal details
    type: ProposalType
    target_path: str
    reason: str

    # Content (type-dependent)
    content: str | None = None
    patch: str | None = None
    new_scope: str | None = None

    # Metadata
    proposed_by: str = "agent"
    created_at: datetime = field(default_factory=datetime.now)
    status: ProposalStatus = ProposalStatus.PENDING

    # For UPDATE: the memory ID being updated
    memory_id: str | None = None

    # For DEPRECATE: the reason for deprecation
    deprecation_reason: str | None = None

    # For PROMOTE: source and destination scopes
    source_scope: str | None = None

    # Review tracking
    reviewed_at: datetime | None = None
    reviewer_notes: str | None = None
    retry_count: int = 0

    # Commit tracking
    committed_at: datetime | None = None
    commit_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "proposal_id": self.proposal_id,
            "type": self.type.value,
            "target_path": self.target_path,
            "reason": self.reason,
            "content": self.content,
            "patch": self.patch,
            "new_scope": self.new_scope,
            "proposed_by": self.proposed_by,
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
            "memory_id": self.memory_id,
            "deprecation_reason": self.deprecation_reason,
            "source_scope": self.source_scope,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewer_notes": self.reviewer_notes,
            "retry_count": self.retry_count,
            "committed_at": self.committed_at.isoformat() if self.committed_at else None,
            "commit_error": self.commit_error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WriteProposal":
        """Create from dictionary."""
        return cls(
            proposal_id=data["proposal_id"],
            type=ProposalType(data["type"]),
            target_path=data["target_path"],
            reason=data["reason"],
            content=data.get("content"),
            patch=data.get("patch"),
            new_scope=data.get("new_scope"),
            proposed_by=data.get("proposed_by", "agent"),
            created_at=datetime.fromisoformat(data["created_at"]),
            status=ProposalStatus(data["status"]),
            memory_id=data.get("memory_id"),
            deprecation_reason=data.get("deprecation_reason"),
            source_scope=data.get("source_scope"),
            reviewed_at=datetime.fromisoformat(data["reviewed_at"]) if data.get("reviewed_at") else None,
            reviewer_notes=data.get("reviewer_notes"),
            retry_count=data.get("retry_count", 0),
            committed_at=datetime.fromisoformat(data["committed_at"]) if data.get("committed_at") else None,
            commit_error=data.get("commit_error"),
        )


@dataclass
class ValidationIssue:
    """A single validation issue found during review."""

    code: str
    message: str
    severity: str  # "error", "warning", "info"
    field: str | None = None
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "field": self.field,
            "suggestion": self.suggestion,
        }


@dataclass
class DuplicateMatch:
    """A potential duplicate memory match."""

    memory_id: str
    memory_path: str
    similarity: float
    match_type: str  # "exact", "semantic", "similar"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "memory_id": self.memory_id,
            "memory_path": self.memory_path,
            "similarity": self.similarity,
            "match_type": self.match_type,
        }


@dataclass
class ReviewResult:
    """Result of reviewing a write proposal."""

    proposal_id: str
    decision: ReviewDecision
    confidence: float

    # Validation results
    schema_valid: bool = True
    quality_valid: bool = True
    duplicate_check_passed: bool = True

    # Issues found
    issues: list[ValidationIssue] = field(default_factory=list)

    # Duplicate matches
    duplicates: list[DuplicateMatch] = field(default_factory=list)

    # Modified content (if decision is MODIFY)
    modified_content: str | None = None
    modifications_applied: list[str] = field(default_factory=list)

    # Reviewer notes
    notes: str | None = None

    # Timing
    review_duration_ms: float = 0.0

    @property
    def is_approved(self) -> bool:
        """Check if the proposal was approved."""
        return self.decision == ReviewDecision.APPROVE

    @property
    def is_rejected(self) -> bool:
        """Check if the proposal was rejected."""
        return self.decision == ReviewDecision.REJECT

    @property
    def errors(self) -> list[ValidationIssue]:
        """Get only error-level issues."""
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Get only warning-level issues."""
        return [i for i in self.issues if i.severity == "warning"]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "proposal_id": self.proposal_id,
            "decision": self.decision.value,
            "confidence": self.confidence,
            "schema_valid": self.schema_valid,
            "quality_valid": self.quality_valid,
            "duplicate_check_passed": self.duplicate_check_passed,
            "issues": [i.to_dict() for i in self.issues],
            "duplicates": [d.to_dict() for d in self.duplicates],
            "modified_content": self.modified_content,
            "modifications_applied": self.modifications_applied,
            "notes": self.notes,
            "review_duration_ms": self.review_duration_ms,
        }


@dataclass
class CommitResult:
    """Result of committing an approved proposal."""

    proposal_id: str
    success: bool
    memory_id: str | None = None
    memory_path: str | None = None

    # Error details
    error: str | None = None
    rollback_performed: bool = False
    rollback_success: bool | None = None

    # Timing
    commit_duration_ms: float = 0.0
    reindex_duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "proposal_id": self.proposal_id,
            "success": self.success,
            "memory_id": self.memory_id,
            "memory_path": self.memory_path,
            "error": self.error,
            "rollback_performed": self.rollback_performed,
            "rollback_success": self.rollback_success,
            "commit_duration_ms": self.commit_duration_ms,
            "reindex_duration_ms": self.reindex_duration_ms,
        }
