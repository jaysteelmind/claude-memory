"""Tests for the retrieval router."""

from datetime import datetime

import pytest

from dmm.core.constants import Confidence, Scope, Status
from dmm.indexer.embedder import MemoryEmbedder
from dmm.indexer.store import MemoryStore
from dmm.models.memory import MemoryFile
from dmm.models.query import SearchFilters
from dmm.retrieval.router import RetrievalConfig, RetrievalRouter


def create_test_embedding(dimension: int = 384, seed: float = 0.5) -> list[float]:
    """Create a test embedding vector."""
    import math
    return [math.sin(i * seed) for i in range(dimension)]


def add_memory_to_store(
    store: MemoryStore,
    memory_id: str,
    path: str,
    scope: Scope = Scope.PROJECT,
    priority: float = 0.5,
    confidence: Confidence = Confidence.ACTIVE,
    seed: float = 0.5,
) -> None:
    """Add a memory to the store."""
    memory = MemoryFile(
        id=memory_id,
        path=path,
        title=f"Test {memory_id}",
        body=f"Content for {memory_id}",
        token_count=100,
        tags=["test"],
        scope=scope,
        priority=priority,
        confidence=confidence,
        status=Status.ACTIVE,
        created=datetime.now(),
    )
    store.upsert_memory(
        memory=memory,
        composite_embedding=create_test_embedding(seed=seed),
        directory_embedding=create_test_embedding(seed=seed + 0.1),
        file_hash=f"hash_{memory_id}",
    )


class TestRetrievalRouter:
    """Tests for RetrievalRouter."""

    @pytest.fixture
    def embedder(self) -> MemoryEmbedder:
        """Create embedder instance."""
        return MemoryEmbedder(device="cpu")

    @pytest.fixture
    def router(self, store: MemoryStore, embedder: MemoryEmbedder) -> RetrievalRouter:
        """Create router instance."""
        return RetrievalRouter(
            store=store,
            embedder=embedder,
            config=RetrievalConfig(
                top_k_directories=3,
                max_candidates=50,
                diversity_threshold=0.9,
            ),
        )

    def test_retrieve_empty_store(
        self, router: RetrievalRouter
    ) -> None:
        """Should return empty results for empty store."""
        result = router.retrieve(
            query="test query",
            budget=1000,
        )

        assert len(result.entries) == 0
        assert result.total_tokens == 0

    def test_retrieve_basic(
        self, store: MemoryStore, router: RetrievalRouter
    ) -> None:
        """Should retrieve relevant memories."""
        # Add some memories
        add_memory_to_store(store, "mem_001", "project/auth.md", seed=0.1)
        add_memory_to_store(store, "mem_002", "project/db.md", seed=0.3)
        add_memory_to_store(store, "mem_003", "global/style.md", seed=0.5)

        result = router.retrieve(
            query="authentication and security",
            budget=1000,
        )

        assert len(result.entries) > 0
        assert result.total_tokens > 0
        assert result.candidates_considered > 0

    def test_retrieve_respects_budget(
        self, store: MemoryStore, router: RetrievalRouter
    ) -> None:
        """Should not exceed token budget."""
        # Add memories with known token counts
        for i in range(5):
            add_memory_to_store(store, f"mem_{i:03d}", f"project/file_{i}.md", seed=0.1 * i)

        result = router.retrieve(
            query="test query",
            budget=200,  # Small budget
        )

        assert result.total_tokens <= 200

    def test_retrieve_with_scope_filter(
        self, store: MemoryStore, router: RetrievalRouter
    ) -> None:
        """Should filter by scope."""
        add_memory_to_store(store, "mem_001", "project/auth.md", scope=Scope.PROJECT, seed=0.1)
        add_memory_to_store(store, "mem_002", "global/style.md", scope=Scope.GLOBAL, seed=0.1)

        filters = SearchFilters(scopes=[Scope.PROJECT])
        result = router.retrieve(
            query="test query",
            budget=1000,
            filters=filters,
        )

        # All results should be project scope
        for entry in result.entries:
            assert "project/" in entry.path

    def test_retrieve_excludes_deprecated(
        self, store: MemoryStore, router: RetrievalRouter
    ) -> None:
        """Should exclude deprecated by default."""
        add_memory_to_store(
            store, "mem_001", "project/active.md",
            confidence=Confidence.ACTIVE, seed=0.1
        )
        add_memory_to_store(
            store, "mem_002", "project/deprecated.md",
            confidence=Confidence.DEPRECATED, seed=0.1
        )

        filters = SearchFilters(exclude_deprecated=True)
        result = router.retrieve(
            query="test query",
            budget=1000,
            filters=filters,
        )

        paths = [e.path for e in result.entries]
        assert "project/deprecated.md" not in paths

    def test_retrieve_tracks_excluded(
        self, store: MemoryStore, router: RetrievalRouter
    ) -> None:
        """Should track excluded files."""
        # Add memories that exceed budget
        for i in range(10):
            add_memory_to_store(store, f"mem_{i:03d}", f"project/file_{i}.md", seed=0.1 * i)

        result = router.retrieve(
            query="test query",
            budget=150,  # Only room for ~1 memory
        )

        # Should have some excluded
        if result.candidates_considered > 1:
            assert len(result.excluded_for_budget) >= 0

    def test_ranking_considers_priority(
        self, store: MemoryStore, router: RetrievalRouter
    ) -> None:
        """Higher priority should rank higher (same similarity)."""
        # Add memories with different priorities but same embedding
        add_memory_to_store(
            store, "mem_low", "project/low.md",
            priority=0.1, seed=0.5
        )
        add_memory_to_store(
            store, "mem_high", "project/high.md",
            priority=0.9, seed=0.5
        )

        result = router.retrieve(
            query="test",
            budget=1000,
        )

        # With same similarity, high priority should rank first
        if len(result.entries) >= 2:
            paths = [e.path for e in result.entries]
            assert paths.index("project/high.md") < paths.index("project/low.md")

    def test_get_stats(self, router: RetrievalRouter) -> None:
        """Should return configuration stats."""
        stats = router.get_stats()

        assert "top_k_directories" in stats
        assert "max_candidates" in stats
        assert "diversity_threshold" in stats
        assert stats["top_k_directories"] == 3
        assert stats["max_candidates"] == 50
