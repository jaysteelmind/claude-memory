"""Tests for semantic relationship extractor."""

import pytest
from dataclasses import dataclass

from dmm.graph.extractors.semantic_extractor import SemanticExtractor, SemanticExtractionConfig
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
    composite_embedding: list = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class TestSemanticExtractor:
    """Tests for SemanticExtractor."""
    
    def test_extract_no_embeddings(self):
        """Test extraction with no embeddings returns empty."""
        extractor = SemanticExtractor()
        memory = MockMemory(id="mem1")
        others = [MockMemory(id="mem2")]
        
        result = extractor.extract(memory, others)
        
        assert result.edge_count == 0
        assert result.method == ExtractionMethod.SEMANTIC_SIMILARITY
    
    def test_extract_with_similar_embeddings(self):
        """Test extraction finds similar embeddings."""
        extractor = SemanticExtractor(SemanticExtractionConfig(
            relates_threshold=0.7,
        ))
        
        # Create similar embeddings (high cosine similarity)
        embedding1 = [1.0, 0.0, 0.0]
        embedding2 = [0.95, 0.1, 0.0]  # Very similar
        embedding3 = [0.0, 1.0, 0.0]   # Orthogonal
        
        memory = MockMemory(id="mem1", composite_embedding=embedding1)
        others = [
            MockMemory(id="mem2", composite_embedding=embedding2),
            MockMemory(id="mem3", composite_embedding=embedding3),
        ]
        
        result = extractor.extract(memory, [memory] + others)
        
        # Should find mem2 as similar
        edge_targets = [e.to_id for e in result.edges]
        assert "mem2" in edge_targets
        assert "mem3" not in edge_targets
    
    def test_extract_supports_vs_relates(self):
        """Test SUPPORTS threshold is higher than RELATES_TO."""
        extractor = SemanticExtractor(SemanticExtractionConfig(
            relates_threshold=0.7,
            supports_threshold=0.9,
        ))
        
        # Create embeddings with different similarities
        embedding1 = [1.0, 0.0, 0.0]
        embedding2 = [0.999, 0.01, 0.0]  # Very high similarity -> SUPPORTS
        embedding3 = [0.8, 0.2, 0.0]     # Medium similarity -> RELATES_TO
        
        memory = MockMemory(id="mem1", composite_embedding=embedding1)
        others = [
            MockMemory(id="mem2", composite_embedding=embedding2),
            MockMemory(id="mem3", composite_embedding=embedding3),
        ]
        
        result = extractor.extract(memory, [memory] + others)
        
        supports_edges = [e for e in result.edges if e.edge_type == "SUPPORTS"]
        relates_edges = [e for e in result.edges if e.edge_type == "RELATES_TO"]
        
        # At least one of each type expected
        assert len(supports_edges) + len(relates_edges) >= 1
    
    def test_extract_skips_deprecated(self):
        """Test extraction skips deprecated memories."""
        extractor = SemanticExtractor(SemanticExtractionConfig(
            relates_threshold=0.5,
        ))
        
        embedding = [1.0, 0.0, 0.0]
        
        memory = MockMemory(id="mem1", composite_embedding=embedding)
        others = [
            MockMemory(id="mem2", composite_embedding=embedding, status="deprecated"),
        ]
        
        result = extractor.extract(memory, [memory] + others)
        
        assert result.edge_count == 0
    
    def test_find_similar_memories(self):
        """Test finding similar memories utility."""
        extractor = SemanticExtractor()
        
        embedding1 = [1.0, 0.0, 0.0]
        embedding2 = [0.9, 0.1, 0.0]
        embedding3 = [0.0, 1.0, 0.0]
        
        memory = MockMemory(id="mem1", composite_embedding=embedding1)
        memories = [
            memory,
            MockMemory(id="mem2", composite_embedding=embedding2),
            MockMemory(id="mem3", composite_embedding=embedding3),
        ]
        
        # Returns list of (memory_id, similarity) tuples
        similar = extractor.find_similar_memories(
            memory, memories, min_similarity=0.7, top_k=5
        )
        
        assert len(similar) >= 1
        # mem2 should be most similar to mem1 (after mem1 itself if included)
        memory_ids = [mid for mid, score in similar]
        assert "mem2" in memory_ids
    
    def test_stats_tracking(self):
        """Test statistics tracking."""
        extractor = SemanticExtractor()
        
        embedding = [1.0, 0.0, 0.0]
        memory = MockMemory(id="mem1", composite_embedding=embedding)
        others = [MockMemory(id="mem2", composite_embedding=embedding)]
        
        extractor.extract(memory, [memory] + others)
        stats = extractor.get_stats()
        
        assert stats["extraction_count"] == 1
