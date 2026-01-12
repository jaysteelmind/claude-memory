"""Tests for the baseline manager."""

from datetime import datetime
from pathlib import Path

import pytest

from dmm.core.constants import Confidence, Scope, Status
from dmm.indexer.store import MemoryStore
from dmm.models.memory import MemoryFile
from dmm.retrieval.baseline import BaselineManager


def create_test_embedding(dimension: int = 384, seed: float = 0.5) -> list[float]:
    """Create a test embedding vector."""
    import math
    return [math.sin(i * seed) for i in range(dimension)]


def add_baseline_memory(
    store: MemoryStore,
    memory_id: str,
    filename: str,
    token_count: int = 100,
    priority: float = 1.0,
) -> None:
    """Add a baseline memory to the store."""
    memory = MemoryFile(
        id=memory_id,
        path=f"baseline/{filename}",
        title=f"Baseline {filename}",
        body=f"Content for {filename}",
        token_count=token_count,
        tags=["baseline"],
        scope=Scope.BASELINE,
        priority=priority,
        confidence=Confidence.STABLE,
        status=Status.ACTIVE,
        created=datetime.now(),
    )
    store.upsert_memory(
        memory=memory,
        composite_embedding=create_test_embedding(seed=hash(memory_id) % 100 / 100),
        directory_embedding=create_test_embedding(seed=0.1),
        file_hash=f"hash_{memory_id}",
    )


class TestBaselineManager:
    """Tests for BaselineManager."""

    def test_get_baseline_pack_empty(self, store: MemoryStore, temp_dir: Path) -> None:
        """Should return empty pack when no baseline memories exist."""
        manager = BaselineManager(store=store, base_path=temp_dir)

        pack = manager.get_baseline_pack()

        assert pack.is_empty
        assert pack.total_tokens == 0
        assert len(pack.entries) == 0

    def test_get_baseline_pack_with_memories(
        self, store: MemoryStore, temp_dir: Path
    ) -> None:
        """Should return pack with baseline memories."""
        add_baseline_memory(store, "mem_001", "identity.md", token_count=150)
        add_baseline_memory(store, "mem_002", "constraints.md", token_count=200)

        manager = BaselineManager(store=store, base_path=temp_dir)
        pack = manager.get_baseline_pack()

        assert not pack.is_empty
        assert len(pack.entries) == 2
        assert pack.total_tokens == 350

    def test_baseline_pack_ordering_identity_first(
        self, store: MemoryStore, temp_dir: Path
    ) -> None:
        """identity.md should always be first."""
        add_baseline_memory(store, "mem_002", "constraints.md")
        add_baseline_memory(store, "mem_001", "identity.md")
        add_baseline_memory(store, "mem_003", "other.md")

        manager = BaselineManager(store=store, base_path=temp_dir)
        pack = manager.get_baseline_pack()

        assert len(pack.entries) == 3
        assert pack.entries[0].path == "baseline/identity.md"

    def test_baseline_pack_ordering_hard_constraints_second(
        self, store: MemoryStore, temp_dir: Path
    ) -> None:
        """hard_constraints.md should be second after identity.md."""
        add_baseline_memory(store, "mem_003", "other.md")
        add_baseline_memory(store, "mem_002", "hard_constraints.md")
        add_baseline_memory(store, "mem_001", "identity.md")

        manager = BaselineManager(store=store, base_path=temp_dir)
        pack = manager.get_baseline_pack()

        assert len(pack.entries) == 3
        assert pack.entries[0].path == "baseline/identity.md"
        assert pack.entries[1].path == "baseline/hard_constraints.md"

    def test_baseline_pack_caching(
        self, store: MemoryStore, temp_dir: Path
    ) -> None:
        """Pack should be cached and reused."""
        add_baseline_memory(store, "mem_001", "identity.md")

        manager = BaselineManager(store=store, base_path=temp_dir)

        pack1 = manager.get_baseline_pack()
        pack2 = manager.get_baseline_pack()

        # Same generated_at means same cached pack
        assert pack1.generated_at == pack2.generated_at

    def test_invalidate_cache(
        self, store: MemoryStore, temp_dir: Path
    ) -> None:
        """Cache invalidation should force regeneration."""
        add_baseline_memory(store, "mem_001", "identity.md")

        manager = BaselineManager(store=store, base_path=temp_dir)

        pack1 = manager.get_baseline_pack()
        manager.invalidate_cache()
        pack2 = manager.get_baseline_pack()

        # Different generated_at after invalidation
        assert pack1.generated_at != pack2.generated_at

    def test_validate_baseline_budget_within_budget(
        self, store: MemoryStore, temp_dir: Path
    ) -> None:
        """Should validate when within budget."""
        add_baseline_memory(store, "mem_001", "identity.md", token_count=200)
        add_baseline_memory(store, "mem_002", "constraints.md", token_count=200)

        manager = BaselineManager(store=store, base_path=temp_dir, token_budget=800)
        validation = manager.validate_baseline_budget()

        assert validation.is_valid
        assert validation.total_tokens == 400
        assert validation.budget == 800
        assert len(validation.overflow_files) == 0

    def test_validate_baseline_budget_exceeds_budget(
        self, store: MemoryStore, temp_dir: Path
    ) -> None:
        """Should detect when exceeding budget."""
        add_baseline_memory(store, "mem_001", "identity.md", token_count=500)
        add_baseline_memory(store, "mem_002", "constraints.md", token_count=500)

        manager = BaselineManager(store=store, base_path=temp_dir, token_budget=800)
        validation = manager.validate_baseline_budget()

        assert not validation.is_valid
        assert validation.total_tokens == 1000
        assert len(validation.overflow_files) > 0

    def test_get_baseline_tokens(
        self, store: MemoryStore, temp_dir: Path
    ) -> None:
        """Should return total baseline tokens."""
        add_baseline_memory(store, "mem_001", "identity.md", token_count=150)
        add_baseline_memory(store, "mem_002", "constraints.md", token_count=250)

        manager = BaselineManager(store=store, base_path=temp_dir)
        tokens = manager.get_baseline_tokens()

        assert tokens == 400

    def test_baseline_entries_have_correct_source(
        self, store: MemoryStore, temp_dir: Path
    ) -> None:
        """All baseline entries should have source='baseline'."""
        add_baseline_memory(store, "mem_001", "identity.md")

        manager = BaselineManager(store=store, base_path=temp_dir)
        pack = manager.get_baseline_pack()

        assert all(entry.source == "baseline" for entry in pack.entries)

    def test_baseline_entries_have_max_relevance(
        self, store: MemoryStore, temp_dir: Path
    ) -> None:
        """All baseline entries should have relevance_score=1.0."""
        add_baseline_memory(store, "mem_001", "identity.md")

        manager = BaselineManager(store=store, base_path=temp_dir)
        pack = manager.get_baseline_pack()

        assert all(entry.relevance_score == 1.0 for entry in pack.entries)
