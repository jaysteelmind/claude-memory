"""
Hybrid retriever combining vector and graph search.

Implements a multi-stage retrieval pipeline that:
1. Performs vector similarity search for initial candidates
2. Expands candidates via graph relationship traversal
3. Calculates combined scores with configurable weights
4. Returns ranked results with relationship context

Algorithm Complexity:
- Vector search: O(n) or O(log n) with ANN index
- Graph expansion: O(k * d) where k is candidates, d is avg degree
- Score combination: O(m) where m is total candidates
- Total: O(n + k*d + m)

Mathematical Foundation:
- Combined score: alpha * vector_score + (1 - alpha) * graph_score
- Graph score: sum of connection weights with hop decay
- Hop decay: base_score * (decay_factor ^ hop_count)
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from dmm.graph.extractors.base import MemoryLike


logger = logging.getLogger(__name__)


@runtime_checkable
class VectorStore(Protocol):
    """Protocol for vector store operations."""
    
    async def search_by_content(
        self,
        query_embedding: list[float],
        directories: list[str],
        filters: Any,
        limit: int,
    ) -> list[tuple[Any, float]]:
        """Search memories by embedding similarity."""
        ...


@runtime_checkable
class GraphStore(Protocol):
    """Protocol for graph store operations."""
    
    def get_edges_from(
        self,
        node_id: str,
        edge_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get outgoing edges from a node."""
        ...
    
    def get_edges_to(
        self,
        node_id: str,
        edge_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get incoming edges to a node."""
        ...
    
    def get_memory_node(self, memory_id: str) -> Any | None:
        """Get a memory node by ID."""
        ...


@dataclass(frozen=True)
class HybridRetrievalConfig:
    """
    Configuration for hybrid retrieval.
    
    Attributes:
        vector_weight: Weight for vector similarity score (0.0-1.0)
        graph_weight: Weight for graph-based score (0.0-1.0)
        max_graph_depth: Maximum hops for graph expansion
        expansion_edge_types: Edge types to follow during expansion
        negative_edge_types: Edge types that reduce score
        direct_connection_boost: Score boost for direct connections
        hop_decay: Decay factor per hop (0.0-1.0)
        include_relationship_context: Include relationship info in results
        max_expansion_per_hop: Maximum nodes to expand per hop
        vector_candidate_multiplier: Multiplier for initial vector candidates
    """
    
    vector_weight: float = 0.6
    graph_weight: float = 0.4
    max_graph_depth: int = 2
    expansion_edge_types: tuple[str, ...] = (
        "SUPPORTS", "RELATES_TO", "DEPENDS_ON"
    )
    negative_edge_types: tuple[str, ...] = ("CONTRADICTS",)
    direct_connection_boost: float = 0.2
    hop_decay: float = 0.5
    include_relationship_context: bool = True
    max_expansion_per_hop: int = 20
    vector_candidate_multiplier: int = 3


@dataclass
class RetrievalResult:
    """
    Single retrieval result with scoring details.
    
    Attributes:
        memory: The retrieved memory object
        memory_id: Memory identifier
        vector_score: Score from vector similarity
        graph_score: Score from graph relationships
        combined_score: Final weighted score
        relationship_context: Descriptions of relationships
        path_from_query: Path of relationships from query results
        hop_distance: Minimum hops from vector results (0 = direct match)
    """
    
    memory: Any
    memory_id: str
    vector_score: float
    graph_score: float
    combined_score: float
    relationship_context: list[str] = field(default_factory=list)
    path_from_query: list[str] = field(default_factory=list)
    hop_distance: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "memory_id": self.memory_id,
            "vector_score": round(self.vector_score, 4),
            "graph_score": round(self.graph_score, 4),
            "combined_score": round(self.combined_score, 4),
            "hop_distance": self.hop_distance,
            "relationship_context": self.relationship_context,
        }


@dataclass
class RetrievalStats:
    """
    Statistics about a retrieval operation.
    
    Attributes:
        query_time_ms: Total retrieval time
        vector_search_time_ms: Time for vector search
        graph_expansion_time_ms: Time for graph expansion
        scoring_time_ms: Time for score calculation
        vector_candidates: Number of vector search results
        graph_expanded: Number of nodes added via expansion
        final_results: Number of results returned
        expansion_depth_reached: Maximum depth reached in expansion
    """
    
    query_time_ms: float = 0.0
    vector_search_time_ms: float = 0.0
    graph_expansion_time_ms: float = 0.0
    scoring_time_ms: float = 0.0
    vector_candidates: int = 0
    graph_expanded: int = 0
    final_results: int = 0
    expansion_depth_reached: int = 0


class HybridRetriever:
    """
    Combines vector search with graph traversal for retrieval.
    
    The hybrid retriever implements a multi-stage pipeline:
    
    1. Vector Search: Find semantically similar memories using embeddings
    2. Graph Expansion: Follow relationship edges to find connected memories
    3. Score Calculation: Combine vector and graph scores
    4. Result Assembly: Rank and return with relationship context
    
    Graph Expansion Algorithm (BFS):
    - Start with vector search results as frontier
    - For each depth level up to max_depth:
      - For each node in frontier:
        - Find outgoing edges of allowed types
        - Add target nodes to next frontier
        - Record path and hop distance
    - Calculate graph score based on connections and hop decay
    
    Score Calculation:
    - Vector score: Direct from embedding similarity
    - Graph score: Sum of connection contributions with decay
    - Combined: vector_weight * vector + graph_weight * graph
    
    Example:
        retriever = HybridRetriever(vector_store, graph_store, config)
        results = await retriever.retrieve(query_embedding, limit=10)
        for result in results:
            print(f"{result.memory_id}: {result.combined_score}")
    """
    
    def __init__(
        self,
        vector_store: VectorStore | None = None,
        graph_store: GraphStore | None = None,
        config: HybridRetrievalConfig | None = None,
    ) -> None:
        """
        Initialize the hybrid retriever.
        
        Args:
            vector_store: Store for vector similarity search
            graph_store: Store for graph traversal
            config: Retrieval configuration
        """
        self._vector_store = vector_store
        self._graph_store = graph_store
        self._config = config or HybridRetrievalConfig()
        
        self._total_retrievals = 0
        self._total_results_returned = 0
        self._total_time_ms = 0.0
    
    @property
    def config(self) -> HybridRetrievalConfig:
        """Return the current configuration."""
        return self._config
    
    def set_stores(
        self,
        vector_store: VectorStore | None = None,
        graph_store: GraphStore | None = None,
    ) -> None:
        """
        Set or update the stores.
        
        Args:
            vector_store: Vector store instance
            graph_store: Graph store instance
        """
        if vector_store is not None:
            self._vector_store = vector_store
        if graph_store is not None:
            self._graph_store = graph_store
    
    async def retrieve(
        self,
        query_embedding: list[float],
        limit: int = 10,
        scope_filter: str | None = None,
        exclude_deprecated: bool = True,
    ) -> tuple[list[RetrievalResult], RetrievalStats]:
        """
        Perform hybrid retrieval.
        
        Args:
            query_embedding: Query vector for similarity search
            limit: Maximum results to return
            scope_filter: Optional scope to filter by
            exclude_deprecated: Whether to exclude deprecated memories
            
        Returns:
            Tuple of (results list, retrieval statistics)
        """
        start_time = time.perf_counter()
        stats = RetrievalStats()
        
        vector_start = time.perf_counter()
        vector_results = await self._vector_search(
            query_embedding,
            limit * self._config.vector_candidate_multiplier,
            scope_filter,
            exclude_deprecated,
        )
        stats.vector_search_time_ms = (time.perf_counter() - vector_start) * 1000
        stats.vector_candidates = len(vector_results)
        
        if not vector_results:
            stats.query_time_ms = (time.perf_counter() - start_time) * 1000
            return [], stats
        
        graph_start = time.perf_counter()
        expanded, max_depth = self._graph_expand(vector_results)
        stats.graph_expansion_time_ms = (time.perf_counter() - graph_start) * 1000
        stats.graph_expanded = len(expanded) - len(vector_results)
        stats.expansion_depth_reached = max_depth
        
        scoring_start = time.perf_counter()
        graph_scores = self._calculate_graph_scores(vector_results, expanded)
        stats.scoring_time_ms = (time.perf_counter() - scoring_start) * 1000
        
        results = self._combine_and_rank(
            vector_results, expanded, graph_scores, limit
        )
        
        stats.final_results = len(results)
        stats.query_time_ms = (time.perf_counter() - start_time) * 1000
        
        self._total_retrievals += 1
        self._total_results_returned += len(results)
        self._total_time_ms += stats.query_time_ms
        
        return results, stats
    
    def retrieve_sync(
        self,
        query_embedding: list[float],
        limit: int = 10,
        scope_filter: str | None = None,
        exclude_deprecated: bool = True,
    ) -> tuple[list[RetrievalResult], RetrievalStats]:
        """
        Synchronous retrieval wrapper.
        
        Args:
            query_embedding: Query vector
            limit: Maximum results
            scope_filter: Optional scope filter
            exclude_deprecated: Exclude deprecated memories
            
        Returns:
            Tuple of (results, stats)
        """
        import asyncio
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.retrieve(
                            query_embedding, limit, scope_filter, exclude_deprecated
                        )
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.retrieve(
                        query_embedding, limit, scope_filter, exclude_deprecated
                    )
                )
        except RuntimeError:
            return asyncio.run(
                self.retrieve(
                    query_embedding, limit, scope_filter, exclude_deprecated
                )
            )
    
    async def _vector_search(
        self,
        query_embedding: list[float],
        limit: int,
        scope_filter: str | None,
        exclude_deprecated: bool,
    ) -> dict[str, tuple[Any, float]]:
        """
        Perform vector similarity search.
        
        Returns:
            Dict mapping memory_id to (memory, score)
        """
        if self._vector_store is None:
            logger.warning("No vector store configured")
            return {}
        
        try:
            filters = type("Filters", (), {
                "exclude_deprecated": exclude_deprecated,
                "scopes": [scope_filter] if scope_filter else None,
            })()
            
            results = await self._vector_store.search_by_content(
                query_embedding=query_embedding,
                directories=[],
                filters=filters,
                limit=limit,
            )
            
            return {
                self._get_memory_id(memory): (memory, score)
                for memory, score in results
            }
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return {}
    
    def _graph_expand(
        self,
        vector_results: dict[str, tuple[Any, float]],
    ) -> tuple[dict[str, list[tuple[str, str, int]]], int]:
        """
        Expand results via graph traversal (BFS).
        
        Args:
            vector_results: Initial vector search results
            
        Returns:
            Tuple of (expanded dict mapping id to connections, max depth reached)
        """
        if self._graph_store is None:
            return {mid: [("query", "DIRECT", 0)] for mid in vector_results}, 0
        
        expanded: dict[str, list[tuple[str, str, int]]] = {
            mid: [("query", "DIRECT", 0)] for mid in vector_results
        }
        
        frontier = list(vector_results.keys())
        visited = set(frontier)
        max_depth_reached = 0
        
        for depth in range(1, self._config.max_graph_depth + 1):
            next_frontier: list[str] = []
            
            for memory_id in frontier:
                try:
                    edges = self._graph_store.get_edges_from(memory_id)
                except Exception as e:
                    logger.debug(f"Failed to get edges for {memory_id}: {e}")
                    continue
                
                expansion_count = 0
                
                for edge in edges:
                    edge_type = edge.get("type", edge.get("edge_type", ""))
                    
                    if edge_type not in self._config.expansion_edge_types:
                        continue
                    
                    target_id = edge.get("to_id", edge.get("target_id", ""))
                    
                    if not target_id or target_id in visited:
                        continue
                    
                    visited.add(target_id)
                    next_frontier.append(target_id)
                    
                    if target_id not in expanded:
                        expanded[target_id] = []
                    expanded[target_id].append((memory_id, edge_type, depth))
                    
                    expansion_count += 1
                    if expansion_count >= self._config.max_expansion_per_hop:
                        break
            
            if next_frontier:
                max_depth_reached = depth
            
            frontier = next_frontier
            
            if not frontier:
                break
        
        return expanded, max_depth_reached
    
    def _calculate_graph_scores(
        self,
        vector_results: dict[str, tuple[Any, float]],
        expanded: dict[str, list[tuple[str, str, int]]],
    ) -> dict[str, float]:
        """
        Calculate graph-based scores for all candidates.
        
        Args:
            vector_results: Original vector search results
            expanded: Expanded nodes with connections
            
        Returns:
            Dict mapping memory_id to graph score
        """
        scores: dict[str, float] = {}
        
        for memory_id, connections in expanded.items():
            score = 0.0
            
            for source_id, edge_type, hops in connections:
                if source_id == "query":
                    continue
                
                conn_score = self._config.direct_connection_boost
                conn_score *= (self._config.hop_decay ** hops)
                
                if source_id in vector_results:
                    source_vector_score = vector_results[source_id][1]
                    conn_score *= (1.0 + source_vector_score)
                
                score += conn_score
            
            if self._graph_store is not None:
                try:
                    contradictions = self._graph_store.get_edges_to(
                        memory_id, "CONTRADICTS"
                    )
                    if contradictions:
                        score *= 0.5
                except Exception:
                    pass
            
            scores[memory_id] = min(score, 1.0)
        
        return scores
    
    def _combine_and_rank(
        self,
        vector_results: dict[str, tuple[Any, float]],
        expanded: dict[str, list[tuple[str, str, int]]],
        graph_scores: dict[str, float],
        limit: int,
    ) -> list[RetrievalResult]:
        """
        Combine scores and create ranked results.
        
        Args:
            vector_results: Vector search results
            expanded: Expanded connections
            graph_scores: Graph-based scores
            limit: Maximum results
            
        Returns:
            Ranked list of RetrievalResult
        """
        results: list[RetrievalResult] = []
        
        all_memory_ids = set(vector_results.keys()) | set(expanded.keys())
        
        for memory_id in all_memory_ids:
            if memory_id in vector_results:
                memory, vector_score = vector_results[memory_id]
            else:
                vector_score = 0.0
                memory = self._get_memory_from_graph(memory_id)
                if memory is None:
                    continue
            
            graph_score = graph_scores.get(memory_id, 0.0)
            
            combined_score = (
                self._config.vector_weight * vector_score +
                self._config.graph_weight * graph_score
            )
            
            connections = expanded.get(memory_id, [])
            hop_distance = min(
                (c[2] for c in connections),
                default=self._config.max_graph_depth + 1
            )
            
            relationship_context: list[str] = []
            path_from_query: list[str] = []
            
            if self._config.include_relationship_context:
                for source_id, edge_type, hops in connections:
                    if source_id != "query":
                        relationship_context.append(
                            f"{edge_type} from {source_id} ({hops} hop{'s' if hops != 1 else ''})"
                        )
                        if not path_from_query:
                            path_from_query = [source_id, edge_type, memory_id]
            
            results.append(RetrievalResult(
                memory=memory,
                memory_id=memory_id,
                vector_score=vector_score,
                graph_score=graph_score,
                combined_score=combined_score,
                relationship_context=relationship_context[:5],
                path_from_query=path_from_query,
                hop_distance=hop_distance,
            ))
        
        results.sort(key=lambda r: r.combined_score, reverse=True)
        
        return results[:limit]
    
    def _get_memory_id(self, memory: Any) -> str:
        """Extract memory ID from memory object."""
        if hasattr(memory, "id"):
            return memory.id
        if isinstance(memory, dict):
            return memory.get("id", "")
        return str(memory)
    
    def _get_memory_from_graph(self, memory_id: str) -> Any | None:
        """Retrieve memory from graph store."""
        if self._graph_store is None:
            return None
        try:
            return self._graph_store.get_memory_node(memory_id)
        except Exception:
            return None
    
    def get_stats(self) -> dict[str, Any]:
        """
        Get retriever statistics.
        
        Returns:
            Dictionary with retrieval statistics
        """
        return {
            "total_retrievals": self._total_retrievals,
            "total_results_returned": self._total_results_returned,
            "total_time_ms": self._total_time_ms,
            "avg_results_per_query": (
                self._total_results_returned / self._total_retrievals
                if self._total_retrievals > 0
                else 0.0
            ),
            "avg_time_ms": (
                self._total_time_ms / self._total_retrievals
                if self._total_retrievals > 0
                else 0.0
            ),
        }
    
    def reset_stats(self) -> None:
        """Reset retrieval statistics."""
        self._total_retrievals = 0
        self._total_results_returned = 0
        self._total_time_ms = 0.0
