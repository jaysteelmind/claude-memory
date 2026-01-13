"""Conflict checker for reviewer agent.

Checks if a proposed memory would conflict with existing memories.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from dmm.models.proposal import ValidationIssue

if TYPE_CHECKING:
    from dmm.conflicts.store import ConflictStore
    from dmm.indexer.embedder import MemoryEmbedder
    from dmm.indexer.store import MemoryStore


logger = logging.getLogger(__name__)


@dataclass
class ConflictMatch:
    """A potential conflict with an existing memory."""
    
    memory_id: str
    memory_path: str
    memory_title: str
    detection_method: str
    score: float
    reason: str


class ConflictChecker:
    """Checks proposals for potential conflicts with existing memories.
    
    This checker is used during the review process to warn about
    potential conflicts before a memory is committed.
    """

    def __init__(
        self,
        memory_store: "MemoryStore",
        embedder: "MemoryEmbedder",
        conflict_store: "ConflictStore | None" = None,
        similarity_threshold: float = 0.80,
        tag_overlap_threshold: int = 2,
    ) -> None:
        """Initialize the conflict checker.
        
        Args:
            memory_store: The memory store.
            embedder: The memory embedder.
            conflict_store: Optional conflict store for existing conflicts.
            similarity_threshold: Threshold for semantic similarity warnings.
            tag_overlap_threshold: Minimum shared tags for tag overlap warnings.
        """
        self._memory_store = memory_store
        self._embedder = embedder
        self._conflict_store = conflict_store
        self._similarity_threshold = similarity_threshold
        self._tag_overlap_threshold = tag_overlap_threshold
        
        # Contradiction patterns (simplified set for review)
        self._contradiction_pairs = [
            ("always", "never"),
            ("must", "must not"),
            ("use", "avoid"),
            ("enable", "disable"),
            ("required", "forbidden"),
            ("sync", "async"),
            ("tabs", "spaces"),
        ]

    def check(
        self,
        content: str,
        target_path: str,
        tags: list[str] | None = None,
        exclude_id: str | None = None,
    ) -> tuple[list[ValidationIssue], list[ConflictMatch]]:
        """Check if proposed content would conflict with existing memories.
        
        Args:
            content: The proposed memory content.
            target_path: The target path for the memory.
            tags: Optional list of tags from the content.
            exclude_id: Memory ID to exclude (for updates).
            
        Returns:
            Tuple of (validation issues, conflict matches).
        """
        issues: list[ValidationIssue] = []
        matches: list[ConflictMatch] = []
        
        try:
            # Extract tags from content if not provided
            if tags is None:
                tags = self._extract_tags(content)
            
            # Get all active memories
            all_memories = self._memory_store.get_all_memories()
            active_memories = [
                m for m in all_memories 
                if m.status.value == "active" and m.id != exclude_id
            ]
            
            if not active_memories:
                return issues, matches
            
            # Check for tag overlap conflicts
            tag_matches = self._check_tag_overlap(content, tags, active_memories)
            matches.extend(tag_matches)
            
            # Check for semantic similarity conflicts
            semantic_matches = self._check_semantic_similarity(content, active_memories)
            matches.extend(semantic_matches)
            
            # Deduplicate matches by memory_id
            seen_ids = set()
            unique_matches = []
            for match in matches:
                if match.memory_id not in seen_ids:
                    seen_ids.add(match.memory_id)
                    unique_matches.append(match)
            matches = unique_matches
            
            # Create validation issues for high-confidence matches
            for match in matches:
                if match.score >= 0.7:
                    issues.append(ValidationIssue(
                        field="content",
                        message=f"Potential conflict with '{match.memory_title}' ({match.memory_path}): {match.reason}",
                        severity="warning",
                        suggestion=f"Review existing memory {match.memory_id} before proceeding",
                    ))
            
            if len(matches) > 0:
                logger.info(f"Found {len(matches)} potential conflicts for {target_path}")
            
        except Exception as e:
            logger.warning(f"Conflict check failed: {e}")
        
        return issues, matches

    def _extract_tags(self, content: str) -> list[str]:
        """Extract tags from frontmatter content."""
        tags = []
        
        if "tags:" in content:
            try:
                # Simple extraction - look for tags: [tag1, tag2]
                import re
                match = re.search(r'tags:\s*\[(.*?)\]', content)
                if match:
                    tags_str = match.group(1)
                    tags = [t.strip().strip('"\'') for t in tags_str.split(',')]
            except Exception:
                pass
        
        return tags

    def _check_tag_overlap(
        self,
        content: str,
        tags: list[str],
        memories: list,
    ) -> list[ConflictMatch]:
        """Check for conflicts via tag overlap."""
        matches = []
        content_lower = content.lower()
        
        for memory in memories:
            shared_tags = set(tags) & set(memory.tags)
            
            if len(shared_tags) < self._tag_overlap_threshold:
                continue
            
            # Check for contradiction patterns
            memory_text = f"{memory.title} {memory.body}".lower()
            contradictions = []
            
            for pos, neg in self._contradiction_pairs:
                if (pos in content_lower and neg in memory_text) or \
                   (neg in content_lower and pos in memory_text):
                    contradictions.append(f"{pos}/{neg}")
            
            if contradictions:
                score = min(0.5 + len(contradictions) * 0.15 + len(shared_tags) * 0.05, 1.0)
                matches.append(ConflictMatch(
                    memory_id=memory.id,
                    memory_path=memory.path,
                    memory_title=memory.title,
                    detection_method="tag_overlap",
                    score=score,
                    reason=f"Shared tags ({', '.join(shared_tags)}) with contradictory language ({', '.join(contradictions[:3])})",
                ))
        
        return matches

    def _check_semantic_similarity(
        self,
        content: str,
        memories: list,
    ) -> list[ConflictMatch]:
        """Check for conflicts via semantic similarity."""
        matches = []
        
        try:
            import numpy as np
            
            # Embed the proposed content
            proposal_embedding = self._embedder.embed_text(content)
            
            for memory in memories[:100]:  # Limit for performance
                if not memory.composite_embedding:
                    continue
                
                # Compute similarity
                memory_embedding = np.array(memory.composite_embedding)
                proposal_arr = np.array(proposal_embedding)
                
                norm_p = np.linalg.norm(proposal_arr)
                norm_m = np.linalg.norm(memory_embedding)
                
                if norm_p == 0 or norm_m == 0:
                    continue
                
                similarity = float(np.dot(proposal_arr, memory_embedding) / (norm_p * norm_m))
                
                if similarity >= self._similarity_threshold:
                    # Check for divergence (contradictory language despite similarity)
                    has_divergence = self._check_divergence(content, memory.body)
                    
                    if has_divergence:
                        matches.append(ConflictMatch(
                            memory_id=memory.id,
                            memory_path=memory.path,
                            memory_title=memory.title,
                            detection_method="semantic_similarity",
                            score=similarity,
                            reason=f"High semantic similarity ({similarity:.2f}) with potentially contradictory content",
                        ))
                        
        except Exception as e:
            logger.warning(f"Semantic similarity check failed: {e}")
        
        return matches

    def _check_divergence(self, content1: str, content2: str) -> bool:
        """Check if two similar texts have divergent conclusions."""
        content1_lower = content1.lower()
        content2_lower = content2.lower()
        
        divergence_keywords = ["not", "never", "avoid", "don't", "shouldn't", "instead", "rather", "but", "however"]
        
        # Count divergence keywords in each
        count1 = sum(1 for kw in divergence_keywords if kw in content1_lower)
        count2 = sum(1 for kw in divergence_keywords if kw in content2_lower)
        
        # Asymmetric divergence suggests contradiction
        if max(count1, count2) > 0:
            asymmetry = abs(count1 - count2) / (max(count1, count2) + 1)
            return asymmetry > 0.3
        
        return False

    def check_existing_conflicts(
        self,
        memory_id: str,
    ) -> list[ValidationIssue]:
        """Check if a memory has existing unresolved conflicts.
        
        Args:
            memory_id: The memory ID to check.
            
        Returns:
            List of validation issues for existing conflicts.
        """
        issues = []
        
        if not self._conflict_store:
            return issues
        
        try:
            conflicts = self._conflict_store.get_by_memory(memory_id)
            unresolved = [c for c in conflicts if c.status.value == "unresolved"]
            
            for conflict in unresolved:
                other_memory = None
                for mem in conflict.memories:
                    if mem.memory_id != memory_id:
                        other_memory = mem
                        break
                
                if other_memory:
                    issues.append(ValidationIssue(
                        field="conflicts",
                        message=f"Existing unresolved conflict with '{other_memory.title}' ({other_memory.path})",
                        severity="warning",
                        suggestion=f"Resolve conflict {conflict.conflict_id} before updating",
                    ))
                    
        except Exception as e:
            logger.warning(f"Failed to check existing conflicts: {e}")
        
        return issues
