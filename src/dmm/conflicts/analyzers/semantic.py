"""Semantic similarity conflict detection analyzer.

This analyzer detects conflicts by finding memories with high embedding
similarity but divergent conclusions or recommendations.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from dmm.core.constants import (
    DIVERGENCE_KEYWORDS,
    SEMANTIC_DIVERGENCE_THRESHOLD,
    SEMANTIC_MAX_PAIRS_TO_CHECK,
    SEMANTIC_SIMILARITY_THRESHOLD,
)
from dmm.models.conflict import ConflictCandidate, DetectionMethod

if TYPE_CHECKING:
    from dmm.indexer.embedder import MemoryEmbedder
    from dmm.indexer.store import MemoryStore
    from dmm.models.memory import IndexedMemory


@dataclass
class SemanticConfig:
    """Configuration for semantic similarity analysis."""
    
    similarity_threshold: float = SEMANTIC_SIMILARITY_THRESHOLD
    divergence_threshold: float = SEMANTIC_DIVERGENCE_THRESHOLD
    max_pairs_to_check: int = SEMANTIC_MAX_PAIRS_TO_CHECK
    max_candidates: int = 100
    ignore_deprecated: bool = True
    ignore_high_similarity_same_scope: bool = True
    high_similarity_threshold: float = 0.95
    divergence_keywords: tuple[str, ...] = field(default_factory=lambda: DIVERGENCE_KEYWORDS)


class SemanticClusteringAnalyzer:
    """Detects conflicts via embedding similarity and divergence.
    
    This analyzer works by:
    1. Computing pairwise embedding similarities
    2. Finding pairs above the similarity threshold
    3. Checking for divergence signals (contradictory language)
    4. Scoring based on similarity * divergence
    
    High similarity + high divergence = likely conflict
    """

    def __init__(
        self,
        store: "MemoryStore",
        embedder: "MemoryEmbedder",
        config: SemanticConfig | None = None,
    ) -> None:
        """Initialize the analyzer.
        
        Args:
            store: The memory store to query.
            embedder: The embedder for computing similarities.
            config: Optional configuration.
        """
        self._store = store
        self._embedder = embedder
        self._config = config or SemanticConfig()

    def analyze(
        self,
        memory_ids: list[str] | None = None,
    ) -> list[ConflictCandidate]:
        """Find conflicts via semantic similarity.
        
        Args:
            memory_ids: Optional list of memory IDs to analyze.
                       If None, analyzes all active memories.
                       
        Returns:
            List of conflict candidates.
        """
        memories = self._get_memories(memory_ids)
        
        if len(memories) < 2:
            return []
        
        similar_pairs = self._find_similar_pairs(memories)
        candidates = self._filter_to_conflicts(memories, similar_pairs)
        
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
        target_embedding = np.array(target_memory.composite_embedding)
        
        for other in other_memories:
            other_embedding = np.array(other.composite_embedding)
            similarity = self._compute_cosine_similarity(target_embedding, other_embedding)
            
            if similarity < self._config.similarity_threshold:
                continue
            
            if (
                self._config.ignore_high_similarity_same_scope
                and similarity > self._config.high_similarity_threshold
                and target_memory.scope == other.scope
            ):
                continue
            
            divergence = self._compute_divergence(target_memory, other)
            
            if divergence >= self._config.divergence_threshold:
                score = similarity * divergence
                divergence_signals = self._get_divergence_signals(target_memory, other)
                
                candidates.append(ConflictCandidate(
                    memory_ids=(target_memory.id, other.id),
                    detection_method=DetectionMethod.SEMANTIC_SIMILARITY,
                    raw_score=score,
                    evidence={
                        "similarity": round(similarity, 4),
                        "divergence": round(divergence, 4),
                        "divergence_signals": divergence_signals,
                        "scope_match": target_memory.scope == other.scope,
                    },
                ))
        
        candidates.sort(key=lambda c: c.raw_score, reverse=True)
        return candidates[:self._config.max_candidates]

    def find_similar(
        self,
        memory_id: str,
        threshold: float | None = None,
        limit: int = 10,
    ) -> list[tuple[str, float]]:
        """Find memories similar to a given one.
        
        Args:
            memory_id: The memory ID to compare against.
            threshold: Similarity threshold (uses config default if None).
            limit: Maximum number of results.
            
        Returns:
            List of (memory_id, similarity) tuples.
        """
        threshold = threshold or self._config.similarity_threshold
        
        target_memory = self._store.get_memory(memory_id)
        if target_memory is None:
            return []
        
        all_memories = self._get_memories(None)
        other_memories = [m for m in all_memories if m.id != memory_id]
        
        if not other_memories:
            return []
        
        target_embedding = np.array(target_memory.composite_embedding)
        similarities = []
        
        for other in other_memories:
            other_embedding = np.array(other.composite_embedding)
            similarity = self._compute_cosine_similarity(target_embedding, other_embedding)
            
            if similarity >= threshold:
                similarities.append((other.id, similarity))
        
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:limit]

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

    def _find_similar_pairs(
        self,
        memories: list["IndexedMemory"],
    ) -> list[tuple[str, str, float]]:
        """Find pairs of memories with high similarity.
        
        Args:
            memories: List of memories to compare.
            
        Returns:
            List of (memory_id_1, memory_id_2, similarity) tuples.
        """
        pairs = []
        n = len(memories)
        pairs_checked = 0
        
        embeddings = {
            m.id: np.array(m.composite_embedding) for m in memories
        }
        
        for i in range(n):
            if pairs_checked >= self._config.max_pairs_to_check:
                break
                
            m1 = memories[i]
            emb1 = embeddings[m1.id]
            
            for j in range(i + 1, n):
                if pairs_checked >= self._config.max_pairs_to_check:
                    break
                
                m2 = memories[j]
                emb2 = embeddings[m2.id]
                
                similarity = self._compute_cosine_similarity(emb1, emb2)
                pairs_checked += 1
                
                if similarity >= self._config.similarity_threshold:
                    pairs.append((m1.id, m2.id, similarity))
        
        return pairs

    def _filter_to_conflicts(
        self,
        memories: list["IndexedMemory"],
        similar_pairs: list[tuple[str, str, float]],
    ) -> list[ConflictCandidate]:
        """Filter similar pairs to those that are likely conflicts.
        
        Args:
            memories: List of all memories.
            similar_pairs: Pairs with high similarity.
            
        Returns:
            List of conflict candidates.
        """
        memory_map = {m.id: m for m in memories}
        candidates = []
        
        for m1_id, m2_id, similarity in similar_pairs:
            m1 = memory_map.get(m1_id)
            m2 = memory_map.get(m2_id)
            
            if m1 is None or m2 is None:
                continue
            
            if (
                self._config.ignore_high_similarity_same_scope
                and similarity > self._config.high_similarity_threshold
                and m1.scope == m2.scope
            ):
                continue
            
            divergence = self._compute_divergence(m1, m2)
            
            if divergence >= self._config.divergence_threshold:
                score = similarity * divergence
                divergence_signals = self._get_divergence_signals(m1, m2)
                
                candidates.append(ConflictCandidate(
                    memory_ids=(m1_id, m2_id),
                    detection_method=DetectionMethod.SEMANTIC_SIMILARITY,
                    raw_score=score,
                    evidence={
                        "similarity": round(similarity, 4),
                        "divergence": round(divergence, 4),
                        "divergence_signals": divergence_signals,
                        "scope_match": m1.scope == m2.scope,
                    },
                ))
        
        return candidates

    def _compute_cosine_similarity(
        self,
        embedding_a: np.ndarray,
        embedding_b: np.ndarray,
    ) -> float:
        """Compute cosine similarity between two embeddings."""
        norm_a = np.linalg.norm(embedding_a)
        norm_b = np.linalg.norm(embedding_b)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return float(np.dot(embedding_a, embedding_b) / (norm_a * norm_b))

    def _compute_divergence(
        self,
        m1: "IndexedMemory",
        m2: "IndexedMemory",
    ) -> float:
        """Compute divergence score between two memories.
        
        High divergence + high similarity = likely conflict.
        
        Args:
            m1: First memory.
            m2: Second memory.
            
        Returns:
            Divergence score between 0.0 and 1.0.
        """
        text1 = f"{m1.title} {m1.body}".lower()
        text2 = f"{m2.title} {m2.body}".lower()
        
        div1 = sum(1 for kw in self._config.divergence_keywords if kw in text1)
        div2 = sum(1 for kw in self._config.divergence_keywords if kw in text2)
        
        if max(div1, div2) == 0:
            asymmetry = 0.0
        else:
            asymmetry = abs(div1 - div2) / (max(div1, div2) + 1)
        
        scope_diff = 0.2 if m1.scope != m2.scope else 0.0
        
        priority_diff = abs(m1.priority - m2.priority)
        priority_boost = priority_diff * 0.1
        
        return min(asymmetry + scope_diff + priority_boost, 1.0)

    def _get_divergence_signals(
        self,
        m1: "IndexedMemory",
        m2: "IndexedMemory",
    ) -> list[str]:
        """Get specific divergence signals between memories.
        
        Args:
            m1: First memory.
            m2: Second memory.
            
        Returns:
            List of divergence signal descriptions.
        """
        signals = []
        
        text1 = f"{m1.title} {m1.body}".lower()
        text2 = f"{m2.title} {m2.body}".lower()
        
        kw1 = [kw for kw in self._config.divergence_keywords if kw in text1]
        kw2 = [kw for kw in self._config.divergence_keywords if kw in text2]
        
        only_in_1 = set(kw1) - set(kw2)
        only_in_2 = set(kw2) - set(kw1)
        
        if only_in_1:
            signals.append(f"Memory 1 contains: {', '.join(sorted(only_in_1))}")
        if only_in_2:
            signals.append(f"Memory 2 contains: {', '.join(sorted(only_in_2))}")
        
        if m1.scope != m2.scope:
            signals.append(f"Different scopes: {m1.scope.value} vs {m2.scope.value}")
        
        if abs(m1.priority - m2.priority) > 0.3:
            signals.append(f"Priority difference: {m1.priority} vs {m2.priority}")
        
        return signals

    def get_stats(self) -> dict:
        """Get analyzer statistics."""
        return {
            "similarity_threshold": self._config.similarity_threshold,
            "divergence_threshold": self._config.divergence_threshold,
            "max_pairs_to_check": self._config.max_pairs_to_check,
            "max_candidates": self._config.max_candidates,
            "divergence_keywords_count": len(self._config.divergence_keywords),
        }
