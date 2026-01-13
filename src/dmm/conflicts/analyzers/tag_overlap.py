"""Tag overlap conflict detection analyzer.

This analyzer detects conflicts by finding memories that share tags
and exhibit contradiction patterns in their content.
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dmm.core.constants import (
    CONTRADICTION_PATTERNS,
    TAG_OVERLAP_CONTRADICTION_SCORE_INCREMENT,
    TAG_OVERLAP_MIN_SHARED_TAGS,
)
from dmm.models.conflict import ConflictCandidate, DetectionMethod

if TYPE_CHECKING:
    from dmm.indexer.store import MemoryStore
    from dmm.models.memory import IndexedMemory


@dataclass
class TagOverlapConfig:
    """Configuration for tag overlap analysis."""
    
    min_shared_tags: int = TAG_OVERLAP_MIN_SHARED_TAGS
    contradiction_score_increment: float = TAG_OVERLAP_CONTRADICTION_SCORE_INCREMENT
    max_candidates: int = 100
    ignore_deprecated: bool = True


class TagOverlapAnalyzer:
    """Detects conflicts via shared tags and contradiction patterns.
    
    This analyzer works by:
    1. Grouping memories by their tags
    2. Finding pairs that share multiple tags
    3. Checking for contradiction signals in titles/content
    4. Scoring based on signal strength
    """

    def __init__(
        self,
        store: "MemoryStore",
        config: TagOverlapConfig | None = None,
    ) -> None:
        """Initialize the analyzer.
        
        Args:
            store: The memory store to query.
            config: Optional configuration.
        """
        self._store = store
        self._config = config or TagOverlapConfig()
        self._compiled_patterns: list[tuple[re.Pattern, re.Pattern]] = []
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile contradiction regex patterns."""
        self._compiled_patterns = [
            (re.compile(p1, re.IGNORECASE), re.compile(p2, re.IGNORECASE))
            for p1, p2 in CONTRADICTION_PATTERNS
        ]

    def analyze(
        self,
        memory_ids: list[str] | None = None,
    ) -> list[ConflictCandidate]:
        """Find conflicts via tag overlap.
        
        Args:
            memory_ids: Optional list of memory IDs to analyze.
                       If None, analyzes all active memories.
                       
        Returns:
            List of conflict candidates.
        """
        memories = self._get_memories(memory_ids)
        
        if len(memories) < 2:
            return []
        
        tag_to_memories = self._build_tag_index(memories)
        candidates = self._find_candidates(memories, tag_to_memories)
        
        candidates.sort(key=lambda c: c.raw_score, reverse=True)
        return candidates[:self._config.max_candidates]

    def analyze_single(
        self,
        memory_id: str,
    ) -> list[ConflictCandidate]:
        """Analyze a single memory against all others.
        
        Args:
            memory_id: The memory ID to analyze.
            
        Returns:
            List of conflict candidates involving this memory.
        """
        target_memory = self._store.get_memory(memory_id)
        if target_memory is None:
            return []
        
        all_memories = self._get_memories(None)
        other_memories = [m for m in all_memories if m.id != memory_id]
        
        if not other_memories:
            return []
        
        candidates = []
        target_tags = set(target_memory.tags)
        
        for other in other_memories:
            other_tags = set(other.tags)
            shared_tags = target_tags & other_tags
            
            if len(shared_tags) < self._config.min_shared_tags:
                continue
            
            score, evidence = self._check_contradiction(target_memory, other)
            
            if score > 0:
                candidates.append(ConflictCandidate(
                    memory_ids=(target_memory.id, other.id),
                    detection_method=DetectionMethod.TAG_OVERLAP,
                    raw_score=score,
                    evidence={
                        "shared_tags": list(shared_tags),
                        "contradiction_signals": evidence,
                        "shared_tag_count": len(shared_tags),
                    },
                ))
        
        candidates.sort(key=lambda c: c.raw_score, reverse=True)
        return candidates[:self._config.max_candidates]

    def _get_memories(
        self,
        memory_ids: list[str] | None,
    ) -> list["IndexedMemory"]:
        """Get memories to analyze."""
        if memory_ids:
            memories = []
            for mid in memory_ids:
                mem = self._store.get_memory(mid)
                if mem is not None:
                    memories.append(mem)
            return memories
        
        all_memories = self._store.get_all_memories()
        
        if self._config.ignore_deprecated:
            all_memories = [m for m in all_memories if m.status.value != "deprecated"]
        
        return all_memories

    def _build_tag_index(
        self,
        memories: list["IndexedMemory"],
    ) -> dict[str, list["IndexedMemory"]]:
        """Build an index mapping tags to memories."""
        tag_to_memories: dict[str, list["IndexedMemory"]] = defaultdict(list)
        
        for memory in memories:
            for tag in memory.tags:
                tag_to_memories[tag.lower()].append(memory)
        
        return tag_to_memories

    def _find_candidates(
        self,
        memories: list["IndexedMemory"],
        tag_to_memories: dict[str, list["IndexedMemory"]],
    ) -> list[ConflictCandidate]:
        """Find conflict candidates from tag overlap."""
        candidates = []
        checked_pairs: set[tuple[str, str]] = set()
        memory_map = {m.id: m for m in memories}
        
        for tag, tag_memories in tag_to_memories.items():
            if len(tag_memories) < 2:
                continue
            
            for i, m1 in enumerate(tag_memories):
                for m2 in tag_memories[i + 1:]:
                    pair_key = tuple(sorted([m1.id, m2.id]))
                    
                    if pair_key in checked_pairs:
                        continue
                    checked_pairs.add(pair_key)
                    
                    shared_tags = set(m1.tags) & set(m2.tags)
                    if len(shared_tags) < self._config.min_shared_tags:
                        continue
                    
                    score, evidence = self._check_contradiction(m1, m2)
                    
                    if score > 0:
                        candidates.append(ConflictCandidate(
                            memory_ids=(m1.id, m2.id),
                            detection_method=DetectionMethod.TAG_OVERLAP,
                            raw_score=score,
                            evidence={
                                "shared_tags": list(shared_tags),
                                "contradiction_signals": evidence,
                                "shared_tag_count": len(shared_tags),
                            },
                        ))
        
        return candidates

    def _check_contradiction(
        self,
        m1: "IndexedMemory",
        m2: "IndexedMemory",
    ) -> tuple[float, list[str]]:
        """Check for contradiction signals between two memories.
        
        Args:
            m1: First memory.
            m2: Second memory.
            
        Returns:
            Tuple of (score, list of evidence strings).
        """
        evidence = []
        score = 0.0
        
        text1 = f"{m1.title} {m1.body}".lower()
        text2 = f"{m2.title} {m2.body}".lower()
        
        for pattern1, pattern2 in self._compiled_patterns:
            has1_p1 = bool(pattern1.search(text1))
            has1_p2 = bool(pattern2.search(text1))
            has2_p1 = bool(pattern1.search(text2))
            has2_p2 = bool(pattern2.search(text2))
            
            if (has1_p1 and has2_p2) or (has1_p2 and has2_p1):
                evidence.append(f"{pattern1.pattern} vs {pattern2.pattern}")
                score += self._config.contradiction_score_increment
        
        shared_tags_boost = min(len(set(m1.tags) & set(m2.tags)) * 0.05, 0.2)
        score += shared_tags_boost
        
        return min(score, 1.0), evidence

    def get_stats(self) -> dict:
        """Get analyzer statistics."""
        return {
            "min_shared_tags": self._config.min_shared_tags,
            "contradiction_patterns": len(self._compiled_patterns),
            "max_candidates": self._config.max_candidates,
        }
