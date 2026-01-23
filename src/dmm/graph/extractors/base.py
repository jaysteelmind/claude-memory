"""
Base classes for relationship extractors.

Provides the abstract interface and common data structures used by all
extraction strategies. Each extractor analyzes memories and yields
candidate edges for the knowledge graph.

Complexity Analysis:
- Base extraction interface: O(1) per method call
- Result aggregation: O(n) where n is number of extracted edges
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Iterator, Protocol, runtime_checkable

from dmm.graph.edges import Edge


class ExtractionMethod(str, Enum):
    """Enumeration of extraction methods for traceability."""
    
    TAG_OVERLAP = "tag_overlap"
    SEMANTIC_SIMILARITY = "semantic_similarity"
    TEMPORAL_PATTERN = "temporal_pattern"
    LLM_ANALYSIS = "llm_analysis"
    MANUAL = "manual"


@dataclass(frozen=True)
class ExtractionConfig:
    """
    Master configuration for relationship extraction.
    
    Controls which extractors are enabled and sets global parameters
    that apply across all extraction strategies.
    
    Attributes:
        enable_tag_extraction: Enable tag overlap analysis
        enable_semantic_extraction: Enable embedding similarity analysis
        enable_temporal_extraction: Enable temporal pattern detection
        enable_llm_extraction: Enable LLM-assisted analysis (expensive)
        merge_duplicates: Merge edges with same (from, to, type)
        min_edge_weight: Minimum weight threshold for edge retention
        max_edges_per_memory: Maximum edges to create per source memory
    """
    
    enable_tag_extraction: bool = True
    enable_semantic_extraction: bool = True
    enable_temporal_extraction: bool = True
    enable_llm_extraction: bool = False
    
    merge_duplicates: bool = True
    min_edge_weight: float = 0.3
    max_edges_per_memory: int = 30


@dataclass
class ExtractionResult:
    """
    Result of an extraction operation.
    
    Contains the extracted edges along with metadata about the
    extraction process for debugging and analysis.
    
    Attributes:
        edges: List of extracted edge candidates
        source_memory_id: ID of the memory that was analyzed
        method: Extraction method that produced these results
        duration_ms: Time taken for extraction in milliseconds
        candidates_considered: Number of potential relationships evaluated
        edges_filtered: Number of edges removed by filtering
        metadata: Additional method-specific metadata
    """
    
    edges: list[Edge] = field(default_factory=list)
    source_memory_id: str = ""
    method: ExtractionMethod = ExtractionMethod.MANUAL
    duration_ms: float = 0.0
    candidates_considered: int = 0
    edges_filtered: int = 0
    metadata: dict = field(default_factory=dict)
    
    @property
    def edge_count(self) -> int:
        """Return number of extracted edges."""
        return len(self.edges)
    
    def merge_with(self, other: "ExtractionResult") -> "ExtractionResult":
        """
        Merge this result with another result.
        
        Combines edges and aggregates statistics. Used by orchestrator
        to combine results from multiple extractors.
        
        Args:
            other: Another extraction result to merge
            
        Returns:
            New ExtractionResult with combined data
        """
        combined_edges = self.edges + other.edges
        combined_metadata = {**self.metadata, **other.metadata}
        
        return ExtractionResult(
            edges=combined_edges,
            source_memory_id=self.source_memory_id or other.source_memory_id,
            method=ExtractionMethod.MANUAL,
            duration_ms=self.duration_ms + other.duration_ms,
            candidates_considered=self.candidates_considered + other.candidates_considered,
            edges_filtered=self.edges_filtered + other.edges_filtered,
            metadata=combined_metadata,
        )


@runtime_checkable
class MemoryLike(Protocol):
    """
    Protocol defining the minimum interface for memory objects.
    
    Extractors work with any object that provides these attributes,
    allowing flexibility in the memory representation used.
    """
    
    @property
    def id(self) -> str:
        """Unique memory identifier."""
        ...
    
    @property
    def path(self) -> str:
        """File path relative to memory root."""
        ...
    
    @property
    def title(self) -> str:
        """Memory title (H1 heading)."""
        ...
    
    @property
    def tags(self) -> list[str]:
        """Semantic tags for categorization."""
        ...
    
    @property
    def scope(self) -> str:
        """Memory scope (baseline, global, project, etc.)."""
        ...
    
    @property
    def priority(self) -> float:
        """Priority value between 0.0 and 1.0."""
        ...
    
    @property
    def confidence(self) -> str:
        """Confidence level (experimental, active, stable)."""
        ...
    
    @property
    def status(self) -> str:
        """Status (active, deprecated)."""
        ...


class BaseExtractor(ABC):
    """
    Abstract base class for relationship extractors.
    
    All extraction strategies must inherit from this class and implement
    the extract() method. The base class provides common functionality
    for configuration, timing, and result building.
    
    Subclasses should:
    1. Define their own configuration dataclass
    2. Implement extract() to yield Edge instances
    3. Use _build_result() to construct ExtractionResult
    
    Example:
        class MyExtractor(BaseExtractor):
            def __init__(self, config: MyConfig):
                super().__init__()
                self._config = config
            
            def extract(self, memory, all_memories):
                start = time.perf_counter()
                edges = []
                # ... extraction logic ...
                return self._build_result(
                    edges=edges,
                    source_id=memory.id,
                    method=ExtractionMethod.MANUAL,
                    duration_ms=(time.perf_counter() - start) * 1000,
                )
    """
    
    def __init__(self) -> None:
        """Initialize the base extractor."""
        self._extraction_count: int = 0
        self._total_edges_extracted: int = 0
        self._total_duration_ms: float = 0.0
    
    @abstractmethod
    def extract(
        self,
        memory: MemoryLike,
        all_memories: list[MemoryLike],
    ) -> ExtractionResult:
        """
        Extract relationships for a single memory.
        
        Analyzes the given memory against all other memories to discover
        potential relationships. Returns an ExtractionResult containing
        candidate edges.
        
        Args:
            memory: The memory to analyze
            all_memories: All memories in the system for comparison
            
        Returns:
            ExtractionResult with discovered edges and metadata
            
        Note:
            Implementations should handle the case where memory.id
            appears in all_memories (skip self-comparison).
        """
        ...
    
    def extract_batch(
        self,
        memories: list[MemoryLike],
    ) -> list[ExtractionResult]:
        """
        Extract relationships for multiple memories.
        
        Convenience method that calls extract() for each memory.
        Override in subclasses for optimized batch processing.
        
        Args:
            memories: List of memories to analyze
            
        Returns:
            List of ExtractionResults, one per memory
            
        Complexity: O(n * m) where n is len(memories) and m is
                   the complexity of extract() for each memory
        """
        results = []
        for memory in memories:
            result = self.extract(memory, memories)
            results.append(result)
            self._update_stats(result)
        return results
    
    def _build_result(
        self,
        edges: list[Edge],
        source_id: str,
        method: ExtractionMethod,
        duration_ms: float,
        candidates_considered: int = 0,
        edges_filtered: int = 0,
        metadata: dict | None = None,
    ) -> ExtractionResult:
        """
        Build an ExtractionResult with the given data.
        
        Helper method for subclasses to construct results consistently.
        
        Args:
            edges: Extracted edges
            source_id: Source memory ID
            method: Extraction method used
            duration_ms: Extraction duration
            candidates_considered: Number of candidates evaluated
            edges_filtered: Number of edges removed by filtering
            metadata: Additional metadata
            
        Returns:
            Populated ExtractionResult
        """
        result = ExtractionResult(
            edges=edges,
            source_memory_id=source_id,
            method=method,
            duration_ms=duration_ms,
            candidates_considered=candidates_considered,
            edges_filtered=edges_filtered,
            metadata=metadata or {},
        )
        self._update_stats(result)
        return result
    
    def _update_stats(self, result: ExtractionResult) -> None:
        """Update internal statistics from an extraction result."""
        self._extraction_count += 1
        self._total_edges_extracted += result.edge_count
        self._total_duration_ms += result.duration_ms
    
    def get_stats(self) -> dict:
        """
        Get extraction statistics.
        
        Returns:
            Dictionary with extraction statistics
        """
        return {
            "extraction_count": self._extraction_count,
            "total_edges_extracted": self._total_edges_extracted,
            "total_duration_ms": self._total_duration_ms,
            "avg_edges_per_extraction": (
                self._total_edges_extracted / self._extraction_count
                if self._extraction_count > 0
                else 0.0
            ),
            "avg_duration_ms": (
                self._total_duration_ms / self._extraction_count
                if self._extraction_count > 0
                else 0.0
            ),
        }
    
    def reset_stats(self) -> None:
        """Reset extraction statistics."""
        self._extraction_count = 0
        self._total_edges_extracted = 0
        self._total_duration_ms = 0.0
