"""
DMM Graph Retrieval Module.

Provides hybrid retrieval combining vector similarity search with
graph traversal for enhanced context gathering. The retrieval system:

- Performs initial vector search for semantic relevance
- Expands results via graph relationships
- Combines scores with configurable weights
- Assembles rich context with relationship annotations

Components:
- HybridRetriever: Main retrieval pipeline
- GraphContextAssembler: Enhanced context formatting
"""

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

__all__ = [
    # Retriever
    "HybridRetriever",
    "HybridRetrievalConfig",
    "RetrievalResult",
    "RetrievalStats",
    # Assembler
    "GraphContextAssembler",
    "ContextAssemblerConfig",
    "AssembledContext",
]
