"""Unit tests for graph edge classes."""

import pytest
from datetime import datetime

from dmm.graph.edges import (
    Edge,
    RelatesTo,
    Supersedes,
    Contradicts,
    Supports,
    DependsOn,
    HasTag,
    InScope,
    TagCooccurs,
    About,
    Defines,
    create_edge,
)


class TestEdgeBase:
    """Tests for Edge base class."""

    def test_edge_to_cypher_params(self) -> None:
        """Test base edge Cypher parameter conversion."""
        edge = Edge(
            edge_type="TEST",
            from_id="node_001",
            to_id="node_002",
        )

        params = edge.to_cypher_params()

        assert params["from_id"] == "node_001"
        assert params["to_id"] == "node_002"

    def test_edge_to_dict(self) -> None:
        """Test base edge dictionary conversion."""
        edge = Edge(
            edge_type="TEST",
            from_id="node_001",
            to_id="node_002",
        )

        d = edge.to_dict()

        assert d["edge_type"] == "TEST"
        assert d["from_id"] == "node_001"
        assert d["to_id"] == "node_002"


class TestRelatesTo:
    """Tests for RelatesTo edge class."""

    def test_create_relates_to(self) -> None:
        """Test creating a RelatesTo edge."""
        edge = RelatesTo(
            from_id="mem_001",
            to_id="mem_002",
            weight=0.85,
            context="Both discuss authentication",
        )

        assert edge.edge_type == "RELATES_TO"
        assert edge.from_id == "mem_001"
        assert edge.to_id == "mem_002"
        assert edge.weight == 0.85
        assert edge.context == "Both discuss authentication"

    def test_relates_to_default_weight(self) -> None:
        """Test RelatesTo default weight."""
        edge = RelatesTo(from_id="mem_001", to_id="mem_002")

        assert edge.weight == 0.5
        assert edge.context is None

    def test_relates_to_cypher_params(self) -> None:
        """Test RelatesTo Cypher parameters."""
        edge = RelatesTo(
            from_id="mem_001",
            to_id="mem_002",
            weight=0.9,
            context="Test context",
        )

        params = edge.to_cypher_params()

        assert params["from_id"] == "mem_001"
        assert params["to_id"] == "mem_002"
        assert params["weight"] == 0.9
        assert params["context"] == "Test context"


class TestSupersedes:
    """Tests for Supersedes edge class."""

    def test_create_supersedes(self) -> None:
        """Test creating a Supersedes edge."""
        edge = Supersedes(
            from_id="mem_002",
            to_id="mem_001",
            reason="Updated API version",
        )

        assert edge.edge_type == "SUPERSEDES"
        assert edge.from_id == "mem_002"
        assert edge.to_id == "mem_001"
        assert edge.reason == "Updated API version"
        assert edge.superseded_at is not None

    def test_supersedes_auto_timestamp(self) -> None:
        """Test Supersedes auto-generates timestamp."""
        before = datetime.now()
        edge = Supersedes(from_id="mem_002", to_id="mem_001")
        after = datetime.now()

        assert edge.superseded_at is not None
        assert before <= edge.superseded_at <= after

    def test_supersedes_explicit_timestamp(self) -> None:
        """Test Supersedes with explicit timestamp."""
        timestamp = datetime(2026, 1, 15, 10, 30, 0)
        edge = Supersedes(
            from_id="mem_002",
            to_id="mem_001",
            superseded_at=timestamp,
        )

        assert edge.superseded_at == timestamp


class TestContradicts:
    """Tests for Contradicts edge class."""

    def test_create_contradicts(self) -> None:
        """Test creating a Contradicts edge."""
        edge = Contradicts(
            from_id="mem_001",
            to_id="mem_003",
            description="Conflicting database recommendations",
            resolution="Kept newer memory",
        )

        assert edge.edge_type == "CONTRADICTS"
        assert edge.description == "Conflicting database recommendations"
        assert edge.resolution == "Kept newer memory"

    def test_contradicts_no_resolution(self) -> None:
        """Test Contradicts without resolution."""
        edge = Contradicts(
            from_id="mem_001",
            to_id="mem_003",
            description="Unresolved conflict",
        )

        assert edge.resolution is None

    def test_contradicts_cypher_params(self) -> None:
        """Test Contradicts Cypher parameters."""
        edge = Contradicts(
            from_id="mem_001",
            to_id="mem_002",
            description="Test conflict",
        )

        params = edge.to_cypher_params()

        assert params["description"] == "Test conflict"
        assert params["resolution"] == ""


class TestSupports:
    """Tests for Supports edge class."""

    def test_create_supports(self) -> None:
        """Test creating a Supports edge."""
        edge = Supports(
            from_id="mem_evidence",
            to_id="mem_claim",
            strength=0.95,
        )

        assert edge.edge_type == "SUPPORTS"
        assert edge.strength == 0.95

    def test_supports_default_strength(self) -> None:
        """Test Supports default strength."""
        edge = Supports(from_id="mem_001", to_id="mem_002")

        assert edge.strength == 0.5


class TestDependsOn:
    """Tests for DependsOn edge class."""

    def test_create_depends_on(self) -> None:
        """Test creating a DependsOn edge."""
        edge = DependsOn(
            from_id="mem_advanced",
            to_id="mem_basic",
        )

        assert edge.edge_type == "DEPENDS_ON"
        assert edge.from_id == "mem_advanced"
        assert edge.to_id == "mem_basic"


class TestHasTag:
    """Tests for HasTag edge class."""

    def test_create_has_tag(self) -> None:
        """Test creating a HasTag edge."""
        edge = HasTag(
            from_id="mem_001",
            to_id="tag_security",
        )

        assert edge.edge_type == "HAS_TAG"
        assert edge.from_id == "mem_001"
        assert edge.to_id == "tag_security"


class TestInScope:
    """Tests for InScope edge class."""

    def test_create_in_scope(self) -> None:
        """Test creating an InScope edge."""
        edge = InScope(
            from_id="mem_001",
            to_id="scope_project",
        )

        assert edge.edge_type == "IN_SCOPE"
        assert edge.to_id == "scope_project"


class TestTagCooccurs:
    """Tests for TagCooccurs edge class."""

    def test_create_tag_cooccurs(self) -> None:
        """Test creating a TagCooccurs edge."""
        edge = TagCooccurs(
            from_id="tag_auth",
            to_id="tag_security",
            count=15,
            strength=0.75,
        )

        assert edge.edge_type == "TAG_COOCCURS"
        assert edge.count == 15
        assert edge.strength == 0.75

    def test_tag_cooccurs_defaults(self) -> None:
        """Test TagCooccurs default values."""
        edge = TagCooccurs(from_id="tag_a", to_id="tag_b")

        assert edge.count == 0
        assert edge.strength == 0.0


class TestAbout:
    """Tests for About edge class."""

    def test_create_about(self) -> None:
        """Test creating an About edge."""
        edge = About(
            from_id="mem_001",
            to_id="concept_oauth",
            relevance=0.9,
        )

        assert edge.edge_type == "ABOUT"
        assert edge.relevance == 0.9


class TestDefines:
    """Tests for Defines edge class."""

    def test_create_defines(self) -> None:
        """Test creating a Defines edge."""
        edge = Defines(
            from_id="mem_glossary",
            to_id="concept_api",
        )

        assert edge.edge_type == "DEFINES"


class TestCreateEdgeFactory:
    """Tests for the create_edge factory function."""

    def test_create_relates_to_edge(self) -> None:
        """Test factory creates RelatesTo edge."""
        edge = create_edge(
            "RELATES_TO",
            "mem_001",
            "mem_002",
            {"weight": 0.8, "context": "Test"},
        )

        assert isinstance(edge, RelatesTo)
        assert edge.weight == 0.8
        assert edge.context == "Test"

    def test_create_supersedes_edge(self) -> None:
        """Test factory creates Supersedes edge."""
        edge = create_edge(
            "SUPERSEDES",
            "mem_002",
            "mem_001",
            {"reason": "Updated"},
        )

        assert isinstance(edge, Supersedes)
        assert edge.reason == "Updated"

    def test_create_contradicts_edge(self) -> None:
        """Test factory creates Contradicts edge."""
        edge = create_edge(
            "CONTRADICTS",
            "mem_001",
            "mem_002",
            {"description": "Conflict"},
        )

        assert isinstance(edge, Contradicts)
        assert edge.description == "Conflict"

    def test_create_simple_edge(self) -> None:
        """Test factory creates simple edges without properties."""
        edge = create_edge("HAS_TAG", "mem_001", "tag_001")

        assert isinstance(edge, HasTag)
        assert edge.from_id == "mem_001"
        assert edge.to_id == "tag_001"

    def test_create_edge_case_insensitive(self) -> None:
        """Test factory handles case-insensitive edge types."""
        edge = create_edge("relates_to", "mem_001", "mem_002")

        assert isinstance(edge, RelatesTo)

    def test_create_edge_unknown_type(self) -> None:
        """Test factory raises error for unknown edge type."""
        with pytest.raises(ValueError, match="Unknown edge type"):
            create_edge("UNKNOWN_TYPE", "a", "b")

    def test_create_tag_cooccurs_edge(self) -> None:
        """Test factory creates TagCooccurs edge."""
        edge = create_edge(
            "TAG_COOCCURS",
            "tag_a",
            "tag_b",
            {"count": 10, "strength": 0.5},
        )

        assert isinstance(edge, TagCooccurs)
        assert edge.count == 10
        assert edge.strength == 0.5
