"""Conflict candidate merger.

This module handles deduplication and merging of conflict candidates
from multiple detection methods, computing final confidence scores
and persisting new conflicts.
"""

import hashlib
import secrets
from collections import defaultdict
from datetime import datetime
from typing import TYPE_CHECKING

from dmm.core.constants import (
    CONFLICT_MULTI_METHOD_BOOST,
    CONFLICT_MULTI_METHOD_MAX_BOOST,
)
from dmm.models.conflict import (
    Conflict,
    ConflictCandidate,
    ConflictMemory,
    ConflictStatus,
    ConflictType,
    DetectionMethod,
    MergeResult,
)

if TYPE_CHECKING:
    from dmm.conflicts.store import ConflictStore
    from dmm.models.memory import IndexedMemory


class ConflictMerger:
    """Merges conflict candidates from multiple detection methods.
    
    This class:
    1. Groups candidates by memory pair
    2. Combines evidence from multiple methods
    3. Computes final confidence scores
    4. Checks for existing conflicts (deduplication)
    5. Persists new conflicts
    """

    def __init__(
        self,
        conflict_store: "ConflictStore",
        multi_method_boost: float = CONFLICT_MULTI_METHOD_BOOST,
        max_boost: float = CONFLICT_MULTI_METHOD_MAX_BOOST,
    ) -> None:
        """Initialize the merger.
        
        Args:
            conflict_store: The conflict store for persistence.
            multi_method_boost: Confidence boost per additional detection method.
            max_boost: Maximum total confidence boost.
        """
        self._store = conflict_store
        self._multi_method_boost = multi_method_boost
        self._max_boost = max_boost

    def merge_and_persist(
        self,
        candidates: list[ConflictCandidate],
        memory_map: dict[str, "IndexedMemory"],
        scan_id: str,
    ) -> MergeResult:
        """Merge candidates and persist new conflicts.
        
        Args:
            candidates: List of conflict candidates from analyzers.
            memory_map: Map of memory ID to memory object.
            scan_id: ID of the scan that produced these candidates.
            
        Returns:
            Merge result with statistics.
        """
        if not candidates:
            return MergeResult(
                total_candidates=0,
                unique_pairs=0,
                new_conflicts=0,
                existing_conflicts=0,
                conflicts=[],
            )
        
        pair_to_candidates = self._group_by_pair(candidates)
        
        new_conflicts = []
        existing_count = 0
        
        for pair_key, pair_candidates in pair_to_candidates.items():
            if self._store.exists_for_pair(pair_key):
                existing_count += 1
                continue
            
            m1 = memory_map.get(pair_key[0])
            m2 = memory_map.get(pair_key[1])
            
            if m1 is None or m2 is None:
                continue
            
            conflict = self._create_conflict(
                pair_candidates=pair_candidates,
                m1=m1,
                m2=m2,
                scan_id=scan_id,
            )
            
            try:
                self._store.create(conflict)
                new_conflicts.append(conflict)
            except Exception:
                existing_count += 1
        
        return MergeResult(
            total_candidates=len(candidates),
            unique_pairs=len(pair_to_candidates),
            new_conflicts=len(new_conflicts),
            existing_conflicts=existing_count,
            conflicts=new_conflicts,
        )

    def merge_without_persist(
        self,
        candidates: list[ConflictCandidate],
        memory_map: dict[str, "IndexedMemory"],
    ) -> list[Conflict]:
        """Merge candidates without persisting (for preview).
        
        Args:
            candidates: List of conflict candidates.
            memory_map: Map of memory ID to memory object.
            
        Returns:
            List of merged conflicts.
        """
        if not candidates:
            return []
        
        pair_to_candidates = self._group_by_pair(candidates)
        conflicts = []
        
        for pair_key, pair_candidates in pair_to_candidates.items():
            m1 = memory_map.get(pair_key[0])
            m2 = memory_map.get(pair_key[1])
            
            if m1 is None or m2 is None:
                continue
            
            conflict = self._create_conflict(
                pair_candidates=pair_candidates,
                m1=m1,
                m2=m2,
                scan_id="preview",
            )
            conflicts.append(conflict)
        
        return conflicts

    def _group_by_pair(
        self,
        candidates: list[ConflictCandidate],
    ) -> dict[tuple[str, str], list[ConflictCandidate]]:
        """Group candidates by memory pair."""
        pair_to_candidates: dict[tuple[str, str], list[ConflictCandidate]] = defaultdict(list)
        
        for candidate in candidates:
            pair_key = candidate.pair_key
            pair_to_candidates[pair_key].append(candidate)
        
        return pair_to_candidates

    def _create_conflict(
        self,
        pair_candidates: list[ConflictCandidate],
        m1: "IndexedMemory",
        m2: "IndexedMemory",
        scan_id: str,
    ) -> Conflict:
        """Create a conflict from merged candidates.
        
        Args:
            pair_candidates: Candidates for this memory pair.
            m1: First memory.
            m2: Second memory.
            scan_id: ID of the scan.
            
        Returns:
            Created conflict object.
        """
        confidence = self._compute_confidence(pair_candidates)
        conflict_type = self._determine_type(pair_candidates, m1, m2)
        combined_evidence = self._combine_evidence(pair_candidates)
        description = self._generate_description(m1, m2, pair_candidates, conflict_type)
        primary_method = self._get_primary_method(pair_candidates)
        
        return Conflict(
            conflict_id=self._generate_id(),
            memories=[
                ConflictMemory(
                    memory_id=m1.id,
                    path=m1.path,
                    title=m1.title,
                    summary=m1.body[:200] if m1.body else "",
                    scope=m1.scope.value,
                    priority=m1.priority,
                    role="primary",
                ),
                ConflictMemory(
                    memory_id=m2.id,
                    path=m2.path,
                    title=m2.title,
                    summary=m2.body[:200] if m2.body else "",
                    scope=m2.scope.value,
                    priority=m2.priority,
                    role="secondary",
                ),
            ],
            conflict_type=conflict_type,
            detection_method=primary_method,
            confidence=confidence,
            description=description,
            evidence=str(combined_evidence),
            status=ConflictStatus.UNRESOLVED,
            detected_at=datetime.utcnow(),
            scan_id=scan_id,
        )

    def _compute_confidence(
        self,
        candidates: list[ConflictCandidate],
    ) -> float:
        """Compute final confidence score.
        
        Confidence increases when multiple methods detect the conflict.
        
        Args:
            candidates: Candidates for a memory pair.
            
        Returns:
            Final confidence score (0.0 to 1.0).
        """
        if not candidates:
            return 0.0
        
        base_score = max(c.raw_score for c in candidates)
        
        methods = set(c.detection_method for c in candidates)
        method_boost = min(
            (len(methods) - 1) * self._multi_method_boost,
            self._max_boost,
        )
        
        return min(base_score + method_boost, 1.0)

    def _determine_type(
        self,
        candidates: list[ConflictCandidate],
        m1: "IndexedMemory",
        m2: "IndexedMemory",
    ) -> ConflictType:
        """Determine the conflict type.
        
        Args:
            candidates: Candidates for a memory pair.
            m1: First memory.
            m2: Second memory.
            
        Returns:
            The conflict type.
        """
        for candidate in candidates:
            evidence = candidate.evidence
            
            if candidate.detection_method == DetectionMethod.SUPERSESSION_CHAIN:
                issue_type = evidence.get("issue_type", "")
                if issue_type in ("orphaned", "incomplete", "circular", "contested"):
                    return ConflictType.SUPERSESSION
            
            if candidate.detection_method == DetectionMethod.SEMANTIC_SIMILARITY:
                similarity = evidence.get("similarity", 0)
                if similarity > 0.95:
                    return ConflictType.DUPLICATE
        
        if m1.scope != m2.scope:
            shared_tags = set(m1.tags) & set(m2.tags)
            if len(shared_tags) >= 3:
                return ConflictType.SCOPE_OVERLAP
        
        return ConflictType.CONTRADICTORY

    def _combine_evidence(
        self,
        candidates: list[ConflictCandidate],
    ) -> dict:
        """Combine evidence from multiple candidates.
        
        Args:
            candidates: Candidates for a memory pair.
            
        Returns:
            Combined evidence dictionary.
        """
        combined = {
            "methods": [],
            "scores": [],
            "details": {},
        }
        
        for candidate in candidates:
            method = candidate.detection_method.value
            combined["methods"].append(method)
            combined["scores"].append({
                "method": method,
                "score": round(candidate.raw_score, 4),
            })
            combined["details"][method] = candidate.evidence
        
        return combined

    def _generate_description(
        self,
        m1: "IndexedMemory",
        m2: "IndexedMemory",
        candidates: list[ConflictCandidate],
        conflict_type: ConflictType,
    ) -> str:
        """Generate a human-readable conflict description.
        
        Args:
            m1: First memory.
            m2: Second memory.
            candidates: Candidates for this pair.
            conflict_type: The determined conflict type.
            
        Returns:
            Description string.
        """
        type_descriptions = {
            ConflictType.CONTRADICTORY: "contain contradictory information",
            ConflictType.DUPLICATE: "appear to be duplicates",
            ConflictType.SUPERSESSION: "have supersession relationship issues",
            ConflictType.SCOPE_OVERLAP: "cover the same topic in different scopes",
            ConflictType.STALE: "may have stale or outdated information",
        }
        
        base_desc = type_descriptions.get(conflict_type, "may conflict")
        
        methods = list(set(c.detection_method.value for c in candidates))
        methods_str = ", ".join(methods)
        
        return (
            f"Memories '{m1.title}' and '{m2.title}' {base_desc}. "
            f"Detected via: {methods_str}."
        )

    def _get_primary_method(
        self,
        candidates: list[ConflictCandidate],
    ) -> DetectionMethod:
        """Get the primary detection method (highest score).
        
        Args:
            candidates: Candidates for a memory pair.
            
        Returns:
            The detection method with the highest score.
        """
        if not candidates:
            return DetectionMethod.MANUAL
        
        best = max(candidates, key=lambda c: c.raw_score)
        return best.detection_method

    def _generate_id(self) -> str:
        """Generate a unique conflict ID."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        random_suffix = secrets.token_hex(4)
        return f"conflict_{timestamp}_{random_suffix}"

    def get_stats(self) -> dict:
        """Get merger statistics."""
        return {
            "multi_method_boost": self._multi_method_boost,
            "max_boost": self._max_boost,
        }
