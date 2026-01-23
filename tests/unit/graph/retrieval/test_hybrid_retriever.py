"""Tests for hybrid retriever."""

import pytest
from dataclasses import dataclass

from dmm.graph.retrieval.hybrid_retriever import (
    HybridRetriever,
    HybridRetrievalConfig,
    RetrievalResult,
    RetrievalStats,
)


@dataclass
class MockMemory:
    """Mock memory for testing."""
    id: str
    title: str = ""
    scope: str = "global"
    status: str = "active"


class TestHybridRetriever:
    """Tests for HybridRetriever."""
    
    def test_retriever_initialization(self):
        """Test retriever initializes with default config."""
        retriever = HybridRetriever()
        
        assert retriever.config is not None
        assert retriever.config.vector_weight == 0.6
        assert retriever.config.graph_weight == 0.4
    
    def test_retriever_with_custom_config(self):
        """Test retriever with custom configuration."""
        config = HybridRetrievalConfig(
            vector_weight=0.7,
            graph_weight=0.3,
            max_graph_depth=3,
        )
        
        retriever = HybridRetriever(config=config)
        
        assert retriever.config.vector_weight == 0.7
        assert retriever.config.max_graph_depth == 3
    
    def test_set_stores(self):
        """Test setting stores after initialization."""
        retriever = HybridRetriever()
        
        # Should not raise
        retriever.set_stores(vector_store=None, graph_store=None)
    
    def test_config_weights_sum_to_one(self):
        """Test default weights sum to 1.0."""
        config = HybridRetrievalConfig()
        
        assert config.vector_weight + config.graph_weight == 1.0
    
    def test_retrieval_result_to_dict(self):
        """Test RetrievalResult serialization."""
        result = RetrievalResult(
            memory=MockMemory(id="mem1", title="Test"),
            memory_id="mem1",
            vector_score=0.8,
            graph_score=0.6,
            combined_score=0.72,
            hop_distance=1,
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["memory_id"] == "mem1"
        assert result_dict["vector_score"] == 0.8
        assert result_dict["combined_score"] == 0.72
    
    def test_stats_tracking(self):
        """Test statistics tracking."""
        retriever = HybridRetriever()
        
        stats = retriever.get_stats()
        
        assert stats["total_retrievals"] == 0
        assert stats["total_results_returned"] == 0
        
        retriever.reset_stats()
        stats = retriever.get_stats()
        assert stats["total_retrievals"] == 0
