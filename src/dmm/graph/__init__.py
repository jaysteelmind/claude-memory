"""DMM Knowledge Graph Module.

This module provides the knowledge graph infrastructure for DMM,
enabling rich relationships between memories, tags, scopes, and concepts.

Main components:
- KnowledgeGraphStore: Primary interface for graph operations
- Node classes: MemoryNode, TagNode, ScopeNode, ConceptNode
- Edge classes: RelatesTo, Supersedes, Contradicts, Supports, etc.
- Migration: Tools to populate graph from existing memories
- Queries: High-level query functions

Example usage:
    from dmm.graph import KnowledgeGraphStore, MemoryNode

    store = KnowledgeGraphStore(Path(".dmm/index/knowledge.kuzu"))
    store.initialize()

    # Create a memory node
    node = MemoryNode(
        id="mem_2026_01_20_001",
        path="project/auth.md",
        ...
    )
    store.upsert_memory_node(node)

    # Find related memories
    related = store.get_related_memories("mem_2026_01_20_001", max_depth=2)
"""

from dmm.graph.store import KnowledgeGraphStore, GraphStats
from dmm.graph.schema import (
    initialize_schema,
    get_schema_version,
    get_node_tables,
    get_edge_tables,
    SCHEMA_VERSION,
)
from dmm.graph.nodes import (
    MemoryNode,
    TagNode,
    ScopeNode,
    ConceptNode,
    SCOPE_DEFINITIONS,
    create_all_scope_nodes,
)
from dmm.graph.edges import (
    Edge,
    RelatesTo,
    Supersedes,
    Contradicts,
    Supports,
    DependsOn,
    HasTag,
    InScope,
    TagCooccurs,
    About,
    Defines,
    EdgeType,
    create_edge,
)
from dmm.graph.migration import (
    GraphMigration,
    MigrationStats,
    migrate_from_memory_store,
)
from dmm.graph.queries import (
    RelatedMemoryResult,
    TagRelationship,
    MemoryCluster,
    find_related_memories_weighted,
    find_memories_by_tag_overlap,
    get_tag_cooccurrence_graph,
    find_potential_conflicts,
    get_memory_context_graph,
    compute_memory_centrality,
    find_isolated_memories,
    get_scope_summary,
)

__all__ = [
    # Store
    "KnowledgeGraphStore",
    "GraphStats",
    # Schema
    "initialize_schema",
    "get_schema_version",
    "get_node_tables",
    "get_edge_tables",
    "SCHEMA_VERSION",
    # Nodes
    "MemoryNode",
    "TagNode",
    "ScopeNode",
    "ConceptNode",
    "SCOPE_DEFINITIONS",
    "create_all_scope_nodes",
    # Edges
    "Edge",
    "RelatesTo",
    "Supersedes",
    "Contradicts",
    "Supports",
    "DependsOn",
    "HasTag",
    "InScope",
    "TagCooccurs",
    "About",
    "Defines",
    "EdgeType",
    "create_edge",
    # Migration
    "GraphMigration",
    "MigrationStats",
    "migrate_from_memory_store",
    # Queries
    "RelatedMemoryResult",
    "TagRelationship",
    "MemoryCluster",
    "find_related_memories_weighted",
    "find_memories_by_tag_overlap",
    "get_tag_cooccurrence_graph",
    "find_potential_conflicts",
    "get_memory_context_graph",
    "compute_memory_centrality",
    "find_isolated_memories",
    "get_scope_summary",
]
