"""Unit tests for graph node classes."""

import pytest
from datetime import datetime

from dmm.graph.nodes import (
    MemoryNode,
    TagNode,
    ScopeNode,
    ConceptNode,
    SCOPE_DEFINITIONS,
    create_all_scope_nodes,
)


class TestMemoryNode:
    """Tests for MemoryNode class."""

    def test_create_memory_node(self) -> None:
        """Test creating a MemoryNode with all fields."""
        node = MemoryNode(
            id="mem_2026_01_20_001",
            path="project/auth.md",
            directory="project",
            title="Authentication Patterns",
            scope="project",
            priority=0.8,
            confidence="stable",
            status="active",
            token_count=450,
            created=datetime(2026, 1, 20),
            usage_count=5,
        )

        assert node.id == "mem_2026_01_20_001"
        assert node.path == "project/auth.md"
        assert node.directory == "project"
        assert node.title == "Authentication Patterns"
        assert node.scope == "project"
        assert node.priority == 0.8
        assert node.confidence == "stable"
        assert node.status == "active"
        assert node.token_count == 450
        assert node.usage_count == 5

    def test_memory_node_to_dict(self) -> None:
        """Test converting MemoryNode to dictionary."""
        node = MemoryNode(
            id="mem_001",
            path="test.md",
            directory="project",
            title="Test",
            scope="project",
            priority=0.5,
            confidence="active",
            status="active",
            token_count=100,
        )

        d = node.to_dict()

        assert d["id"] == "mem_001"
        assert d["path"] == "test.md"
        assert d["priority"] == 0.5
        assert "created" in d
        assert "indexed_at" in d

    def test_memory_node_from_dict(self) -> None:
        """Test creating MemoryNode from dictionary."""
        data = {
            "id": "mem_002",
            "path": "global/standards.md",
            "directory": "global",
            "title": "Coding Standards",
            "scope": "global",
            "priority": 0.9,
            "confidence": "stable",
            "status": "active",
            "token_count": 350,
        }

        node = MemoryNode.from_dict(data)

        assert node.id == "mem_002"
        assert node.scope == "global"
        assert node.priority == 0.9

    def test_memory_node_from_dict_defaults(self) -> None:
        """Test that from_dict provides sensible defaults."""
        data = {"id": "mem_003"}

        node = MemoryNode.from_dict(data)

        assert node.id == "mem_003"
        assert node.scope == "project"  # Default
        assert node.priority == 0.5  # Default
        assert node.confidence == "active"  # Default
        assert node.status == "active"  # Default
        assert node.token_count == 0  # Default


class TestTagNode:
    """Tests for TagNode class."""

    def test_create_tag_node(self) -> None:
        """Test creating a TagNode."""
        node = TagNode(
            id="tag_authentication",
            name="authentication",
            normalized="authentication",
            usage_count=10,
        )

        assert node.id == "tag_authentication"
        assert node.name == "authentication"
        assert node.normalized == "authentication"
        assert node.usage_count == 10

    def test_tag_node_from_tag_name(self) -> None:
        """Test creating TagNode from a tag name string."""
        node = TagNode.from_tag_name("API Design")

        assert node.id == "tag_api_design"
        assert node.name == "API Design"
        assert node.normalized == "api design"
        assert node.usage_count == 0

    def test_tag_node_from_tag_name_with_special_chars(self) -> None:
        """Test tag normalization handles special characters."""
        node = TagNode.from_tag_name("  Error-Handling  ")

        assert node.id == "tag_error_handling"
        assert node.normalized == "error-handling"

    def test_tag_node_to_dict(self) -> None:
        """Test converting TagNode to dictionary."""
        node = TagNode.from_tag_name("security")
        node.usage_count = 5

        d = node.to_dict()

        assert d["id"] == "tag_security"
        assert d["name"] == "security"
        assert d["usage_count"] == 5

    def test_tag_node_from_dict(self) -> None:
        """Test creating TagNode from dictionary."""
        data = {
            "id": "tag_testing",
            "name": "Testing",
            "normalized": "testing",
            "usage_count": 15,
        }

        node = TagNode.from_dict(data)

        assert node.id == "tag_testing"
        assert node.usage_count == 15


class TestScopeNode:
    """Tests for ScopeNode class."""

    def test_create_scope_node(self) -> None:
        """Test creating a ScopeNode."""
        node = ScopeNode(
            id="scope_project",
            name="project",
            description="Project-specific decisions",
            memory_count=25,
            token_total=12500,
        )

        assert node.id == "scope_project"
        assert node.name == "project"
        assert node.memory_count == 25
        assert node.token_total == 12500

    def test_scope_node_from_scope_name(self) -> None:
        """Test creating ScopeNode from scope name."""
        node = ScopeNode.from_scope_name("baseline")

        assert node.id == "scope_baseline"
        assert node.name == "baseline"
        assert "always included" in node.description.lower()
        assert node.memory_count == 0
        assert node.token_total == 0

    def test_scope_node_from_unknown_scope(self) -> None:
        """Test creating ScopeNode from unknown scope name."""
        node = ScopeNode.from_scope_name("custom")

        assert node.id == "scope_custom"
        assert node.name == "custom"
        assert "custom" in node.description.lower()

    def test_scope_node_to_dict(self) -> None:
        """Test converting ScopeNode to dictionary."""
        node = ScopeNode.from_scope_name("global")
        node.memory_count = 10

        d = node.to_dict()

        assert d["id"] == "scope_global"
        assert d["memory_count"] == 10


class TestConceptNode:
    """Tests for ConceptNode class."""

    def test_create_concept_node(self) -> None:
        """Test creating a ConceptNode."""
        node = ConceptNode(
            id="concept_oauth",
            name="OAuth 2.0",
            definition="Authorization framework for secure API access",
            source_count=3,
        )

        assert node.id == "concept_oauth"
        assert node.name == "OAuth 2.0"
        assert "Authorization" in node.definition
        assert node.source_count == 3

    def test_concept_node_to_dict(self) -> None:
        """Test converting ConceptNode to dictionary."""
        node = ConceptNode(
            id="concept_rest",
            name="REST",
            source_count=5,
        )

        d = node.to_dict()

        assert d["id"] == "concept_rest"
        assert d["name"] == "REST"
        assert d["definition"] is None
        assert d["source_count"] == 5


class TestScopeDefinitions:
    """Tests for scope definitions and helpers."""

    def test_scope_definitions_exist(self) -> None:
        """Test that all expected scopes are defined."""
        expected_scopes = ["baseline", "global", "agent", "project", "ephemeral", "deprecated"]

        for scope in expected_scopes:
            assert scope in SCOPE_DEFINITIONS
            assert len(SCOPE_DEFINITIONS[scope]) > 0

    def test_create_all_scope_nodes(self) -> None:
        """Test creating all scope nodes."""
        nodes = create_all_scope_nodes()

        assert len(nodes) == len(SCOPE_DEFINITIONS)

        names = {n.name for n in nodes}
        assert "baseline" in names
        assert "project" in names
        assert "deprecated" in names
