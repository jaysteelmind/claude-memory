"""
DMM Knowledge Graph Module.

Provides a living knowledge graph for modeling relationships between
memories. The graph enables semantic navigation, contradiction detection,
dependency tracking, and enhanced context retrieval.

Phase 5.1 Components (Foundation):
- KnowledgeGraphStore: Kuzu-based graph database backend
- MemoryNode: Node representation for memories
- Edge types: RelatesTo, Supports, Contradicts, DependsOn, Supersedes
- GraphMigration: Schema migration management

Phase 5.2 Components (Advanced Features):
- Extractors: Tag, Semantic, Temporal, LLM-based relationship extraction
- Retrieval: Hybrid vector+graph search with context assembly
- Inference: Transitive closure and cluster detection
- Visualization: Multi-format graph rendering
"""

# Phase 5.1 - Foundation
from dmm.graph.store import KnowledgeGraphStore, GraphStats
from dmm.graph.nodes import MemoryNode, TagNode, ScopeNode, ConceptNode, SkillNode, ToolNode, AgentNode
from dmm.graph.edges import (
    Edge,
    RelatesTo,
    Supports,
    Contradicts,
    DependsOn,
    Supersedes,
    HasTag,
    InScope,
    TagCooccurs,
    About,
    Defines,
    # Phase 6 edges
    RequiresSkill,
    UsesTool,
    HasSkill,
    HasTool,
    SkillDependsOn,
    PrefersScope,
    create_edge,
)
from dmm.graph.migration import GraphMigration, MigrationStats

# Phase 5.2 - Extractors
from dmm.graph.extractors.base import (
    BaseExtractor,
    ExtractionConfig,
    ExtractionResult,
    ExtractionMethod,
)
from dmm.graph.extractors.tag_extractor import TagExtractor, TagExtractionConfig
from dmm.graph.extractors.semantic_extractor import SemanticExtractor, SemanticExtractionConfig
from dmm.graph.extractors.temporal_extractor import TemporalExtractor, TemporalExtractionConfig
from dmm.graph.extractors.llm_extractor import LLMExtractor, LLMExtractionConfig
from dmm.graph.extractors.orchestrator import (
    ExtractionOrchestrator,
    OrchestratorConfig,
    OrchestrationResult,
)

# Phase 5.2 - Retrieval
from dmm.graph.retrieval.hybrid_retriever import (
    HybridRetriever,
    HybridRetrievalConfig,
    RetrievalResult,
    RetrievalStats,
)
from dmm.graph.retrieval.context_assembler import (
    GraphContextAssembler,
    ContextAssemblerConfig,
    AssembledContext,
)

# Phase 5.2 - Inference
from dmm.graph.inference.transitive import (
    TransitiveInferenceEngine,
    TransitiveConfig,
    InferredEdge,
    TransitiveResult,
)
from dmm.graph.inference.cluster import (
    ClusterDetector,
    ClusterConfig,
    MemoryCluster,
    ClusterResult,
)

# Phase 5.2 - Visualization
from dmm.graph.visualization.renderer import (
    GraphRenderer,
    RenderConfig,
    RenderResult,
)

__all__ = [
    # Phase 5.1 - Store
    "KnowledgeGraphStore",
    "GraphStats",
    # Phase 5.1 - Nodes
    "MemoryNode",
    "TagNode",
    "ScopeNode",
    "ConceptNode",
    # Phase 6 - Nodes
    "SkillNode",
    "ToolNode",
    "AgentNode",
    # Phase 5.1 - Edges
    "Edge",
    "RelatesTo",
    "Supports",
    "Contradicts",
    "DependsOn",
    "Supersedes",
    "HasTag",
    "InScope",
    "TagCooccurs",
    "About",
    "Defines",
    # Phase 6 - Edges
    "RequiresSkill",
    "UsesTool",
    "HasSkill",
    "HasTool",
    "SkillDependsOn",
    "PrefersScope",
    "create_edge",
    # Phase 5.1 - Migration
    "GraphMigration",
    "MigrationStats",
    # Phase 5.2 - Extractors
    "BaseExtractor",
    "ExtractionConfig",
    "ExtractionResult",
    "ExtractionMethod",
    "TagExtractor",
    "TagExtractionConfig",
    "SemanticExtractor",
    "SemanticExtractionConfig",
    "TemporalExtractor",
    "TemporalExtractionConfig",
    "LLMExtractor",
    "LLMExtractionConfig",
    "ExtractionOrchestrator",
    "OrchestratorConfig",
    "OrchestrationResult",
    # Phase 5.2 - Retrieval
    "HybridRetriever",
    "HybridRetrievalConfig",
    "RetrievalResult",
    "RetrievalStats",
    "GraphContextAssembler",
    "ContextAssemblerConfig",
    "AssembledContext",
    # Phase 5.2 - Inference
    "TransitiveInferenceEngine",
    "TransitiveConfig",
    "InferredEdge",
    "TransitiveResult",
    "ClusterDetector",
    "ClusterConfig",
    "MemoryCluster",
    "ClusterResult",
    # Phase 5.2 - Visualization
    "GraphRenderer",
    "RenderConfig",
    "RenderResult",
]
