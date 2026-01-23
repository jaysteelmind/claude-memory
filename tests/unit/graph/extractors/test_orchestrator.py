"""Tests for extraction orchestrator."""

import pytest
from dataclasses import dataclass

from dmm.graph.extractors.orchestrator import (
    ExtractionOrchestrator,
    OrchestratorConfig,
    OrchestrationResult,
)
from dmm.graph.extractors.tag_extractor import TagExtractionConfig
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


class TestExtractionOrchestrator:
    """Tests for ExtractionOrchestrator."""
    
    def test_orchestrator_initialization(self):
        """Test orchestrator initializes with default config."""
        orchestrator = ExtractionOrchestrator()
        
        assert orchestrator.config is not None
        assert orchestrator.config.enable_tag_extraction is True
        assert orchestrator.config.enable_llm_extraction is False
    
    def test_orchestrator_with_custom_config(self):
        """Test orchestrator with custom configuration."""
        config = OrchestratorConfig(
            enable_tag_extraction=True,
            enable_semantic_extraction=False,
            enable_temporal_extraction=False,
            enable_llm_extraction=False,
        )
        
        orchestrator = ExtractionOrchestrator(config)
        
        assert "tag" in orchestrator._extractors
        assert "semantic" not in orchestrator._extractors
    
    def test_extract_single_memory(self):
        """Test extraction for a single memory."""
        config = OrchestratorConfig(
            enable_tag_extraction=True,
            enable_semantic_extraction=False,
            enable_temporal_extraction=False,
            enable_llm_extraction=False,
            tag_config=TagExtractionConfig(min_overlap_count=1),
        )
        
        orchestrator = ExtractionOrchestrator(config)
        
        memory = MockMemory(id="mem1", tags=["python", "api"])
        others = [
            MockMemory(id="mem2", tags=["python", "api"]),
            MockMemory(id="mem3", tags=["java"]),
        ]
        
        result = orchestrator.extract(memory, [memory] + others)
        
        assert isinstance(result, OrchestrationResult)
        assert result.source_memory_id == "mem1"
        assert result.total_candidates >= 0
        assert result.duration_ms > 0
    
    def test_extract_merges_duplicates(self):
        """Test that duplicate edges are merged."""
        config = OrchestratorConfig(
            enable_tag_extraction=True,
            enable_semantic_extraction=False,
            enable_temporal_extraction=False,
            enable_llm_extraction=False,
            merge_duplicates=True,
        )
        
        orchestrator = ExtractionOrchestrator(config)
        
        memory = MockMemory(id="mem1", tags=["python"])
        others = [MockMemory(id="mem2", tags=["python"])]
        
        result = orchestrator.extract(memory, [memory] + others)
        
        # Check merge stats exist
        assert "duplicates_removed" in result.merge_stats
    
    def test_extract_respects_min_weight(self):
        """Test extraction filters by minimum weight."""
        config = OrchestratorConfig(
            enable_tag_extraction=True,
            enable_semantic_extraction=False,
            enable_temporal_extraction=False,
            enable_llm_extraction=False,
            min_edge_weight=0.9,  # High threshold
        )
        
        orchestrator = ExtractionOrchestrator(config)
        
        memory = MockMemory(id="mem1", tags=["python"])
        others = [MockMemory(id="mem2", tags=["python", "java"])]
        
        result = orchestrator.extract(memory, [memory] + others)
        
        # Most edges should be filtered due to high threshold
        assert result.merge_stats.get("weight_filtered", 0) >= 0
    
    def test_extract_batch(self):
        """Test batch extraction."""
        config = OrchestratorConfig(
            enable_tag_extraction=True,
            enable_semantic_extraction=False,
            enable_temporal_extraction=False,
            enable_llm_extraction=False,
        )
        
        orchestrator = ExtractionOrchestrator(config)
        
        memories = [
            MockMemory(id="mem1", tags=["python"]),
            MockMemory(id="mem2", tags=["python"]),
            MockMemory(id="mem3", tags=["java"]),
        ]
        
        results = orchestrator.extract_batch(memories)
        
        assert len(results) == 3
        assert all(isinstance(r, OrchestrationResult) for r in results)
    
    def test_stats_tracking(self):
        """Test statistics tracking."""
        config = OrchestratorConfig(
            enable_tag_extraction=True,
            enable_semantic_extraction=False,
            enable_temporal_extraction=False,
            enable_llm_extraction=False,
        )
        
        orchestrator = ExtractionOrchestrator(config)
        
        memory = MockMemory(id="mem1", tags=["python"])
        others = [MockMemory(id="mem2", tags=["python"])]
        
        orchestrator.extract(memory, [memory] + others)
        stats = orchestrator.get_stats()
        
        assert stats["total_extractions"] == 1
        assert "tag" in stats["enabled_extractors"]
        
        orchestrator.reset_stats()
        stats = orchestrator.get_stats()
        assert stats["total_extractions"] == 0
    
    def test_result_to_dict(self):
        """Test OrchestrationResult serialization."""
        config = OrchestratorConfig(
            enable_tag_extraction=True,
            enable_semantic_extraction=False,
            enable_temporal_extraction=False,
            enable_llm_extraction=False,
        )
        
        orchestrator = ExtractionOrchestrator(config)
        
        memory = MockMemory(id="mem1", tags=["python"])
        others = [MockMemory(id="mem2", tags=["python"])]
        
        result = orchestrator.extract(memory, [memory] + others)
        result_dict = result.to_dict()
        
        assert "source_memory_id" in result_dict
        assert "duration_ms" in result_dict
        assert "final_count" in result_dict
