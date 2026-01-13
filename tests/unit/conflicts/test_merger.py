"""Unit tests for ConflictMerger."""

import pytest
from unittest.mock import MagicMock
from datetime import datetime

from dmm.conflicts.merger import ConflictMerger
from dmm.models.conflict import (
    ConflictCandidate,
    ConflictType,
    DetectionMethod,
)


@pytest.fixture
def mock_conflict_store():
    """Create a mock conflict store."""
    store = MagicMock()
    store.exists_for_pair.return_value = False
    store.create.return_value = None
    return store


@pytest.fixture
def mock_memory():
    """Create a mock memory."""
    def _create(memory_id: str, title: str = "Test", scope: str = "project"):
        memory = MagicMock()
        memory.id = memory_id
        memory.path = f"test/{memory_id}.md"
        memory.title = title
        memory.body = "Test body content"
        memory.scope = MagicMock()
        memory.scope.value = scope
        memory.priority = 0.5
        memory.tags = ["tag1", "tag2"]
        return memory
    return _create


class TestConflictMerger:
    """Tests for ConflictMerger."""

    def test_init(self, mock_conflict_store):
        """Test initialization."""
        merger = ConflictMerger(mock_conflict_store)
        
        stats = merger.get_stats()
        assert stats["multi_method_boost"] == 0.10
        assert stats["max_boost"] == 0.30

    def test_merge_empty_candidates(self, mock_conflict_store):
        """Test merging empty candidate list."""
        merger = ConflictMerger(mock_conflict_store)
        
        result = merger.merge_and_persist([], {}, "scan_001")
        
        assert result.total_candidates == 0
        assert result.unique_pairs == 0
        assert result.new_conflicts == 0

    def test_merge_single_candidate(self, mock_conflict_store, mock_memory):
        """Test merging single candidate."""
        merger = ConflictMerger(mock_conflict_store)
        
        candidates = [
            ConflictCandidate(
                memory_ids=("mem_001", "mem_002"),
                detection_method=DetectionMethod.TAG_OVERLAP,
                raw_score=0.75,
                evidence={"shared_tags": ["config"]},
            ),
        ]
        
        memory_map = {
            "mem_001": mock_memory("mem_001", "Config A"),
            "mem_002": mock_memory("mem_002", "Config B"),
        }
        
        result = merger.merge_and_persist(candidates, memory_map, "scan_001")
        
        assert result.total_candidates == 1
        assert result.unique_pairs == 1
        assert result.new_conflicts == 1
        assert mock_conflict_store.create.called

    def test_merge_deduplicates_pairs(self, mock_conflict_store, mock_memory):
        """Test that duplicate pairs are deduplicated."""
        merger = ConflictMerger(mock_conflict_store)
        
        # Same pair, different methods
        candidates = [
            ConflictCandidate(
                memory_ids=("mem_001", "mem_002"),
                detection_method=DetectionMethod.TAG_OVERLAP,
                raw_score=0.70,
                evidence={"method": "tag"},
            ),
            ConflictCandidate(
                memory_ids=("mem_002", "mem_001"),  # Reversed order
                detection_method=DetectionMethod.SEMANTIC_SIMILARITY,
                raw_score=0.80,
                evidence={"method": "semantic"},
            ),
        ]
        
        memory_map = {
            "mem_001": mock_memory("mem_001"),
            "mem_002": mock_memory("mem_002"),
        }
        
        result = merger.merge_and_persist(candidates, memory_map, "scan_001")
        
        assert result.total_candidates == 2
        assert result.unique_pairs == 1  # Only one unique pair
        assert result.new_conflicts == 1

    def test_merge_multi_method_boost(self, mock_conflict_store, mock_memory):
        """Test that multi-method detection boosts confidence."""
        merger = ConflictMerger(mock_conflict_store, multi_method_boost=0.10)
        
        candidates = [
            ConflictCandidate(
                memory_ids=("mem_001", "mem_002"),
                detection_method=DetectionMethod.TAG_OVERLAP,
                raw_score=0.70,
                evidence={},
            ),
            ConflictCandidate(
                memory_ids=("mem_001", "mem_002"),
                detection_method=DetectionMethod.SEMANTIC_SIMILARITY,
                raw_score=0.75,
                evidence={},
            ),
        ]
        
        memory_map = {
            "mem_001": mock_memory("mem_001"),
            "mem_002": mock_memory("mem_002"),
        }
        
        result = merger.merge_and_persist(candidates, memory_map, "scan_001")
        
        # Check that created conflict has boosted confidence
        assert mock_conflict_store.create.called
        created_conflict = mock_conflict_store.create.call_args[0][0]
        # Base score (0.75) + boost (0.10 for 1 additional method)
        assert created_conflict.confidence >= 0.80

    def test_merge_existing_conflict_skipped(self, mock_conflict_store, mock_memory):
        """Test that existing conflicts are skipped."""
        mock_conflict_store.exists_for_pair.return_value = True
        merger = ConflictMerger(mock_conflict_store)
        
        candidates = [
            ConflictCandidate(
                memory_ids=("mem_001", "mem_002"),
                detection_method=DetectionMethod.TAG_OVERLAP,
                raw_score=0.75,
                evidence={},
            ),
        ]
        
        memory_map = {
            "mem_001": mock_memory("mem_001"),
            "mem_002": mock_memory("mem_002"),
        }
        
        result = merger.merge_and_persist(candidates, memory_map, "scan_001")
        
        assert result.new_conflicts == 0
        assert result.existing_conflicts == 1
        assert not mock_conflict_store.create.called

    def test_merge_without_persist(self, mock_conflict_store, mock_memory):
        """Test merge_without_persist for preview."""
        merger = ConflictMerger(mock_conflict_store)
        
        candidates = [
            ConflictCandidate(
                memory_ids=("mem_001", "mem_002"),
                detection_method=DetectionMethod.TAG_OVERLAP,
                raw_score=0.75,
                evidence={},
            ),
        ]
        
        memory_map = {
            "mem_001": mock_memory("mem_001"),
            "mem_002": mock_memory("mem_002"),
        }
        
        conflicts = merger.merge_without_persist(candidates, memory_map)
        
        assert len(conflicts) == 1
        assert conflicts[0].scan_id == "preview"
        assert not mock_conflict_store.create.called

    def test_merge_determines_type_supersession(self, mock_conflict_store, mock_memory):
        """Test conflict type determination for supersession."""
        merger = ConflictMerger(mock_conflict_store)
        
        candidates = [
            ConflictCandidate(
                memory_ids=("mem_001", "mem_002"),
                detection_method=DetectionMethod.SUPERSESSION_CHAIN,
                raw_score=0.90,
                evidence={"issue_type": "orphaned"},
            ),
        ]
        
        memory_map = {
            "mem_001": mock_memory("mem_001"),
            "mem_002": mock_memory("mem_002"),
        }
        
        result = merger.merge_and_persist(candidates, memory_map, "scan_001")
        
        created_conflict = mock_conflict_store.create.call_args[0][0]
        assert created_conflict.conflict_type == ConflictType.SUPERSESSION

    def test_merge_determines_type_duplicate(self, mock_conflict_store, mock_memory):
        """Test conflict type determination for duplicate."""
        merger = ConflictMerger(mock_conflict_store)
        
        candidates = [
            ConflictCandidate(
                memory_ids=("mem_001", "mem_002"),
                detection_method=DetectionMethod.SEMANTIC_SIMILARITY,
                raw_score=0.98,
                evidence={"similarity": 0.98},
            ),
        ]
        
        memory_map = {
            "mem_001": mock_memory("mem_001"),
            "mem_002": mock_memory("mem_002"),
        }
        
        result = merger.merge_and_persist(candidates, memory_map, "scan_001")
        
        created_conflict = mock_conflict_store.create.call_args[0][0]
        assert created_conflict.conflict_type == ConflictType.DUPLICATE

    def test_merge_max_boost_capped(self, mock_conflict_store, mock_memory):
        """Test that multi-method boost is capped."""
        merger = ConflictMerger(
            mock_conflict_store,
            multi_method_boost=0.20,
            max_boost=0.30,
        )
        
        # 4 different methods would give 0.60 boost, but should be capped at 0.30
        candidates = [
            ConflictCandidate(
                memory_ids=("mem_001", "mem_002"),
                detection_method=DetectionMethod.TAG_OVERLAP,
                raw_score=0.60,
                evidence={},
            ),
            ConflictCandidate(
                memory_ids=("mem_001", "mem_002"),
                detection_method=DetectionMethod.SEMANTIC_SIMILARITY,
                raw_score=0.60,
                evidence={},
            ),
            ConflictCandidate(
                memory_ids=("mem_001", "mem_002"),
                detection_method=DetectionMethod.SUPERSESSION_CHAIN,
                raw_score=0.60,
                evidence={},
            ),
            ConflictCandidate(
                memory_ids=("mem_001", "mem_002"),
                detection_method=DetectionMethod.RULE_EXTRACTION,
                raw_score=0.60,
                evidence={},
            ),
        ]
        
        memory_map = {
            "mem_001": mock_memory("mem_001"),
            "mem_002": mock_memory("mem_002"),
        }
        
        result = merger.merge_and_persist(candidates, memory_map, "scan_001")
        
        created_conflict = mock_conflict_store.create.call_args[0][0]
        # 0.60 + 0.30 (capped) = 0.90
        assert created_conflict.confidence == pytest.approx(0.90, abs=0.01)

    def test_merge_missing_memory_skipped(self, mock_conflict_store, mock_memory):
        """Test that candidates with missing memories are skipped."""
        merger = ConflictMerger(mock_conflict_store)
        
        candidates = [
            ConflictCandidate(
                memory_ids=("mem_001", "mem_002"),
                detection_method=DetectionMethod.TAG_OVERLAP,
                raw_score=0.75,
                evidence={},
            ),
        ]
        
        # Only one memory in map
        memory_map = {
            "mem_001": mock_memory("mem_001"),
            # mem_002 missing
        }
        
        result = merger.merge_and_persist(candidates, memory_map, "scan_001")
        
        assert result.new_conflicts == 0
        assert not mock_conflict_store.create.called
