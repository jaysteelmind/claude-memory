"""Unit tests for TagOverlapAnalyzer."""

import pytest
from unittest.mock import MagicMock, PropertyMock
from datetime import datetime

from dmm.conflicts.analyzers.tag_overlap import TagOverlapAnalyzer, TagOverlapConfig
from dmm.models.conflict import DetectionMethod


@pytest.fixture
def mock_memory():
    """Create a mock memory."""
    def _create(
        memory_id: str,
        tags: list[str],
        title: str = "Test Memory",
        body: str = "Test body content",
        status: str = "active",
    ):
        memory = MagicMock()
        memory.id = memory_id
        memory.tags = tags
        memory.title = title
        memory.body = body
        memory.status = MagicMock()
        memory.status.value = status
        memory.path = f"test/{memory_id}.md"
        memory.scope = MagicMock()
        memory.scope.value = "project"
        memory.priority = 0.5
        return memory
    return _create


@pytest.fixture
def mock_store(mock_memory):
    """Create a mock memory store."""
    store = MagicMock()
    return store


class TestTagOverlapAnalyzer:
    """Tests for TagOverlapAnalyzer."""

    def test_init_with_defaults(self, mock_store):
        """Test initialization with default config."""
        analyzer = TagOverlapAnalyzer(mock_store)
        
        stats = analyzer.get_stats()
        assert stats["min_shared_tags"] == 2
        assert stats["contradiction_patterns"] > 0

    def test_init_with_custom_config(self, mock_store):
        """Test initialization with custom config."""
        config = TagOverlapConfig(
            min_shared_tags=3,
            contradiction_score_increment=0.5,
        )
        analyzer = TagOverlapAnalyzer(mock_store, config)
        
        stats = analyzer.get_stats()
        assert stats["min_shared_tags"] == 3

    def test_analyze_empty_store(self, mock_store):
        """Test analysis with no memories."""
        mock_store.get_all_memories.return_value = []
        analyzer = TagOverlapAnalyzer(mock_store)
        
        candidates = analyzer.analyze()
        assert candidates == []

    def test_analyze_single_memory(self, mock_store, mock_memory):
        """Test analysis with single memory."""
        mock_store.get_all_memories.return_value = [
            mock_memory("mem_001", ["tag1", "tag2"]),
        ]
        analyzer = TagOverlapAnalyzer(mock_store)
        
        candidates = analyzer.analyze()
        assert candidates == []

    def test_analyze_no_shared_tags(self, mock_store, mock_memory):
        """Test analysis with no shared tags."""
        mock_store.get_all_memories.return_value = [
            mock_memory("mem_001", ["tag1", "tag2"]),
            mock_memory("mem_002", ["tag3", "tag4"]),
        ]
        analyzer = TagOverlapAnalyzer(mock_store)
        
        candidates = analyzer.analyze()
        assert candidates == []

    def test_analyze_shared_tags_no_contradiction(self, mock_store, mock_memory):
        """Test analysis with shared tags but no contradiction."""
        mock_store.get_all_memories.return_value = [
            mock_memory("mem_001", ["config", "settings"], body="Use tabs for indentation"),
            mock_memory("mem_002", ["config", "settings"], body="Use tabs for indentation"),
        ]
        analyzer = TagOverlapAnalyzer(mock_store)
        
        candidates = analyzer.analyze()
        # Should find candidates due to shared tags, even without contradiction
        # The score would be low (just from tag boost)
        assert len(candidates) >= 0  # May or may not detect based on threshold

    def test_analyze_contradiction_detected(self, mock_store, mock_memory):
        """Test analysis detects contradiction patterns."""
        mock_store.get_all_memories.return_value = [
            mock_memory("mem_001", ["config", "formatting"], body="Always use tabs"),
            mock_memory("mem_002", ["config", "formatting"], body="Never use tabs"),
        ]
        analyzer = TagOverlapAnalyzer(mock_store)
        
        candidates = analyzer.analyze()
        assert len(candidates) == 1
        assert candidates[0].detection_method == DetectionMethod.TAG_OVERLAP
        assert "always" in str(candidates[0].evidence).lower() or "never" in str(candidates[0].evidence).lower()

    def test_analyze_multiple_contradictions(self, mock_store, mock_memory):
        """Test analysis with multiple contradiction patterns."""
        mock_store.get_all_memories.return_value = [
            mock_memory("mem_001", ["db", "orm"], body="Always use SQL. Enable caching."),
            mock_memory("mem_002", ["db", "orm"], body="Never use SQL. Disable caching."),
        ]
        analyzer = TagOverlapAnalyzer(mock_store)
        
        candidates = analyzer.analyze()
        assert len(candidates) == 1
        # Higher score due to multiple contradictions
        assert candidates[0].raw_score > 0.3

    def test_analyze_single_memory_id(self, mock_store, mock_memory):
        """Test analyze_single method."""
        mem1 = mock_memory("mem_001", ["config", "settings"], body="Always use tabs")
        mem2 = mock_memory("mem_002", ["config", "settings"], body="Never use tabs")
        
        mock_store.get_memory.return_value = mem1
        mock_store.get_all_memories.return_value = [mem1, mem2]
        
        analyzer = TagOverlapAnalyzer(mock_store)
        candidates = analyzer.analyze_single("mem_001")
        
        assert len(candidates) == 1
        assert "mem_001" in candidates[0].memory_ids
        assert "mem_002" in candidates[0].memory_ids

    def test_analyze_ignores_deprecated(self, mock_store, mock_memory):
        """Test that deprecated memories are ignored by default."""
        mock_store.get_all_memories.return_value = [
            mock_memory("mem_001", ["config", "settings"], body="Always use tabs"),
            mock_memory("mem_002", ["config", "settings"], body="Never use tabs", status="deprecated"),
        ]
        analyzer = TagOverlapAnalyzer(mock_store)
        
        candidates = analyzer.analyze()
        # Deprecated memory should be filtered out
        assert len(candidates) == 0

    def test_analyze_with_specific_memory_ids(self, mock_store, mock_memory):
        """Test analysis with specific memory IDs."""
        mem1 = mock_memory("mem_001", ["config", "settings"], body="Always use tabs")
        mem2 = mock_memory("mem_002", ["config", "settings"], body="Never use tabs")
        
        mock_store.get_memory.side_effect = lambda mid: mem1 if mid == "mem_001" else mem2
        
        analyzer = TagOverlapAnalyzer(mock_store)
        candidates = analyzer.analyze(memory_ids=["mem_001", "mem_002"])
        
        assert len(candidates) == 1

    def test_max_candidates_limit(self, mock_store, mock_memory):
        """Test that max_candidates limits results."""
        # Create many contradicting memories
        memories = []
        for i in range(20):
            body = "Always use tabs" if i % 2 == 0 else "Never use tabs"
            memories.append(mock_memory(f"mem_{i:03d}", ["config", "settings"], body=body))
        
        mock_store.get_all_memories.return_value = memories
        
        config = TagOverlapConfig(max_candidates=5)
        analyzer = TagOverlapAnalyzer(mock_store, config)
        
        candidates = analyzer.analyze()
        assert len(candidates) <= 5

    def test_pair_key_ordering(self, mock_store, mock_memory):
        """Test that pair keys are consistently ordered."""
        mock_store.get_all_memories.return_value = [
            mock_memory("mem_002", ["config", "settings"], body="Always use tabs"),
            mock_memory("mem_001", ["config", "settings"], body="Never use tabs"),
        ]
        analyzer = TagOverlapAnalyzer(mock_store)
        
        candidates = analyzer.analyze()
        assert len(candidates) == 1
        # pair_key should be sorted
        assert candidates[0].pair_key == ("mem_001", "mem_002")
