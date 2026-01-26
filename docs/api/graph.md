# Graph API Reference

The graph module provides knowledge graph operations using Kuzu embedded database.

## Module: dmm.graph.store

### KnowledgeGraphStore

Main interface for graph operations.
```python
from pathlib import Path
from dmm.graph import KnowledgeGraphStore

store = KnowledgeGraphStore(Path(".dmm/index/knowledge.kuzu"))
store.initialize()
```

#### Initialization
```python
def __init__(self, db_path: Path) -> None:
    """Initialize the graph store.
    
    Args:
        db_path: Path to Kuzu database directory.
    """

def initialize(self) -> None:
    """Create schema and indexes if not exists."""

def close(self) -> None:
    """Close database connection."""
```

#### Node Operations
```python
def upsert_memory_node(self, node: MemoryNode) -> bool:
    """Insert or update a memory node.
    
    Args:
        node: MemoryNode to upsert.
        
    Returns:
        True if successful.
    """

def get_memory_node(self, memory_id: str) -> MemoryNode | None:
    """Get a memory node by ID.
    
    Args:
        memory_id: Memory identifier.
        
    Returns:
        MemoryNode or None if not found.
    """

def delete_memory_node(self, memory_id: str) -> bool:
    """Delete a memory node and its edges.
    
    Args:
        memory_id: Memory identifier.
        
    Returns:
        True if deleted.
    """

def get_all_memory_nodes(self) -> list[MemoryNode]:
    """Get all memory nodes."""
```

#### Edge Operations
```python
def create_edge(
    self,
    edge_type: str,
    from_id: str,
    to_id: str,
    properties: dict[str, Any] | None = None,
) -> bool:
    """Create an edge between nodes.
    
    Args:
        edge_type: Type of edge (RELATES_TO, SUPPORTS, etc.)
        from_id: Source node ID.
        to_id: Target node ID.
        properties: Optional edge properties.
        
    Returns:
        True if created.
    """

def edge_exists(
    self,
    edge_type: str,
    from_id: str,
    to_id: str,
) -> bool:
    """Check if edge exists."""

def get_edges_from(
    self,
    node_id: str,
    edge_type: str | None = None,
) -> list[dict]:
    """Get all edges from a node.
    
    Args:
        node_id: Source node ID.
        edge_type: Optional filter by edge type.
        
    Returns:
        List of edge dictionaries.
    """

def delete_edge(
    self,
    edge_type: str,
    from_id: str,
    to_id: str,
) -> bool:
    """Delete an edge."""
```

#### Graph Queries
```python
def get_related_memories(
    self,
    memory_id: str,
    max_depth: int = 2,
    edge_types: list[str] | None = None,
) -> list[MemoryNode]:
    """Get memories related to a given memory.
    
    Args:
        memory_id: Starting memory ID.
        max_depth: Maximum traversal depth.
        edge_types: Optional filter by edge types.
        
    Returns:
        List of related MemoryNodes.
    """

def get_memories_by_tag(self, tag: str) -> list[MemoryNode]:
    """Get all memories with a specific tag."""

def find_path(
    self,
    from_id: str,
    to_id: str,
    max_depth: int = 5,
) -> list[str] | None:
    """Find shortest path between two memories.
    
    Returns:
        List of memory IDs in path, or None if no path.
    """

def get_stats(self) -> GraphStats:
    """Get graph statistics."""

def execute_cypher(
    self,
    query: str,
    params: dict[str, Any] | None = None,
) -> list[dict]:
    """Execute raw Cypher query.
    
    Args:
        query: Cypher query string.
        params: Optional query parameters.
        
    Returns:
        List of result dictionaries.
    """
```

## Module: dmm.graph.nodes

### MemoryNode
```python
@dataclass
class MemoryNode:
    id: str
    path: str
    title: str
    scope: str
    priority: float
    confidence: str
    token_count: int
    created_at: datetime | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
```

### TagNode
```python
@dataclass
class TagNode:
    id: str           # tag_{normalized_name}
    name: str         # Original tag name
    normalized: str   # Lowercase, trimmed
    usage_count: int  # Number of memories using this tag
```

### ScopeNode
```python
@dataclass
class ScopeNode:
    id: str           # scope_{name}
    name: str
    description: str
    memory_count: int
    token_total: int
```

### ConceptNode
```python
@dataclass
class ConceptNode:
    id: str           # concept_{hash}
    name: str
    definition: str
    source_count: int
```

## Module: dmm.graph.edges

### Edge Types

| Edge Type | From | To | Purpose |
|-----------|------|-----|---------|
| RELATES_TO | Memory | Memory | General relationship |
| SUPERSEDES | Memory | Memory | Version replacement |
| CONTRADICTS | Memory | Memory | Conflicting information |
| SUPPORTS | Memory | Memory | Evidence relationship |
| DEPENDS_ON | Memory | Memory | Prerequisite |
| HAS_TAG | Memory | Tag | Tag association |
| IN_SCOPE | Memory | Scope | Scope membership |
| TAG_COOCCURS | Tag | Tag | Tag co-occurrence |
| ABOUT | Memory | Concept | Discusses concept |
| DEFINES | Memory | Concept | Defines concept |

### RelationshipEdge
```python
@dataclass
class RelationshipEdge:
    edge_type: str
    from_id: str
    to_id: str
    weight: float = 1.0
    context: str | None = None
    created_at: datetime | None = None
```

## Module: dmm.graph.extractors

### ExtractionOrchestrator

Coordinates multiple extractors.
```python
from dmm.graph import ExtractionOrchestrator, OrchestratorConfig

config = OrchestratorConfig(
    enable_tag_extractor=True,
    enable_semantic_extractor=True,
    enable_temporal_extractor=True,
    enable_llm_extractor=False,
    min_edge_weight=0.3,
    max_edges_per_memory=30,
)

orchestrator = ExtractionOrchestrator(config)
result = orchestrator.extract(memory, all_memories)
```

### TagExtractor

Extracts relationships from tag overlap.
```python
from dmm.graph.extractors import TagExtractor, TagExtractorConfig

config = TagExtractorConfig(
    min_overlap=2,
    similarity_method="jaccard",  # or "ratio"
)

extractor = TagExtractor(config)
edges = extractor.extract(memory, all_memories)
```

### SemanticExtractor

Extracts relationships from embedding similarity.
```python
from dmm.graph.extractors import SemanticExtractor, SemanticExtractorConfig

config = SemanticExtractorConfig(
    relates_threshold=0.75,
    supports_threshold=0.85,
)

extractor = SemanticExtractor(config, embedding_store)
edges = extractor.extract(memory, all_memories)
```

### TemporalExtractor

Extracts version relationships from titles/dates.
```python
from dmm.graph.extractors import TemporalExtractor

extractor = TemporalExtractor()
edges = extractor.extract(memory, all_memories)
```

## Module: dmm.graph.retrieval

### HybridRetriever

Combines vector and graph search.
```python
from dmm.graph import HybridRetriever, HybridRetrievalConfig

config = HybridRetrievalConfig(
    vector_weight=0.6,      # alpha
    graph_weight=0.4,       # 1 - alpha
    max_graph_depth=2,
    boost_per_connection=0.2,
    decay_per_hop=0.5,
)

retriever = HybridRetriever(vector_store, graph_store, config)
results, stats = await retriever.retrieve(query_embedding, limit=10)
```

**Scoring Formula:**
```
S(m) = α × V(m) + (1-α) × G(m)

G(m) = min(1, Σ boost × decay^h × V(source))
```

## Module: dmm.graph.inference

### TransitiveInferenceEngine

Discovers implicit relationships.
```python
from dmm.graph import TransitiveInferenceEngine, TransitiveConfig

config = TransitiveConfig(
    decay_factor=0.8,
    min_confidence=0.3,
    max_path_length=3,
    edge_types=["DEPENDS_ON", "SUPPORTS"],
)

engine = TransitiveInferenceEngine(graph_store, config)
result = engine.infer_all()

print(f"Inferred {result.edges_created} new edges")
```

### ClusterDetector

Finds groups of related memories.
```python
from dmm.graph import ClusterDetector, ClusterConfig

config = ClusterConfig(
    min_cluster_size=3,
    edge_types=["RELATES_TO", "SUPPORTS", "DEPENDS_ON"],
)

detector = ClusterDetector(graph_store, config)
clusters = detector.detect_clusters()

for cluster in clusters:
    print(f"Cluster: {len(cluster.members)} members, density={cluster.density:.2f}")
```

## Module: dmm.graph.visualization

### GraphRenderer

Renders graph in multiple formats.
```python
from dmm.graph import GraphRenderer, RenderConfig

config = RenderConfig(
    output_format="html",  # html, json, dot, mermaid
    include_edges=True,
    max_nodes=100,
)

renderer = GraphRenderer(graph_store, config)
result = renderer.render()
result.save("graph.html")
```

**Output Formats:**

| Format | Description | Use Case |
|--------|-------------|----------|
| HTML | Interactive D3.js visualization | Browser viewing |
| JSON | Structured data | Programmatic use |
| DOT | Graphviz format | Static rendering |
| Mermaid | Markdown-embeddable | Documentation |

## See Also

- [Core API](core.md) - Memory models
- [AgentOS API](agentos/index.md) - Agent capabilities
- [Architecture](../ARCHITECTURE.md) - System design
