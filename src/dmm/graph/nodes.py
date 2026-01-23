"""Node type definitions for the knowledge graph.

This module defines dataclass representations for all node types in the DMM
knowledge graph:
- MemoryNode: Represents a memory file
- TagNode: Represents a semantic tag
- ScopeNode: Represents a memory scope (baseline, global, agent, project, ephemeral)
- ConceptNode: Represents an extracted concept (Phase 5 Part 2)

Each node class provides serialization methods for database operations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final, Optional

# Scope definitions with descriptions for initialization
SCOPE_DEFINITIONS: Final[dict[str, str]] = {
    "baseline": "Critical context always included in every query",
    "global": "Stable truths that apply across projects",
    "agent": "Behavioral rules and preferences for the agent",
    "project": "Project-specific decisions and constraints",
    "ephemeral": "Temporary findings that may expire",
    "deprecated": "Archived memories excluded from retrieval",
}


@dataclass
class MemoryNode:
    """Represents a memory in the knowledge graph.

    This node type corresponds to a memory file in the .dmm/memory/ directory.
    It captures all metadata from the frontmatter plus derived fields.

    Attributes:
        id: Unique identifier in format mem_YYYY_MM_DD_NNN.
        path: File path relative to memory root.
        directory: Parent directory indicating scope/category.
        title: Memory title extracted from H1 heading.
        scope: Memory scope (baseline, global, agent, project, ephemeral).
        priority: Priority score between 0.0 and 1.0.
        confidence: Confidence level (experimental, active, stable, deprecated).
        status: Status flag (active, deprecated).
        token_count: Number of tokens in the memory content.
        created: Creation timestamp.
        last_used: Last retrieval timestamp.
        usage_count: Number of times retrieved.
        file_hash: Content hash for change detection.
        indexed_at: Last indexing timestamp.
    """

    id: str
    path: str
    directory: str
    title: str
    scope: str
    priority: float
    confidence: str
    status: str
    token_count: int
    created: Optional[datetime] = None
    last_used: Optional[datetime] = None
    usage_count: int = 0
    file_hash: str = ""
    indexed_at: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database insertion.

        Returns:
            Dictionary with all node properties suitable for Kuzu insertion.
        """
        return {
            "id": self.id,
            "path": self.path,
            "directory": self.directory,
            "title": self.title,
            "scope": self.scope,
            "priority": self.priority,
            "confidence": self.confidence,
            "status": self.status,
            "token_count": self.token_count,
            "created": self.created,
            "last_used": self.last_used,
            "usage_count": self.usage_count,
            "file_hash": self.file_hash,
            "indexed_at": self.indexed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryNode":
        """Create MemoryNode from dictionary.

        Args:
            data: Dictionary containing node properties.

        Returns:
            MemoryNode instance populated from dictionary.
        """
        return cls(
            id=data["id"],
            path=data.get("path", ""),
            directory=data.get("directory", ""),
            title=data.get("title", ""),
            scope=data.get("scope", "project"),
            priority=float(data.get("priority", 0.5)),
            confidence=data.get("confidence", "active"),
            status=data.get("status", "active"),
            token_count=int(data.get("token_count", 0)),
            created=data.get("created"),
            last_used=data.get("last_used"),
            usage_count=int(data.get("usage_count", 0)),
            file_hash=data.get("file_hash", ""),
            indexed_at=data.get("indexed_at"),
        )

    @classmethod
    def from_indexed_memory(cls, memory: Any) -> "MemoryNode":
        """Create MemoryNode from an IndexedMemory object.

        Args:
            memory: IndexedMemory instance from the memory store.

        Returns:
            MemoryNode instance with properties copied from IndexedMemory.
        """
        return cls(
            id=memory.id,
            path=memory.path,
            directory=memory.directory,
            title=memory.title,
            scope=str(memory.scope.value) if hasattr(memory.scope, "value") else str(memory.scope),
            priority=memory.priority,
            confidence=str(memory.confidence.value) if hasattr(memory.confidence, "value") else str(memory.confidence),
            status=str(memory.status.value) if hasattr(memory.status, "value") else str(memory.status),
            token_count=memory.token_count,
            file_hash=memory.file_hash if hasattr(memory, "file_hash") else "",
            indexed_at=memory.indexed_at if hasattr(memory, "indexed_at") else None,
            created=memory.created_at if hasattr(memory, "created_at") else None,
            last_used=memory.last_used_at if hasattr(memory, "last_used_at") else None,
            usage_count=memory.usage_count if hasattr(memory, "usage_count") else 0,
        )


@dataclass
class TagNode:
    """Represents a tag in the knowledge graph.

    Tags are semantic labels applied to memories for categorization
    and retrieval optimization.

    Attributes:
        id: Unique identifier in format tag_{normalized_name}.
        name: Original tag name as specified in frontmatter.
        normalized: Lowercase, trimmed tag name for matching.
        usage_count: Number of memories using this tag.
    """

    id: str
    name: str
    normalized: str
    usage_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database insertion.

        Returns:
            Dictionary with all node properties suitable for Kuzu insertion.
        """
        return {
            "id": self.id,
            "name": self.name,
            "normalized": self.normalized,
            "usage_count": self.usage_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TagNode":
        """Create TagNode from dictionary.

        Args:
            data: Dictionary containing node properties.

        Returns:
            TagNode instance populated from dictionary.
        """
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            normalized=data.get("normalized", ""),
            usage_count=int(data.get("usage_count", 0)),
        )

    @classmethod
    def from_tag_name(cls, name: str) -> "TagNode":
        """Create TagNode from a tag name string.

        Automatically generates the ID and normalized form.

        Args:
            name: Original tag name.

        Returns:
            TagNode instance with generated ID and normalized name.
        """
        normalized = name.lower().strip()
        tag_id = f"tag_{normalized.replace(' ', '_').replace('-', '_')}"
        return cls(
            id=tag_id,
            name=name,
            normalized=normalized,
            usage_count=0,
        )


@dataclass
class ScopeNode:
    """Represents a memory scope in the knowledge graph.

    Scopes define the category and retrieval behavior for memories.

    Attributes:
        id: Unique identifier in format scope_{name}.
        name: Scope name (baseline, global, agent, project, ephemeral, deprecated).
        description: Human-readable description of the scope's purpose.
        memory_count: Number of memories in this scope.
        token_total: Total tokens across all memories in scope.
    """

    id: str
    name: str
    description: str
    memory_count: int = 0
    token_total: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database insertion.

        Returns:
            Dictionary with all node properties suitable for Kuzu insertion.
        """
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "memory_count": self.memory_count,
            "token_total": self.token_total,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScopeNode":
        """Create ScopeNode from dictionary.

        Args:
            data: Dictionary containing node properties.

        Returns:
            ScopeNode instance populated from dictionary.
        """
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            description=data.get("description", ""),
            memory_count=int(data.get("memory_count", 0)),
            token_total=int(data.get("token_total", 0)),
        )

    @classmethod
    def from_scope_name(cls, name: str) -> "ScopeNode":
        """Create ScopeNode from a scope name.

        Uses predefined descriptions from SCOPE_DEFINITIONS.

        Args:
            name: Scope name.

        Returns:
            ScopeNode instance with description from definitions.
        """
        return cls(
            id=f"scope_{name}",
            name=name,
            description=SCOPE_DEFINITIONS.get(name, f"Scope: {name}"),
            memory_count=0,
            token_total=0,
        )


@dataclass
class ConceptNode:
    """Represents an extracted concept in the knowledge graph.

    Concepts are entities or ideas extracted from memory content,
    enabling concept-based navigation and retrieval.

    Note: Full concept extraction is implemented in Phase 5 Part 2.

    Attributes:
        id: Unique identifier in format concept_{hash}.
        name: Concept name or label.
        definition: Optional definition or description.
        source_count: Number of memories mentioning this concept.
    """

    id: str
    name: str
    definition: Optional[str] = None
    source_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database insertion.

        Returns:
            Dictionary with all node properties suitable for Kuzu insertion.
        """
        return {
            "id": self.id,
            "name": self.name,
            "definition": self.definition,
            "source_count": self.source_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConceptNode":
        """Create ConceptNode from dictionary.

        Args:
            data: Dictionary containing node properties.

        Returns:
            ConceptNode instance populated from dictionary.
        """
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            definition=data.get("definition"),
            source_count=int(data.get("source_count", 0)),
        )


def create_all_scope_nodes() -> list[ScopeNode]:
    """Create ScopeNode instances for all defined scopes.

    Returns:
        List of ScopeNode instances for baseline, global, agent,
        project, ephemeral, and deprecated scopes.
    """
    return [ScopeNode.from_scope_name(name) for name in SCOPE_DEFINITIONS]
