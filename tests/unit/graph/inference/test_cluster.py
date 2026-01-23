"""Tests for cluster detector."""

import pytest
from dataclasses import dataclass

from dmm.graph.inference.cluster import (
    ClusterDetector,
    ClusterConfig,
    MemoryCluster,
    ClusterResult,
    KnowledgeGap,
)


@dataclass
class MockMemory:
    """Mock memory for testing."""
    id: str
    tags: list = None
    scope: str = "global"
    status: str = "active"
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


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
            "weight": props.get("weight", 0.5),
            **props,
        })
    
    def get_all_memory_nodes(self):
        return self.memories
    
    def get_memory_node(self, mid):
        for m in self.memories:
            if m.id == mid:
                return m
        return None
    
    def get_edges_from(self, node_id, edge_type=None):
        if node_id not in self.edges:
            return []
        if edge_type:
            return self.edges[node_id].get(edge_type, [])
        all_edges = []
        for edges in self.edges[node_id].values():
            all_edges.extend(edges)
        return all_edges


class TestClusterDetector:
    """Tests for ClusterDetector."""
    
    def test_detector_initialization(self):
        """Test detector initializes with default config."""
        store = MockGraphStore()
        detector = ClusterDetector(store)
        
        assert detector.config is not None
        assert detector.config.min_cluster_size == 3
    
    def test_detect_single_cluster(self):
        """Test detection of a single cluster."""
        store = MockGraphStore()
        
        # Create a cluster of 4 connected memories
        for i in range(4):
            store.add_memory(MockMemory(id=f"mem{i}", tags=["python"]))
        
        store.add_edge("mem0", "mem1", "RELATES_TO", weight=0.8)
        store.add_edge("mem1", "mem2", "RELATES_TO", weight=0.8)
        store.add_edge("mem2", "mem3", "RELATES_TO", weight=0.8)
        store.add_edge("mem0", "mem3", "RELATES_TO", weight=0.8)
        
        config = ClusterConfig(min_cluster_size=3, min_edge_weight=0.5)
        detector = ClusterDetector(store, config)
        
        result = detector.detect_clusters()
        
        assert result.cluster_count >= 1
        assert result.clustered_memories >= 3
    
    def test_detect_multiple_clusters(self):
        """Test detection of multiple disconnected clusters."""
        store = MockGraphStore()
        
        # Cluster 1
        for i in range(3):
            store.add_memory(MockMemory(id=f"c1_mem{i}"))
        store.add_edge("c1_mem0", "c1_mem1", "RELATES_TO", weight=0.8)
        store.add_edge("c1_mem1", "c1_mem2", "RELATES_TO", weight=0.8)
        
        # Cluster 2 (disconnected)
        for i in range(3):
            store.add_memory(MockMemory(id=f"c2_mem{i}"))
        store.add_edge("c2_mem0", "c2_mem1", "RELATES_TO", weight=0.8)
        store.add_edge("c2_mem1", "c2_mem2", "RELATES_TO", weight=0.8)
        
        config = ClusterConfig(min_cluster_size=3, min_edge_weight=0.5)
        detector = ClusterDetector(store, config)
        
        result = detector.detect_clusters()
        
        assert result.cluster_count >= 2
    
    def test_detect_knowledge_gaps(self):
        """Test detection of knowledge gaps."""
        store = MockGraphStore()
        
        # Two memories with same tags but no connection
        store.add_memory(MockMemory(id="mem1", tags=["python", "api", "design"]))
        store.add_memory(MockMemory(id="mem2", tags=["python", "api", "patterns"]))
        
        config = ClusterConfig(
            detect_knowledge_gaps=True,
            gap_min_tag_similarity=0.3,
        )
        detector = ClusterDetector(store, config)
        
        result = detector.detect_clusters()
        
        assert result.gap_count >= 1
        gap = result.knowledge_gaps[0]
        assert "python" in gap.shared_tags or "api" in gap.shared_tags
    
    def test_cluster_metrics(self):
        """Test cluster metric calculation."""
        store = MockGraphStore()
        
        # Create fully connected cluster (complete graph)
        for i in range(4):
            store.add_memory(MockMemory(id=f"mem{i}", tags=["test"], scope="global"))
        
        # Connect all pairs
        for i in range(4):
            for j in range(i + 1, 4):
                store.add_edge(f"mem{i}", f"mem{j}", "RELATES_TO", weight=0.8)
        
        config = ClusterConfig(min_cluster_size=3, min_edge_weight=0.5)
        detector = ClusterDetector(store, config)
        
        result = detector.detect_clusters()
        
        if result.clusters:
            cluster = result.clusters[0]
            assert cluster.size >= 3
            assert cluster.density > 0
            assert cluster.central_memory_id is not None
    
    def test_memory_cluster_to_dict(self):
        """Test MemoryCluster serialization."""
        cluster = MemoryCluster(
            cluster_id="cluster_001",
            memory_ids=["mem1", "mem2", "mem3"],
            size=3,
            density=0.67,
            avg_edge_weight=0.75,
            central_memory_id="mem2",
            common_tags=["python"],
        )
        
        cluster_dict = cluster.to_dict()
        
        assert cluster_dict["cluster_id"] == "cluster_001"
        assert cluster_dict["size"] == 3
        assert cluster_dict["density"] == 0.67
    
    def test_knowledge_gap_to_dict(self):
        """Test KnowledgeGap serialization."""
        gap = KnowledgeGap(
            memory_id_1="mem1",
            memory_id_2="mem2",
            similarity_score=0.65,
            shared_tags=["python", "api"],
            same_scope=True,
            reason="High similarity",
        )
        
        gap_dict = gap.to_dict()
        
        assert gap_dict["memory_id_1"] == "mem1"
        assert gap_dict["similarity_score"] == 0.65
    
    def test_result_to_dict(self):
        """Test ClusterResult serialization."""
        result = ClusterResult(
            duration_ms=50.0,
            total_memories=10,
            clustered_memories=8,
            singleton_count=2,
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["total_memories"] == 10
        assert result_dict["clustered_memories"] == 8
