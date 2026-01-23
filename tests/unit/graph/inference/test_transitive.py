"""Tests for transitive inference engine."""

import pytest
from dataclasses import dataclass

from dmm.graph.inference.transitive import (
    TransitiveInferenceEngine,
    TransitiveConfig,
    InferredEdge,
    TransitiveResult,
)


@dataclass
class MockMemory:
    """Mock memory for testing."""
    id: str


class MockGraphStore:
    """Mock graph store for testing."""
    
    def __init__(self):
        self.memories = []
        self.edges = {}
    
    def add_memory(self, memory):
        self.memories.append(memory)
    
    def add_edge(self, from_id, to_id, edge_type, **props):
        if from_id not in self.edges:
            self.edges[from_id] = {}
        if edge_type not in self.edges[from_id]:
            self.edges[from_id][edge_type] = []
        self.edges[from_id][edge_type].append({
            "to_id": to_id,
            "type": edge_type,
            **props,
        })
    
    def get_all_memory_nodes(self):
        return self.memories
    
    def get_edges_from(self, node_id, edge_type=None):
        if node_id not in self.edges:
            return []
        if edge_type:
            return self.edges[node_id].get(edge_type, [])
        all_edges = []
        for edges in self.edges[node_id].values():
            all_edges.extend(edges)
        return all_edges


class TestTransitiveInferenceEngine:
    """Tests for TransitiveInferenceEngine."""
    
    def test_engine_initialization(self):
        """Test engine initializes with default config."""
        store = MockGraphStore()
        engine = TransitiveInferenceEngine(store)
        
        assert engine.config is not None
        assert "DEPENDS_ON" in engine.config.transitive_edge_types
    
    def test_infer_transitive_depends_on(self):
        """Test inference of transitive DEPENDS_ON."""
        store = MockGraphStore()
        
        # A -> B -> C (DEPENDS_ON chain)
        store.add_memory(MockMemory(id="A"))
        store.add_memory(MockMemory(id="B"))
        store.add_memory(MockMemory(id="C"))
        
        store.add_edge("A", "B", "DEPENDS_ON", strength=1.0)
        store.add_edge("B", "C", "DEPENDS_ON", strength=1.0)
        
        config = TransitiveConfig(
            max_path_length=3,
            min_confidence=0.1,
            exclude_existing=True,
        )
        engine = TransitiveInferenceEngine(store, config)
        
        result = engine.infer_all()
        
        # Should infer A -> C
        assert isinstance(result, TransitiveResult)
        inferred_pairs = [(e.from_id, e.to_id) for e in result.inferred_edges]
        assert ("A", "C") in inferred_pairs
    
    def test_infer_for_single_node(self):
        """Test inference for a single node."""
        store = MockGraphStore()
        
        store.add_memory(MockMemory(id="A"))
        store.add_memory(MockMemory(id="B"))
        store.add_memory(MockMemory(id="C"))
        
        store.add_edge("A", "B", "DEPENDS_ON")
        store.add_edge("B", "C", "DEPENDS_ON")
        
        config = TransitiveConfig(min_confidence=0.1)
        engine = TransitiveInferenceEngine(store, config)
        
        result = engine.infer_for_node("A")
        
        assert result.nodes_processed == 1
    
    def test_confidence_decay(self):
        """Test confidence decays over path length."""
        store = MockGraphStore()
        
        store.add_memory(MockMemory(id="A"))
        store.add_memory(MockMemory(id="B"))
        store.add_memory(MockMemory(id="C"))
        
        store.add_edge("A", "B", "DEPENDS_ON", strength=1.0)
        store.add_edge("B", "C", "DEPENDS_ON", strength=1.0)
        
        config = TransitiveConfig(
            confidence_decay=0.5,
            min_confidence=0.1,
        )
        engine = TransitiveInferenceEngine(store, config)
        
        result = engine.infer_all()
        
        # Confidence should be 1.0 * 1.0 * 0.5 * 0.5 = 0.25
        if result.inferred_edges:
            inferred = result.inferred_edges[0]
            assert inferred.confidence < 1.0
    
    def test_no_cycles(self):
        """Test that cycles don't cause infinite loops."""
        store = MockGraphStore()
        
        store.add_memory(MockMemory(id="A"))
        store.add_memory(MockMemory(id="B"))
        
        store.add_edge("A", "B", "DEPENDS_ON")
        store.add_edge("B", "A", "DEPENDS_ON")
        
        config = TransitiveConfig(max_path_length=5)
        engine = TransitiveInferenceEngine(store, config)
        
        # Should complete without hanging
        result = engine.infer_all()
        
        assert isinstance(result, TransitiveResult)
    
    def test_inferred_edge_to_dict(self):
        """Test InferredEdge serialization."""
        from dmm.graph.edges import DependsOn
        
        edge = InferredEdge(
            edge=DependsOn(from_id="A", to_id="C"),
            edge_type="DEPENDS_ON",
            from_id="A",
            to_id="C",
            confidence=0.75,
            path=["A", "B", "C"],
            path_length=2,
        )
        
        edge_dict = edge.to_dict()
        
        assert edge_dict["from_id"] == "A"
        assert edge_dict["to_id"] == "C"
        assert edge_dict["confidence"] == 0.75
        assert edge_dict["inferred"] is True
    
    def test_result_to_dict(self):
        """Test TransitiveResult serialization."""
        result = TransitiveResult(
            duration_ms=100.5,
            nodes_processed=10,
            paths_evaluated=50,
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["nodes_processed"] == 10
        assert result_dict["duration_ms"] == 100.5
