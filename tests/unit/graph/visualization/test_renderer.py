"""Tests for graph renderer."""

import pytest
from dataclasses import dataclass

from dmm.graph.visualization.renderer import (
    GraphRenderer,
    RenderConfig,
    RenderResult,
)
from dmm.graph.inference.cluster import MemoryCluster


@dataclass
class MockMemory:
    """Mock memory for testing."""
    id: str
    title: str = "Test Memory"
    scope: str = "global"
    priority: float = 0.5
    tags: list = None
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
    
    def get_edges_from(self, node_id, edge_type=None):
        if node_id not in self.edges:
            return []
        if edge_type:
            return self.edges[node_id].get(edge_type, [])
        all_edges = []
        for edges in self.edges[node_id].values():
            all_edges.extend(edges)
        return all_edges


class TestGraphRenderer:
    """Tests for GraphRenderer."""
    
    def test_renderer_initialization(self):
        """Test renderer initializes with default config."""
        store = MockGraphStore()
        renderer = GraphRenderer(store)
        
        assert renderer.config is not None
        assert renderer.config.output_format == "html"
    
    def test_render_html_format(self):
        """Test HTML output format."""
        store = MockGraphStore()
        store.add_memory(MockMemory(id="mem1", title="Memory 1"))
        store.add_memory(MockMemory(id="mem2", title="Memory 2"))
        store.add_edge("mem1", "mem2", "RELATES_TO", weight=0.8)
        
        config = RenderConfig(output_format="html")
        renderer = GraphRenderer(store, config)
        
        result = renderer.render()
        
        assert result.format == "html"
        assert "<!DOCTYPE html>" in result.content
        assert "d3" in result.content.lower()
        assert result.node_count == 2
        assert result.edge_count == 1
    
    def test_render_json_format(self):
        """Test JSON output format."""
        store = MockGraphStore()
        store.add_memory(MockMemory(id="mem1", title="Memory 1"))
        store.add_memory(MockMemory(id="mem2", title="Memory 2"))
        store.add_edge("mem1", "mem2", "SUPPORTS", weight=0.9)
        
        config = RenderConfig(output_format="json")
        renderer = GraphRenderer(store, config)
        
        result = renderer.render()
        
        assert result.format == "json"
        assert '"nodes"' in result.content
        assert '"edges"' in result.content
        assert result.node_count == 2
    
    def test_render_dot_format(self):
        """Test DOT (Graphviz) output format."""
        store = MockGraphStore()
        store.add_memory(MockMemory(id="mem1", title="Memory 1"))
        store.add_memory(MockMemory(id="mem2", title="Memory 2"))
        store.add_edge("mem1", "mem2", "DEPENDS_ON")
        
        config = RenderConfig(output_format="dot")
        renderer = GraphRenderer(store, config)
        
        result = renderer.render()
        
        assert result.format == "dot"
        assert "digraph" in result.content
        assert "->" in result.content
    
    def test_render_mermaid_format(self):
        """Test Mermaid output format."""
        store = MockGraphStore()
        store.add_memory(MockMemory(id="mem1", title="Memory 1"))
        store.add_memory(MockMemory(id="mem2", title="Memory 2"))
        store.add_edge("mem1", "mem2", "RELATES_TO")
        
        config = RenderConfig(output_format="mermaid")
        renderer = GraphRenderer(store, config)
        
        result = renderer.render()
        
        assert result.format == "mermaid"
        assert "graph" in result.content
    
    def test_render_with_scope_filter(self):
        """Test filtering by scope."""
        store = MockGraphStore()
        store.add_memory(MockMemory(id="mem1", scope="global"))
        store.add_memory(MockMemory(id="mem2", scope="project"))
        store.add_memory(MockMemory(id="mem3", scope="global"))
        
        config = RenderConfig(
            output_format="json",
            filter_scopes=("global",),
        )
        renderer = GraphRenderer(store, config)
        
        result = renderer.render()
        
        assert result.node_count == 2
    
    def test_render_with_edge_type_filter(self):
        """Test filtering by edge type."""
        store = MockGraphStore()
        store.add_memory(MockMemory(id="mem1"))
        store.add_memory(MockMemory(id="mem2"))
        store.add_memory(MockMemory(id="mem3"))
        
        store.add_edge("mem1", "mem2", "SUPPORTS")
        store.add_edge("mem1", "mem3", "CONTRADICTS")
        
        config = RenderConfig(
            output_format="json",
            filter_edge_types=("SUPPORTS",),
        )
        renderer = GraphRenderer(store, config)
        
        result = renderer.render()
        
        # Should only have SUPPORTS edge
        assert result.edge_count == 1
    
    def test_render_with_clusters(self):
        """Test rendering with cluster highlighting."""
        store = MockGraphStore()
        store.add_memory(MockMemory(id="mem1"))
        store.add_memory(MockMemory(id="mem2"))
        
        config = RenderConfig(
            output_format="json",
            highlight_clusters=True,
        )
        renderer = GraphRenderer(store, config)
        
        clusters = [
            MemoryCluster(
                cluster_id="cluster_001",
                memory_ids=["mem1", "mem2"],
                size=2,
            )
        ]
        renderer.set_clusters(clusters)
        
        result = renderer.render()
        
        assert "cluster" in result.content.lower()
    
    def test_render_empty_graph(self):
        """Test rendering empty graph."""
        store = MockGraphStore()
        
        renderer = GraphRenderer(store)
        result = renderer.render()
        
        assert result.node_count == 0
        assert result.edge_count == 0
    
    def test_label_truncation(self):
        """Test long labels are truncated."""
        store = MockGraphStore()
        long_title = "A" * 100
        store.add_memory(MockMemory(id="mem1", title=long_title))
        
        config = RenderConfig(
            output_format="json",
            max_label_length=30,
        )
        renderer = GraphRenderer(store, config)
        
        result = renderer.render()
        
        # Label should be truncated
        assert long_title not in result.content
        assert "..." in result.content
    
    def test_render_result_save(self, tmp_path):
        """Test saving render result to file."""
        store = MockGraphStore()
        store.add_memory(MockMemory(id="mem1"))
        
        renderer = GraphRenderer(store, RenderConfig(output_format="json"))
        result = renderer.render()
        
        output_file = tmp_path / "graph.json"
        result.save(str(output_file))
        
        assert output_file.exists()
        content = output_file.read_text()
        assert '"nodes"' in content
