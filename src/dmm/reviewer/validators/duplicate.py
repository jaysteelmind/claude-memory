"""Duplicate detector for memory content."""

import hashlib
from pathlib import Path

import frontmatter

from dmm.core.constants import (
    DUPLICATE_EXACT_THRESHOLD,
    DUPLICATE_SEMANTIC_THRESHOLD,
    DUPLICATE_WARNING_THRESHOLD,
)
from dmm.indexer.embedder import MemoryEmbedder
from dmm.indexer.store import MemoryStore
from dmm.models.proposal import DuplicateMatch, ValidationIssue


class DuplicateDetector:
    """Detects duplicate memories using content hashing and embedding similarity."""

    def __init__(
        self,
        store: MemoryStore,
        embedder: MemoryEmbedder,
        exact_threshold: float = DUPLICATE_EXACT_THRESHOLD,
        semantic_threshold: float = DUPLICATE_SEMANTIC_THRESHOLD,
        warning_threshold: float = DUPLICATE_WARNING_THRESHOLD,
    ) -> None:
        """Initialize the duplicate detector.
        
        Args:
            store: The memory store for querying existing memories.
            embedder: The embedder for generating comparison embeddings.
            exact_threshold: Similarity threshold for exact duplicates (default 0.99).
            semantic_threshold: Similarity threshold for semantic duplicates (default 0.85).
            warning_threshold: Similarity threshold for warnings (default 0.70).
        """
        self._store = store
        self._embedder = embedder
        self._exact_threshold = exact_threshold
        self._semantic_threshold = semantic_threshold
        self._warning_threshold = warning_threshold

    def check(
        self,
        content: str,
        target_path: str,
        exclude_id: str | None = None,
    ) -> tuple[list[ValidationIssue], list[DuplicateMatch]]:
        """Check for duplicate memories.
        
        Args:
            content: The proposed memory content.
            target_path: The target path for the memory.
            exclude_id: Memory ID to exclude from comparison (for updates).
            
        Returns:
            Tuple of (validation issues, duplicate matches).
        """
        issues: list[ValidationIssue] = []
        matches: list[DuplicateMatch] = []

        try:
            post = frontmatter.loads(content)
            body = post.content
            metadata = post.metadata
        except Exception:
            issues.append(ValidationIssue(
                code="parse_error",
                message="Cannot parse content for duplicate check",
                severity="error",
                field="content",
            ))
            return issues, matches

        exact_match = self._check_exact_duplicate(body, exclude_id)
        if exact_match:
            matches.append(exact_match)
            issues.append(ValidationIssue(
                code="duplicate_exact",
                message=f"Exact duplicate found: {exact_match.memory_path}",
                severity="error",
                field="content",
                suggestion="This memory already exists - consider updating instead",
            ))
            return issues, matches

        semantic_matches = self._check_semantic_duplicates(
            body,
            metadata,
            target_path,
            exclude_id,
        )

        for match in semantic_matches:
            matches.append(match)
            
            if match.similarity >= self._semantic_threshold:
                issues.append(ValidationIssue(
                    code="duplicate_semantic",
                    message=f"Semantic duplicate found ({match.similarity:.2%} similar): {match.memory_path}",
                    severity="error",
                    field="content",
                    suggestion="Very similar memory exists - consider updating existing or differentiating",
                ))
            elif match.similarity >= self._warning_threshold:
                issues.append(ValidationIssue(
                    code="similar_memory",
                    message=f"Similar memory found ({match.similarity:.2%} similar): {match.memory_path}",
                    severity="warning",
                    field="content",
                    suggestion="Check if this duplicates existing knowledge",
                ))

        return issues, matches

    def _check_exact_duplicate(
        self,
        body: str,
        exclude_id: str | None,
    ) -> DuplicateMatch | None:
        """Check for exact content duplicates using hash.
        
        Args:
            body: The memory body content.
            exclude_id: Memory ID to exclude.
            
        Returns:
            DuplicateMatch if found, None otherwise.
        """
        content_hash = hashlib.sha256(body.encode()).hexdigest()

        all_memories = self._store.get_all_memories()
        
        for memory in all_memories:
            if exclude_id and memory.id == exclude_id:
                continue

            existing_hash = hashlib.sha256(memory.body.encode()).hexdigest()
            if content_hash == existing_hash:
                return DuplicateMatch(
                    memory_id=memory.id,
                    memory_path=memory.path,
                    similarity=1.0,
                    match_type="exact",
                )

        return None

    def _check_semantic_duplicates(
        self,
        body: str,
        metadata: dict,
        target_path: str,
        exclude_id: str | None,
    ) -> list[DuplicateMatch]:
        """Check for semantic duplicates using embedding similarity.
        
        Args:
            body: The memory body content.
            metadata: The memory metadata.
            target_path: The target path.
            exclude_id: Memory ID to exclude.
            
        Returns:
            List of DuplicateMatch for similar memories.
        """
        matches: list[DuplicateMatch] = []

        title = self._extract_title(body)
        tags = metadata.get("tags", [])
        scope = metadata.get("scope", "project")
        directory = str(Path(target_path).parent)

        composite_text = self._build_composite_text(
            directory=directory,
            title=title,
            tags=tags,
            scope=scope,
            body=body,
        )

        try:
            query_embedding = self._embedder.embed_query(composite_text)
        except Exception:
            return matches

        all_memories = self._store.get_all_memories()

        for memory in all_memories:
            if exclude_id and memory.id == exclude_id:
                continue

            similarity = self._embedder.compute_similarity(
                query_embedding,
                memory.composite_embedding,
            )

            if similarity >= self._warning_threshold:
                match_type = "exact" if similarity >= self._exact_threshold else \
                            "semantic" if similarity >= self._semantic_threshold else \
                            "similar"
                
                matches.append(DuplicateMatch(
                    memory_id=memory.id,
                    memory_path=memory.path,
                    similarity=similarity,
                    match_type=match_type,
                ))

        matches.sort(key=lambda m: m.similarity, reverse=True)
        return matches[:10]

    def find_similar(
        self,
        content: str,
        limit: int = 5,
        min_similarity: float = 0.5,
    ) -> list[DuplicateMatch]:
        """Find similar memories without triggering validation.
        
        Useful for suggesting related memories.
        
        Args:
            content: The content to compare.
            limit: Maximum number of results.
            min_similarity: Minimum similarity threshold.
            
        Returns:
            List of similar memories.
        """
        try:
            post = frontmatter.loads(content)
            body = post.content
            metadata = post.metadata
        except Exception:
            return []

        title = self._extract_title(body)
        tags = metadata.get("tags", [])
        scope = metadata.get("scope", "project")

        composite_text = self._build_composite_text(
            directory="",
            title=title,
            tags=tags,
            scope=scope,
            body=body,
        )

        try:
            query_embedding = self._embedder.embed_query(composite_text)
        except Exception:
            return []

        matches: list[DuplicateMatch] = []
        all_memories = self._store.get_all_memories()

        for memory in all_memories:
            similarity = self._embedder.compute_similarity(
                query_embedding,
                memory.composite_embedding,
            )

            if similarity >= min_similarity:
                matches.append(DuplicateMatch(
                    memory_id=memory.id,
                    memory_path=memory.path,
                    similarity=similarity,
                    match_type="similar",
                ))

        matches.sort(key=lambda m: m.similarity, reverse=True)
        return matches[:limit]

    def check_by_tags(
        self,
        tags: list[str],
        exclude_id: str | None = None,
    ) -> list[DuplicateMatch]:
        """Find memories with overlapping tags.
        
        Args:
            tags: Tags to check for overlap.
            exclude_id: Memory ID to exclude.
            
        Returns:
            List of memories with overlapping tags.
        """
        if not tags:
            return []

        matches: list[DuplicateMatch] = []
        tag_set = set(t.lower() for t in tags)

        all_memories = self._store.get_all_memories()

        for memory in all_memories:
            if exclude_id and memory.id == exclude_id:
                continue

            memory_tags = set(t.lower() for t in memory.tags)
            overlap = tag_set & memory_tags

            if overlap:
                overlap_ratio = len(overlap) / max(len(tag_set), len(memory_tags))
                
                if overlap_ratio >= 0.5:
                    matches.append(DuplicateMatch(
                        memory_id=memory.id,
                        memory_path=memory.path,
                        similarity=overlap_ratio,
                        match_type="tag_overlap",
                    ))

        matches.sort(key=lambda m: m.similarity, reverse=True)
        return matches[:10]

    def _extract_title(self, body: str) -> str:
        """Extract title from body content.
        
        Args:
            body: The markdown body.
            
        Returns:
            The extracted title or empty string.
        """
        import re
        match = re.search(r"^#\s+(.+?)(?:\s*#*)?$", body, re.MULTILINE)
        return match.group(1).strip() if match else ""

    def _build_composite_text(
        self,
        directory: str,
        title: str,
        tags: list,
        scope: str,
        body: str,
    ) -> str:
        """Build composite text for embedding.
        
        Args:
            directory: The directory path.
            title: The memory title.
            tags: List of tags.
            scope: The memory scope.
            body: The memory body.
            
        Returns:
            Composite text string.
        """
        tag_str = ", ".join(str(t) for t in tags) if tags else ""
        parts = [
            f"[DIRECTORY] {directory}",
            f"[TITLE] {title}",
            f"[TAGS] {tag_str}",
            f"[SCOPE] {scope}",
            f"[CONTENT] {body}",
        ]
        return "\n".join(parts)
