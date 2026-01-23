"""Tests for tag-based relationship extractor."""

import pytest
from dataclasses import dataclass

from dmm.graph.extractors.tag_extractor import TagExtractor, TagExtractionConfig
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
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class TestTagExtractor:
    """Tests for TagExtractor."""
    
    def test_extract_no_tags(self):
        """Test extraction with no tags returns empty."""
        extractor = TagExtractor()
        memory = MockMemory(id="mem1", tags=[])
        others = [MockMemory(id="mem2", tags=["python"])]
        
        result = extractor.extract(memory, others)
        
        assert result.edge_count == 0
        assert result.method == ExtractionMethod.TAG_OVERLAP
    
    def test_extract_with_overlap(self):
        """Test extraction finds overlapping tags."""
        extractor = TagExtractor(TagExtractionConfig(
            min_overlap_count=1,
            min_overlap_ratio=0.3,
        ))
        
        memory = MockMemory(id="mem1", tags=["python", "api", "design"])
        others = [
            MockMemory(id="mem2", tags=["python", "api"]),
            MockMemory(id="mem3", tags=["java", "design"]),
            MockMemory(id="mem4", tags=["rust"]),
        ]
        
        result = extractor.extract(memory, [memory] + others)
        
        assert result.edge_count >= 1
        edge_targets = [e.to_id for e in result.edges]
        assert "mem2" in edge_targets
    
    def test_extract_skips_deprecated(self):
        """Test extraction skips deprecated memories."""
        extractor = TagExtractor(TagExtractionConfig(min_overlap_count=1))
        
        memory = MockMemory(id="mem1", tags=["python"])
        others = [
            MockMemory(id="mem2", tags=["python"], status="deprecated"),
        ]
        
        result = extractor.extract(memory, [memory] + others)
        
        assert result.edge_count == 0
    
    def test_extract_respects_max_edges(self):
        """Test extraction respects max_edges_per_memory."""
        extractor = TagExtractor(TagExtractionConfig(
            min_overlap_count=1,
            max_edges_per_memory=2,
        ))
        
        memory = MockMemory(id="mem1", tags=["python"])
        others = [
            MockMemory(id=f"mem{i}", tags=["python"])
            for i in range(2, 10)
        ]
        
        result = extractor.extract(memory, [memory] + others)
        
        assert result.edge_count <= 2
    
    def test_normalize_tags(self):
        """Test tag normalization."""
        extractor = TagExtractor(TagExtractionConfig(
            normalize_tags=True,
            min_overlap_count=1,
        ))
        
        memory = MockMemory(id="mem1", tags=["Python", "API"])
        others = [
            MockMemory(id="mem2", tags=["python", "api"]),
        ]
        
        result = extractor.extract(memory, [memory] + others)
        
        assert result.edge_count >= 1
    
    def test_find_tag_clusters(self):
        """Test finding tag clusters."""
        extractor = TagExtractor(TagExtractionConfig(min_overlap_count=1))
        
        # Need at least 3 memories with overlapping tags to form a cluster
        memories = [
            MockMemory(id="mem1", tags=["python", "api"]),
            MockMemory(id="mem2", tags=["python", "api"]),
            MockMemory(id="mem3", tags=["python", "api"]),
            MockMemory(id="mem4", tags=["java"]),  # Isolated
        ]
        
        clusters = extractor.find_tag_clusters(memories, min_cluster_size=2)
        
        assert len(clusters) >= 1
        # First cluster should contain the python/api memories
        cluster_ids = clusters[0]
        assert len(cluster_ids) >= 2
    
    def test_stats_tracking(self):
        """Test statistics tracking."""
        extractor = TagExtractor()
        
        memory = MockMemory(id="mem1", tags=["python"])
        others = [MockMemory(id="mem2", tags=["python"])]
        
        extractor.extract(memory, [memory] + others)
        stats = extractor.get_stats()
        
        assert stats["extraction_count"] == 1
        
        extractor.reset_stats()
        stats = extractor.get_stats()
        assert stats["extraction_count"] == 0
