"""
Semantic relationship extractor.

Discovers relationships between memories based on embedding similarity.
Uses cosine similarity on composite embeddings to identify semantically
related memories and creates RELATES_TO or SUPPORTS edges.

Algorithm Complexity:
- Single extraction: O(n * d) where n is number of memories, d is embedding dimension
- Cosine similarity: O(d) per pair
- Batch optimization possible with matrix operations: O(n * d) for all pairs

Mathematical Foundation:
- Cosine similarity: cos(A, B) = (A . B) / (||A|| * ||B||)
- Range: [-1, 1] for general vectors, [0, 1] for normalized embeddings
- Threshold-based classification:
  - similarity >= 0.85: SUPPORTS (strong semantic alignment)
  - similarity >= 0.75: RELATES_TO (topical relationship)
"""

import time
from dataclasses import dataclass
from typing import Iterator, Sequence

import numpy as np
from numpy.typing import NDArray

from dmm.graph.edges import RelatesTo, Supports
from dmm.graph.extractors.base import (
    BaseExtractor,
    ExtractionMethod,
    ExtractionResult,
    MemoryLike,
    Edge,
)


@dataclass(frozen=True)
class SemanticExtractionConfig:
    """
    Configuration for semantic extraction.
    
    Attributes:
        relates_threshold: Minimum similarity for RELATES_TO edge (0.0-1.0)
        supports_threshold: Minimum similarity for SUPPORTS edge (0.0-1.0)
        max_edges_per_memory: Maximum edges to create per source memory
        embedding_attribute: Name of the embedding attribute on memory objects
        use_normalized_embeddings: Whether embeddings are pre-normalized
        exclude_same_scope: Exclude memories in the same scope from results
        scope_similarity_boost: Boost factor for memories in related scopes
    """
    
    relates_threshold: float = 0.75
    supports_threshold: float = 0.85
    max_edges_per_memory: int = 15
    embedding_attribute: str = "composite_embedding"
    use_normalized_embeddings: bool = False
    exclude_same_scope: bool = False
    scope_similarity_boost: float = 0.0


class SemanticExtractor(BaseExtractor):
    """
    Extracts relationships based on embedding similarity.
    
    This extractor computes cosine similarity between memory embeddings
    to discover semantically related content. It creates two types of edges:
    
    - SUPPORTS: For very high similarity (>= 0.85 default), indicating
      memories that reinforce or provide evidence for each other
    - RELATES_TO: For moderate similarity (>= 0.75 default), indicating
      topical or conceptual relationships
    
    The algorithm:
    1. Get the source memory's embedding vector
    2. For each other memory, compute cosine similarity
    3. Classify edges based on similarity thresholds
    4. Sort by similarity (descending)
    5. Limit to max_edges_per_memory
    
    Optimization Notes:
    - For large memory sets, consider using batch matrix operations
    - Pre-normalizing embeddings allows dot product instead of full cosine
    - Approximate nearest neighbor (ANN) indices can speed up large-scale search
    """
    
    def __init__(self, config: SemanticExtractionConfig | None = None) -> None:
        """
        Initialize the semantic extractor.
        
        Args:
            config: Extraction configuration, uses defaults if None
        """
        super().__init__()
        self._config = config or SemanticExtractionConfig()
        self._embedding_cache: dict[str, NDArray[np.float64]] = {}
    
    @property
    def config(self) -> SemanticExtractionConfig:
        """Return the current configuration."""
        return self._config
    
    def extract(
        self,
        memory: MemoryLike,
        all_memories: list[MemoryLike],
    ) -> ExtractionResult:
        """
        Extract semantic relationships for a memory.
        
        Args:
            memory: The memory to analyze
            all_memories: All memories for comparison
            
        Returns:
            ExtractionResult with RELATES_TO and SUPPORTS edges
        """
        start_time = time.perf_counter()
        
        memory_embedding = self._get_embedding(memory)
        
        if memory_embedding is None or len(memory_embedding) == 0:
            return self._build_result(
                edges=[],
                source_id=memory.id,
                method=ExtractionMethod.SEMANTIC_SIMILARITY,
                duration_ms=(time.perf_counter() - start_time) * 1000,
                candidates_considered=0,
                edges_filtered=0,
                metadata={"reason": "source_memory_has_no_embedding"},
            )
        
        memory_vec = np.asarray(memory_embedding, dtype=np.float64)
        
        if not self._config.use_normalized_embeddings:
            memory_norm = np.linalg.norm(memory_vec)
            if memory_norm > 0:
                memory_vec = memory_vec / memory_norm
        
        candidates: list[tuple[str, float, str]] = []
        candidates_considered = 0
        
        for other in all_memories:
            if other.id == memory.id:
                continue
            
            if other.status == "deprecated":
                continue
            
            if self._config.exclude_same_scope and other.scope == memory.scope:
                continue
            
            candidates_considered += 1
            
            other_embedding = self._get_embedding(other)
            if other_embedding is None or len(other_embedding) == 0:
                continue
            
            other_vec = np.asarray(other_embedding, dtype=np.float64)
            
            if not self._config.use_normalized_embeddings:
                other_norm = np.linalg.norm(other_vec)
                if other_norm > 0:
                    other_vec = other_vec / other_norm
            
            similarity = float(np.dot(memory_vec, other_vec))
            
            if self._config.scope_similarity_boost > 0:
                if self._scopes_related(memory.scope, other.scope):
                    similarity = min(1.0, similarity + self._config.scope_similarity_boost)
            
            if similarity >= self._config.relates_threshold:
                edge_type = "SUPPORTS" if similarity >= self._config.supports_threshold else "RELATES_TO"
                candidates.append((other.id, similarity, edge_type))
        
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        edges_filtered = max(0, len(candidates) - self._config.max_edges_per_memory)
        selected = candidates[:self._config.max_edges_per_memory]
        
        edges: list[Edge] = []
        for other_id, similarity, edge_type in selected:
            if edge_type == "SUPPORTS":
                edge = Supports(
                    from_id=memory.id,
                    to_id=other_id,
                    strength=round(similarity, 4),
                )
            else:
                edge = RelatesTo(
                    from_id=memory.id,
                    to_id=other_id,
                    weight=round(similarity, 4),
                    context=f"Semantic similarity: {similarity:.3f}",
                )
            edges.append(edge)
        
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        return self._build_result(
            edges=edges,
            source_id=memory.id,
            method=ExtractionMethod.SEMANTIC_SIMILARITY,
            duration_ms=duration_ms,
            candidates_considered=candidates_considered,
            edges_filtered=edges_filtered,
            metadata={
                "embedding_dimension": len(memory_embedding),
                "supports_count": sum(1 for e in edges if isinstance(e, Supports)),
                "relates_count": sum(1 for e in edges if isinstance(e, RelatesTo)),
            },
        )
    
    def extract_batch_optimized(
        self,
        memories: list[MemoryLike],
    ) -> list[ExtractionResult]:
        """
        Extract relationships for all memories using matrix operations.
        
        This optimized version computes all pairwise similarities in a single
        matrix operation, which is more efficient for large memory sets.
        
        Args:
            memories: All memories to analyze
            
        Returns:
            List of ExtractionResults, one per memory
            
        Complexity: O(n^2 * d) but with optimized BLAS operations
        """
        start_time = time.perf_counter()
        
        valid_memories: list[tuple[int, MemoryLike, NDArray[np.float64]]] = []
        
        for idx, memory in enumerate(memories):
            if memory.status == "deprecated":
                continue
            
            embedding = self._get_embedding(memory)
            if embedding is None or len(embedding) == 0:
                continue
            
            vec = np.asarray(embedding, dtype=np.float64)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            valid_memories.append((idx, memory, vec))
        
        if len(valid_memories) < 2:
            return [
                self._build_result(
                    edges=[],
                    source_id=m.id,
                    method=ExtractionMethod.SEMANTIC_SIMILARITY,
                    duration_ms=0,
                )
                for m in memories
            ]
        
        embedding_matrix = np.vstack([v[2] for v in valid_memories])
        
        similarity_matrix = np.dot(embedding_matrix, embedding_matrix.T)
        
        np.fill_diagonal(similarity_matrix, 0.0)
        
        results: list[ExtractionResult] = []
        result_map: dict[str, ExtractionResult] = {}
        
        for i, (orig_idx, memory, _) in enumerate(valid_memories):
            similarities = similarity_matrix[i]
            
            candidates: list[tuple[str, float, str]] = []
            
            for j, (_, other, _) in enumerate(valid_memories):
                if i == j:
                    continue
                
                sim = float(similarities[j])
                
                if sim >= self._config.relates_threshold:
                    edge_type = "SUPPORTS" if sim >= self._config.supports_threshold else "RELATES_TO"
                    candidates.append((other.id, sim, edge_type))
            
            candidates.sort(key=lambda x: x[1], reverse=True)
            selected = candidates[:self._config.max_edges_per_memory]
            
            edges: list[Edge] = []
            for other_id, similarity, edge_type in selected:
                if edge_type == "SUPPORTS":
                    edge = Supports(
                        from_id=memory.id,
                        to_id=other_id,
                        strength=round(similarity, 4),
                    )
                else:
                    edge = RelatesTo(
                        from_id=memory.id,
                        to_id=other_id,
                        weight=round(similarity, 4),
                        context=f"Semantic similarity: {similarity:.3f}",
                    )
                edges.append(edge)
            
            result = self._build_result(
                edges=edges,
                source_id=memory.id,
                method=ExtractionMethod.SEMANTIC_SIMILARITY,
                duration_ms=0,
                candidates_considered=len(valid_memories) - 1,
                edges_filtered=max(0, len(candidates) - self._config.max_edges_per_memory),
            )
            result_map[memory.id] = result
        
        total_duration = (time.perf_counter() - start_time) * 1000
        per_memory_duration = total_duration / len(valid_memories) if valid_memories else 0
        
        for memory in memories:
            if memory.id in result_map:
                result = result_map[memory.id]
                result = ExtractionResult(
                    edges=result.edges,
                    source_memory_id=result.source_memory_id,
                    method=result.method,
                    duration_ms=per_memory_duration,
                    candidates_considered=result.candidates_considered,
                    edges_filtered=result.edges_filtered,
                    metadata=result.metadata,
                )
                results.append(result)
            else:
                results.append(
                    self._build_result(
                        edges=[],
                        source_id=memory.id,
                        method=ExtractionMethod.SEMANTIC_SIMILARITY,
                        duration_ms=per_memory_duration,
                        metadata={"reason": "no_valid_embedding_or_deprecated"},
                    )
                )
        
        return results
    
    def _get_embedding(self, memory: MemoryLike) -> list[float] | None:
        """
        Get the embedding vector for a memory.
        
        Args:
            memory: Memory object to get embedding from
            
        Returns:
            Embedding vector or None if not available
        """
        return getattr(memory, self._config.embedding_attribute, None)
    
    def _scopes_related(self, scope1: str, scope2: str) -> bool:
        """
        Check if two scopes are related for similarity boosting.
        
        Args:
            scope1: First scope
            scope2: Second scope
            
        Returns:
            True if scopes are considered related
        """
        related_pairs = {
            ("baseline", "global"),
            ("global", "project"),
            ("project", "ephemeral"),
            ("agent", "global"),
        }
        
        pair = tuple(sorted([scope1, scope2]))
        return pair in related_pairs or scope1 == scope2
    
    def find_similar_memories(
        self,
        memory: MemoryLike,
        all_memories: list[MemoryLike],
        top_k: int = 10,
        min_similarity: float = 0.0,
    ) -> list[tuple[str, float]]:
        """
        Find the most similar memories to a given memory.
        
        This is a utility method for retrieval that returns ranked
        results without creating edges.
        
        Args:
            memory: The query memory
            all_memories: All memories to search
            top_k: Maximum number of results
            min_similarity: Minimum similarity threshold
            
        Returns:
            List of (memory_id, similarity) tuples, sorted by similarity
        """
        memory_embedding = self._get_embedding(memory)
        if memory_embedding is None:
            return []
        
        memory_vec = np.asarray(memory_embedding, dtype=np.float64)
        norm = np.linalg.norm(memory_vec)
        if norm > 0:
            memory_vec = memory_vec / norm
        
        results: list[tuple[str, float]] = []
        
        for other in all_memories:
            if other.id == memory.id or other.status == "deprecated":
                continue
            
            other_embedding = self._get_embedding(other)
            if other_embedding is None:
                continue
            
            other_vec = np.asarray(other_embedding, dtype=np.float64)
            other_norm = np.linalg.norm(other_vec)
            if other_norm > 0:
                other_vec = other_vec / other_norm
            
            similarity = float(np.dot(memory_vec, other_vec))
            
            if similarity >= min_similarity:
                results.append((other.id, round(similarity, 4)))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
    
    def clear_cache(self) -> None:
        """Clear the embedding cache."""
        self._embedding_cache.clear()
