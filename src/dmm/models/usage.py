"""Data models for usage tracking."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class QueryLogEntry:
    """Log entry for a query operation."""

    query_id: str
    query_text: str
    timestamp: datetime
    
    # Query parameters
    budget: int
    baseline_budget: int
    scope_filter: str | None = None
    
    # Results
    baseline_files_returned: int = 0
    retrieved_files_returned: int = 0
    total_tokens_used: int = 0
    
    # Performance
    query_time_ms: float = 0.0
    embedding_time_ms: float = 0.0
    retrieval_time_ms: float = 0.0
    assembly_time_ms: float = 0.0
    
    # Memory IDs that were retrieved
    retrieved_memory_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "query_id": self.query_id,
            "query_text": self.query_text,
            "timestamp": self.timestamp.isoformat(),
            "budget": self.budget,
            "baseline_budget": self.baseline_budget,
            "scope_filter": self.scope_filter,
            "baseline_files_returned": self.baseline_files_returned,
            "retrieved_files_returned": self.retrieved_files_returned,
            "total_tokens_used": self.total_tokens_used,
            "query_time_ms": self.query_time_ms,
            "embedding_time_ms": self.embedding_time_ms,
            "retrieval_time_ms": self.retrieval_time_ms,
            "assembly_time_ms": self.assembly_time_ms,
            "retrieved_memory_ids": self.retrieved_memory_ids,
        }


@dataclass
class MemoryUsageRecord:
    """Usage record for a single memory."""

    memory_id: str
    memory_path: str
    
    # Counts
    total_retrievals: int = 0
    baseline_retrievals: int = 0
    query_retrievals: int = 0
    
    # Timestamps
    first_used: datetime | None = None
    last_used: datetime | None = None
    
    # Co-occurrence tracking (which memories appear together)
    co_occurred_with: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "memory_id": self.memory_id,
            "memory_path": self.memory_path,
            "total_retrievals": self.total_retrievals,
            "baseline_retrievals": self.baseline_retrievals,
            "query_retrievals": self.query_retrievals,
            "first_used": self.first_used.isoformat() if self.first_used else None,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "co_occurred_with": self.co_occurred_with,
        }


@dataclass
class UsageStats:
    """Aggregated usage statistics."""

    # Time range
    period_start: datetime
    period_end: datetime
    
    # Query stats
    total_queries: int = 0
    avg_query_time_ms: float = 0.0
    avg_tokens_per_query: float = 0.0
    
    # Memory stats
    total_memories_retrieved: int = 0
    unique_memories_retrieved: int = 0
    
    # Top memories
    most_retrieved: list[tuple[str, int]] = field(default_factory=list)
    least_retrieved: list[tuple[str, int]] = field(default_factory=list)
    never_retrieved: list[str] = field(default_factory=list)
    
    # Scope distribution
    retrievals_by_scope: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "total_queries": self.total_queries,
            "avg_query_time_ms": self.avg_query_time_ms,
            "avg_tokens_per_query": self.avg_tokens_per_query,
            "total_memories_retrieved": self.total_memories_retrieved,
            "unique_memories_retrieved": self.unique_memories_retrieved,
            "most_retrieved": self.most_retrieved,
            "least_retrieved": self.least_retrieved,
            "never_retrieved": self.never_retrieved,
            "retrievals_by_scope": self.retrievals_by_scope,
        }


@dataclass
class MemoryHealthReport:
    """Health report for memory usage patterns."""

    generated_at: datetime
    
    # Stale memories (not retrieved recently)
    stale_memories: list[dict[str, Any]] = field(default_factory=list)
    stale_threshold_days: int = 30
    
    # Hot memories (frequently retrieved)
    hot_memories: list[dict[str, Any]] = field(default_factory=list)
    hot_threshold_retrievals: int = 10
    
    # Candidates for promotion (ephemeral with high usage)
    promotion_candidates: list[dict[str, Any]] = field(default_factory=list)
    
    # Candidates for deprecation (low usage, old)
    deprecation_candidates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "generated_at": self.generated_at.isoformat(),
            "stale_memories": self.stale_memories,
            "stale_threshold_days": self.stale_threshold_days,
            "hot_memories": self.hot_memories,
            "hot_threshold_retrievals": self.hot_threshold_retrievals,
            "promotion_candidates": self.promotion_candidates,
            "deprecation_candidates": self.deprecation_candidates,
        }
