"""
Transitive inference engine.

Discovers implicit relationships through transitive reasoning:
- If A DEPENDS_ON B and B DEPENDS_ON C, then A DEPENDS_ON C
- If A SUPPORTS B and B SUPPORTS C, then A weakly SUPPORTS C

Non-transitive relationships:
- CONTRADICTS: Not transitive (A contradicts B, B contradicts C does not imply A contradicts C)
- SUPERSEDES: Not transitive (linear versioning)

Algorithm Complexity:
- Path finding: O(V + E) using BFS
- All transitive pairs: O(V * (V + E)) worst case
- With optimization: O(E * average_path_length)

Mathematical Foundation:
- Transitive closure: R+ = R union R^2 union R^3 union ...
- Confidence decay: conf(A->C) = conf(A->B) * conf(B->C) * decay_factor
- Path length penalty: Longer paths have lower confidence
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterator

from dmm.graph.edges import Edge, DependsOn, Supports, RelatesTo


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TransitiveConfig:
    """
    Configuration for transitive inference.
    
    Attributes:
        transitive_edge_types: Edge types to compute transitive closure for
        max_path_length: Maximum path length to consider
        confidence_decay: Confidence multiplier per hop
        min_confidence: Minimum confidence to create inferred edge
        exclude_existing: Don't create edges that already exist
        mark_as_inferred: Add metadata marking edges as inferred
        max_inferred_per_source: Maximum inferred edges per source node
    """
    
    transitive_edge_types: tuple[str, ...] = ("DEPENDS_ON", "SUPPORTS")
    max_path_length: int = 3
    confidence_decay: float = 0.8
    min_confidence: float = 0.3
    exclude_existing: bool = True
    mark_as_inferred: bool = True
    max_inferred_per_source: int = 20


@dataclass
class InferredEdge:
    """
    An inferred edge with provenance information.
    
    Attributes:
        edge: The inferred edge object
        edge_type: Type of the edge
        from_id: Source node ID
        to_id: Target node ID
        confidence: Confidence score (product of path confidences * decay)
        path: List of node IDs in the inference path
        path_length: Number of hops
        source_edges: Original edges used for inference
    """
    
    edge: Edge
    edge_type: str
    from_id: str
    to_id: str
    confidence: float
    path: list[str] = field(default_factory=list)
    path_length: int = 0
    source_edges: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "edge_type": self.edge_type,
            "from_id": self.from_id,
            "to_id": self.to_id,
            "confidence": round(self.confidence, 4),
            "path": self.path,
            "path_length": self.path_length,
            "inferred": True,
        }


@dataclass
class TransitiveResult:
    """
    Result of transitive inference.
    
    Attributes:
        inferred_edges: List of discovered inferred edges
        duration_ms: Time taken for inference
        nodes_processed: Number of nodes processed
        paths_evaluated: Number of paths evaluated
        edges_by_type: Count of inferred edges by type
        skipped_existing: Edges skipped because they already exist
        skipped_low_confidence: Edges skipped due to low confidence
    """
    
    inferred_edges: list[InferredEdge] = field(default_factory=list)
    duration_ms: float = 0.0
    nodes_processed: int = 0
    paths_evaluated: int = 0
    edges_by_type: dict[str, int] = field(default_factory=dict)
    skipped_existing: int = 0
    skipped_low_confidence: int = 0
    
    @property
    def total_inferred(self) -> int:
        """Total number of inferred edges."""
        return len(self.inferred_edges)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_inferred": self.total_inferred,
            "duration_ms": round(self.duration_ms, 2),
            "nodes_processed": self.nodes_processed,
            "paths_evaluated": self.paths_evaluated,
            "edges_by_type": self.edges_by_type,
            "skipped_existing": self.skipped_existing,
            "skipped_low_confidence": self.skipped_low_confidence,
        }


class TransitiveInferenceEngine:
    """
    Discovers transitive relationships in the knowledge graph.
    
    The engine computes transitive closures for specified edge types,
    discovering implicit relationships that span multiple hops.
    
    Transitive Rules:
    - DEPENDS_ON: A depends on B, B depends on C => A depends on C
      (Prerequisite knowledge chains)
    - SUPPORTS: A supports B, B supports C => A weakly supports C
      (Evidence chains with confidence decay)
    
    Non-Transitive (by design):
    - CONTRADICTS: Contradiction is not transitive
    - SUPERSEDES: Version chains are linear, not transitive
    - RELATES_TO: General relation doesn't imply transitivity
    
    Algorithm:
    1. For each node, perform BFS following transitive edge types
    2. Track paths and accumulate confidence with decay
    3. Create inferred edges for paths that meet confidence threshold
    4. Optionally filter out edges that already exist
    
    Example:
        engine = TransitiveInferenceEngine(graph_store, config)
        result = engine.infer_all()
        for inferred in result.inferred_edges:
            if inferred.confidence > 0.5:
                graph_store.create_edge(inferred.edge)
    """
    
    def __init__(
        self,
        graph_store: Any,
        config: TransitiveConfig | None = None,
    ) -> None:
        """
        Initialize the transitive inference engine.
        
        Args:
            graph_store: Knowledge graph store instance
            config: Inference configuration
        """
        self._graph = graph_store
        self._config = config or TransitiveConfig()
    
    @property
    def config(self) -> TransitiveConfig:
        """Return the current configuration."""
        return self._config
    
    def infer_all(self) -> TransitiveResult:
        """
        Compute transitive closure for all nodes.
        
        Returns:
            TransitiveResult with all inferred edges
        """
        start_time = time.perf_counter()
        result = TransitiveResult()
        
        try:
            memory_nodes = self._graph.get_all_memory_nodes()
        except Exception as e:
            logger.error(f"Failed to get memory nodes: {e}")
            result.duration_ms = (time.perf_counter() - start_time) * 1000
            return result
        
        existing_edges: set[tuple[str, str, str]] = set()
        if self._config.exclude_existing:
            existing_edges = self._get_existing_edges()
        
        all_inferred: list[InferredEdge] = []
        
        for node in memory_nodes:
            node_id = node.id if hasattr(node, "id") else str(node)
            result.nodes_processed += 1
            
            for edge_type in self._config.transitive_edge_types:
                inferred = self._find_transitive_paths(
                    node_id, edge_type, existing_edges, result
                )
                all_inferred.extend(inferred)
        
        for inferred in all_inferred:
            edge_type = inferred.edge_type
            result.edges_by_type[edge_type] = result.edges_by_type.get(edge_type, 0) + 1
        
        result.inferred_edges = all_inferred
        result.duration_ms = (time.perf_counter() - start_time) * 1000
        
        return result
    
    def infer_for_node(self, node_id: str) -> TransitiveResult:
        """
        Compute transitive edges for a specific node.
        
        Args:
            node_id: Node to compute transitive closure for
            
        Returns:
            TransitiveResult with inferred edges from this node
        """
        start_time = time.perf_counter()
        result = TransitiveResult()
        result.nodes_processed = 1
        
        existing_edges: set[tuple[str, str, str]] = set()
        if self._config.exclude_existing:
            existing_edges = self._get_existing_edges()
        
        all_inferred: list[InferredEdge] = []
        
        for edge_type in self._config.transitive_edge_types:
            inferred = self._find_transitive_paths(
                node_id, edge_type, existing_edges, result
            )
            all_inferred.extend(inferred)
        
        for inferred in all_inferred:
            edge_type = inferred.edge_type
            result.edges_by_type[edge_type] = result.edges_by_type.get(edge_type, 0) + 1
        
        result.inferred_edges = all_inferred
        result.duration_ms = (time.perf_counter() - start_time) * 1000
        
        return result
    
    def _find_transitive_paths(
        self,
        start_id: str,
        edge_type: str,
        existing_edges: set[tuple[str, str, str]],
        result: TransitiveResult,
    ) -> list[InferredEdge]:
        """
        Find all transitive paths from a node for a specific edge type.
        
        Uses BFS to explore paths up to max_path_length.
        
        Args:
            start_id: Starting node ID
            edge_type: Edge type to follow
            existing_edges: Set of existing edges to exclude
            result: Result object to update statistics
            
        Returns:
            List of inferred edges
        """
        inferred: list[InferredEdge] = []
        
        queue: deque[tuple[str, list[str], float]] = deque()
        queue.append((start_id, [start_id], 1.0))
        
        visited_at_depth: dict[str, int] = {start_id: 0}
        
        while queue:
            current_id, path, confidence = queue.popleft()
            current_depth = len(path) - 1
            
            if current_depth >= self._config.max_path_length:
                continue
            
            try:
                edges = self._graph.get_edges_from(current_id, edge_type)
            except Exception as e:
                logger.debug(f"Failed to get edges from {current_id}: {e}")
                continue
            
            for edge in edges:
                target_id = edge.get("to_id", edge.get("target_id", ""))
                if not target_id:
                    continue
                
                result.paths_evaluated += 1
                
                if target_id in path:
                    continue
                
                edge_confidence = self._get_edge_confidence(edge, edge_type)
                new_confidence = confidence * edge_confidence * self._config.confidence_decay
                
                new_path = path + [target_id]
                new_depth = len(new_path) - 1
                
                if target_id in visited_at_depth and visited_at_depth[target_id] <= new_depth:
                    continue
                visited_at_depth[target_id] = new_depth
                
                if new_depth >= 2:
                    if new_confidence < self._config.min_confidence:
                        result.skipped_low_confidence += 1
                    elif (start_id, target_id, edge_type) in existing_edges:
                        result.skipped_existing += 1
                    else:
                        inferred_edge = self._create_inferred_edge(
                            edge_type, start_id, target_id, new_confidence, new_path
                        )
                        if inferred_edge is not None:
                            inferred.append(inferred_edge)
                
                if new_depth < self._config.max_path_length:
                    queue.append((target_id, new_path, new_confidence))
        
        inferred.sort(key=lambda e: e.confidence, reverse=True)
        return inferred[:self._config.max_inferred_per_source]
    
    def _get_existing_edges(self) -> set[tuple[str, str, str]]:
        """Get all existing edges as (from, to, type) tuples."""
        existing: set[tuple[str, str, str]] = set()
        
        try:
            memory_nodes = self._graph.get_all_memory_nodes()
            
            for node in memory_nodes:
                node_id = node.id if hasattr(node, "id") else str(node)
                
                for edge_type in self._config.transitive_edge_types:
                    try:
                        edges = self._graph.get_edges_from(node_id, edge_type)
                        for edge in edges:
                            target_id = edge.get("to_id", edge.get("target_id", ""))
                            if target_id:
                                existing.add((node_id, target_id, edge_type))
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Failed to get existing edges: {e}")
        
        return existing
    
    def _get_edge_confidence(self, edge: dict[str, Any], edge_type: str) -> float:
        """
        Get confidence/strength from an edge.
        
        Args:
            edge: Edge dictionary
            edge_type: Type of edge
            
        Returns:
            Confidence value (0.0-1.0)
        """
        if "strength" in edge:
            return float(edge["strength"])
        if "weight" in edge:
            return float(edge["weight"])
        if "confidence" in edge:
            return float(edge["confidence"])
        
        return 1.0
    
    def _create_inferred_edge(
        self,
        edge_type: str,
        from_id: str,
        to_id: str,
        confidence: float,
        path: list[str],
    ) -> InferredEdge | None:
        """
        Create an inferred edge with the appropriate type.
        
        Args:
            edge_type: Type of edge to create
            from_id: Source node ID
            to_id: Target node ID
            confidence: Inferred confidence
            path: Path used for inference
            
        Returns:
            InferredEdge or None if type not supported
        """
        edge: Edge | None = None
        
        if edge_type == "DEPENDS_ON":
            edge = DependsOn(from_id=from_id, to_id=to_id)
        elif edge_type == "SUPPORTS":
            edge = Supports(from_id=from_id, to_id=to_id, strength=round(confidence, 4))
        elif edge_type == "RELATES_TO":
            edge = RelatesTo(
                from_id=from_id,
                to_id=to_id,
                weight=round(confidence, 4),
                context=f"Inferred via {len(path)-1} hop path",
            )
        
        if edge is None:
            return None
        
        return InferredEdge(
            edge=edge,
            edge_type=edge_type,
            from_id=from_id,
            to_id=to_id,
            confidence=confidence,
            path=path,
            path_length=len(path) - 1,
            source_edges=[f"{path[i]}->{path[i+1]}" for i in range(len(path)-1)],
        )
    
    def apply_inferred_edges(
        self,
        inferred_edges: list[InferredEdge],
        min_confidence: float | None = None,
    ) -> tuple[int, int]:
        """
        Apply inferred edges to the graph.
        
        Args:
            inferred_edges: Edges to apply
            min_confidence: Override minimum confidence
            
        Returns:
            Tuple of (applied count, skipped count)
        """
        min_conf = min_confidence or self._config.min_confidence
        applied = 0
        skipped = 0
        
        for inferred in inferred_edges:
            if inferred.confidence < min_conf:
                skipped += 1
                continue
            
            try:
                properties = inferred.edge.to_cypher_params()
                if self._config.mark_as_inferred:
                    properties["inferred"] = True
                    properties["inference_path"] = "->".join(inferred.path)
                    properties["inference_confidence"] = round(inferred.confidence, 4)
                
                success = self._graph.create_edge(
                    inferred.edge_type,
                    inferred.from_id,
                    inferred.to_id,
                    properties,
                )
                
                if success:
                    applied += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error(f"Failed to apply inferred edge: {e}")
                skipped += 1
        
        return applied, skipped
    
    def get_inference_candidates(
        self,
        min_confidence: float = 0.5,
        limit: int = 50,
    ) -> list[InferredEdge]:
        """
        Get top inference candidates for review.
        
        Args:
            min_confidence: Minimum confidence threshold
            limit: Maximum candidates to return
            
        Returns:
            List of high-confidence inference candidates
        """
        result = self.infer_all()
        
        candidates = [
            e for e in result.inferred_edges
            if e.confidence >= min_confidence
        ]
        
        candidates.sort(key=lambda e: e.confidence, reverse=True)
        
        return candidates[:limit]
