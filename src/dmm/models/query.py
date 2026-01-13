"""Query request and response data models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from dmm.core.constants import (
    DEFAULT_BASELINE_BUDGET,
    DEFAULT_TOTAL_BUDGET,
    Scope,
)
from dmm.models.pack import MemoryPack


@dataclass
class SearchFilters:
    """Filters for memory search operations."""

    scopes: list[Scope] | None = None
    exclude_deprecated: bool = True
    exclude_ephemeral: bool = False
    include_deprecated: bool = False
    min_priority: float = 0.0
    max_token_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "scopes": [s.value for s in self.scopes] if self.scopes else None,
            "exclude_deprecated": self.exclude_deprecated,
            "exclude_ephemeral": self.exclude_ephemeral,
            "include_deprecated": self.include_deprecated,
            "min_priority": self.min_priority,
            "max_token_count": self.max_token_count,
        }


@dataclass
class QueryRequest:
    """Request to retrieve a Memory Pack."""

    query: str
    budget: int = DEFAULT_TOTAL_BUDGET
    baseline_budget: int = DEFAULT_BASELINE_BUDGET
    scope_filter: Scope | None = None
    exclude_ephemeral: bool = False
    include_deprecated: bool = False
    verbose: bool = False

    def to_search_filters(self) -> SearchFilters:
        """Convert to SearchFilters."""
        scopes = [self.scope_filter] if self.scope_filter else None
        return SearchFilters(
            scopes=scopes,
            exclude_deprecated=not self.include_deprecated,
            exclude_ephemeral=self.exclude_ephemeral,
            include_deprecated=self.include_deprecated,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "query": self.query,
            "budget": self.budget,
            "baseline_budget": self.baseline_budget,
            "scope_filter": self.scope_filter.value if self.scope_filter else None,
            "exclude_ephemeral": self.exclude_ephemeral,
            "include_deprecated": self.include_deprecated,
            "verbose": self.verbose,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueryRequest":
        """Create from dictionary."""
        scope_filter = None
        if data.get("scope_filter"):
            scope_filter = Scope(data["scope_filter"])

        return cls(
            query=data["query"],
            budget=data.get("budget", DEFAULT_TOTAL_BUDGET),
            baseline_budget=data.get("baseline_budget", DEFAULT_BASELINE_BUDGET),
            scope_filter=scope_filter,
            exclude_ephemeral=data.get("exclude_ephemeral", False),
            include_deprecated=data.get("include_deprecated", False),
            verbose=data.get("verbose", False),
        )


@dataclass
class QueryStats:
    """Statistics about query execution."""

    query_time_ms: float
    embedding_time_ms: float
    retrieval_time_ms: float
    assembly_time_ms: float
    directories_searched: list[str] = field(default_factory=list)
    candidates_considered: int = 0
    baseline_files: int = 0
    retrieved_files: int = 0
    excluded_files: int = 0

    @property
    def total_time_ms(self) -> float:
        """Total query time."""
        return self.query_time_ms

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "query_time_ms": round(self.query_time_ms, 2),
            "embedding_time_ms": round(self.embedding_time_ms, 2),
            "retrieval_time_ms": round(self.retrieval_time_ms, 2),
            "assembly_time_ms": round(self.assembly_time_ms, 2),
            "directories_searched": self.directories_searched,
            "candidates_considered": self.candidates_considered,
            "baseline_files": self.baseline_files,
            "retrieved_files": self.retrieved_files,
            "excluded_files": self.excluded_files,
        }


@dataclass
class QueryResponse:
    """Response containing the Memory Pack."""

    pack: MemoryPack
    pack_markdown: str
    stats: QueryStats
    success: bool = True
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "error": self.error,
            "pack": {
                "generated_at": self.pack.generated_at.isoformat(),
                "query": self.pack.query,
                "baseline_tokens": self.pack.baseline_tokens,
                "retrieved_tokens": self.pack.retrieved_tokens,
                "total_tokens": self.pack.total_tokens,
                "budget": self.pack.budget,
                "baseline_count": self.pack.baseline_count,
                "retrieved_count": self.pack.retrieved_count,
                "included_paths": self.pack.included_paths,
                "excluded_paths": self.pack.excluded_paths,
            },
            "pack_markdown": self.pack_markdown,
            "stats": self.stats.to_dict(),
        }


@dataclass
class RetrievalResult:
    """Result from the retrieval router."""

    entries: list[Any]  # list[MemoryPackEntry] - avoid circular import
    total_tokens: int
    directories_searched: list[str]
    candidates_considered: int
    excluded_for_budget: list[str] = field(default_factory=list)
    conflict_alerts: list[dict] = field(default_factory=list)  # Phase 3


@dataclass
class HealthResponse:
    """Daemon health check response."""

    status: str  # "healthy" | "unhealthy"
    uptime_seconds: float
    indexed_count: int
    baseline_tokens: int
    last_reindex: datetime | None
    watcher_active: bool
    version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "indexed_count": self.indexed_count,
            "baseline_tokens": self.baseline_tokens,
            "last_reindex": self.last_reindex.isoformat() if self.last_reindex else None,
            "watcher_active": self.watcher_active,
            "version": self.version,
        }


@dataclass
class StatusResponse:
    """System status response."""

    daemon_running: bool
    daemon_pid: int | None
    daemon_version: str
    memory_root: str
    indexed_memories: int
    baseline_files: int
    baseline_tokens: int
    last_reindex: datetime | None
    watcher_active: bool
    uptime_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "daemon_running": self.daemon_running,
            "daemon_pid": self.daemon_pid,
            "daemon_version": self.daemon_version,
            "memory_root": self.memory_root,
            "indexed_memories": self.indexed_memories,
            "baseline_files": self.baseline_files,
            "baseline_tokens": self.baseline_tokens,
            "last_reindex": self.last_reindex.isoformat() if self.last_reindex else None,
            "watcher_active": self.watcher_active,
            "uptime_seconds": round(self.uptime_seconds, 2) if self.uptime_seconds else None,
        }


@dataclass
class ReindexResponse:
    """Response from reindex operation."""

    reindexed: int
    errors: int
    duration_ms: float
    error_details: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "reindexed": self.reindexed,
            "errors": self.errors,
            "duration_ms": round(self.duration_ms, 2),
            "error_details": self.error_details,
        }
