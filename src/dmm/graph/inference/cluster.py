"""
Cluster detection and knowledge gap analysis.

Discovers groups of highly interconnected memories and identifies
potential missing relationships between related memories.

Features:
- Connected component detection
- Weighted clustering with edge thresholds
- Knowledge gap detection via tag similarity
- Cluster quality metrics

Algorithm Complexity:
- Connected components: O(V + E) using DFS/BFS
- Knowledge gap detection: O(V^2 * T) where T is avg tags per memory
- Cluster metrics: O(C * E_c) where C is clusters, E_c is edges per cluster
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from dmm.graph.extractors.base import MemoryLike


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClusterConfig:
    """
    Configuration for cluster detection.
    
    Attributes:
        min_cluster_size: Minimum memories to form a cluster
        min_edge_weight: Minimum edge weight to consider for clustering
        edge_types_for_clustering: Edge types to consider
        detect_knowledge_gaps: Whether to detect missing relationships
        gap_min_tag_similarity: Minimum Jaccard similarity for gap detection
        gap_max_results: Maximum gap candidates to return
        include_singletons: Include single-memory "clusters"
    """
    
    min_cluster_size: int = 3
    min_edge_weight: float = 0.5
    edge_types_for_clustering: tuple[str, ...] = (
        "RELATES_TO", "SUPPORTS", "DEPENDS_ON"
    )
    detect_knowledge_gaps: bool = True
    gap_min_tag_similarity: float = 0.4
    gap_max_results: int = 20
    include_singletons: bool = False


@dataclass
class MemoryCluster:
    """
    A cluster of related memories.
    
    Attributes:
        cluster_id: Unique cluster identifier
        memory_ids: List of memory IDs in the cluster
        size: Number of memories
        density: Edge density (edges / max_possible_edges)
        avg_edge_weight: Average weight of edges in cluster
        central_memory_id: Most connected memory (hub)
        common_tags: Tags shared by most members
        common_scope: Dominant scope if any
        internal_edges: Number of edges within cluster
    """
    
    cluster_id: str
    memory_ids: list[str] = field(default_factory=list)
    size: int = 0
    density: float = 0.0
    avg_edge_weight: float = 0.0
    central_memory_id: str | None = None
    common_tags: list[str] = field(default_factory=list)
    common_scope: str | None = None
    internal_edges: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "cluster_id": self.cluster_id,
            "memory_ids": self.memory_ids,
            "size": self.size,
            "density": round(self.density, 4),
            "avg_edge_weight": round(self.avg_edge_weight, 4),
            "central_memory_id": self.central_memory_id,
            "common_tags": self.common_tags,
            "common_scope": self.common_scope,
            "internal_edges": self.internal_edges,
        }


@dataclass
class KnowledgeGap:
    """
    A potential missing relationship.
    
    Attributes:
        memory_id_1: First memory ID
        memory_id_2: Second memory ID
        similarity_score: Jaccard similarity of tags
        shared_tags: Tags shared between memories
        same_scope: Whether memories are in same scope
        reason: Explanation for why this is a gap
    """
    
    memory_id_1: str
    memory_id_2: str
    similarity_score: float
    shared_tags: list[str] = field(default_factory=list)
    same_scope: bool = False
    reason: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "memory_id_1": self.memory_id_1,
            "memory_id_2": self.memory_id_2,
            "similarity_score": round(self.similarity_score, 4),
            "shared_tags": self.shared_tags,
            "same_scope": self.same_scope,
            "reason": self.reason,
        }


@dataclass
class ClusterResult:
    """
    Result of cluster detection.
    
    Attributes:
        clusters: List of detected clusters
        knowledge_gaps: List of potential missing relationships
        duration_ms: Time taken for detection
        total_memories: Total memories analyzed
        clustered_memories: Memories assigned to clusters
        singleton_count: Memories not in any cluster
        largest_cluster_size: Size of largest cluster
        avg_cluster_size: Average cluster size
    """
    
    clusters: list[MemoryCluster] = field(default_factory=list)
    knowledge_gaps: list[KnowledgeGap] = field(default_factory=list)
    duration_ms: float = 0.0
    total_memories: int = 0
    clustered_memories: int = 0
    singleton_count: int = 0
    largest_cluster_size: int = 0
    avg_cluster_size: float = 0.0
    
    @property
    def cluster_count(self) -> int:
        """Number of clusters found."""
        return len(self.clusters)
    
    @property
    def gap_count(self) -> int:
        """Number of knowledge gaps found."""
        return len(self.knowledge_gaps)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "cluster_count": self.cluster_count,
            "gap_count": self.gap_count,
            "duration_ms": round(self.duration_ms, 2),
            "total_memories": self.total_memories,
            "clustered_memories": self.clustered_memories,
            "singleton_count": self.singleton_count,
            "largest_cluster_size": self.largest_cluster_size,
            "avg_cluster_size": round(self.avg_cluster_size, 2),
            "clusters": [c.to_dict() for c in self.clusters],
            "knowledge_gaps": [g.to_dict() for g in self.knowledge_gaps],
        }


class ClusterDetector:
    """
    Detects clusters of related memories and knowledge gaps.
    
    The detector performs two main functions:
    
    1. Cluster Detection:
       - Builds adjacency graph from weighted edges
       - Finds connected components using DFS
       - Calculates cluster metrics (density, centrality)
       - Identifies common tags and scopes
    
    2. Knowledge Gap Detection:
       - Finds memory pairs with high tag similarity
       - Checks if they have direct relationships
       - Flags unconnected similar memories as gaps
    
    Clustering Algorithm:
    1. Build adjacency list from edges meeting weight threshold
    2. Run DFS to find connected components
    3. Filter components by minimum size
    4. Calculate metrics for each cluster
    
    Gap Detection Algorithm:
    1. For each pair of memories not directly connected
    2. Calculate Jaccard similarity of tags
    3. If similarity exceeds threshold, flag as gap
    4. Sort by similarity and return top candidates
    
    Example:
        detector = ClusterDetector(graph_store, config)
        result = detector.detect_clusters()
        for cluster in result.clusters:
            print(f"Cluster {cluster.cluster_id}: {cluster.size} memories")
        for gap in result.knowledge_gaps:
            print(f"Gap: {gap.memory_id_1} <-> {gap.memory_id_2}")
    """
    
    def __init__(
        self,
        graph_store: Any,
        config: ClusterConfig | None = None,
    ) -> None:
        """
        Initialize the cluster detector.
        
        Args:
            graph_store: Knowledge graph store instance
            config: Detection configuration
        """
        self._graph = graph_store
        self._config = config or ClusterConfig()
    
    @property
    def config(self) -> ClusterConfig:
        """Return the current configuration."""
        return self._config
    
    def detect_clusters(
        self,
        memory_ids: list[str] | None = None,
    ) -> ClusterResult:
        """
        Detect clusters in the knowledge graph.
        
        Args:
            memory_ids: Optional subset of memories to analyze
            
        Returns:
            ClusterResult with clusters and optional gaps
        """
        start_time = time.perf_counter()
        result = ClusterResult()
        
        try:
            if memory_ids:
                memories = [
                    self._graph.get_memory_node(mid)
                    for mid in memory_ids
                ]
                memories = [m for m in memories if m is not None]
            else:
                memories = self._graph.get_all_memory_nodes()
        except Exception as e:
            logger.error(f"Failed to get memories: {e}")
            result.duration_ms = (time.perf_counter() - start_time) * 1000
            return result
        
        result.total_memories = len(memories)
        
        if not memories:
            result.duration_ms = (time.perf_counter() - start_time) * 1000
            return result
        
        memory_map = {
            (m.id if hasattr(m, "id") else str(m)): m
            for m in memories
        }
        memory_id_set = set(memory_map.keys())
        
        adjacency = self._build_adjacency(memory_id_set)
        
        components = self._find_connected_components(adjacency, memory_id_set)
        
        clusters: list[MemoryCluster] = []
        clustered_ids: set[str] = set()
        
        for i, component in enumerate(components):
            if len(component) < self._config.min_cluster_size:
                if not self._config.include_singletons:
                    continue
            
            cluster = self._build_cluster(
                cluster_id=f"cluster_{i:03d}",
                memory_ids=list(component),
                memory_map=memory_map,
                adjacency=adjacency,
            )
            clusters.append(cluster)
            clustered_ids.update(component)
        
        clusters.sort(key=lambda c: c.size, reverse=True)
        
        result.clusters = clusters
        result.clustered_memories = len(clustered_ids)
        result.singleton_count = result.total_memories - result.clustered_memories
        
        if clusters:
            result.largest_cluster_size = clusters[0].size
            result.avg_cluster_size = sum(c.size for c in clusters) / len(clusters)
        
        if self._config.detect_knowledge_gaps:
            gaps = self._find_knowledge_gaps(memory_map, adjacency)
            result.knowledge_gaps = gaps
        
        result.duration_ms = (time.perf_counter() - start_time) * 1000
        
        return result
    
    def _build_adjacency(
        self,
        memory_ids: set[str],
    ) -> dict[str, set[str]]:
        """
        Build adjacency list from graph edges.
        
        Args:
            memory_ids: Set of memory IDs to include
            
        Returns:
            Adjacency dict mapping ID to set of connected IDs
        """
        adjacency: dict[str, set[str]] = {mid: set() for mid in memory_ids}
        
        for mid in memory_ids:
            for edge_type in self._config.edge_types_for_clustering:
                try:
                    edges = self._graph.get_edges_from(mid, edge_type)
                    for edge in edges:
                        target = edge.get("to_id", edge.get("target_id", ""))
                        weight = edge.get("weight", edge.get("strength", 1.0))
                        
                        if target in memory_ids and weight >= self._config.min_edge_weight:
                            adjacency[mid].add(target)
                            adjacency[target].add(mid)
                except Exception as e:
                    logger.debug(f"Failed to get edges for {mid}: {e}")
        
        return adjacency
    
    def _find_connected_components(
        self,
        adjacency: dict[str, set[str]],
        all_ids: set[str],
    ) -> list[set[str]]:
        """
        Find connected components using DFS.
        
        Args:
            adjacency: Adjacency list
            all_ids: All node IDs
            
        Returns:
            List of components (sets of IDs)
        """
        visited: set[str] = set()
        components: list[set[str]] = []
        
        for start_id in all_ids:
            if start_id in visited:
                continue
            
            component: set[str] = set()
            stack = [start_id]
            
            while stack:
                node = stack.pop()
                if node in visited:
                    continue
                
                visited.add(node)
                component.add(node)
                
                for neighbor in adjacency.get(node, set()):
                    if neighbor not in visited:
                        stack.append(neighbor)
            
            components.append(component)
        
        return components
    
    def _build_cluster(
        self,
        cluster_id: str,
        memory_ids: list[str],
        memory_map: dict[str, Any],
        adjacency: dict[str, set[str]],
    ) -> MemoryCluster:
        """
        Build a cluster with metrics.
        
        Args:
            cluster_id: Cluster identifier
            memory_ids: IDs in the cluster
            memory_map: Map of ID to memory object
            adjacency: Adjacency list
            
        Returns:
            MemoryCluster with calculated metrics
        """
        size = len(memory_ids)
        id_set = set(memory_ids)
        
        internal_edges = 0
        edge_weights: list[float] = []
        degree_map: dict[str, int] = {}
        
        for mid in memory_ids:
            neighbors = adjacency.get(mid, set()) & id_set
            degree_map[mid] = len(neighbors)
            
            for neighbor in neighbors:
                if mid < neighbor:
                    internal_edges += 1
                    
                    for edge_type in self._config.edge_types_for_clustering:
                        try:
                            edges = self._graph.get_edges_from(mid, edge_type)
                            for edge in edges:
                                if edge.get("to_id", edge.get("target_id", "")) == neighbor:
                                    weight = edge.get("weight", edge.get("strength", 0.5))
                                    edge_weights.append(weight)
                        except Exception:
                            pass
        
        max_edges = (size * (size - 1)) // 2 if size > 1 else 1
        density = internal_edges / max_edges if max_edges > 0 else 0.0
        
        avg_weight = sum(edge_weights) / len(edge_weights) if edge_weights else 0.0
        
        central_id = max(degree_map, key=degree_map.get) if degree_map else None
        
        tag_counts: dict[str, int] = defaultdict(int)
        scope_counts: dict[str, int] = defaultdict(int)
        
        for mid in memory_ids:
            memory = memory_map.get(mid)
            if memory:
                tags = getattr(memory, "tags", []) or []
                for tag in tags:
                    tag_counts[tag.lower()] += 1
                
                scope = getattr(memory, "scope", None)
                if scope:
                    scope_counts[scope] += 1
        
        common_tags = [
            tag for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1])
            if count >= size * 0.5
        ][:5]
        
        common_scope = None
        if scope_counts:
            top_scope, top_count = max(scope_counts.items(), key=lambda x: x[1])
            if top_count >= size * 0.5:
                common_scope = top_scope
        
        return MemoryCluster(
            cluster_id=cluster_id,
            memory_ids=sorted(memory_ids),
            size=size,
            density=density,
            avg_edge_weight=avg_weight,
            central_memory_id=central_id,
            common_tags=common_tags,
            common_scope=common_scope,
            internal_edges=internal_edges,
        )
    
    def _find_knowledge_gaps(
        self,
        memory_map: dict[str, Any],
        adjacency: dict[str, set[str]],
    ) -> list[KnowledgeGap]:
        """
        Find potential missing relationships.
        
        Args:
            memory_map: Map of ID to memory object
            adjacency: Adjacency list
            
        Returns:
            List of knowledge gaps
        """
        gaps: list[KnowledgeGap] = []
        
        memory_tags: dict[str, set[str]] = {}
        memory_scopes: dict[str, str] = {}
        
        for mid, memory in memory_map.items():
            tags = getattr(memory, "tags", []) or []
            memory_tags[mid] = {t.lower() for t in tags}
            memory_scopes[mid] = getattr(memory, "scope", "")
        
        memory_ids = list(memory_map.keys())
        
        for i, mid1 in enumerate(memory_ids):
            tags1 = memory_tags.get(mid1, set())
            if not tags1:
                continue
            
            for mid2 in memory_ids[i + 1:]:
                if mid2 in adjacency.get(mid1, set()):
                    continue
                
                tags2 = memory_tags.get(mid2, set())
                if not tags2:
                    continue
                
                intersection = tags1 & tags2
                union = tags1 | tags2
                
                jaccard = len(intersection) / len(union) if union else 0.0
                
                same_scope = memory_scopes.get(mid1) == memory_scopes.get(mid2)
                if same_scope:
                    jaccard *= 1.2
                
                if jaccard >= self._config.gap_min_tag_similarity:
                    reason = f"High tag similarity ({jaccard:.2f}) but no direct relationship"
                    if same_scope:
                        reason += f" (same scope: {memory_scopes.get(mid1)})"
                    
                    gaps.append(KnowledgeGap(
                        memory_id_1=mid1,
                        memory_id_2=mid2,
                        similarity_score=jaccard,
                        shared_tags=sorted(intersection),
                        same_scope=same_scope,
                        reason=reason,
                    ))
        
        gaps.sort(key=lambda g: g.similarity_score, reverse=True)
        
        return gaps[:self._config.gap_max_results]
    
    def get_cluster_by_memory(self, memory_id: str) -> MemoryCluster | None:
        """
        Find the cluster containing a specific memory.
        
        Args:
            memory_id: Memory ID to search for
            
        Returns:
            MemoryCluster or None if not in any cluster
        """
        result = self.detect_clusters()
        
        for cluster in result.clusters:
            if memory_id in cluster.memory_ids:
                return cluster
        
        return None
    
    def suggest_cluster_merges(
        self,
        min_shared_tags: int = 2,
    ) -> list[tuple[str, str, list[str]]]:
        """
        Suggest clusters that might be merged.
        
        Args:
            min_shared_tags: Minimum shared tags to suggest merge
            
        Returns:
            List of (cluster1_id, cluster2_id, shared_tags) tuples
        """
        result = self.detect_clusters()
        suggestions: list[tuple[str, str, list[str]]] = []
        
        clusters = result.clusters
        
        for i, c1 in enumerate(clusters):
            for c2 in clusters[i + 1:]:
                tags1 = set(c1.common_tags)
                tags2 = set(c2.common_tags)
                
                shared = tags1 & tags2
                
                if len(shared) >= min_shared_tags:
                    suggestions.append((c1.cluster_id, c2.cluster_id, sorted(shared)))
        
        suggestions.sort(key=lambda x: len(x[2]), reverse=True)
        
        return suggestions
