"""Conflict detection orchestrator.

This module provides the main ConflictDetector class that orchestrates
multiple detection methods and manages the conflict detection pipeline.
"""

import logging
import secrets
from datetime import datetime
from typing import TYPE_CHECKING

from dmm.core.constants import (
    IGNORE_DEPRECATED_IN_SCAN,
    IGNORE_EPHEMERAL_VS_EPHEMERAL,
    MAX_CANDIDATES_PER_METHOD,
)
from dmm.models.conflict import (
    ConflictCandidate,
    DetectionMethod,
    ScanRequest,
    ScanResult,
)

if TYPE_CHECKING:
    from dmm.conflicts.analyzers.rule_extraction import RuleExtractionAnalyzer
    from dmm.conflicts.analyzers.semantic import SemanticClusteringAnalyzer
    from dmm.conflicts.analyzers.supersession import SupersessionChainAnalyzer
    from dmm.conflicts.analyzers.tag_overlap import TagOverlapAnalyzer
    from dmm.conflicts.merger import ConflictMerger
    from dmm.conflicts.store import ConflictStore
    from dmm.indexer.embedder import MemoryEmbedder
    from dmm.indexer.store import MemoryStore
    from dmm.models.memory import IndexedMemory


logger = logging.getLogger(__name__)


class ConflictConfig:
    """Configuration for conflict detection."""

    def __init__(
        self,
        max_candidates_per_method: int = MAX_CANDIDATES_PER_METHOD,
        ignore_deprecated: bool = IGNORE_DEPRECATED_IN_SCAN,
        ignore_ephemeral_vs_ephemeral: bool = IGNORE_EPHEMERAL_VS_EPHEMERAL,
        use_rule_extraction: bool = False,
        llm_client=None,
    ) -> None:
        """Initialize configuration.
        
        Args:
            max_candidates_per_method: Max candidates from each analyzer.
            ignore_deprecated: Skip deprecated memories in scans.
            ignore_ephemeral_vs_ephemeral: Skip ephemeral vs ephemeral conflicts.
            use_rule_extraction: Enable LLM rule extraction.
            llm_client: Optional LLM client for rule extraction.
        """
        self.max_candidates_per_method = max_candidates_per_method
        self.ignore_deprecated = ignore_deprecated
        self.ignore_ephemeral_vs_ephemeral = ignore_ephemeral_vs_ephemeral
        self.use_rule_extraction = use_rule_extraction
        self.llm_client = llm_client


class ConflictDetector:
    """Main orchestrator for conflict detection.
    
    This class coordinates multiple detection methods:
    - Tag overlap analysis
    - Semantic similarity clustering
    - Supersession chain validation
    - Optional LLM-based rule extraction
    
    It merges results from all methods, deduplicates, and persists conflicts.
    """

    def __init__(
        self,
        memory_store: "MemoryStore",
        conflict_store: "ConflictStore",
        embedder: "MemoryEmbedder",
        merger: "ConflictMerger",
        config: ConflictConfig | None = None,
    ) -> None:
        """Initialize the detector.
        
        Args:
            memory_store: The memory store.
            conflict_store: The conflict store.
            embedder: The memory embedder.
            merger: The conflict merger.
            config: Optional configuration.
        """
        self._memory_store = memory_store
        self._conflict_store = conflict_store
        self._embedder = embedder
        self._merger = merger
        self._config = config or ConflictConfig()
        
        self._tag_analyzer: "TagOverlapAnalyzer | None" = None
        self._semantic_analyzer: "SemanticClusteringAnalyzer | None" = None
        self._supersession_analyzer: "SupersessionChainAnalyzer | None" = None
        self._rule_analyzer: "RuleExtractionAnalyzer | None" = None
        
        self._initialize_analyzers()

    def _initialize_analyzers(self) -> None:
        """Initialize all analyzers."""
        from dmm.conflicts.analyzers.rule_extraction import (
            RuleExtractionAnalyzer,
            RuleExtractionConfig,
        )
        from dmm.conflicts.analyzers.semantic import SemanticClusteringAnalyzer
        from dmm.conflicts.analyzers.supersession import SupersessionChainAnalyzer
        from dmm.conflicts.analyzers.tag_overlap import TagOverlapAnalyzer
        
        self._tag_analyzer = TagOverlapAnalyzer(self._memory_store)
        self._semantic_analyzer = SemanticClusteringAnalyzer(
            self._memory_store, self._embedder
        )
        self._supersession_analyzer = SupersessionChainAnalyzer(self._memory_store)
        
        rule_config = RuleExtractionConfig()
        self._rule_analyzer = RuleExtractionAnalyzer(
            config=rule_config,
            llm_client=self._config.llm_client if self._config.use_rule_extraction else None,
        )

    async def scan(self, request: ScanRequest) -> ScanResult:
        """Execute a conflict scan.
        
        Args:
            request: The scan request specifying type and methods.
            
        Returns:
            Scan result with statistics.
        """
        scan_id = self._generate_scan_id()
        started_at = datetime.utcnow()
        errors: list[str] = []
        
        self._conflict_store.save_scan(
            scan_id=scan_id,
            scan_type=request.scan_type,
            started_at=started_at,
            status="running",
        )
        
        try:
            if request.scan_type == "targeted" and request.target_memory_id:
                candidates = await self._analyze_single_memory(
                    request.target_memory_id, request
                )
                memories_scanned = 1
            else:
                candidates, memories_scanned = await self._analyze_all_memories(request)
            
            if request.include_rule_extraction and self._rule_analyzer and self._rule_analyzer.is_enabled:
                memory_map = self._get_memory_map()
                candidates = self._rule_analyzer.analyze_candidates(candidates, memory_map)
            
            candidates = self._filter_candidates(candidates)
            
            memory_map = self._get_memory_map()
            merge_result = self._merger.merge_and_persist(candidates, memory_map, scan_id)
            
            completed_at = datetime.utcnow()
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)
            
            by_type = self._count_by_type(merge_result.conflicts)
            by_method = self._count_by_method(candidates)
            
            result = ScanResult(
                scan_id=scan_id,
                scan_type=request.scan_type,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                memories_scanned=memories_scanned,
                methods_used=[m.value for m in request.methods],
                conflicts_detected=merge_result.new_conflicts + merge_result.existing_conflicts,
                conflicts_new=merge_result.new_conflicts,
                conflicts_existing=merge_result.existing_conflicts,
                by_type=by_type,
                by_method=by_method,
                errors=errors,
            )
            
            self._conflict_store.save_scan(
                scan_id=scan_id,
                scan_type=request.scan_type,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                memories_scanned=memories_scanned,
                methods_used=[m.value for m in request.methods],
                conflicts_detected=result.conflicts_detected,
                conflicts_new=result.conflicts_new,
                conflicts_existing=result.conflicts_existing,
                by_type=by_type,
                by_method=by_method,
                status="completed",
                errors=errors,
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Scan failed: {e}")
            errors.append(str(e))
            
            completed_at = datetime.utcnow()
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)
            
            self._conflict_store.save_scan(
                scan_id=scan_id,
                scan_type=request.scan_type,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                status="failed",
                errors=errors,
            )
            
            return ScanResult(
                scan_id=scan_id,
                scan_type=request.scan_type,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                memories_scanned=0,
                methods_used=[m.value for m in request.methods],
                conflicts_detected=0,
                conflicts_new=0,
                conflicts_existing=0,
                errors=errors,
            )

    async def scan_new_memory(self, memory_id: str) -> ScanResult:
        """Scan for conflicts involving a newly committed memory.
        
        Args:
            memory_id: The memory ID to scan.
            
        Returns:
            Scan result.
        """
        request = ScanRequest(
            scan_type="incremental",
            target_memory_id=memory_id,
        )
        
        return await self.scan(request)

    async def check_proposal(
        self,
        content: str,
        path: str,
        tags: list[str],
    ) -> list[ConflictCandidate]:
        """Check if proposed content would conflict with existing memories.
        
        Called by ReviewerAgent during review.
        
        Args:
            content: Proposed memory content.
            path: Proposed memory path.
            tags: Proposed memory tags.
            
        Returns:
            List of potential conflict candidates.
        """
        candidates = []
        
        all_memories = self._memory_store.get_all_memories()
        if self._config.ignore_deprecated:
            all_memories = [m for m in all_memories if m.status != "deprecated"]
        
        for memory in all_memories:
            shared_tags = set(tags) & set(memory.tags)
            if len(shared_tags) >= 2:
                candidates.append(ConflictCandidate(
                    memory_ids=("proposal", memory.id),
                    detection_method=DetectionMethod.TAG_OVERLAP,
                    raw_score=len(shared_tags) * 0.2,
                    evidence={
                        "shared_tags": list(shared_tags),
                        "existing_memory": memory.id,
                        "existing_path": memory.path,
                    },
                ))
        
        if self._embedder:
            try:
                proposal_embedding = self._embedder.embed_text(content)
                
                for memory in all_memories[:100]:
                    if memory.composite_embedding:
                        import numpy as np
                        similarity = float(np.dot(
                            proposal_embedding,
                            np.array(memory.composite_embedding)
                        ) / (
                            np.linalg.norm(proposal_embedding) *
                            np.linalg.norm(memory.composite_embedding)
                        ))
                        
                        if similarity > 0.8:
                            candidates.append(ConflictCandidate(
                                memory_ids=("proposal", memory.id),
                                detection_method=DetectionMethod.SEMANTIC_SIMILARITY,
                                raw_score=similarity,
                                evidence={
                                    "similarity": round(similarity, 4),
                                    "existing_memory": memory.id,
                                    "existing_path": memory.path,
                                },
                            ))
            except Exception as e:
                logger.warning(f"Embedding check failed: {e}")
        
        return candidates

    async def _analyze_all_memories(
        self,
        request: ScanRequest,
    ) -> tuple[list[ConflictCandidate], int]:
        """Run all analyzers on all memories.
        
        Args:
            request: The scan request.
            
        Returns:
            Tuple of (candidates, memories_scanned).
        """
        all_candidates: list[ConflictCandidate] = []
        
        memories = self._memory_store.get_all_memories()
        if self._config.ignore_deprecated:
            memories = [m for m in memories if m.status != "deprecated"]
        
        memory_ids = [m.id for m in memories]
        
        for method in request.methods:
            try:
                method_candidates = await self._run_analyzer(method, memory_ids)
                all_candidates.extend(method_candidates[:self._config.max_candidates_per_method])
            except Exception as e:
                logger.error(f"Analyzer {method.value} failed: {e}")
        
        return all_candidates, len(memories)

    async def _analyze_single_memory(
        self,
        memory_id: str,
        request: ScanRequest,
    ) -> list[ConflictCandidate]:
        """Run analyzers for a single memory.
        
        Args:
            memory_id: The memory to analyze.
            request: The scan request.
            
        Returns:
            List of conflict candidates.
        """
        all_candidates: list[ConflictCandidate] = []
        
        for method in request.methods:
            try:
                if method == DetectionMethod.TAG_OVERLAP and self._tag_analyzer:
                    candidates = self._tag_analyzer.analyze_single(memory_id)
                elif method == DetectionMethod.SEMANTIC_SIMILARITY and self._semantic_analyzer:
                    candidates = self._semantic_analyzer.analyze_single(memory_id)
                elif method == DetectionMethod.SUPERSESSION_CHAIN and self._supersession_analyzer:
                    candidates = self._supersession_analyzer.analyze_single(memory_id)
                else:
                    candidates = []
                
                all_candidates.extend(candidates[:self._config.max_candidates_per_method])
            except Exception as e:
                logger.error(f"Single memory analyzer {method.value} failed: {e}")
        
        return all_candidates

    async def _run_analyzer(
        self,
        method: DetectionMethod,
        memory_ids: list[str] | None = None,
    ) -> list[ConflictCandidate]:
        """Run a specific analyzer.
        
        Args:
            method: The detection method.
            memory_ids: Optional list of memory IDs.
            
        Returns:
            List of conflict candidates.
        """
        if method == DetectionMethod.TAG_OVERLAP and self._tag_analyzer:
            return self._tag_analyzer.analyze(memory_ids)
        elif method == DetectionMethod.SEMANTIC_SIMILARITY and self._semantic_analyzer:
            return self._semantic_analyzer.analyze(memory_ids)
        elif method == DetectionMethod.SUPERSESSION_CHAIN and self._supersession_analyzer:
            return self._supersession_analyzer.analyze(memory_ids)
        elif method == DetectionMethod.RULE_EXTRACTION and self._rule_analyzer:
            return []
        else:
            return []

    def _filter_candidates(
        self,
        candidates: list[ConflictCandidate],
    ) -> list[ConflictCandidate]:
        """Filter candidates based on configuration.
        
        Args:
            candidates: Raw candidates from analyzers.
            
        Returns:
            Filtered candidates.
        """
        if not self._config.ignore_ephemeral_vs_ephemeral:
            return candidates
        
        filtered = []
        memory_map = self._get_memory_map()
        
        for candidate in candidates:
            m1_id, m2_id = candidate.memory_ids
            m1 = memory_map.get(m1_id)
            m2 = memory_map.get(m2_id)
            
            if m1 and m2:
                if m1.scope == "ephemeral" and m2.scope == "ephemeral":
                    continue
            
            filtered.append(candidate)
        
        return filtered

    def _get_memory_map(self) -> dict[str, "IndexedMemory"]:
        """Get a map of all memories."""
        memories = self._memory_store.get_all_memories()
        return {m.id: m for m in memories}

    def _count_by_type(self, conflicts) -> dict[str, int]:
        """Count conflicts by type."""
        counts: dict[str, int] = {}
        for conflict in conflicts:
            type_val = conflict.conflict_type.value
            counts[type_val] = counts.get(type_val, 0) + 1
        return counts

    def _count_by_method(self, candidates: list[ConflictCandidate]) -> dict[str, int]:
        """Count candidates by detection method."""
        counts: dict[str, int] = {}
        for candidate in candidates:
            method_val = candidate.detection_method.value
            counts[method_val] = counts.get(method_val, 0) + 1
        return counts

    def _generate_scan_id(self) -> str:
        """Generate a unique scan ID."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        random_suffix = secrets.token_hex(4)
        return f"scan_{timestamp}_{random_suffix}"

    def get_stats(self) -> dict:
        """Get detector statistics."""
        return {
            "analyzers": {
                "tag_overlap": self._tag_analyzer.get_stats() if self._tag_analyzer else None,
                "semantic": self._semantic_analyzer.get_stats() if self._semantic_analyzer else None,
                "supersession": self._supersession_analyzer.get_stats() if self._supersession_analyzer else None,
                "rule_extraction": self._rule_analyzer.get_stats() if self._rule_analyzer else None,
            },
            "config": {
                "max_candidates_per_method": self._config.max_candidates_per_method,
                "ignore_deprecated": self._config.ignore_deprecated,
                "ignore_ephemeral_vs_ephemeral": self._config.ignore_ephemeral_vs_ephemeral,
                "use_rule_extraction": self._config.use_rule_extraction,
            },
        }
