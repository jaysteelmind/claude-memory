"""Unit tests for KnowledgeGraphStore."""

import pytest
import tempfile
from pathlib import Path

from dmm.graph.store import KnowledgeGraphStore, GraphStats
from dmm.graph.nodes import MemoryNode, TagNode, ScopeNode


@pytest.fixture
def temp_graph_path():
    """Create a temporary path for graph database (Kuzu creates the directory)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Return path to a subdirectory that doesn't exist yet
        # Kuzu will create it
        yield Path(tmpdir) / "graph_db"


@pytest.fixture
def graph_store(temp_graph_path):
    """Create an initialized graph store for testing."""
    store = KnowledgeGraphStore(temp_graph_path)
    store.initialize()
    yield store
    store.close()


class TestKnowledgeGraphStoreInitialization:
    """Tests for store initialization."""

    def test_initialize_creates_database(self, temp_graph_path) -> None:
        """Test that initialization creates the database directory."""
        store = KnowledgeGraphStore(temp_graph_path)
        store.initialize()

        assert temp_graph_path.exists()
        assert store.is_initialized

        store.close()

    def test_initialize_is_idempotent(self, graph_store) -> None:
        """Test that calling initialize multiple times is safe."""
        graph_store.initialize()
        graph_store.initialize()

        assert graph_store.is_initialized

    def test_close_clears_state(self, temp_graph_path) -> None:
        """Test that close clears the initialized state."""
        store = KnowledgeGraphStore(temp_graph_path)
        store.initialize()
        store.close()

        assert not store.is_initialized

    def test_operations_require_initialization(self, temp_graph_path) -> None:
        """Test that operations fail without initialization."""
        store = KnowledgeGraphStore(temp_graph_path)

        with pytest.raises(RuntimeError, match="not initialized"):
            store.get_stats()


class TestMemoryNodeOperations:
    """Tests for memory node CRUD operations."""

    def test_upsert_and_get_memory_node(self, graph_store) -> None:
        """Test creating and retrieving a memory node."""
        node = MemoryNode(
            id="mem_2026_01_20_001",
            path="project/auth.md",
            directory="project",
            title="Authentication",
            scope="project",
            priority=0.8,
            confidence="stable",
            status="active",
            token_count=450,
        )

        graph_store.upsert_memory_node(node)
        retrieved = graph_store.get_memory_node("mem_2026_01_20_001")

        assert retrieved is not None
        assert retrieved.id == "mem_2026_01_20_001"
        assert retrieved.title == "Authentication"
        assert retrieved.priority == 0.8

    def test_upsert_updates_existing_node(self, graph_store) -> None:
        """Test that upsert updates an existing node."""
        node = MemoryNode(
            id="mem_001",
            path="test.md",
            directory="project",
            title="Original Title",
            scope="project",
            priority=0.5,
            confidence="active",
            status="active",
            token_count=100,
        )
        graph_store.upsert_memory_node(node)

        # Update the node
        node.title = "Updated Title"
        node.priority = 0.9
        graph_store.upsert_memory_node(node)

        retrieved = graph_store.get_memory_node("mem_001")
        assert retrieved.title == "Updated Title"
        assert retrieved.priority == 0.9

    def test_get_nonexistent_memory_returns_none(self, graph_store) -> None:
        """Test that getting a nonexistent memory returns None."""
        result = graph_store.get_memory_node("nonexistent_id")
        assert result is None

    def test_delete_memory_node(self, graph_store) -> None:
        """Test deleting a memory node."""
        node = MemoryNode(
            id="mem_to_delete",
            path="test.md",
            directory="project",
            title="To Delete",
            scope="project",
            priority=0.5,
            confidence="active",
            status="active",
            token_count=100,
        )
        graph_store.upsert_memory_node(node)

        result = graph_store.delete_memory_node("mem_to_delete")
        assert result is True

        retrieved = graph_store.get_memory_node("mem_to_delete")
        assert retrieved is None

    def test_delete_nonexistent_memory_returns_false(self, graph_store) -> None:
        """Test deleting nonexistent memory returns False."""
        result = graph_store.delete_memory_node("nonexistent")
        assert result is False

    def test_get_all_memory_nodes(self, graph_store) -> None:
        """Test retrieving all memory nodes."""
        for i in range(3):
            node = MemoryNode(
                id=f"mem_{i:03d}",
                path=f"test{i}.md",
                directory="project",
                title=f"Memory {i}",
                scope="project",
                priority=0.5,
                confidence="active",
                status="active",
                token_count=100,
            )
            graph_store.upsert_memory_node(node)

        all_nodes = graph_store.get_all_memory_nodes()
        assert len(all_nodes) == 3


class TestTagNodeOperations:
    """Tests for tag node operations."""

    def test_upsert_and_get_tag_node(self, graph_store) -> None:
        """Test creating and retrieving a tag node."""
        node = TagNode(
            id="tag_security",
            name="security",
            normalized="security",
            usage_count=5,
        )

        graph_store.upsert_tag_node(node)
        retrieved = graph_store.get_tag_node("tag_security")

        assert retrieved is not None
        assert retrieved.name == "security"
        assert retrieved.usage_count == 5

    def test_get_all_tag_nodes(self, graph_store) -> None:
        """Test retrieving all tag nodes."""
        tags = ["auth", "api", "database"]
        for tag in tags:
            node = TagNode.from_tag_name(tag)
            graph_store.upsert_tag_node(node)

        all_tags = graph_store.get_all_tag_nodes()
        assert len(all_tags) == 3


class TestScopeNodeOperations:
    """Tests for scope node operations."""

    def test_upsert_and_get_scope_node(self, graph_store) -> None:
        """Test creating and retrieving a scope node."""
        node = ScopeNode(
            id="scope_project",
            name="project",
            description="Project-specific memories",
            memory_count=10,
            token_total=5000,
        )

        graph_store.upsert_scope_node(node)
        retrieved = graph_store.get_scope_node("scope_project")

        assert retrieved is not None
        assert retrieved.name == "project"
        assert retrieved.memory_count == 10


class TestEdgeOperations:
    """Tests for edge/relationship operations."""

    def test_create_edge(self, graph_store) -> None:
        """Test creating an edge between nodes."""
        # Create two memory nodes
        node1 = MemoryNode(
            id="mem_001", path="test1.md", directory="project",
            title="Memory 1", scope="project", priority=0.5,
            confidence="active", status="active", token_count=100,
        )
        node2 = MemoryNode(
            id="mem_002", path="test2.md", directory="project",
            title="Memory 2", scope="project", priority=0.5,
            confidence="active", status="active", token_count=100,
        )
        graph_store.upsert_memory_node(node1)
        graph_store.upsert_memory_node(node2)

        # Create edge
        result = graph_store.create_edge(
            "RELATES_TO",
            "mem_001",
            "mem_002",
            {"weight": 0.8, "context": "Test relationship"},
        )

        assert result is True

    def test_edge_exists(self, graph_store) -> None:
        """Test checking if an edge exists."""
        # Create nodes
        node1 = MemoryNode(
            id="mem_001", path="test1.md", directory="project",
            title="Memory 1", scope="project", priority=0.5,
            confidence="active", status="active", token_count=100,
        )
        node2 = MemoryNode(
            id="mem_002", path="test2.md", directory="project",
            title="Memory 2", scope="project", priority=0.5,
            confidence="active", status="active", token_count=100,
        )
        graph_store.upsert_memory_node(node1)
        graph_store.upsert_memory_node(node2)

        # No edge yet
        assert not graph_store.edge_exists("RELATES_TO", "mem_001", "mem_002")

        # Create edge
        graph_store.create_edge("RELATES_TO", "mem_001", "mem_002")

        # Edge exists now
        assert graph_store.edge_exists("RELATES_TO", "mem_001", "mem_002")

    def test_get_edges_from(self, graph_store) -> None:
        """Test getting outgoing edges from a node."""
        # Create nodes
        for i in range(3):
            node = MemoryNode(
                id=f"mem_{i:03d}", path=f"test{i}.md", directory="project",
                title=f"Memory {i}", scope="project", priority=0.5,
                confidence="active", status="active", token_count=100,
            )
            graph_store.upsert_memory_node(node)

        # Create edges from mem_000
        graph_store.create_edge("RELATES_TO", "mem_000", "mem_001", {"weight": 0.8})
        graph_store.create_edge("RELATES_TO", "mem_000", "mem_002", {"weight": 0.6})

        edges = graph_store.get_edges_from("mem_000", edge_type="RELATES_TO")
        assert len(edges) == 2

    def test_delete_edge(self, graph_store) -> None:
        """Test deleting an edge."""
        # Create nodes and edge
        node1 = MemoryNode(
            id="mem_001", path="test1.md", directory="project",
            title="Memory 1", scope="project", priority=0.5,
            confidence="active", status="active", token_count=100,
        )
        node2 = MemoryNode(
            id="mem_002", path="test2.md", directory="project",
            title="Memory 2", scope="project", priority=0.5,
            confidence="active", status="active", token_count=100,
        )
        graph_store.upsert_memory_node(node1)
        graph_store.upsert_memory_node(node2)
        graph_store.create_edge("RELATES_TO", "mem_001", "mem_002")

        # Delete edge
        result = graph_store.delete_edge("RELATES_TO", "mem_001", "mem_002")
        assert result is True

        # Verify edge is gone
        assert not graph_store.edge_exists("RELATES_TO", "mem_001", "mem_002")


class TestGraphTraversal:
    """Tests for graph traversal operations."""

    def test_get_related_memories(self, graph_store) -> None:
        """Test finding related memories via traversal."""
        # Create a chain: mem_000 -> mem_001 -> mem_002
        for i in range(3):
            node = MemoryNode(
                id=f"mem_{i:03d}", path=f"test{i}.md", directory="project",
                title=f"Memory {i}", scope="project", priority=0.5,
                confidence="active", status="active", token_count=100,
            )
            graph_store.upsert_memory_node(node)

        graph_store.create_edge("RELATES_TO", "mem_000", "mem_001", {"weight": 1.0})
        graph_store.create_edge("RELATES_TO", "mem_001", "mem_002", {"weight": 1.0})

        # Depth 1 should find mem_001
        related_d1 = graph_store.get_related_memories("mem_000", max_depth=1)
        assert len(related_d1) >= 1
        related_ids = {m.id for m in related_d1}
        assert "mem_001" in related_ids

    def test_get_tags_for_memory(self, graph_store) -> None:
        """Test getting tags associated with a memory."""
        # Create memory and tags
        memory = MemoryNode(
            id="mem_001", path="test.md", directory="project",
            title="Memory", scope="project", priority=0.5,
            confidence="active", status="active", token_count=100,
        )
        graph_store.upsert_memory_node(memory)

        tag1 = TagNode.from_tag_name("security")
        tag2 = TagNode.from_tag_name("api")
        graph_store.upsert_tag_node(tag1)
        graph_store.upsert_tag_node(tag2)

        # Create HAS_TAG edges
        graph_store.create_edge("HAS_TAG", "mem_001", tag1.id)
        graph_store.create_edge("HAS_TAG", "mem_001", tag2.id)

        tags = graph_store.get_tags_for_memory("mem_001")
        assert len(tags) == 2
        tag_names = {t.name for t in tags}
        assert "security" in tag_names
        assert "api" in tag_names


class TestGraphStatistics:
    """Tests for graph statistics."""

    def test_get_stats_empty_graph(self, graph_store) -> None:
        """Test getting stats from empty graph."""
        stats = graph_store.get_stats()

        assert isinstance(stats, GraphStats)
        assert stats.memory_count == 0
        assert stats.tag_count == 0
        assert stats.edge_count == 0

    def test_get_stats_with_data(self, graph_store) -> None:
        """Test getting stats from populated graph."""
        # Add nodes
        for i in range(5):
            node = MemoryNode(
                id=f"mem_{i:03d}", path=f"test{i}.md", directory="project",
                title=f"Memory {i}", scope="project", priority=0.5,
                confidence="active", status="active", token_count=100,
            )
            graph_store.upsert_memory_node(node)

        for tag in ["a", "b", "c"]:
            graph_store.upsert_tag_node(TagNode.from_tag_name(tag))

        stats = graph_store.get_stats()

        assert stats.memory_count == 5
        assert stats.tag_count == 3


class TestCypherExecution:
    """Tests for raw Cypher query execution."""

    def test_execute_cypher_query(self, graph_store) -> None:
        """Test executing a raw Cypher query."""
        # Add a memory
        node = MemoryNode(
            id="mem_001", path="test.md", directory="project",
            title="Test Memory", scope="project", priority=0.5,
            confidence="active", status="active", token_count=100,
        )
        graph_store.upsert_memory_node(node)

        # Query it
        results = graph_store.execute_cypher(
            "MATCH (m:Memory) RETURN m.id, m.title"
        )

        assert len(results) == 1
        assert results[0]["m.id"] == "mem_001"
        assert results[0]["m.title"] == "Test Memory"

    def test_execute_cypher_with_params(self, graph_store) -> None:
        """Test executing Cypher with parameters."""
        node = MemoryNode(
            id="mem_001", path="test.md", directory="project",
            title="Test", scope="project", priority=0.5,
            confidence="active", status="active", token_count=100,
        )
        graph_store.upsert_memory_node(node)

        results = graph_store.execute_cypher(
            "MATCH (m:Memory {id: $id}) RETURN m.title",
            {"id": "mem_001"},
        )

        assert len(results) == 1
        assert results[0]["m.title"] == "Test"
