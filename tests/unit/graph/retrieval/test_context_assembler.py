"""Tests for context assembler."""

import pytest
from dataclasses import dataclass

from dmm.graph.retrieval.context_assembler import (
    GraphContextAssembler,
    ContextAssemblerConfig,
    AssembledContext,
)
from dmm.graph.retrieval.hybrid_retriever import RetrievalResult


@dataclass
class MockMemory:
    """Mock memory for testing."""
    id: str
    title: str = "Test Memory"
    body: str = "Test content"
    scope: str = "global"


class TestGraphContextAssembler:
    """Tests for GraphContextAssembler."""
    
    def test_assembler_initialization(self):
        """Test assembler initializes with default config."""
        assembler = GraphContextAssembler()
        
        assert assembler.config is not None
        assert assembler.config.output_format == "markdown"
    
    def test_assemble_empty_results(self):
        """Test assembling empty results."""
        assembler = GraphContextAssembler()
        
        result = assembler.assemble([])
        
        assert result.memory_count == 0
        assert "No memories" in result.content
    
    def test_assemble_markdown_format(self):
        """Test markdown output format."""
        config = ContextAssemblerConfig(output_format="markdown")
        assembler = GraphContextAssembler(config)
        
        results = [
            RetrievalResult(
                memory=MockMemory(id="mem1", title="Test 1", body="Content 1"),
                memory_id="mem1",
                vector_score=0.8,
                graph_score=0.6,
                combined_score=0.72,
            ),
        ]
        
        assembled = assembler.assemble(results)
        
        assert assembled.format == "markdown"
        assert "# DMM Memory Pack" in assembled.content
        assert "Test 1" in assembled.content
    
    def test_assemble_json_format(self):
        """Test JSON output format."""
        config = ContextAssemblerConfig(output_format="json")
        assembler = GraphContextAssembler(config)
        
        results = [
            RetrievalResult(
                memory=MockMemory(id="mem1"),
                memory_id="mem1",
                vector_score=0.8,
                graph_score=0.6,
                combined_score=0.72,
            ),
        ]
        
        assembled = assembler.assemble(results)
        
        assert assembled.format == "json"
        assert '"memories"' in assembled.content
    
    def test_assemble_plain_format(self):
        """Test plain text output format."""
        config = ContextAssemblerConfig(output_format="plain")
        assembler = GraphContextAssembler(config)
        
        results = [
            RetrievalResult(
                memory=MockMemory(id="mem1"),
                memory_id="mem1",
                vector_score=0.8,
                graph_score=0.6,
                combined_score=0.72,
            ),
        ]
        
        assembled = assembler.assemble(results)
        
        assert assembled.format == "plain"
        assert "RETRIEVED MEMORIES" in assembled.content
    
    def test_assemble_with_baseline(self):
        """Test assembly with baseline content."""
        assembler = GraphContextAssembler()
        
        results = [
            RetrievalResult(
                memory=MockMemory(id="mem1"),
                memory_id="mem1",
                vector_score=0.8,
                graph_score=0.6,
                combined_score=0.72,
            ),
        ]
        
        assembled = assembler.assemble(results, baseline_content="Baseline info here")
        
        assert "Baseline" in assembled.content
    
    def test_assemble_token_budget(self):
        """Test token budget truncation."""
        config = ContextAssemblerConfig(
            token_budget=100,
            tokens_per_char=0.25,
        )
        assembler = GraphContextAssembler(config)
        
        # Create content that exceeds budget
        results = [
            RetrievalResult(
                memory=MockMemory(id=f"mem{i}", body="x" * 500),
                memory_id=f"mem{i}",
                vector_score=0.8,
                graph_score=0.6,
                combined_score=0.72,
            )
            for i in range(10)
        ]
        
        assembled = assembler.assemble(results)
        
        # Should be truncated
        assert assembled.truncated or assembled.total_tokens <= 100
    
    def test_assembled_context_to_dict(self):
        """Test AssembledContext serialization."""
        context = AssembledContext(
            content="Test content",
            format="markdown",
            memory_count=5,
            total_tokens=100,
        )
        
        context_dict = context.to_dict()
        
        assert context_dict["format"] == "markdown"
        assert context_dict["memory_count"] == 5
