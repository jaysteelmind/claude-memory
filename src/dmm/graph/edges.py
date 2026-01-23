"""Edge type definitions for the knowledge graph.

This module defines dataclass representations for all relationship types
in the DMM knowledge graph:

Memory-to-Memory relationships:
- RelatesTo: General semantic relationship
- Supersedes: One memory replaces another
- Contradicts: Two memories have conflicting information
- Supports: One memory provides evidence for another
- DependsOn: One memory requires understanding of another

Memory-to-Tag relationships:
- HasTag: Memory is labeled with a tag

Memory-to-Scope relationships:
- InScope: Memory belongs to a scope

Tag-to-Tag relationships:
- TagCooccurs: Two tags frequently appear together

Memory-to-Concept relationships (Phase 5 Part 2):
- About: Memory discusses a concept
- Defines: Memory defines a concept
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class Edge:
    """Base class for all graph edges.

    Provides common functionality for edge serialization and
    identification of source and target nodes.

    Attributes:
        edge_type: The relationship type name (e.g., RELATES_TO).
        from_id: Source node identifier.
        to_id: Target node identifier.
    """

    edge_type: str
    from_id: str
    to_id: str

    def to_cypher_params(self) -> dict[str, Any]:
        """Convert to Cypher query parameters.

        Returns:
            Dictionary with from_id and to_id for parameterized queries.
        """
        return {
            "from_id": self.from_id,
            "to_id": self.to_id,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary with edge type and endpoint identifiers.
        """
        return {
            "edge_type": self.edge_type,
            "from_id": self.from_id,
            "to_id": self.to_id,
        }


@dataclass
class RelatesTo(Edge):
    """General semantic relationship between memories.

    Used when two memories discuss related topics but don't have
    a more specific relationship type.

    Attributes:
        weight: Relationship strength between 0.0 and 1.0.
            Higher values indicate stronger relationships.
        context: Optional description of why the relationship exists.
    """

    weight: float = 0.5
    context: Optional[str] = None
    edge_type: str = field(default="RELATES_TO", init=False)

    def __post_init__(self) -> None:
        """Set the edge type after initialization."""
        object.__setattr__(self, "edge_type", "RELATES_TO")

    def to_cypher_params(self) -> dict[str, Any]:
        """Convert to Cypher query parameters.

        Returns:
            Dictionary with all edge properties for parameterized queries.
        """
        params = super().to_cypher_params()
        params["weight"] = self.weight
        params["context"] = self.context or ""
        return params

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary with all edge properties.
        """
        result = super().to_dict()
        result["weight"] = self.weight
        result["context"] = self.context
        return result


@dataclass
class Supersedes(Edge):
    """Indicates one memory replaces another.

    Used when a newer memory contains updated information that
    should be used instead of an older memory.

    Attributes:
        reason: Explanation of why the supersession occurred.
        superseded_at: Timestamp when the supersession was declared.
    """

    reason: Optional[str] = None
    superseded_at: Optional[datetime] = None
    edge_type: str = field(default="SUPERSEDES", init=False)

    def __post_init__(self) -> None:
        """Set the edge type and default timestamp."""
        object.__setattr__(self, "edge_type", "SUPERSEDES")
        if self.superseded_at is None:
            object.__setattr__(self, "superseded_at", datetime.now())

    def to_cypher_params(self) -> dict[str, Any]:
        """Convert to Cypher query parameters.

        Returns:
            Dictionary with all edge properties for parameterized queries.
        """
        params = super().to_cypher_params()
        params["reason"] = self.reason or ""
        params["superseded_at"] = self.superseded_at
        return params

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary with all edge properties.
        """
        result = super().to_dict()
        result["reason"] = self.reason
        result["superseded_at"] = self.superseded_at
        return result


@dataclass
class Contradicts(Edge):
    """Indicates two memories contain conflicting information.

    Created by the conflict detection system when memories
    provide contradictory guidance.

    Attributes:
        description: Description of the nature of the contradiction.
        resolution: How the conflict was resolved, if applicable.
    """

    description: Optional[str] = None
    resolution: Optional[str] = None
    edge_type: str = field(default="CONTRADICTS", init=False)

    def __post_init__(self) -> None:
        """Set the edge type after initialization."""
        object.__setattr__(self, "edge_type", "CONTRADICTS")

    def to_cypher_params(self) -> dict[str, Any]:
        """Convert to Cypher query parameters.

        Returns:
            Dictionary with all edge properties for parameterized queries.
        """
        params = super().to_cypher_params()
        params["description"] = self.description or ""
        params["resolution"] = self.resolution or ""
        return params

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary with all edge properties.
        """
        result = super().to_dict()
        result["description"] = self.description
        result["resolution"] = self.resolution
        return result


@dataclass
class Supports(Edge):
    """Indicates one memory provides evidence supporting another.

    Used when one memory contains evidence, examples, or rationale
    that strengthens the claims in another memory.

    Attributes:
        strength: How strongly the evidence supports, between 0.0 and 1.0.
            1.0 indicates direct evidence, 0.5 indicates partial support.
    """

    strength: float = 0.5
    edge_type: str = field(default="SUPPORTS", init=False)

    def __post_init__(self) -> None:
        """Set the edge type after initialization."""
        object.__setattr__(self, "edge_type", "SUPPORTS")

    def to_cypher_params(self) -> dict[str, Any]:
        """Convert to Cypher query parameters.

        Returns:
            Dictionary with all edge properties for parameterized queries.
        """
        params = super().to_cypher_params()
        params["strength"] = self.strength
        return params

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary with all edge properties.
        """
        result = super().to_dict()
        result["strength"] = self.strength
        return result


@dataclass
class DependsOn(Edge):
    """Indicates one memory depends on understanding another.

    Used when comprehending one memory requires prior knowledge
    from another memory.

    This is a simple edge with no additional properties.
    """

    edge_type: str = field(default="DEPENDS_ON", init=False)

    def __post_init__(self) -> None:
        """Set the edge type after initialization."""
        object.__setattr__(self, "edge_type", "DEPENDS_ON")


@dataclass
class HasTag(Edge):
    """Indicates a memory is labeled with a tag.

    Connects Memory nodes to Tag nodes for tag-based retrieval
    and co-occurrence analysis.

    This is a simple edge with no additional properties.
    """

    edge_type: str = field(default="HAS_TAG", init=False)

    def __post_init__(self) -> None:
        """Set the edge type after initialization."""
        object.__setattr__(self, "edge_type", "HAS_TAG")


@dataclass
class InScope(Edge):
    """Indicates a memory belongs to a scope.

    Connects Memory nodes to Scope nodes for scope-based
    filtering and statistics.

    This is a simple edge with no additional properties.
    """

    edge_type: str = field(default="IN_SCOPE", init=False)

    def __post_init__(self) -> None:
        """Set the edge type after initialization."""
        object.__setattr__(self, "edge_type", "IN_SCOPE")


@dataclass
class TagCooccurs(Edge):
    """Indicates two tags frequently appear together.

    Created during migration and updated as memories are indexed.
    Used for tag-based recommendations and relationship inference.

    Attributes:
        count: Number of memories where both tags appear.
        strength: Normalized co-occurrence strength between 0.0 and 1.0.
    """

    count: int = 0
    strength: float = 0.0
    edge_type: str = field(default="TAG_COOCCURS", init=False)

    def __post_init__(self) -> None:
        """Set the edge type after initialization."""
        object.__setattr__(self, "edge_type", "TAG_COOCCURS")

    def to_cypher_params(self) -> dict[str, Any]:
        """Convert to Cypher query parameters.

        Returns:
            Dictionary with all edge properties for parameterized queries.
        """
        params = super().to_cypher_params()
        params["count"] = self.count
        params["strength"] = self.strength
        return params

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary with all edge properties.
        """
        result = super().to_dict()
        result["count"] = self.count
        result["strength"] = self.strength
        return result


@dataclass
class About(Edge):
    """Indicates a memory discusses a concept.

    Connects Memory nodes to Concept nodes for concept-based
    navigation and retrieval.

    Note: Full implementation in Phase 5 Part 2.

    Attributes:
        relevance: How relevant the concept is to the memory,
            between 0.0 and 1.0.
    """

    relevance: float = 0.5
    edge_type: str = field(default="ABOUT", init=False)

    def __post_init__(self) -> None:
        """Set the edge type after initialization."""
        object.__setattr__(self, "edge_type", "ABOUT")

    def to_cypher_params(self) -> dict[str, Any]:
        """Convert to Cypher query parameters.

        Returns:
            Dictionary with all edge properties for parameterized queries.
        """
        params = super().to_cypher_params()
        params["relevance"] = self.relevance
        return params

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary with all edge properties.
        """
        result = super().to_dict()
        result["relevance"] = self.relevance
        return result


@dataclass
class Defines(Edge):
    """Indicates a memory defines a concept.

    Connects Memory nodes to Concept nodes when the memory
    provides a definition or authoritative description.

    Note: Full implementation in Phase 5 Part 2.

    This is a simple edge with no additional properties.
    """

    edge_type: str = field(default="DEFINES", init=False)

    def __post_init__(self) -> None:
        """Set the edge type after initialization."""
        object.__setattr__(self, "edge_type", "DEFINES")


# Type alias for any edge type
EdgeType = (
    RelatesTo
    | Supersedes
    | Contradicts
    | Supports
    | DependsOn
    | HasTag
    | InScope
    | TagCooccurs
    | About
    | Defines
)


def create_edge(
    edge_type: str,
    from_id: str,
    to_id: str,
    properties: Optional[dict[str, Any]] = None,
) -> EdgeType:
    """Factory function to create an edge by type name.

    Args:
        edge_type: Name of the edge type (e.g., "RELATES_TO").
        from_id: Source node identifier.
        to_id: Target node identifier.
        properties: Optional dictionary of edge properties.

    Returns:
        Edge instance of the appropriate type.

    Raises:
        ValueError: If edge_type is not recognized.
    """
    props = properties or {}

    edge_classes: dict[str, type] = {
        "RELATES_TO": RelatesTo,
        "SUPERSEDES": Supersedes,
        "CONTRADICTS": Contradicts,
        "SUPPORTS": Supports,
        "DEPENDS_ON": DependsOn,
        "HAS_TAG": HasTag,
        "IN_SCOPE": InScope,
        "TAG_COOCCURS": TagCooccurs,
        "ABOUT": About,
        "DEFINES": Defines,
    }

    edge_class = edge_classes.get(edge_type.upper())
    if edge_class is None:
        raise ValueError(f"Unknown edge type: {edge_type}")

    # Filter properties to only those accepted by the edge class
    if edge_type.upper() == "RELATES_TO":
        return RelatesTo(
            from_id=from_id,
            to_id=to_id,
            weight=props.get("weight", 0.5),
            context=props.get("context"),
        )
    elif edge_type.upper() == "SUPERSEDES":
        return Supersedes(
            from_id=from_id,
            to_id=to_id,
            reason=props.get("reason"),
            superseded_at=props.get("superseded_at"),
        )
    elif edge_type.upper() == "CONTRADICTS":
        return Contradicts(
            from_id=from_id,
            to_id=to_id,
            description=props.get("description"),
            resolution=props.get("resolution"),
        )
    elif edge_type.upper() == "SUPPORTS":
        return Supports(
            from_id=from_id,
            to_id=to_id,
            strength=props.get("strength", 0.5),
        )
    elif edge_type.upper() == "TAG_COOCCURS":
        return TagCooccurs(
            from_id=from_id,
            to_id=to_id,
            count=props.get("count", 0),
            strength=props.get("strength", 0.0),
        )
    elif edge_type.upper() == "ABOUT":
        return About(
            from_id=from_id,
            to_id=to_id,
            relevance=props.get("relevance", 0.5),
        )
    else:
        # Simple edges without additional properties
        return edge_class(from_id=from_id, to_id=to_id)
