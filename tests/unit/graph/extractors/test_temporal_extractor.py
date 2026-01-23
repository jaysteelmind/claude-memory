"""Tests for temporal relationship extractor."""

import pytest
from dataclasses import dataclass
from datetime import datetime, timedelta

from dmm.graph.extractors.temporal_extractor import TemporalExtractor, TemporalExtractionConfig
from dmm.graph.extractors.base import ExtractionMethod


@dataclass
class MockMemory:
    """Mock memory for testing."""
    id: str
    path: str = ""
    title: str = ""
    tags: list = None
    scope: str = "global"
    priority: float = 0.5
    confidence: float = 0.8
    status: str = "active"
    created: datetime = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.created is None:
            self.created = datetime.now()


class TestTemporalExtractor:
    """Tests for TemporalExtractor."""
    
    def test_extract_version_detection(self):
        """Test detection of version-based supersession."""
        extractor = TemporalExtractor(TemporalExtractionConfig(
            detect_versions=True,
            title_similarity_threshold=0.5,
        ))
        
        memory_v2 = MockMemory(id="mem2", title="API Design v2")
        memory_v1 = MockMemory(id="mem1", title="API Design v1")
        
        result = extractor.extract(memory_v2, [memory_v2, memory_v1])
        
        # v2 should supersede v1
        supersedes_edges = [e for e in result.edges if e.edge_type == "SUPERSEDES"]
        assert len(supersedes_edges) >= 1
        assert supersedes_edges[0].to_id == "mem1"
    
    def test_extract_temporal_proximity(self):
        """Test detection of temporal proximity."""
        extractor = TemporalExtractor(TemporalExtractionConfig(
            proximity_days=7,
        ))
        
        now = datetime.now()
        
        memory1 = MockMemory(id="mem1", title="Design Doc", created=now)
        memory2 = MockMemory(id="mem2", title="Implementation", created=now - timedelta(days=2))
        memory3 = MockMemory(id="mem3", title="Old Doc", created=now - timedelta(days=30))
        
        result = extractor.extract(memory1, [memory1, memory2, memory3])
        
        # Should find mem2 as temporally related but not mem3
        edge_targets = [e.to_id for e in result.edges]
        assert "mem2" in edge_targets
        assert "mem3" not in edge_targets
    
    def test_extract_skips_deprecated(self):
        """Test extraction skips deprecated memories."""
        extractor = TemporalExtractor()
        
        memory1 = MockMemory(id="mem1", title="API v2")
        memory2 = MockMemory(id="mem2", title="API v1", status="deprecated")
        
        result = extractor.extract(memory1, [memory1, memory2])
        
        assert result.edge_count == 0
    
    def test_version_extraction(self):
        """Test version number extraction from titles."""
        extractor = TemporalExtractor()
        
        test_cases = [
            ("API Design v2", (2,)),
            ("API Design v2.1", (2, 1)),
            ("API Design version 3.0.1", (3, 0, 1)),
            ("Design 1.0", (1, 0)),
            ("No version here", None),
        ]
        
        for title, expected in test_cases:
            result = extractor._extract_version(title)
            assert result == expected, f"Failed for '{title}': got {result}, expected {expected}"
    
    def test_find_version_chains(self):
        """Test finding version chains."""
        extractor = TemporalExtractor()
        
        memories = [
            MockMemory(id="mem3", title="API Design v3"),
            MockMemory(id="mem1", title="API Design v1"),
            MockMemory(id="mem2", title="API Design v2"),
            MockMemory(id="other", title="Something Else"),
        ]
        
        chains = extractor.find_version_chains(memories)
        
        assert len(chains) >= 1
        # Chain should be ordered by version
        api_chain = chains[0]
        assert api_chain == ["mem1", "mem2", "mem3"]
    
    def test_find_temporal_clusters(self):
        """Test finding temporal clusters."""
        extractor = TemporalExtractor()
        
        now = datetime.now()
        
        memories = [
            MockMemory(id="mem1", created=now),
            MockMemory(id="mem2", created=now - timedelta(days=1)),
            MockMemory(id="mem3", created=now - timedelta(days=2)),
            MockMemory(id="mem4", created=now - timedelta(days=30)),
        ]
        
        clusters = extractor.find_temporal_clusters(memories, window_days=7)
        
        # First 3 should be in same cluster
        assert len(clusters) >= 1
        first_cluster = clusters[0]
        assert "mem1" in first_cluster
        assert "mem4" not in first_cluster
    
    def test_stats_tracking(self):
        """Test statistics tracking."""
        extractor = TemporalExtractor()
        
        memory = MockMemory(id="mem1", title="Test v1")
        others = [MockMemory(id="mem2", title="Test v2")]
        
        extractor.extract(memory, [memory] + others)
        stats = extractor.get_stats()
        
        assert stats["extraction_count"] == 1
