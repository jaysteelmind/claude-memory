"""Conflict detection data models for Phase 3.

This module defines the core data structures for conflict detection,
including conflict types, statuses, resolution actions, and detection methods.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ConflictType(str, Enum):
    """Types of conflicts between memories."""
    
    CONTRADICTORY = "contradictory"
    DUPLICATE = "duplicate"
    SUPERSESSION = "supersession"
    SCOPE_OVERLAP = "scope_overlap"
    STALE = "stale"


class ConflictStatus(str, Enum):
    """Status of a detected conflict."""
    
    UNRESOLVED = "unresolved"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ResolutionAction(str, Enum):
    """Actions that can be taken to resolve a conflict."""
    
    DEPRECATE = "deprecate"
    MERGE = "merge"
    CLARIFY = "clarify"
    DISMISS = "dismiss"
    DEFER = "defer"


class DetectionMethod(str, Enum):
    """Methods used to detect conflicts."""
    
    TAG_OVERLAP = "tag_overlap"
    SEMANTIC_SIMILARITY = "semantic_similarity"
    SUPERSESSION_CHAIN = "supersession_chain"
    RULE_EXTRACTION = "rule_extraction"
    MANUAL = "manual"
    CO_RETRIEVAL = "co_retrieval"


@dataclass
class ConflictMemory:
    """A memory involved in a conflict."""
    
    memory_id: str
    path: str
    title: str
    summary: str
    scope: str
    priority: float
    role: str  # "primary" or "secondary"
    key_claims: list[str] = field(default_factory=list)
    last_modified: datetime | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "memory_id": self.memory_id,
            "path": self.path,
            "title": self.title,
            "summary": self.summary,
            "scope": self.scope,
            "priority": self.priority,
            "role": self.role,
            "key_claims": self.key_claims,
            "last_modified": self.last_modified.isoformat() if self.last_modified else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConflictMemory":
        """Create from dictionary."""
        last_modified = None
        if data.get("last_modified"):
            last_modified = datetime.fromisoformat(data["last_modified"])
        
        return cls(
            memory_id=data["memory_id"],
            path=data["path"],
            title=data["title"],
            summary=data["summary"],
            scope=data["scope"],
            priority=data["priority"],
            role=data["role"],
            key_claims=data.get("key_claims", []),
            last_modified=last_modified,
        )


@dataclass
class Conflict:
    """A detected conflict between memories."""
    
    conflict_id: str
    memories: list[ConflictMemory]
    conflict_type: ConflictType
    detection_method: DetectionMethod
    confidence: float
    description: str
    evidence: str
    status: ConflictStatus = ConflictStatus.UNRESOLVED
    detected_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: datetime | None = None
    resolution_action: ResolutionAction | None = None
    resolution_target: str | None = None
    resolution_reason: str | None = None
    resolved_by: str | None = None
    scan_id: str | None = None
    suppressed_until: datetime | None = None
    
    @property
    def memory_ids(self) -> list[str]:
        """Get list of memory IDs involved in this conflict."""
        return [m.memory_id for m in self.memories]
    
    @property
    def memory_pair_hash(self) -> str:
        """Get a hash key for the memory pair (for deduplication)."""
        sorted_ids = sorted(self.memory_ids)
        return "|".join(sorted_ids)
    
    @property
    def is_resolved(self) -> bool:
        """Check if the conflict is resolved."""
        return self.status in (ConflictStatus.RESOLVED, ConflictStatus.DISMISSED)
    
    @property
    def primary_memory(self) -> ConflictMemory | None:
        """Get the primary memory in the conflict."""
        for mem in self.memories:
            if mem.role == "primary":
                return mem
        return self.memories[0] if self.memories else None
    
    @property
    def secondary_memory(self) -> ConflictMemory | None:
        """Get the secondary memory in the conflict."""
        for mem in self.memories:
            if mem.role == "secondary":
                return mem
        return self.memories[1] if len(self.memories) > 1 else None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "conflict_id": self.conflict_id,
            "memories": [m.to_dict() for m in self.memories],
            "conflict_type": self.conflict_type.value,
            "detection_method": self.detection_method.value,
            "confidence": self.confidence,
            "description": self.description,
            "evidence": self.evidence,
            "status": self.status.value,
            "detected_at": self.detected_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution_action": self.resolution_action.value if self.resolution_action else None,
            "resolution_target": self.resolution_target,
            "resolution_reason": self.resolution_reason,
            "resolved_by": self.resolved_by,
            "scan_id": self.scan_id,
            "suppressed_until": self.suppressed_until.isoformat() if self.suppressed_until else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Conflict":
        """Create from dictionary."""
        return cls(
            conflict_id=data["conflict_id"],
            memories=[ConflictMemory.from_dict(m) for m in data["memories"]],
            conflict_type=ConflictType(data["conflict_type"]),
            detection_method=DetectionMethod(data["detection_method"]),
            confidence=data["confidence"],
            description=data["description"],
            evidence=data["evidence"],
            status=ConflictStatus(data["status"]),
            detected_at=datetime.fromisoformat(data["detected_at"]),
            resolved_at=datetime.fromisoformat(data["resolved_at"]) if data.get("resolved_at") else None,
            resolution_action=ResolutionAction(data["resolution_action"]) if data.get("resolution_action") else None,
            resolution_target=data.get("resolution_target"),
            resolution_reason=data.get("resolution_reason"),
            resolved_by=data.get("resolved_by"),
            scan_id=data.get("scan_id"),
            suppressed_until=datetime.fromisoformat(data["suppressed_until"]) if data.get("suppressed_until") else None,
        )


@dataclass
class ConflictCandidate:
    """A potential conflict before final classification."""
    
    memory_ids: tuple[str, str]
    detection_method: DetectionMethod
    raw_score: float
    evidence: dict[str, Any] = field(default_factory=dict)
    
    @property
    def pair_key(self) -> tuple[str, str]:
        """Get sorted tuple for deduplication."""
        return tuple(sorted(self.memory_ids))
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "memory_ids": list(self.memory_ids),
            "detection_method": self.detection_method.value,
            "raw_score": self.raw_score,
            "evidence": self.evidence,
        }


@dataclass
class ScanRequest:
    """Request for a conflict scan."""
    
    scan_type: str  # "full", "incremental", "targeted"
    target_memory_id: str | None = None
    methods: list[DetectionMethod] = field(
        default_factory=lambda: [
            DetectionMethod.TAG_OVERLAP,
            DetectionMethod.SEMANTIC_SIMILARITY,
            DetectionMethod.SUPERSESSION_CHAIN,
        ]
    )
    include_rule_extraction: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "scan_type": self.scan_type,
            "target_memory_id": self.target_memory_id,
            "methods": [m.value for m in self.methods],
            "include_rule_extraction": self.include_rule_extraction,
        }


@dataclass
class ScanResult:
    """Result of a conflict scan."""
    
    scan_id: str
    scan_type: str
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    memories_scanned: int
    methods_used: list[str]
    conflicts_detected: int
    conflicts_new: int
    conflicts_existing: int
    by_type: dict[str, int] = field(default_factory=dict)
    by_method: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    
    @property
    def success(self) -> bool:
        """Check if scan completed without errors."""
        return len(self.errors) == 0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "scan_id": self.scan_id,
            "scan_type": self.scan_type,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_ms": self.duration_ms,
            "memories_scanned": self.memories_scanned,
            "methods_used": self.methods_used,
            "conflicts_detected": self.conflicts_detected,
            "conflicts_new": self.conflicts_new,
            "conflicts_existing": self.conflicts_existing,
            "by_type": self.by_type,
            "by_method": self.by_method,
            "errors": self.errors,
        }


@dataclass
class ResolutionRequest:
    """Request to resolve a conflict."""
    
    conflict_id: str
    action: ResolutionAction
    target_memory_id: str | None = None
    merged_content: str | None = None
    clarification: str | None = None
    dismiss_reason: str | None = None
    resolved_by: str = "agent"
    reason: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "conflict_id": self.conflict_id,
            "action": self.action.value,
            "target_memory_id": self.target_memory_id,
            "merged_content": self.merged_content,
            "clarification": self.clarification,
            "dismiss_reason": self.dismiss_reason,
            "resolved_by": self.resolved_by,
            "reason": self.reason,
        }


@dataclass
class ResolutionResult:
    """Result of a resolution attempt."""
    
    success: bool
    conflict_id: str
    action_taken: ResolutionAction
    memories_modified: list[str] = field(default_factory=list)
    memories_deprecated: list[str] = field(default_factory=list)
    memories_created: list[str] = field(default_factory=list)
    error: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "conflict_id": self.conflict_id,
            "action_taken": self.action_taken.value,
            "memories_modified": self.memories_modified,
            "memories_deprecated": self.memories_deprecated,
            "memories_created": self.memories_created,
            "error": self.error,
        }


@dataclass
class ConflictStats:
    """Statistics about conflicts in the system."""
    
    total: int
    unresolved: int
    in_progress: int
    resolved: int
    dismissed: int
    by_type: dict[str, int] = field(default_factory=dict)
    by_method: dict[str, int] = field(default_factory=dict)
    avg_confidence: float = 0.0
    oldest_unresolved: datetime | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total": self.total,
            "unresolved": self.unresolved,
            "in_progress": self.in_progress,
            "resolved": self.resolved,
            "dismissed": self.dismissed,
            "by_type": self.by_type,
            "by_method": self.by_method,
            "avg_confidence": self.avg_confidence,
            "oldest_unresolved": self.oldest_unresolved.isoformat() if self.oldest_unresolved else None,
        }


@dataclass
class MergeResult:
    """Result of merging conflict candidates."""
    
    total_candidates: int
    unique_pairs: int
    new_conflicts: int
    existing_conflicts: int
    conflicts: list[Conflict] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_candidates": self.total_candidates,
            "unique_pairs": self.unique_pairs,
            "new_conflicts": self.new_conflicts,
            "existing_conflicts": self.existing_conflicts,
            "conflicts": [c.to_dict() for c in self.conflicts],
        }
