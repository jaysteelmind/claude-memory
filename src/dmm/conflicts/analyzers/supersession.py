"""Supersession chain conflict detection analyzer.

This analyzer detects conflicts in supersession relationships between memories,
including orphaned supersessions, circular references, and contested supersessions.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from dmm.core.constants import (
    SUPERSESSION_CIRCULAR_SCORE,
    SUPERSESSION_CONTESTED_SCORE,
    SUPERSESSION_ORPHAN_SCORE,
)
from dmm.models.conflict import ConflictCandidate, DetectionMethod

if TYPE_CHECKING:
    from dmm.indexer.store import MemoryStore
    from dmm.models.memory import IndexedMemory


@dataclass
class SupersessionConfig:
    """Configuration for supersession chain analysis."""
    
    orphan_score: float = SUPERSESSION_ORPHAN_SCORE
    contested_score: float = SUPERSESSION_CONTESTED_SCORE
    circular_score: float = SUPERSESSION_CIRCULAR_SCORE
    max_candidates: int = 100
    max_chain_depth: int = 10


class SupersessionChainAnalyzer:
    """Detects conflicts in supersession chains.
    
    This analyzer detects several types of supersession issues:
    
    1. Orphaned: Memory A claims to supersede B, but B is still active
    2. Circular: A supersedes B supersedes C supersedes A
    3. Contested: Both A and B claim to supersede C
    4. Incomplete: A supersedes B, but A is deprecated
    """

    def __init__(
        self,
        store: "MemoryStore",
        config: SupersessionConfig | None = None,
    ) -> None:
        """Initialize the analyzer.
        
        Args:
            store: The memory store to query.
            config: Optional configuration.
        """
        self._store = store
        self._config = config or SupersessionConfig()

    def analyze(
        self,
        memory_ids: list[str] | None = None,
    ) -> list[ConflictCandidate]:
        """Find conflicts in supersession chains.
        
        Args:
            memory_ids: Optional list of memory IDs to analyze.
                       If None, analyzes all memories with supersession relationships.
                       
        Returns:
            List of conflict candidates.
        """
        memories = self._get_memories(memory_ids)
        
        if not memories:
            return []
        
        supersedes_map, superseded_by = self._build_supersession_graph(memories)
        memory_map = {m.id: m for m in memories}
        
        candidates = []
        
        orphan_candidates = self._find_orphaned(memories, supersedes_map, memory_map)
        candidates.extend(orphan_candidates)
        
        contested_candidates = self._find_contested(superseded_by, memory_map)
        candidates.extend(contested_candidates)
        
        circular_candidates = self._find_circular(supersedes_map)
        candidates.extend(circular_candidates)
        
        incomplete_candidates = self._find_incomplete(memories, supersedes_map, memory_map)
        candidates.extend(incomplete_candidates)
        
        candidates.sort(key=lambda c: c.raw_score, reverse=True)
        return candidates[:self._config.max_candidates]

    def analyze_single(
        self,
        memory_id: str,
    ) -> list[ConflictCandidate]:
        """Analyze supersession chains involving a single memory.
        
        Args:
            memory_id: The memory ID to analyze.
            
        Returns:
            List of conflict candidates involving this memory.
        """
        target_memory = self._store.get_memory(memory_id)
        if target_memory is None:
            return []
        
        all_memories = self._get_memories(None)
        supersedes_map, superseded_by = self._build_supersession_graph(all_memories)
        memory_map = {m.id: m for m in all_memories}
        
        candidates = []
        
        if target_memory.supersedes:
            for target_id in target_memory.supersedes:
                target = memory_map.get(target_id)
                if target and target.status.value == "active":
                    candidates.append(ConflictCandidate(
                        memory_ids=(memory_id, target_id),
                        detection_method=DetectionMethod.SUPERSESSION_CHAIN,
                        raw_score=self._config.orphan_score,
                        evidence={
                            "issue_type": "orphaned",
                            "description": f"{memory_id} claims to supersede {target_id}, but {target_id} is still active",
                            "superseding_memory": memory_id,
                            "superseded_memory": target_id,
                        },
                    ))
        
        if memory_id in superseded_by:
            superseding_ids = superseded_by[memory_id]
            active_superseding = [
                mid for mid in superseding_ids
                if memory_map.get(mid) and memory_map[mid].status.value == "active"
            ]
            if len(active_superseding) > 1:
                candidates.append(ConflictCandidate(
                    memory_ids=(active_superseding[0], active_superseding[1]),
                    detection_method=DetectionMethod.SUPERSESSION_CHAIN,
                    raw_score=self._config.contested_score,
                    evidence={
                        "issue_type": "contested",
                        "description": f"Multiple memories ({', '.join(active_superseding)}) claim to supersede {memory_id}",
                        "contested_target": memory_id,
                        "competing_memories": active_superseding,
                    },
                ))
        
        cycle = self._find_cycle_from(memory_id, supersedes_map)
        if cycle:
            candidates.append(ConflictCandidate(
                memory_ids=(cycle[0], cycle[1] if len(cycle) > 1 else cycle[0]),
                detection_method=DetectionMethod.SUPERSESSION_CHAIN,
                raw_score=self._config.circular_score,
                evidence={
                    "issue_type": "circular",
                    "description": f"Circular supersession detected: {' -> '.join(cycle)}",
                    "cycle": cycle,
                },
            ))
        
        return candidates

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
        
        return self._store.get_all_memories()

    def _build_supersession_graph(
        self,
        memories: list["IndexedMemory"],
    ) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        """Build supersession relationship graphs.
        
        Args:
            memories: List of memories.
            
        Returns:
            Tuple of (supersedes_map, superseded_by_map).
        """
        supersedes_map: dict[str, list[str]] = {}
        superseded_by: dict[str, list[str]] = {}
        
        for memory in memories:
            if memory.supersedes:
                supersedes_map[memory.id] = list(memory.supersedes)
                for target in memory.supersedes:
                    if target not in superseded_by:
                        superseded_by[target] = []
                    superseded_by[target].append(memory.id)
        
        return supersedes_map, superseded_by

    def _find_orphaned(
        self,
        memories: list["IndexedMemory"],
        supersedes_map: dict[str, list[str]],
        memory_map: dict[str, "IndexedMemory"],
    ) -> list[ConflictCandidate]:
        """Find orphaned supersession relationships.
        
        Orphaned: Memory A supersedes B, but B is still active.
        """
        candidates = []
        
        for memory in memories:
            if memory.status.value == "deprecated":
                continue
            
            if memory.id not in supersedes_map:
                continue
            
            for target_id in supersedes_map[memory.id]:
                target = memory_map.get(target_id)
                if target and target.status.value == "active":
                    candidates.append(ConflictCandidate(
                        memory_ids=(memory.id, target_id),
                        detection_method=DetectionMethod.SUPERSESSION_CHAIN,
                        raw_score=self._config.orphan_score,
                        evidence={
                            "issue_type": "orphaned",
                            "description": f"{memory.id} claims to supersede {target_id}, but {target_id} is still active",
                            "superseding_memory": memory.id,
                            "superseded_memory": target_id,
                        },
                    ))
        
        return candidates

    def _find_contested(
        self,
        superseded_by: dict[str, list[str]],
        memory_map: dict[str, "IndexedMemory"],
    ) -> list[ConflictCandidate]:
        """Find contested supersession relationships.
        
        Contested: Multiple active memories claim to supersede the same target.
        """
        candidates = []
        
        for target_id, superseding_ids in superseded_by.items():
            if len(superseding_ids) < 2:
                continue
            
            active_superseding = [
                mid for mid in superseding_ids
                if memory_map.get(mid) and memory_map[mid].status.value == "active"
            ]
            
            if len(active_superseding) > 1:
                candidates.append(ConflictCandidate(
                    memory_ids=(active_superseding[0], active_superseding[1]),
                    detection_method=DetectionMethod.SUPERSESSION_CHAIN,
                    raw_score=self._config.contested_score,
                    evidence={
                        "issue_type": "contested",
                        "description": f"Multiple memories ({', '.join(active_superseding)}) claim to supersede {target_id}",
                        "contested_target": target_id,
                        "competing_memories": active_superseding,
                    },
                ))
        
        return candidates

    def _find_circular(
        self,
        supersedes_map: dict[str, list[str]],
    ) -> list[ConflictCandidate]:
        """Find circular supersession relationships."""
        candidates = []
        visited_global: set[str] = set()
        
        for start_id in supersedes_map:
            if start_id in visited_global:
                continue
            
            cycle = self._find_cycle_from(start_id, supersedes_map)
            if cycle:
                visited_global.update(cycle)
                candidates.append(ConflictCandidate(
                    memory_ids=(cycle[0], cycle[1] if len(cycle) > 1 else cycle[0]),
                    detection_method=DetectionMethod.SUPERSESSION_CHAIN,
                    raw_score=self._config.circular_score,
                    evidence={
                        "issue_type": "circular",
                        "description": f"Circular supersession detected: {' -> '.join(cycle)}",
                        "cycle": cycle,
                    },
                ))
        
        return candidates

    def _find_cycle_from(
        self,
        start_id: str,
        supersedes_map: dict[str, list[str]],
    ) -> list[str] | None:
        """Find a cycle starting from a given memory ID.
        
        Args:
            start_id: The memory ID to start from.
            supersedes_map: Map of memory ID to superseded IDs.
            
        Returns:
            List of memory IDs forming the cycle, or None if no cycle.
        """
        visited: set[str] = set()
        path: list[str] = []
        
        def dfs(current_id: str) -> list[str] | None:
            if current_id in visited:
                if current_id in path:
                    cycle_start = path.index(current_id)
                    return path[cycle_start:] + [current_id]
                return None
            
            if len(path) >= self._config.max_chain_depth:
                return None
            
            visited.add(current_id)
            path.append(current_id)
            
            if current_id in supersedes_map:
                for target_id in supersedes_map[current_id]:
                    result = dfs(target_id)
                    if result:
                        return result
            
            path.pop()
            return None
        
        return dfs(start_id)

    def _find_incomplete(
        self,
        memories: list["IndexedMemory"],
        supersedes_map: dict[str, list[str]],
        memory_map: dict[str, "IndexedMemory"],
    ) -> list[ConflictCandidate]:
        """Find incomplete supersession relationships.
        
        Incomplete: Memory A supersedes B, but A is deprecated.
        """
        candidates = []
        
        for memory in memories:
            if memory.status.value != "deprecated":
                continue
            
            if memory.id not in supersedes_map:
                continue
            
            for target_id in supersedes_map[memory.id]:
                target = memory_map.get(target_id)
                if target and target.status.value == "active":
                    candidates.append(ConflictCandidate(
                        memory_ids=(memory.id, target_id),
                        detection_method=DetectionMethod.SUPERSESSION_CHAIN,
                        raw_score=self._config.orphan_score * 0.8,
                        evidence={
                            "issue_type": "incomplete",
                            "description": f"{memory.id} supersedes {target_id}, but {memory.id} is deprecated while {target_id} remains active",
                            "deprecated_superseding": memory.id,
                            "still_active_target": target_id,
                        },
                    ))
        
        return candidates

    def get_stats(self) -> dict:
        """Get analyzer statistics."""
        return {
            "orphan_score": self._config.orphan_score,
            "contested_score": self._config.contested_score,
            "circular_score": self._config.circular_score,
            "max_chain_depth": self._config.max_chain_depth,
            "max_candidates": self._config.max_candidates,
        }
