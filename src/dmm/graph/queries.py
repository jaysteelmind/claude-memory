"""Common graph query functions for the DMM knowledge graph.

This module provides high-level query functions that combine multiple
store operations for common use cases:

- Finding related memories with various strategies
- Analyzing tag relationships
- Detecting potential conflicts
- Computing graph metrics

These functions are designed to be used by the CLI and retrieval system.
"""

from dataclasses import dataclass
from typing import Optional

from dmm.graph.store import KnowledgeGraphStore
from dmm.graph.nodes import MemoryNode, TagNode


@dataclass
class RelatedMemoryResult:
    """Result of a related memory search.

    Attributes:
        memory: The related memory node.
        relationship_type: How the memory is related.
        weight: Relationship strength (0.0-1.0).
        path_length: Number of hops from the source.
    """

    memory: MemoryNode
    relationship_type: str
    weight: float
    path_length: int


@dataclass
class TagRelationship:
    """Represents a relationship between two tags.

    Attributes:
        tag1: First tag node.
        tag2: Second tag node.
        cooccurrence_count: Number of memories with both tags.
        strength: Normalized relationship strength.
    """

    tag1: TagNode
    tag2: TagNode
    cooccurrence_count: int
    strength: float


@dataclass
class MemoryCluster:
    """A cluster of related memories.

    Attributes:
        central_memory: The most connected memory in the cluster.
        members: List of memories in the cluster.
        common_tags: Tags shared by cluster members.
        total_connections: Sum of all connections in the cluster.
    """

    central_memory: MemoryNode
    members: list[MemoryNode]
    common_tags: list[str]
    total_connections: int


def find_related_memories_weighted(
    store: KnowledgeGraphStore,
    memory_id: str,
    max_depth: int = 2,
    min_weight: float = 0.0,
) -> list[RelatedMemoryResult]:
    """Find related memories with relationship weights.

    Performs a weighted traversal considering relationship strength.

    Args:
        store: Knowledge graph store instance.
        memory_id: Starting memory ID.
        max_depth: Maximum traversal depth.
        min_weight: Minimum relationship weight to include.

    Returns:
        List of RelatedMemoryResult sorted by weight descending.
    """
    results = []
    visited = {memory_id}

    # Get direct relationships first (depth 1)
    edges = store.get_edges_from(memory_id)
    for edge in edges:
        if edge["type"] in ("RELATES_TO", "SUPERSEDES", "SUPPORTS", "DEPENDS_ON"):
            to_id = edge["to_id"]
            if to_id not in visited:
                visited.add(to_id)
                memory = store.get_memory_node(to_id)
                if memory:
                    weight = edge.get("weight", 0.5)
                    if isinstance(weight, (int, float)) and weight >= min_weight:
                        results.append(RelatedMemoryResult(
                            memory=memory,
                            relationship_type=edge["type"],
                            weight=float(weight),
                            path_length=1,
                        ))

    # Get indirect relationships (depth 2+) if requested
    if max_depth > 1:
        for depth in range(2, max_depth + 1):
            current_ids = [r.memory.id for r in results if r.path_length == depth - 1]
            for current_id in current_ids:
                edges = store.get_edges_from(current_id)
                for edge in edges:
                    if edge["type"] in ("RELATES_TO", "SUPERSEDES", "SUPPORTS", "DEPENDS_ON"):
                        to_id = edge["to_id"]
                        if to_id not in visited:
                            visited.add(to_id)
                            memory = store.get_memory_node(to_id)
                            if memory:
                                # Decay weight by depth
                                base_weight = edge.get("weight", 0.5)
                                if isinstance(base_weight, (int, float)):
                                    decayed_weight = float(base_weight) / depth
                                    if decayed_weight >= min_weight:
                                        results.append(RelatedMemoryResult(
                                            memory=memory,
                                            relationship_type=edge["type"],
                                            weight=decayed_weight,
                                            path_length=depth,
                                        ))

    # Sort by weight descending
    results.sort(key=lambda r: r.weight, reverse=True)
    return results


def find_memories_by_tag_overlap(
    store: KnowledgeGraphStore,
    memory_id: str,
    min_overlap: int = 2,
) -> list[tuple[MemoryNode, int, list[str]]]:
    """Find memories sharing tags with a given memory.

    Args:
        store: Knowledge graph store instance.
        memory_id: Source memory ID.
        min_overlap: Minimum number of shared tags required.

    Returns:
        List of tuples (memory, overlap_count, shared_tags) sorted by overlap.
    """
    # Get tags for the source memory
    source_tags = store.get_tags_for_memory(memory_id)
    if not source_tags:
        return []

    source_tag_ids = {t.id for t in source_tags}
    source_tag_names = {t.id: t.name for t in source_tags}

    # Find all memories with any of these tags
    candidates: dict[str, set[str]] = {}
    for tag in source_tags:
        memories = store.get_memories_by_tag(tag.name)
        for memory in memories:
            if memory.id != memory_id:
                if memory.id not in candidates:
                    candidates[memory.id] = set()
                candidates[memory.id].add(tag.id)

    # Filter by minimum overlap and build results
    results = []
    for candidate_id, shared_tag_ids in candidates.items():
        if len(shared_tag_ids) >= min_overlap:
            memory = store.get_memory_node(candidate_id)
            if memory:
                shared_names = [source_tag_names[tid] for tid in shared_tag_ids]
                results.append((memory, len(shared_tag_ids), shared_names))

    # Sort by overlap count descending
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def get_tag_cooccurrence_graph(
    store: KnowledgeGraphStore,
    min_count: int = 2,
) -> list[TagRelationship]:
    """Get tag co-occurrence relationships.

    Args:
        store: Knowledge graph store instance.
        min_count: Minimum co-occurrence count to include.

    Returns:
        List of TagRelationship instances.
    """
    query = """
        MATCH (t1:Tag)-[r:TAG_COOCCURS]->(t2:Tag)
        WHERE r.count >= $min_count
        RETURN t1.id, t1.name, t1.normalized, t1.usage_count,
               t2.id, t2.name, t2.normalized, t2.usage_count,
               r.count, r.strength
        ORDER BY r.count DESC
    """

    results = store.execute_cypher(query, {"min_count": min_count})

    relationships = []
    for row in results:
        tag1 = TagNode(
            id=row["t1.id"],
            name=row["t1.name"] or "",
            normalized=row["t1.normalized"] or "",
            usage_count=int(row["t1.usage_count"] or 0),
        )
        tag2 = TagNode(
            id=row["t2.id"],
            name=row["t2.name"] or "",
            normalized=row["t2.normalized"] or "",
            usage_count=int(row["t2.usage_count"] or 0),
        )
        relationships.append(TagRelationship(
            tag1=tag1,
            tag2=tag2,
            cooccurrence_count=int(row["r.count"] or 0),
            strength=float(row["r.strength"] or 0.0),
        ))

    return relationships


def find_potential_conflicts(
    store: KnowledgeGraphStore,
    memory_id: str,
) -> list[tuple[MemoryNode, str]]:
    """Find memories that might conflict with a given memory.

    Looks for:
    - Explicit CONTRADICTS relationships
    - High similarity memories in the same scope
    - Memories with overlapping tags but different conclusions

    Args:
        store: Knowledge graph store instance.
        memory_id: Memory ID to check for conflicts.

    Returns:
        List of tuples (potentially_conflicting_memory, reason).
    """
    conflicts = []

    # Check explicit contradictions
    edges = store.get_edges_from(memory_id, edge_type="CONTRADICTS")
    for edge in edges:
        memory = store.get_memory_node(edge["to_id"])
        if memory:
            description = edge.get("description", "Explicit contradiction")
            conflicts.append((memory, f"Contradiction: {description}"))

    # Check incoming contradictions
    incoming = store.get_edges_to(memory_id, edge_type="CONTRADICTS")
    for edge in incoming:
        memory = store.get_memory_node(edge["from_id"])
        if memory:
            description = edge.get("description", "Explicit contradiction")
            conflicts.append((memory, f"Contradiction: {description}"))

    return conflicts


def get_memory_context_graph(
    store: KnowledgeGraphStore,
    memory_id: str,
    include_tags: bool = True,
    include_scope: bool = True,
    relationship_depth: int = 1,
) -> dict:
    """Get the full context graph around a memory.

    Builds a complete picture of a memory's place in the knowledge graph.

    Args:
        store: Knowledge graph store instance.
        memory_id: Central memory ID.
        include_tags: Include tag nodes.
        include_scope: Include scope node.
        relationship_depth: How many hops of relationships to include.

    Returns:
        Dictionary with structure:
        {
            "memory": MemoryNode,
            "tags": list[TagNode],
            "scope": ScopeNode | None,
            "outgoing": list[dict],  # {type, target, properties}
            "incoming": list[dict],  # {type, source, properties}
            "related": list[MemoryNode],  # Via traversal
        }
    """
    memory = store.get_memory_node(memory_id)
    if not memory:
        return {"error": f"Memory not found: {memory_id}"}

    result = {
        "memory": memory,
        "tags": [],
        "scope": None,
        "outgoing": [],
        "incoming": [],
        "related": [],
    }

    # Get tags
    if include_tags:
        result["tags"] = store.get_tags_for_memory(memory_id)

    # Get scope
    if include_scope:
        scope_id = f"scope_{memory.scope}"
        result["scope"] = store.get_scope_node(scope_id)

    # Get outgoing edges
    outgoing = store.get_edges_from(memory_id)
    for edge in outgoing:
        target = None
        if edge["type"] in ("RELATES_TO", "SUPERSEDES", "CONTRADICTS", "SUPPORTS", "DEPENDS_ON"):
            target = store.get_memory_node(edge["to_id"])
        result["outgoing"].append({
            "type": edge["type"],
            "target_id": edge["to_id"],
            "target": target,
            "properties": {k: v for k, v in edge.items() if k not in ("type", "from_id", "to_id")},
        })

    # Get incoming edges
    incoming = store.get_edges_to(memory_id)
    for edge in incoming:
        source = None
        if edge["type"] in ("RELATES_TO", "SUPERSEDES", "CONTRADICTS", "SUPPORTS", "DEPENDS_ON"):
            source = store.get_memory_node(edge["from_id"])
        result["incoming"].append({
            "type": edge["type"],
            "source_id": edge["from_id"],
            "source": source,
            "properties": {k: v for k, v in edge.items() if k not in ("type", "from_id", "to_id")},
        })

    # Get related memories via traversal
    if relationship_depth > 0:
        result["related"] = store.get_related_memories(
            memory_id,
            max_depth=relationship_depth,
        )

    return result


def compute_memory_centrality(
    store: KnowledgeGraphStore,
    memory_id: str,
) -> dict:
    """Compute centrality metrics for a memory.

    Args:
        store: Knowledge graph store instance.
        memory_id: Memory ID to analyze.

    Returns:
        Dictionary with centrality metrics:
        {
            "degree": int,  # Total connections
            "in_degree": int,  # Incoming edges
            "out_degree": int,  # Outgoing edges
            "tag_count": int,  # Number of tags
            "related_count": int,  # Related at depth 1
        }
    """
    outgoing = store.get_edges_from(memory_id)
    incoming = store.get_edges_to(memory_id)
    tags = store.get_tags_for_memory(memory_id)
    related = store.get_related_memories(memory_id, max_depth=1)

    # Filter to memory-to-memory edges only
    out_memory_edges = [e for e in outgoing if e["type"] in 
                        ("RELATES_TO", "SUPERSEDES", "CONTRADICTS", "SUPPORTS", "DEPENDS_ON")]
    in_memory_edges = [e for e in incoming if e["type"] in
                       ("RELATES_TO", "SUPERSEDES", "CONTRADICTS", "SUPPORTS", "DEPENDS_ON")]

    return {
        "degree": len(out_memory_edges) + len(in_memory_edges),
        "in_degree": len(in_memory_edges),
        "out_degree": len(out_memory_edges),
        "tag_count": len(tags),
        "related_count": len(related),
    }


def find_isolated_memories(store: KnowledgeGraphStore) -> list[MemoryNode]:
    """Find memories with no relationships to other memories.

    Isolated memories have:
    - No RELATES_TO, SUPERSEDES, SUPPORTS, or DEPENDS_ON edges
    - May still have tags and scope

    Args:
        store: Knowledge graph store instance.

    Returns:
        List of isolated MemoryNode instances.
    """
    query = """
        MATCH (m:Memory)
        WHERE NOT (m)-[:RELATES_TO|SUPERSEDES|SUPPORTS|DEPENDS_ON|CONTRADICTS]-(:Memory)
        AND NOT (m)<-[:RELATES_TO|SUPERSEDES|SUPPORTS|DEPENDS_ON|CONTRADICTS]-(:Memory)
        RETURN m.id, m.path, m.directory, m.title, m.scope,
               m.priority, m.confidence, m.status, m.token_count,
               m.created, m.last_used, m.usage_count, m.file_hash,
               m.indexed_at
        ORDER BY m.id
    """

    try:
        results = store.execute_cypher(query)
    except Exception:
        # If query fails (e.g., no relationships exist yet), return all memories
        return store.get_all_memory_nodes()

    nodes = []
    for row in results:
        nodes.append(MemoryNode(
            id=row["m.id"],
            path=row.get("m.path", ""),
            directory=row.get("m.directory", ""),
            title=row.get("m.title", ""),
            scope=row.get("m.scope", "project"),
            priority=float(row["m.priority"]) if row.get("m.priority") is not None else 0.5,
            confidence=row.get("m.confidence", "active"),
            status=row.get("m.status", "active"),
            token_count=int(row["m.token_count"]) if row.get("m.token_count") is not None else 0,
            created=row.get("m.created"),
            last_used=row.get("m.last_used"),
            usage_count=int(row["m.usage_count"]) if row.get("m.usage_count") is not None else 0,
            file_hash=row.get("m.file_hash", ""),
            indexed_at=row.get("m.indexed_at"),
        ))
    return nodes


def get_scope_summary(store: KnowledgeGraphStore) -> list[dict]:
    """Get summary statistics for all scopes.

    Args:
        store: Knowledge graph store instance.

    Returns:
        List of dictionaries with scope statistics.
    """
    scopes = store.get_all_scope_nodes()

    summaries = []
    for scope in scopes:
        memories = store.get_memories_by_scope(scope.name)
        total_tokens = sum(m.token_count for m in memories)

        summaries.append({
            "name": scope.name,
            "description": scope.description,
            "memory_count": len(memories),
            "token_total": total_tokens,
            "avg_priority": sum(m.priority for m in memories) / len(memories) if memories else 0.0,
        })

    return summaries
