"""Unit tests for ConflictStore."""

import pytest
from datetime import datetime
from pathlib import Path
import tempfile

from dmm.conflicts.store import ConflictStore
from dmm.models.conflict import (
    Conflict,
    ConflictMemory,
    ConflictStatus,
    ConflictType,
    DetectionMethod,
    ResolutionAction,
    ResolutionRequest,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def conflict_store(temp_dir):
    """Create a conflict store for tests."""
    store = ConflictStore(temp_dir)
    store.initialize()
    yield store
    store.close()


@pytest.fixture
def sample_conflict():
    """Create a sample conflict for tests."""
    return Conflict(
        conflict_id="conflict_20250101_test001",
        memories=[
            ConflictMemory(
                memory_id="mem_001",
                path="project/config.md",
                title="Config A",
                summary="Configuration settings",
                scope="project",
                priority=0.7,
                role="primary",
            ),
            ConflictMemory(
                memory_id="mem_002",
                path="project/settings.md",
                title="Config B",
                summary="More settings",
                scope="project",
                priority=0.6,
                role="secondary",
            ),
        ],
        conflict_type=ConflictType.CONTRADICTORY,
        detection_method=DetectionMethod.TAG_OVERLAP,
        confidence=0.85,
        description="Conflicting configuration settings",
        evidence='{"shared_tags": ["config", "settings"]}',
        status=ConflictStatus.UNRESOLVED,
        detected_at=datetime.utcnow(),
        scan_id="scan_test_001",
    )


class TestConflictStoreInitialization:
    """Tests for ConflictStore initialization."""

    def test_initialize_creates_tables(self, temp_dir):
        """Test that initialize creates required tables."""
        store = ConflictStore(temp_dir)
        store.initialize()
        
        # Verify tables exist by querying them
        with store._get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row["name"] for row in cursor.fetchall()}
        
        assert "conflicts" in tables
        assert "conflict_memories" in tables
        assert "conflict_scans" in tables
        assert "resolution_log" in tables
        assert "conflict_meta" in tables
        
        store.close()

    def test_initialize_is_idempotent(self, temp_dir):
        """Test that initialize can be called multiple times."""
        store = ConflictStore(temp_dir)
        store.initialize()
        store.initialize()  # Should not raise
        store.close()


class TestConflictCRUD:
    """Tests for CRUD operations."""

    def test_create_conflict(self, conflict_store, sample_conflict):
        """Test creating a conflict."""
        conflict_store.create(sample_conflict)
        
        retrieved = conflict_store.get(sample_conflict.conflict_id)
        assert retrieved is not None
        assert retrieved.conflict_id == sample_conflict.conflict_id
        assert retrieved.confidence == 0.85
        assert len(retrieved.memories) == 2

    def test_create_duplicate_raises(self, conflict_store, sample_conflict):
        """Test that creating duplicate conflict raises."""
        conflict_store.create(sample_conflict)
        
        with pytest.raises(Exception):  # IntegrityError wrapped
            conflict_store.create(sample_conflict)

    def test_get_nonexistent_returns_none(self, conflict_store):
        """Test getting nonexistent conflict returns None."""
        result = conflict_store.get("nonexistent_id")
        assert result is None

    def test_get_by_memory_pair(self, conflict_store, sample_conflict):
        """Test finding conflict by memory pair."""
        conflict_store.create(sample_conflict)
        
        # Order shouldn't matter
        result = conflict_store.get_by_memory_pair(("mem_002", "mem_001"))
        assert result is not None
        assert result.conflict_id == sample_conflict.conflict_id

    def test_get_by_memory(self, conflict_store, sample_conflict):
        """Test getting conflicts by memory ID."""
        conflict_store.create(sample_conflict)
        
        results = conflict_store.get_by_memory("mem_001")
        assert len(results) == 1
        assert results[0].conflict_id == sample_conflict.conflict_id
        
        results = conflict_store.get_by_memory("mem_002")
        assert len(results) == 1

    def test_get_unresolved(self, conflict_store, sample_conflict):
        """Test getting unresolved conflicts."""
        conflict_store.create(sample_conflict)
        
        results = conflict_store.get_unresolved()
        assert len(results) == 1
        assert results[0].status == ConflictStatus.UNRESOLVED

    def test_get_by_status(self, conflict_store, sample_conflict):
        """Test filtering by status."""
        conflict_store.create(sample_conflict)
        
        results = conflict_store.get_by_status(ConflictStatus.UNRESOLVED)
        assert len(results) == 1
        
        results = conflict_store.get_by_status(ConflictStatus.RESOLVED)
        assert len(results) == 0

    def test_get_by_type(self, conflict_store, sample_conflict):
        """Test filtering by type."""
        conflict_store.create(sample_conflict)
        
        results = conflict_store.get_by_type(ConflictType.CONTRADICTORY)
        assert len(results) == 1
        
        results = conflict_store.get_by_type(ConflictType.DUPLICATE)
        assert len(results) == 0

    def test_update_status(self, conflict_store, sample_conflict):
        """Test updating conflict status."""
        conflict_store.create(sample_conflict)
        
        conflict_store.update_status(
            sample_conflict.conflict_id,
            ConflictStatus.RESOLVED,
            resolution=ResolutionRequest(
                conflict_id=sample_conflict.conflict_id,
                action=ResolutionAction.DEPRECATE,
                target_memory_id="mem_002",
                reason="Outdated",
                resolved_by="user",
            ),
        )
        
        retrieved = conflict_store.get(sample_conflict.conflict_id)
        assert retrieved.status == ConflictStatus.RESOLVED
        assert retrieved.resolution_action == ResolutionAction.DEPRECATE

    def test_delete_conflict(self, conflict_store, sample_conflict):
        """Test deleting a conflict."""
        conflict_store.create(sample_conflict)
        
        deleted = conflict_store.delete(sample_conflict.conflict_id)
        assert deleted
        
        retrieved = conflict_store.get(sample_conflict.conflict_id)
        assert retrieved is None

    def test_exists_for_pair(self, conflict_store, sample_conflict):
        """Test checking pair existence."""
        assert not conflict_store.exists_for_pair(("mem_001", "mem_002"))
        
        conflict_store.create(sample_conflict)
        
        assert conflict_store.exists_for_pair(("mem_001", "mem_002"))
        assert conflict_store.exists_for_pair(("mem_002", "mem_001"))  # Order independent


class TestConflictStats:
    """Tests for statistics."""

    def test_get_stats_empty(self, conflict_store):
        """Test stats on empty store."""
        stats = conflict_store.get_stats()
        assert stats.total == 0
        assert stats.unresolved == 0

    def test_get_stats_with_data(self, conflict_store, sample_conflict):
        """Test stats with data."""
        conflict_store.create(sample_conflict)
        
        stats = conflict_store.get_stats()
        assert stats.total == 1
        assert stats.unresolved == 1
        assert stats.by_type.get("contradictory", 0) == 1
        assert stats.by_method.get("tag_overlap", 0) == 1


class TestResolutionLog:
    """Tests for resolution logging."""

    def test_log_resolution(self, conflict_store, sample_conflict):
        """Test logging a resolution."""
        conflict_store.create(sample_conflict)
        
        conflict_store.log_resolution(
            conflict_id=sample_conflict.conflict_id,
            action="deprecate",
            actor="test_user",
            details={"reason": "outdated"},
            memories_deprecated=["mem_002"],
        )
        
        # Verify log exists (through resolution history query)
        with conflict_store._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM resolution_log WHERE conflict_id = ?",
                (sample_conflict.conflict_id,),
            )
            logs = cursor.fetchall()
        
        assert len(logs) == 1
        assert logs[0]["action"] == "deprecate"
        assert logs[0]["actor"] == "test_user"


class TestScanHistory:
    """Tests for scan history."""

    def test_save_and_get_scan(self, conflict_store):
        """Test saving and retrieving scan records."""
        conflict_store.save_scan(
            scan_id="scan_test_001",
            scan_type="full",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_ms=500,
            memories_scanned=100,
            methods_used=["tag_overlap", "semantic_similarity"],
            conflicts_detected=5,
            conflicts_new=3,
            conflicts_existing=2,
            status="completed",
        )
        
        history = conflict_store.get_scan_history(limit=10)
        assert len(history) == 1
        assert history[0]["scan_id"] == "scan_test_001"
        assert history[0]["memories_scanned"] == 100


class TestGetConflictsAmong:
    """Tests for get_conflicts_among."""

    def test_get_conflicts_among_memories(self, conflict_store, sample_conflict):
        """Test getting conflicts among a set of memories."""
        conflict_store.create(sample_conflict)
        
        # Should find conflict
        results = conflict_store.get_conflicts_among(["mem_001", "mem_002", "mem_003"])
        assert len(results) == 1
        
        # Should not find conflict (different memories)
        results = conflict_store.get_conflicts_among(["mem_003", "mem_004"])
        assert len(results) == 0
