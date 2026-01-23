"""
Extraction orchestrator.

Coordinates multiple extraction strategies and merges their results
into a unified set of edges. Handles deduplication, filtering, and
prioritization of extracted relationships.

Algorithm Complexity:
- Orchestration: O(e * n) where e is number of extractors, n is memories
- Edge merging: O(m * log(m)) where m is total candidate edges
- Deduplication: O(m) using hash-based grouping

Design Principles:
- Run extractors in order of cost (cheap first, LLM last)
- Merge duplicate edges keeping highest weight
- Filter by minimum weight threshold
- Limit total edges per memory
- Provide detailed statistics for debugging
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from dmm.graph.edges import Edge, RelatesTo, Supports
from dmm.graph.extractors.base import (
    BaseExtractor,
    ExtractionConfig,
    ExtractionMethod,
    ExtractionResult,
    MemoryLike,
)
from dmm.graph.extractors.tag_extractor import TagExtractor, TagExtractionConfig
from dmm.graph.extractors.semantic_extractor import SemanticExtractor, SemanticExtractionConfig
from dmm.graph.extractors.temporal_extractor import TemporalExtractor, TemporalExtractionConfig
from dmm.graph.extractors.llm_extractor import LLMExtractor, LLMExtractionConfig


logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    """
    Configuration for the extraction orchestrator.
    
    Attributes:
        enable_tag_extraction: Enable tag-based extraction
        enable_semantic_extraction: Enable semantic similarity extraction
        enable_temporal_extraction: Enable temporal pattern extraction
        enable_llm_extraction: Enable LLM-assisted extraction
        tag_config: Configuration for tag extractor
        semantic_config: Configuration for semantic extractor
        temporal_config: Configuration for temporal extractor
        llm_config: Configuration for LLM extractor
        merge_duplicates: Merge edges with same (from, to, type)
        min_edge_weight: Minimum weight to retain an edge
        max_edges_per_memory: Maximum edges per source memory
        parallel_extraction: Run extractors in parallel where possible
    """
    
    enable_tag_extraction: bool = True
    enable_semantic_extraction: bool = True
    enable_temporal_extraction: bool = True
    enable_llm_extraction: bool = False
    
    tag_config: TagExtractionConfig | None = None
    semantic_config: SemanticExtractionConfig | None = None
    temporal_config: TemporalExtractionConfig | None = None
    llm_config: LLMExtractionConfig | None = None
    
    merge_duplicates: bool = True
    min_edge_weight: float = 0.3
    max_edges_per_memory: int = 30
    parallel_extraction: bool = True


@dataclass
class OrchestrationResult:
    """
    Result of orchestrated extraction.
    
    Attributes:
        edges: Final merged and filtered edges
        source_memory_id: Source memory ID
        duration_ms: Total extraction time
        extractor_results: Results from each extractor
        merge_stats: Statistics about edge merging
        total_candidates: Total edges before merging
        total_merged: Edges after merging duplicates
        total_filtered: Edges after weight filtering
        final_count: Final edge count after all processing
    """
    
    edges: list[Edge] = field(default_factory=list)
    source_memory_id: str = ""
    duration_ms: float = 0.0
    extractor_results: dict[str, ExtractionResult] = field(default_factory=dict)
    merge_stats: dict[str, int] = field(default_factory=dict)
    total_candidates: int = 0
    total_merged: int = 0
    total_filtered: int = 0
    final_count: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source_memory_id": self.source_memory_id,
            "duration_ms": self.duration_ms,
            "total_candidates": self.total_candidates,
            "total_merged": self.total_merged,
            "total_filtered": self.total_filtered,
            "final_count": self.final_count,
            "edges_by_type": self._count_by_type(),
            "extractor_stats": {
                name: {
                    "edge_count": result.edge_count,
                    "duration_ms": result.duration_ms,
                    "method": result.method.value,
                }
                for name, result in self.extractor_results.items()
            },
        }
    
    def _count_by_type(self) -> dict[str, int]:
        """Count edges by type."""
        counts: dict[str, int] = {}
        for edge in self.edges:
            edge_type = edge.edge_type
            counts[edge_type] = counts.get(edge_type, 0) + 1
        return counts


class ExtractionOrchestrator:
    """
    Coordinates multiple extraction strategies.
    
    The orchestrator manages the execution of multiple extractors,
    combining their results into a unified edge set. It handles:
    
    1. Extractor initialization based on configuration
    2. Sequential or parallel execution
    3. Result merging and deduplication
    4. Weight-based filtering
    5. Edge count limiting
    
    Extraction Order:
    1. Tag extraction (fast, O(n*t))
    2. Temporal extraction (fast, O(n))
    3. Semantic extraction (medium, O(n*d))
    4. LLM extraction (slow, API calls)
    
    Merging Strategy:
    - Group edges by (from_id, to_id, edge_type)
    - Keep edge with highest weight/strength
    - Combine context strings where applicable
    
    Example:
        orchestrator = ExtractionOrchestrator(config)
        result = orchestrator.extract(memory, all_memories)
        for edge in result.edges:
            graph_store.create_edge(edge)
    """
    
    def __init__(self, config: OrchestratorConfig | None = None) -> None:
        """
        Initialize the orchestrator.
        
        Args:
            config: Orchestrator configuration
        """
        self._config = config or OrchestratorConfig()
        self._extractors: dict[str, BaseExtractor] = {}
        self._initialize_extractors()
        
        self._total_extractions = 0
        self._total_edges_created = 0
        self._total_duration_ms = 0.0
    
    @property
    def config(self) -> OrchestratorConfig:
        """Return the current configuration."""
        return self._config
    
    def _initialize_extractors(self) -> None:
        """Initialize enabled extractors."""
        if self._config.enable_tag_extraction:
            self._extractors["tag"] = TagExtractor(
                self._config.tag_config or TagExtractionConfig()
            )
        
        if self._config.enable_temporal_extraction:
            self._extractors["temporal"] = TemporalExtractor(
                self._config.temporal_config or TemporalExtractionConfig()
            )
        
        if self._config.enable_semantic_extraction:
            self._extractors["semantic"] = SemanticExtractor(
                self._config.semantic_config or SemanticExtractionConfig()
            )
        
        if self._config.enable_llm_extraction:
            self._extractors["llm"] = LLMExtractor(
                self._config.llm_config or LLMExtractionConfig()
            )
    
    def extract(
        self,
        memory: MemoryLike,
        all_memories: list[MemoryLike],
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> OrchestrationResult:
        """
        Extract relationships for a single memory.
        
        Runs all enabled extractors and merges their results.
        
        Args:
            memory: The memory to analyze
            all_memories: All memories for comparison
            progress_callback: Optional callback(extractor_name, current, total)
            
        Returns:
            OrchestrationResult with merged edges
        """
        start_time = time.perf_counter()
        extractor_results: dict[str, ExtractionResult] = {}
        all_candidates: list[Edge] = []
        
        extractor_names = list(self._extractors.keys())
        total_extractors = len(extractor_names)
        
        for i, name in enumerate(extractor_names):
            if progress_callback:
                progress_callback(name, i + 1, total_extractors)
            
            extractor = self._extractors[name]
            
            try:
                result = extractor.extract(memory, all_memories)
                extractor_results[name] = result
                all_candidates.extend(result.edges)
                
                logger.debug(
                    f"Extractor '{name}' found {result.edge_count} edges "
                    f"in {result.duration_ms:.1f}ms"
                )
            except Exception as e:
                logger.error(f"Extractor '{name}' failed: {e}")
                extractor_results[name] = ExtractionResult(
                    edges=[],
                    source_memory_id=memory.id,
                    method=ExtractionMethod.MANUAL,
                    metadata={"error": str(e)},
                )
        
        total_candidates = len(all_candidates)
        
        if self._config.merge_duplicates:
            merged_edges = self._merge_edges(all_candidates)
        else:
            merged_edges = all_candidates
        
        total_merged = len(merged_edges)
        
        filtered_edges = [
            e for e in merged_edges
            if self._get_edge_weight(e) >= self._config.min_edge_weight
        ]
        total_filtered = len(filtered_edges)
        
        filtered_edges.sort(key=lambda e: self._get_edge_weight(e), reverse=True)
        final_edges = filtered_edges[:self._config.max_edges_per_memory]
        
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        self._total_extractions += 1
        self._total_edges_created += len(final_edges)
        self._total_duration_ms += duration_ms
        
        return OrchestrationResult(
            edges=final_edges,
            source_memory_id=memory.id,
            duration_ms=duration_ms,
            extractor_results=extractor_results,
            merge_stats={
                "duplicates_removed": total_candidates - total_merged,
                "weight_filtered": total_merged - total_filtered,
                "limit_filtered": total_filtered - len(final_edges),
            },
            total_candidates=total_candidates,
            total_merged=total_merged,
            total_filtered=total_filtered,
            final_count=len(final_edges),
        )
    
    async def extract_async(
        self,
        memory: MemoryLike,
        all_memories: list[MemoryLike],
    ) -> OrchestrationResult:
        """
        Async extraction with parallel execution.
        
        Runs non-LLM extractors in parallel, then LLM extractor.
        
        Args:
            memory: The memory to analyze
            all_memories: All memories for comparison
            
        Returns:
            OrchestrationResult with merged edges
        """
        start_time = time.perf_counter()
        extractor_results: dict[str, ExtractionResult] = {}
        all_candidates: list[Edge] = []
        
        sync_extractors = {
            name: ext for name, ext in self._extractors.items()
            if name != "llm"
        }
        
        if self._config.parallel_extraction and len(sync_extractors) > 1:
            loop = asyncio.get_event_loop()
            tasks = []
            
            for name, extractor in sync_extractors.items():
                task = loop.run_in_executor(
                    None, extractor.extract, memory, all_memories
                )
                tasks.append((name, task))
            
            for name, task in tasks:
                try:
                    result = await task
                    extractor_results[name] = result
                    all_candidates.extend(result.edges)
                except Exception as e:
                    logger.error(f"Extractor '{name}' failed: {e}")
        else:
            for name, extractor in sync_extractors.items():
                try:
                    result = extractor.extract(memory, all_memories)
                    extractor_results[name] = result
                    all_candidates.extend(result.edges)
                except Exception as e:
                    logger.error(f"Extractor '{name}' failed: {e}")
        
        if "llm" in self._extractors:
            llm_extractor = self._extractors["llm"]
            if isinstance(llm_extractor, LLMExtractor):
                try:
                    result = await llm_extractor.extract_async(memory, all_memories)
                    extractor_results["llm"] = result
                    all_candidates.extend(result.edges)
                except Exception as e:
                    logger.error(f"LLM extractor failed: {e}")
        
        total_candidates = len(all_candidates)
        
        if self._config.merge_duplicates:
            merged_edges = self._merge_edges(all_candidates)
        else:
            merged_edges = all_candidates
        
        total_merged = len(merged_edges)
        
        filtered_edges = [
            e for e in merged_edges
            if self._get_edge_weight(e) >= self._config.min_edge_weight
        ]
        total_filtered = len(filtered_edges)
        
        filtered_edges.sort(key=lambda e: self._get_edge_weight(e), reverse=True)
        final_edges = filtered_edges[:self._config.max_edges_per_memory]
        
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        self._total_extractions += 1
        self._total_edges_created += len(final_edges)
        self._total_duration_ms += duration_ms
        
        return OrchestrationResult(
            edges=final_edges,
            source_memory_id=memory.id,
            duration_ms=duration_ms,
            extractor_results=extractor_results,
            merge_stats={
                "duplicates_removed": total_candidates - total_merged,
                "weight_filtered": total_merged - total_filtered,
                "limit_filtered": total_filtered - len(final_edges),
            },
            total_candidates=total_candidates,
            total_merged=total_merged,
            total_filtered=total_filtered,
            final_count=len(final_edges),
        )
    
    def extract_batch(
        self,
        memories: list[MemoryLike],
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> list[OrchestrationResult]:
        """
        Extract relationships for multiple memories.
        
        Args:
            memories: List of memories to process
            progress_callback: Optional callback(memory_id, current, total)
            
        Returns:
            List of OrchestrationResults
        """
        results = []
        total = len(memories)
        
        for i, memory in enumerate(memories):
            if progress_callback:
                progress_callback(memory.id, i + 1, total)
            
            result = self.extract(memory, memories)
            results.append(result)
        
        return results
    
    async def extract_batch_async(
        self,
        memories: list[MemoryLike],
        max_concurrent: int = 5,
    ) -> list[OrchestrationResult]:
        """
        Extract relationships for multiple memories with concurrency control.
        
        Args:
            memories: List of memories to process
            max_concurrent: Maximum concurrent extractions
            
        Returns:
            List of OrchestrationResults
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def extract_with_semaphore(memory: MemoryLike) -> OrchestrationResult:
            async with semaphore:
                return await self.extract_async(memory, memories)
        
        tasks = [extract_with_semaphore(m) for m in memories]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Extraction failed for {memories[i].id}: {result}")
                final_results.append(OrchestrationResult(
                    source_memory_id=memories[i].id,
                    edges=[],
                ))
            else:
                final_results.append(result)
        
        return final_results
    
    def _merge_edges(self, edges: list[Edge]) -> list[Edge]:
        """
        Merge duplicate edges keeping the highest weight.
        
        Args:
            edges: List of candidate edges
            
        Returns:
            Deduplicated edge list
        """
        groups: dict[tuple[str, str, str], list[Edge]] = {}
        
        for edge in edges:
            key = (edge.from_id, edge.to_id, edge.edge_type)
            if key not in groups:
                groups[key] = []
            groups[key].append(edge)
        
        merged: list[Edge] = []
        
        for key, group in groups.items():
            if len(group) == 1:
                merged.append(group[0])
            else:
                best = max(group, key=lambda e: self._get_edge_weight(e))
                
                if isinstance(best, RelatesTo):
                    contexts = []
                    for e in group:
                        if isinstance(e, RelatesTo) and e.context:
                            if e.context not in contexts:
                                contexts.append(e.context)
                    
                    if len(contexts) > 1:
                        combined_context = " | ".join(contexts[:3])
                        best = RelatesTo(
                            from_id=best.from_id,
                            to_id=best.to_id,
                            weight=best.weight,
                            context=combined_context,
                        )
                
                merged.append(best)
        
        return merged
    
    def _get_edge_weight(self, edge: Edge) -> float:
        """
        Get the weight/strength of an edge.
        
        Args:
            edge: Edge to get weight for
            
        Returns:
            Weight value (0.0-1.0)
        """
        if hasattr(edge, "weight"):
            return getattr(edge, "weight", 0.5)
        if hasattr(edge, "strength"):
            return getattr(edge, "strength", 0.5)
        
        return 0.5
    
    def get_stats(self) -> dict[str, Any]:
        """
        Get orchestrator statistics.
        
        Returns:
            Dictionary with extraction statistics
        """
        return {
            "total_extractions": self._total_extractions,
            "total_edges_created": self._total_edges_created,
            "total_duration_ms": self._total_duration_ms,
            "avg_edges_per_memory": (
                self._total_edges_created / self._total_extractions
                if self._total_extractions > 0
                else 0.0
            ),
            "avg_duration_ms": (
                self._total_duration_ms / self._total_extractions
                if self._total_extractions > 0
                else 0.0
            ),
            "enabled_extractors": list(self._extractors.keys()),
            "extractor_stats": {
                name: ext.get_stats()
                for name, ext in self._extractors.items()
            },
        }
    
    def reset_stats(self) -> None:
        """Reset all statistics."""
        self._total_extractions = 0
        self._total_edges_created = 0
        self._total_duration_ms = 0.0
        
        for extractor in self._extractors.values():
            extractor.reset_stats()
