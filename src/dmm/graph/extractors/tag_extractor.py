"""
Tag-based relationship extractor.

Discovers relationships between memories based on shared tags.
Uses Jaccard-like similarity metrics to identify related memories
and creates RELATES_TO edges with weights based on overlap ratio.

Algorithm Complexity:
- Single extraction: O(n * t) where n is number of memories, t is avg tags per memory
- Tag normalization: O(t) per memory
- Overlap calculation: O(min(t1, t2)) per pair using set intersection

Mathematical Foundation:
- Overlap ratio = |A intersection B| / min(|A|, |B|)
- This metric ranges from 0.0 (no overlap) to 1.0 (complete subset)
- Jaccard similarity alternative: |A intersection B| / |A union B|
"""

import time
from dataclasses import dataclass
from typing import Iterator

from dmm.graph.edges import RelatesTo
from dmm.graph.extractors.base import (
    BaseExtractor,
    ExtractionMethod,
    ExtractionResult,
    MemoryLike,
)


@dataclass(frozen=True)
class TagExtractionConfig:
    """
    Configuration for tag-based extraction.
    
    Attributes:
        min_overlap_ratio: Minimum ratio of shared tags to create edge (0.0-1.0)
        min_overlap_count: Minimum absolute number of shared tags required
        max_edges_per_memory: Maximum edges to create per source memory
        normalize_tags: Whether to normalize tags (lowercase, strip whitespace)
        use_jaccard: Use Jaccard similarity instead of overlap ratio
    """
    
    min_overlap_ratio: float = 0.3
    min_overlap_count: int = 2
    max_edges_per_memory: int = 20
    normalize_tags: bool = True
    use_jaccard: bool = False


class TagExtractor(BaseExtractor):
    """
    Extracts relationships based on tag overlap between memories.
    
    This extractor analyzes the tags assigned to each memory and creates
    RELATES_TO edges between memories that share a significant number
    of tags. The edge weight is determined by the overlap ratio.
    
    The algorithm:
    1. Normalize tags for consistent comparison (optional)
    2. For each other memory, calculate tag overlap
    3. Filter by minimum overlap count and ratio
    4. Sort by overlap ratio (descending)
    5. Limit to max_edges_per_memory
    
    Example:
        Memory A tags: [authentication, security, api, jwt]
        Memory B tags: [authentication, security, oauth]
        
        Overlap: {authentication, security} = 2 tags
        Ratio: 2 / min(4, 3) = 2/3 = 0.667
        
        If min_overlap_count=2 and min_overlap_ratio=0.3:
        Creates RELATES_TO edge with weight=0.667
    """
    
    def __init__(self, config: TagExtractionConfig | None = None) -> None:
        """
        Initialize the tag extractor.
        
        Args:
            config: Extraction configuration, uses defaults if None
        """
        super().__init__()
        self._config = config or TagExtractionConfig()
    
    @property
    def config(self) -> TagExtractionConfig:
        """Return the current configuration."""
        return self._config
    
    def extract(
        self,
        memory: MemoryLike,
        all_memories: list[MemoryLike],
    ) -> ExtractionResult:
        """
        Extract tag-based relationships for a memory.
        
        Args:
            memory: The memory to analyze
            all_memories: All memories for comparison
            
        Returns:
            ExtractionResult with RELATES_TO edges based on tag overlap
        """
        start_time = time.perf_counter()
        
        memory_tags = self._normalize_tags(memory.tags)
        
        if not memory_tags:
            return self._build_result(
                edges=[],
                source_id=memory.id,
                method=ExtractionMethod.TAG_OVERLAP,
                duration_ms=(time.perf_counter() - start_time) * 1000,
                candidates_considered=0,
                edges_filtered=0,
                metadata={"reason": "source_memory_has_no_tags"},
            )
        
        candidates: list[tuple[str, float, list[str]]] = []
        candidates_considered = 0
        
        for other in all_memories:
            if other.id == memory.id:
                continue
            
            if other.status == "deprecated":
                continue
            
            candidates_considered += 1
            other_tags = self._normalize_tags(other.tags)
            
            if not other_tags:
                continue
            
            overlap = memory_tags & other_tags
            overlap_count = len(overlap)
            
            if overlap_count < self._config.min_overlap_count:
                continue
            
            if self._config.use_jaccard:
                union = memory_tags | other_tags
                ratio = overlap_count / len(union) if union else 0.0
            else:
                min_size = min(len(memory_tags), len(other_tags))
                ratio = overlap_count / min_size if min_size > 0 else 0.0
            
            if ratio >= self._config.min_overlap_ratio:
                candidates.append((other.id, ratio, sorted(overlap)))
        
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        edges_filtered = max(0, len(candidates) - self._config.max_edges_per_memory)
        selected = candidates[:self._config.max_edges_per_memory]
        
        edges: list[RelatesTo] = []
        for other_id, weight, shared_tags in selected:
            edge = RelatesTo(
                from_id=memory.id,
                to_id=other_id,
                weight=round(weight, 4),
                context=f"Shared tags: {', '.join(shared_tags)}",
            )
            edges.append(edge)
        
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        return self._build_result(
            edges=edges,
            source_id=memory.id,
            method=ExtractionMethod.TAG_OVERLAP,
            duration_ms=duration_ms,
            candidates_considered=candidates_considered,
            edges_filtered=edges_filtered,
            metadata={
                "source_tag_count": len(memory_tags),
                "metric": "jaccard" if self._config.use_jaccard else "overlap_ratio",
            },
        )
    
    def _normalize_tags(self, tags: list[str] | None) -> set[str]:
        """
        Normalize tags for consistent comparison.
        
        Args:
            tags: List of tag strings
            
        Returns:
            Set of normalized tag strings
        """
        if not tags:
            return set()
        
        if self._config.normalize_tags:
            return {tag.lower().strip() for tag in tags if tag and tag.strip()}
        
        return {tag for tag in tags if tag}
    
    def extract_bidirectional(
        self,
        memory: MemoryLike,
        all_memories: list[MemoryLike],
    ) -> ExtractionResult:
        """
        Extract relationships and create edges in both directions.
        
        For symmetric relationships like tag overlap, this creates
        both A->B and B->A edges. Useful when you want the graph
        to be navigable from either direction.
        
        Args:
            memory: The memory to analyze
            all_memories: All memories for comparison
            
        Returns:
            ExtractionResult with bidirectional RELATES_TO edges
        """
        result = self.extract(memory, all_memories)
        
        reverse_edges: list[RelatesTo] = []
        for edge in result.edges:
            if isinstance(edge, RelatesTo):
                reverse_edge = RelatesTo(
                    from_id=edge.to_id,
                    to_id=edge.from_id,
                    weight=edge.weight,
                    context=edge.context,
                )
                reverse_edges.append(reverse_edge)
        
        all_edges = list(result.edges) + reverse_edges
        
        return ExtractionResult(
            edges=all_edges,
            source_memory_id=result.source_memory_id,
            method=result.method,
            duration_ms=result.duration_ms,
            candidates_considered=result.candidates_considered,
            edges_filtered=result.edges_filtered,
            metadata={**result.metadata, "bidirectional": True},
        )
    
    def find_tag_clusters(
        self,
        memories: list[MemoryLike],
        min_cluster_size: int = 3,
    ) -> list[list[str]]:
        """
        Find clusters of memories that share common tags.
        
        Uses connected components algorithm on the tag overlap graph.
        
        Args:
            memories: All memories to analyze
            min_cluster_size: Minimum memories to form a cluster
            
        Returns:
            List of clusters, each cluster is a list of memory IDs
            
        Complexity: O(n^2 * t) for building adjacency, O(n) for BFS
        """
        adjacency: dict[str, set[str]] = {m.id: set() for m in memories}
        
        for i, m1 in enumerate(memories):
            tags1 = self._normalize_tags(m1.tags)
            if not tags1:
                continue
            
            for m2 in memories[i + 1:]:
                tags2 = self._normalize_tags(m2.tags)
                if not tags2:
                    continue
                
                overlap = tags1 & tags2
                if len(overlap) >= self._config.min_overlap_count:
                    adjacency[m1.id].add(m2.id)
                    adjacency[m2.id].add(m1.id)
        
        visited: set[str] = set()
        clusters: list[list[str]] = []
        
        for start_id in adjacency:
            if start_id in visited:
                continue
            
            cluster: list[str] = []
            stack = [start_id]
            
            while stack:
                node = stack.pop()
                if node in visited:
                    continue
                visited.add(node)
                cluster.append(node)
                
                for neighbor in adjacency[node]:
                    if neighbor not in visited:
                        stack.append(neighbor)
            
            if len(cluster) >= min_cluster_size:
                clusters.append(sorted(cluster))
        
        clusters.sort(key=len, reverse=True)
        return clusters
