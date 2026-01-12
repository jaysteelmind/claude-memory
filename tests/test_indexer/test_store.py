"""Tests for the memory store."""

from datetime import datetime

import pytest

from dmm.core.constants import Confidence, Scope, Status
from dmm.indexer.store import MemoryStore
from dmm.models.memory import MemoryFile
from dmm.models.query import SearchFilters


def create_test_embedding(dimension: int = 384, seed: float = 0.5) -> list[float]:
    """Create a test embedding vector."""
    import math
    return [math.sin(i * seed) for i in range(dimension)]


def create_test_memory(
    memory_id: str,
    path: str,
    scope: Scope = Scope.PROJECT,
    priority: float = 0.5,
    tags: list[str] | None = None,
) -> MemoryFile:
    """Create a test MemoryFile."""
    return MemoryFile(
        id=memory_id,
        path=path,
        title=f"Test Memory {memory_id}",
        body=f"This is test content for memory {memory_id}.",
        token_count=100,
        tags=tags or ["test"],
        scope=scope,
        priority=priority,
        confidence=Confidence.ACTIVE,
        status=Status.ACTIVE,
        created=datetime.now(),
    )


class TestMemoryStore:
    """Tests for MemoryStore."""

    def test_initialize(self, store: MemoryStore) -> None:
        """Store should initialize successfully."""
        # Store is already initialized by fixture
        count = store.get_memory_count()
        assert count == 0

    def test_upsert_memory(self, store: MemoryStore) -> None:
        """Should insert a new memory."""
        memory = create_test_memory("mem_001", "project/test.md")
        composite_emb = create_test_embedding(seed=0.1)
        directory_emb = create_test_embedding(seed=0.2)

        store.upsert_memory(
            memory=memory,
            composite_embedding=composite_emb,
            directory_embedding=directory_emb,
            file_hash="abc123",
        )

        assert store.get_memory_count() == 1

    def test_upsert_memory_update(self, store: MemoryStore) -> None:
        """Should update existing memory."""
        memory = create_test_memory("mem_001", "project/test.md", priority=0.5)
        composite_emb = create_test_embedding(seed=0.1)
        directory_emb = create_test_embedding(seed=0.2)

        store.upsert_memory(
            memory=memory,
            composite_embedding=composite_emb,
            directory_embedding=directory_emb,
            file_hash="abc123",
        )

        # Update with new priority
        memory_updated = create_test_memory("mem_001", "project/test.md", priority=0.9)
        store.upsert_memory(
            memory=memory_updated,
            composite_embedding=composite_emb,
            directory_embedding=directory_emb,
            file_hash="def456",
        )

        assert store.get_memory_count() == 1
        retrieved = store.get_memory("mem_001")
        assert retrieved is not None
        assert retrieved.priority == 0.9

    def test_get_memory(self, store: MemoryStore) -> None:
        """Should retrieve memory by ID."""
        memory = create_test_memory("mem_001", "project/test.md")
        composite_emb = create_test_embedding(seed=0.1)
        directory_emb = create_test_embedding(seed=0.2)

        store.upsert_memory(
            memory=memory,
            composite_embedding=composite_emb,
            directory_embedding=directory_emb,
            file_hash="abc123",
        )

        retrieved = store.get_memory("mem_001")

        assert retrieved is not None
        assert retrieved.id == "mem_001"
        assert retrieved.path == "project/test.md"
        assert retrieved.title == "Test Memory mem_001"

    def test_get_memory_not_found(self, store: MemoryStore) -> None:
        """Should return None for non-existent memory."""
        retrieved = store.get_memory("nonexistent")
        assert retrieved is None

    def test_get_memory_by_path(self, store: MemoryStore) -> None:
        """Should retrieve memory by path."""
        memory = create_test_memory("mem_001", "project/test.md")
        composite_emb = create_test_embedding(seed=0.1)
        directory_emb = create_test_embedding(seed=0.2)

        store.upsert_memory(
            memory=memory,
            composite_embedding=composite_emb,
            directory_embedding=directory_emb,
            file_hash="abc123",
        )

        retrieved = store.get_memory_by_path("project/test.md")

        assert retrieved is not None
        assert retrieved.id == "mem_001"

    def test_delete_memory(self, store: MemoryStore) -> None:
        """Should delete memory by ID."""
        memory = create_test_memory("mem_001", "project/test.md")
        composite_emb = create_test_embedding(seed=0.1)
        directory_emb = create_test_embedding(seed=0.2)

        store.upsert_memory(
            memory=memory,
            composite_embedding=composite_emb,
            directory_embedding=directory_emb,
            file_hash="abc123",
        )

        assert store.get_memory_count() == 1

        deleted = store.delete_memory("mem_001")

        assert deleted is True
        assert store.get_memory_count() == 0

    def test_delete_memory_not_found(self, store: MemoryStore) -> None:
        """Should return False when deleting non-existent memory."""
        deleted = store.delete_memory("nonexistent")
        assert deleted is False

    def test_delete_memory_by_path(self, store: MemoryStore) -> None:
        """Should delete memory by path."""
        memory = create_test_memory("mem_001", "project/test.md")
        composite_emb = create_test_embedding(seed=0.1)
        directory_emb = create_test_embedding(seed=0.2)

        store.upsert_memory(
            memory=memory,
            composite_embedding=composite_emb,
            directory_embedding=directory_emb,
            file_hash="abc123",
        )

        deleted = store.delete_memory_by_path("project/test.md")

        assert deleted is True
        assert store.get_memory_count() == 0

    def test_get_baseline_memories(self, store: MemoryStore) -> None:
        """Should retrieve only baseline memories."""
        # Add baseline memory
        baseline = create_test_memory("mem_baseline", "baseline/identity.md", scope=Scope.BASELINE)
        store.upsert_memory(
            memory=baseline,
            composite_embedding=create_test_embedding(seed=0.1),
            directory_embedding=create_test_embedding(seed=0.2),
            file_hash="abc123",
        )

        # Add project memory
        project = create_test_memory("mem_project", "project/test.md", scope=Scope.PROJECT)
        store.upsert_memory(
            memory=project,
            composite_embedding=create_test_embedding(seed=0.3),
            directory_embedding=create_test_embedding(seed=0.4),
            file_hash="def456",
        )

        baselines = store.get_baseline_memories()

        assert len(baselines) == 1
        assert baselines[0].id == "mem_baseline"
        assert baselines[0].scope == "baseline"

    def test_get_all_memories(self, store: MemoryStore) -> None:
        """Should retrieve all memories."""
        for i in range(5):
            memory = create_test_memory(f"mem_{i:03d}", f"project/test_{i}.md")
            store.upsert_memory(
                memory=memory,
                composite_embedding=create_test_embedding(seed=0.1 * i),
                directory_embedding=create_test_embedding(seed=0.2 * i),
                file_hash=f"hash_{i}",
            )

        all_memories = store.get_all_memories()

        assert len(all_memories) == 5

    def test_get_file_hash(self, store: MemoryStore) -> None:
        """Should retrieve stored file hash."""
        memory = create_test_memory("mem_001", "project/test.md")
        store.upsert_memory(
            memory=memory,
            composite_embedding=create_test_embedding(seed=0.1),
            directory_embedding=create_test_embedding(seed=0.2),
            file_hash="abc123def456",
        )

        file_hash = store.get_file_hash("project/test.md")

        assert file_hash == "abc123def456"

    def test_get_file_hash_not_found(self, store: MemoryStore) -> None:
        """Should return None for non-existent path."""
        file_hash = store.get_file_hash("nonexistent.md")
        assert file_hash is None

    def test_search_by_directory(self, store: MemoryStore) -> None:
        """Should search and rank directories."""
        # Add memories in different directories
        for scope, seed in [("project", 0.1), ("global", 0.3), ("agent", 0.5)]:
            memory = create_test_memory(
                f"mem_{scope}",
                f"{scope}/test.md",
                scope=Scope(scope),
            )
            store.upsert_memory(
                memory=memory,
                composite_embedding=create_test_embedding(seed=seed),
                directory_embedding=create_test_embedding(seed=seed),
                file_hash=f"hash_{scope}",
            )

        query_embedding = create_test_embedding(seed=0.1)
        results = store.search_by_directory(query_embedding, limit=3)

        assert len(results) > 0
        assert all(isinstance(r, tuple) and len(r) == 2 for r in results)
        # Results should be (directory, score) tuples
        for directory, score in results:
            assert isinstance(directory, str)
            assert 0.0 <= score <= 1.0

    def test_search_by_content(self, store: MemoryStore) -> None:
        """Should search content within directories."""
        # Add multiple memories
        for i in range(5):
            memory = create_test_memory(
                f"mem_{i:03d}",
                f"project/test_{i}.md",
                priority=0.5 + (i * 0.1),
            )
            store.upsert_memory(
                memory=memory,
                composite_embedding=create_test_embedding(seed=0.1 * (i + 1)),
                directory_embedding=create_test_embedding(seed=0.2),
                file_hash=f"hash_{i}",
            )

        query_embedding = create_test_embedding(seed=0.15)
        filters = SearchFilters()
        results = store.search_by_content(
            query_embedding=query_embedding,
            directories=["project"],
            filters=filters,
            limit=3,
        )

        assert len(results) <= 3
        assert all(isinstance(r, tuple) and len(r) == 2 for r in results)

    def test_search_by_content_with_filters(self, store: MemoryStore) -> None:
        """Should apply filters during search."""
        # Add active memory
        active = create_test_memory("mem_active", "project/active.md")
        store.upsert_memory(
            memory=active,
            composite_embedding=create_test_embedding(seed=0.1),
            directory_embedding=create_test_embedding(seed=0.2),
            file_hash="hash_active",
        )

        # Add deprecated memory
        deprecated = MemoryFile(
            id="mem_deprecated",
            path="project/deprecated.md",
            title="Deprecated Memory",
            body="This is deprecated.",
            token_count=50,
            tags=["deprecated"],
            scope=Scope.PROJECT,
            priority=0.5,
            confidence=Confidence.DEPRECATED,
            status=Status.DEPRECATED,
        )
        store.upsert_memory(
            memory=deprecated,
            composite_embedding=create_test_embedding(seed=0.15),
            directory_embedding=create_test_embedding(seed=0.2),
            file_hash="hash_deprecated",
        )

        query_embedding = create_test_embedding(seed=0.1)
        filters = SearchFilters(exclude_deprecated=True)
        results = store.search_by_content(
            query_embedding=query_embedding,
            directories=None,
            filters=filters,
            limit=10,
        )

        # Should not include deprecated memory
        result_ids = [r[0].id for r in results]
        assert "mem_deprecated" not in result_ids

    def test_get_all_directories(self, store: MemoryStore) -> None:
        """Should retrieve directory statistics."""
        # Add memories in different directories
        for scope in ["project", "global", "agent"]:
            memory = create_test_memory(
                f"mem_{scope}",
                f"{scope}/test.md",
                scope=Scope(scope),
            )
            store.upsert_memory(
                memory=memory,
                composite_embedding=create_test_embedding(seed=0.1),
                directory_embedding=create_test_embedding(seed=0.2),
                file_hash=f"hash_{scope}",
            )

        directories = store.get_all_directories()

        assert len(directories) == 3
        dir_paths = [d.path for d in directories]
        assert "project" in dir_paths
        assert "global" in dir_paths
        assert "agent" in dir_paths

    def test_system_meta(self, store: MemoryStore) -> None:
        """Should store and retrieve system metadata."""
        store.set_system_meta("test_key", "test_value")

        value = store.get_system_meta("test_key")

        assert value == "test_value"

    def test_system_meta_update(self, store: MemoryStore) -> None:
        """Should update existing metadata."""
        store.set_system_meta("test_key", "value1")
        store.set_system_meta("test_key", "value2")

        value = store.get_system_meta("test_key")

        assert value == "value2"

    def test_clear_all(self, store: MemoryStore) -> None:
        """Should clear all memories."""
        for i in range(3):
            memory = create_test_memory(f"mem_{i:03d}", f"project/test_{i}.md")
            store.upsert_memory(
                memory=memory,
                composite_embedding=create_test_embedding(seed=0.1 * i),
                directory_embedding=create_test_embedding(seed=0.2 * i),
                file_hash=f"hash_{i}",
            )

        assert store.get_memory_count() == 3

        store.clear_all()

        assert store.get_memory_count() == 0
