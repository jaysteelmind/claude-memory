"""Integration tests for conflict detection system."""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime

from dmm.conflicts.store import ConflictStore
from dmm.conflicts.merger import ConflictMerger
from dmm.conflicts.resolver import ConflictResolver
from dmm.conflicts.detector import ConflictDetector, ConflictConfig
from dmm.conflicts.scanner import ConflictScanner, ScanConfig
from dmm.conflicts.analyzers.tag_overlap import TagOverlapAnalyzer
from dmm.indexer.store import MemoryStore
from dmm.indexer.embedder import MemoryEmbedder
from dmm.models.conflict import (
    ConflictStatus,
    ConflictType,
    DetectionMethod,
    ResolutionAction,
    ResolutionRequest,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def conflict_store(temp_dir):
    """Create a conflict store."""
    store = ConflictStore(temp_dir)
    store.initialize()
    yield store
    store.close()


@pytest.fixture  
def memory_store(temp_dir):
    """Create a memory store."""
    index_dir = temp_dir / ".dmm" / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    store = MemoryStore(index_dir / "embeddings.db")
    store.initialize()
    yield store
    store.close()


class TestConflictStoreIntegration:
    """Integration tests for ConflictStore."""

    def test_full_lifecycle(self, conflict_store):
        """Test conflict creation, update, resolution lifecycle."""
        from dmm.models.conflict import (
            Conflict, ConflictMemory, ConflictStatus, ConflictType, DetectionMethod
        )
        
        # Create a conflict
        conflict = Conflict(
            conflict_id="conflict_integration_001",
            memories=[
                ConflictMemory(
                    memory_id="mem_001",
                    path="test/a.md",
                    title="Config A",
                    summary="Config A summary",
                    scope="project",
                    priority=0.7,
                    role="primary",
                ),
                ConflictMemory(
                    memory_id="mem_002",
                    path="test/b.md",
                    title="Config B",
                    summary="Config B summary",
                    scope="project",
                    priority=0.6,
                    role="secondary",
                ),
            ],
            conflict_type=ConflictType.CONTRADICTORY,
            detection_method=DetectionMethod.TAG_OVERLAP,
            confidence=0.85,
            description="Test conflict",
            evidence='{"test": true}',
            status=ConflictStatus.UNRESOLVED,
            detected_at=datetime.utcnow(),
        )
        
        conflict_store.create(conflict)
        
        # Verify retrieval
        retrieved = conflict_store.get("conflict_integration_001")
        assert retrieved is not None
        assert retrieved.status == ConflictStatus.UNRESOLVED
        assert len(retrieved.memories) == 2
        
        # Update status
        conflict_store.update_status(
            "conflict_integration_001",
            ConflictStatus.IN_PROGRESS,
        )
        
        retrieved = conflict_store.get("conflict_integration_001")
        assert retrieved.status == ConflictStatus.IN_PROGRESS
        
        # Log resolution
        conflict_store.log_resolution(
            conflict_id="conflict_integration_001",
            action="deprecate",
            actor="test_user",
            details={"reason": "outdated"},
            memories_deprecated=["mem_002"],
        )
        
        # Final resolution
        conflict_store.update_status(
            "conflict_integration_001",
            ConflictStatus.RESOLVED,
            resolution=ResolutionRequest(
                conflict_id="conflict_integration_001",
                action=ResolutionAction.DEPRECATE,
                target_memory_id="mem_002",
                reason="Outdated",
                resolved_by="test_user",
            ),
        )
        
        retrieved = conflict_store.get("conflict_integration_001")
        assert retrieved.status == ConflictStatus.RESOLVED
        assert retrieved.resolution_action == ResolutionAction.DEPRECATE
        
        # Verify stats
        stats = conflict_store.get_stats()
        assert stats.total == 1
        assert stats.resolved == 1


class TestMergerIntegration:
    """Integration tests for ConflictMerger."""

    def test_merge_and_persist(self, conflict_store):
        """Test merging candidates and persisting."""
        from unittest.mock import MagicMock
        from dmm.models.conflict import ConflictCandidate
        
        merger = ConflictMerger(conflict_store)
        
        # Create mock memories
        def mock_memory(mid, title):
            m = MagicMock()
            m.id = mid
            m.path = f"test/{mid}.md"
            m.title = title
            m.body = "Test body"
            m.scope = MagicMock()
            m.scope.value = "project"
            m.priority = 0.5
            m.tags = ["config"]
            return m
        
        candidates = [
            ConflictCandidate(
                memory_ids=("mem_001", "mem_002"),
                detection_method=DetectionMethod.TAG_OVERLAP,
                raw_score=0.75,
                evidence={"shared_tags": ["config"]},
            ),
            ConflictCandidate(
                memory_ids=("mem_001", "mem_002"),
                detection_method=DetectionMethod.SEMANTIC_SIMILARITY,
                raw_score=0.80,
                evidence={"similarity": 0.80},
            ),
        ]
        
        memory_map = {
            "mem_001": mock_memory("mem_001", "Config A"),
            "mem_002": mock_memory("mem_002", "Config B"),
        }
        
        result = merger.merge_and_persist(candidates, memory_map, "scan_001")
        
        assert result.total_candidates == 2
        assert result.unique_pairs == 1
        assert result.new_conflicts == 1
        
        # Verify persisted
        conflicts = conflict_store.get_unresolved()
        assert len(conflicts) == 1
        # Multi-method boost should be applied
        assert conflicts[0].confidence >= 0.80


class TestScanHistoryIntegration:
    """Integration tests for scan history."""

    def test_scan_history_tracking(self, conflict_store):
        """Test scan history is tracked correctly."""
        # Save a scan
        conflict_store.save_scan(
            scan_id="scan_test_001",
            scan_type="full",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_ms=1500,
            memories_scanned=100,
            methods_used=["tag_overlap", "semantic_similarity"],
            conflicts_detected=5,
            conflicts_new=3,
            conflicts_existing=2,
            by_type={"contradictory": 3, "duplicate": 2},
            by_method={"tag_overlap": 3, "semantic_similarity": 2},
            status="completed",
        )
        
        # Retrieve history
        history = conflict_store.get_scan_history(limit=10)
        
        assert len(history) == 1
        assert history[0]["scan_id"] == "scan_test_001"
        assert history[0]["memories_scanned"] == 100
        assert history[0]["conflicts_new"] == 3
        assert history[0]["status"] == "completed"


class TestConflictQueries:
    """Integration tests for conflict queries."""

    def test_query_by_memory(self, conflict_store):
        """Test querying conflicts by memory ID."""
        from dmm.models.conflict import Conflict, ConflictMemory
        
        # Create multiple conflicts
        for i in range(3):
            conflict = Conflict(
                conflict_id=f"conflict_query_{i}",
                memories=[
                    ConflictMemory(
                        memory_id="mem_shared",
                        path="shared.md",
                        title="Shared",
                        summary="",
                        scope="project",
                        priority=0.5,
                        role="primary",
                    ),
                    ConflictMemory(
                        memory_id=f"mem_other_{i}",
                        path=f"other_{i}.md",
                        title=f"Other {i}",
                        summary="",
                        scope="project",
                        priority=0.5,
                        role="secondary",
                    ),
                ],
                conflict_type=ConflictType.CONTRADICTORY,
                detection_method=DetectionMethod.TAG_OVERLAP,
                confidence=0.7 + i * 0.05,
                description=f"Test conflict {i}",
                evidence="{}",
                status=ConflictStatus.UNRESOLVED,
            )
            conflict_store.create(conflict)
        
        # Query by shared memory
        results = conflict_store.get_by_memory("mem_shared")
        assert len(results) == 3
        
        # Query by specific memory
        results = conflict_store.get_by_memory("mem_other_1")
        assert len(results) == 1

    def test_query_among_memories(self, conflict_store):
        """Test get_conflicts_among."""
        from dmm.models.conflict import Conflict, ConflictMemory
        
        conflict = Conflict(
            conflict_id="conflict_among_test",
            memories=[
                ConflictMemory(
                    memory_id="mem_a",
                    path="a.md",
                    title="A",
                    summary="",
                    scope="project",
                    priority=0.5,
                    role="primary",
                ),
                ConflictMemory(
                    memory_id="mem_b",
                    path="b.md",
                    title="B",
                    summary="",
                    scope="project",
                    priority=0.5,
                    role="secondary",
                ),
            ],
            conflict_type=ConflictType.CONTRADICTORY,
            detection_method=DetectionMethod.TAG_OVERLAP,
            confidence=0.8,
            description="Test",
            evidence="{}",
            status=ConflictStatus.UNRESOLVED,
        )
        conflict_store.create(conflict)
        
        # Should find conflict
        results = conflict_store.get_conflicts_among(["mem_a", "mem_b", "mem_c"])
        assert len(results) == 1
        
        # Should not find conflict
        results = conflict_store.get_conflicts_among(["mem_c", "mem_d"])
        assert len(results) == 0
