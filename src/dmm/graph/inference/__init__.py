"""
DMM Graph Inference Module.

Provides inference capabilities for discovering implicit knowledge
in the graph structure:

- Transitive relationships: A->B->C implies A->C
- Cluster detection: Groups of highly connected memories
- Knowledge gap detection: Missing relationships

Components:
- TransitiveInferenceEngine: Discovers transitive relationships
- ClusterDetector: Finds memory clusters
- KnowledgeGapDetector: Identifies potential missing connections
"""

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

__all__ = [
    # Transitive
    "TransitiveInferenceEngine",
    "TransitiveConfig",
    "InferredEdge",
    "TransitiveResult",
    # Cluster
    "ClusterDetector",
    "ClusterConfig",
    "MemoryCluster",
    "ClusterResult",
]
