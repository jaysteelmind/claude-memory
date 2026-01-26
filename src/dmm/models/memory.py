"""Memory file data models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from dmm.core.constants import Confidence, Scope, Status


@dataclass
class MemoryFile:
    """Represents a parsed memory markdown file."""

    # Identity
    id: str
    path: str

    # Content
    title: str
    body: str
    token_count: int

    # Metadata (from frontmatter)
    tags: list[str]
    scope: Scope
    priority: float
    confidence: Confidence
    status: Status

    # Optional metadata
    created: datetime | None = None
    last_used: datetime | None = None
    usage_count: int = 0
    supersedes: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    expires: datetime | None = None

    # Derived
    directory: str = field(default="", init=False)

    def __post_init__(self) -> None:
        """Extract directory from path after initialization."""
        parts = self.path.rsplit("/", 1)
        self.directory = parts[0] if len(parts) > 1 else ""

    @property
    def filename(self) -> str:
        """Get the filename from path."""
        return self.path.rsplit("/", 1)[-1]

    @property
    def is_baseline(self) -> bool:
        """Check if this is a baseline memory."""
        return self.scope == Scope.BASELINE

    @property
    def is_active(self) -> bool:
        """Check if this memory is active."""
        return self.status == Status.ACTIVE

    @property
    def is_expired(self) -> bool:
        """Check if this ephemeral memory has expired."""
        if self.expires is None:
            return False
        return datetime.now() > self.expires

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "path": self.path,
            "title": self.title,
            "body": self.body,
            "token_count": self.token_count,
            "tags": self.tags,
            "scope": self.scope.value,
            "priority": self.priority,
            "confidence": self.confidence.value,
            "status": self.status.value,
            "created": self.created.isoformat() if self.created else None,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "usage_count": self.usage_count,
            "supersedes": self.supersedes,
            "related": self.related,
            "expires": self.expires.isoformat() if self.expires else None,
            "directory": self.directory,
        }


@dataclass
class IndexedMemory:
    """Represents a memory stored in the vector database."""

    # Primary key
    id: str

    # File reference
    path: str
    directory: str

    # Content
    title: str
    body: str

    # Embeddings
    composite_embedding: list[float]
    directory_embedding: list[float]

    # Metadata for filtering/ranking
    scope: str
    priority: float
    confidence: str
    status: str
    tags: list[str]
    token_count: int

    # Indexing metadata
    file_hash: str
    indexed_at: datetime

    # Lifecycle (Phase 2)
    created_at: datetime | None = None
    last_used_at: datetime | None = None
    usage_count: int = 0
    expires_at: datetime | None = None

    # Relations
    supersedes: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)

    @classmethod
    def from_memory_file(
        cls,
        memory: MemoryFile,
        composite_embedding: list[float],
        directory_embedding: list[float],
        file_hash: str,
    ) -> "IndexedMemory":
        """Create IndexedMemory from MemoryFile and embeddings."""
        return cls(
            id=memory.id,
            path=memory.path,
            directory=memory.directory,
            title=memory.title,
            body=memory.body,
            composite_embedding=composite_embedding,
            directory_embedding=directory_embedding,
            scope=str(memory.scope),
            priority=memory.priority,
            confidence=memory.confidence.value,
            status=memory.status.value,
            tags=memory.tags,
            token_count=memory.token_count,
            file_hash=file_hash,
            indexed_at=datetime.now(),
            created_at=memory.created,
            last_used_at=memory.last_used,
            usage_count=memory.usage_count,
            expires_at=memory.expires,
            supersedes=memory.supersedes,
            related=memory.related,
        )


@dataclass
class DirectoryInfo:
    """Information about a memory directory."""

    path: str
    file_count: int
    avg_priority: float
    scopes: list[str]
    last_updated: datetime | None = None
