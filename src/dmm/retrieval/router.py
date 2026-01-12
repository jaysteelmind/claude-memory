"""Two-stage retrieval router for memory search."""

from dataclasses import dataclass
from datetime import datetime

from dmm.core.constants import (
    CONFIDENCE_SCORES,
    CONFIDENCE_WEIGHT,
    DEFAULT_DIVERSITY_THRESHOLD,
    DEFAULT_MAX_CANDIDATES,
    DEFAULT_TOP_K_DIRECTORIES,
    PRIORITY_WEIGHT,
    SIMILARITY_WEIGHT,
    Confidence,
)
from dmm.indexer.embedder import MemoryEmbedder
from dmm.indexer.store import MemoryStore
from dmm.models.memory import IndexedMemory
from dmm.models.pack import MemoryPackEntry
from dmm.models.query import RetrievalResult, SearchFilters


@dataclass
class RetrievalConfig:
    """Configuration for retrieval router."""

    top_k_directories: int = DEFAULT_TOP_K_DIRECTORIES
    max_candidates: int = DEFAULT_MAX_CANDIDATES
    diversity_threshold: float = DEFAULT_DIVERSITY_THRESHOLD


class RetrievalRouter:
    """Two-stage retrieval router for memory search."""

    def __init__(
        self,
        store: MemoryStore,
        embedder: MemoryEmbedder,
        config: RetrievalConfig | None = None,
    ) -> None:
        """
        Initialize the retrieval router.

        Args:
            store: Memory store instance
            embedder: Embedder for query embedding
            config: Retrieval configuration
        """
        self._store = store
        self._embedder = embedder
        self._config = config or RetrievalConfig()

    def retrieve(
        self,
        query: str,
        budget: int,
        filters: SearchFilters | None = None,
    ) -> RetrievalResult:
        """
        Execute two-stage retrieval.

        1. Embed query
        2. Find top-K directories
        3. Search within directories
        4. Rank and select within budget

        Args:
            query: Search query string
            budget: Token budget for retrieved memories
            filters: Optional search filters

        Returns:
            RetrievalResult with selected memories
        """
        filters = filters or SearchFilters()

        # Stage 1: Embed query and find relevant directories
        query_embedding = self._embedder.embed_query(query)

        directory_results = self._store.search_by_directory(
            query_embedding=query_embedding,
            limit=self._config.top_k_directories,
        )

        directories_searched = [d for d, _ in directory_results]

        # If no directories found, search all non-baseline
        if not directories_searched:
            directories_searched = None  # type: ignore

        # Stage 2: Search within directories
        content_results = self._store.search_by_content(
            query_embedding=query_embedding,
            directories=directories_searched,
            filters=filters,
            limit=self._config.max_candidates,
        )

        candidates_considered = len(content_results)

        # Compute final ranking scores
        ranked_candidates = self._rank_candidates(content_results)

        # Apply diversity filter
        diverse_candidates = self._apply_diversity_filter(ranked_candidates)

        # Select within budget
        entries, excluded = self._select_within_budget(diverse_candidates, budget)

        return RetrievalResult(
            entries=entries,
            total_tokens=sum(e.token_count for e in entries),
            directories_searched=directories_searched or [],
            candidates_considered=candidates_considered,
            excluded_for_budget=excluded,
        )

    def _rank_candidates(
        self,
        candidates: list[tuple[IndexedMemory, float]],
    ) -> list[tuple[IndexedMemory, float, float]]:
        """
        Compute final ranking scores for candidates.

        Score = (similarity * 0.6) + (priority * 0.25) + (confidence_score * 0.15)

        Returns:
            List of (memory, similarity, final_score) tuples, sorted by final_score
        """
        ranked: list[tuple[IndexedMemory, float, float]] = []

        for memory, similarity in candidates:
            # Get confidence score
            try:
                confidence = Confidence(memory.confidence)
                confidence_score = CONFIDENCE_SCORES.get(confidence, 0.5)
            except ValueError:
                confidence_score = 0.5

            # Compute final score
            final_score = (
                similarity * SIMILARITY_WEIGHT
                + memory.priority * PRIORITY_WEIGHT
                + confidence_score * CONFIDENCE_WEIGHT
            )

            ranked.append((memory, similarity, final_score))

        # Sort by final score descending
        ranked.sort(key=lambda x: x[2], reverse=True)

        return ranked

    def _apply_diversity_filter(
        self,
        candidates: list[tuple[IndexedMemory, float, float]],
    ) -> list[tuple[IndexedMemory, float, float]]:
        """
        Filter out near-duplicate candidates based on similarity threshold.

        Keeps the highest-scoring candidate when two memories are too similar.
        """
        if len(candidates) <= 1:
            return candidates

        filtered: list[tuple[IndexedMemory, float, float]] = []
        seen_embeddings: list[list[float]] = []

        for memory, similarity, score in candidates:
            # Check similarity against already selected memories
            is_duplicate = False
            for seen_embedding in seen_embeddings:
                embed_similarity = self._embedder.compute_similarity(
                    memory.composite_embedding,
                    seen_embedding,
                )
                if embed_similarity >= self._config.diversity_threshold:
                    is_duplicate = True
                    break

            if not is_duplicate:
                filtered.append((memory, similarity, score))
                seen_embeddings.append(memory.composite_embedding)

        return filtered

    def _select_within_budget(
        self,
        candidates: list[tuple[IndexedMemory, float, float]],
        budget: int,
    ) -> tuple[list[MemoryPackEntry], list[str]]:
        """
        Select candidates that fit within token budget.

        Args:
            candidates: Ranked candidates
            budget: Token budget

        Returns:
            Tuple of (selected entries, excluded paths)
        """
        entries: list[MemoryPackEntry] = []
        excluded: list[str] = []
        tokens_used = 0

        for memory, similarity, score in candidates:
            if tokens_used + memory.token_count <= budget:
                entry = MemoryPackEntry(
                    path=memory.path,
                    title=memory.title,
                    content=memory.body,
                    token_count=memory.token_count,
                    relevance_score=round(similarity, 3),
                    source="retrieved",
                )
                entries.append(entry)
                tokens_used += memory.token_count
            else:
                excluded.append(memory.path)

        return entries, excluded

    def get_stats(self) -> dict[str, int | float]:
        """Get router configuration stats."""
        return {
            "top_k_directories": self._config.top_k_directories,
            "max_candidates": self._config.max_candidates,
            "diversity_threshold": self._config.diversity_threshold,
            "similarity_weight": SIMILARITY_WEIGHT,
            "priority_weight": PRIORITY_WEIGHT,
            "confidence_weight": CONFIDENCE_WEIGHT,
        }
