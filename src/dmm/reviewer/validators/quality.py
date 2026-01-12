"""Quality checker for memory content."""

import re
from typing import Any

import frontmatter
import tiktoken

from dmm.core.constants import (
    MAX_MEMORY_TOKENS,
    MAX_MEMORY_TOKENS_HARD,
    MIN_MEMORY_TOKENS,
    QUALITY_MAX_TITLE_LENGTH,
    QUALITY_MIN_BODY_LENGTH,
    QUALITY_MAX_TAGS,
    QUALITY_MIN_TAGS,
)
from dmm.models.proposal import ValidationIssue


class QualityChecker:
    """Checks content quality for memory files."""

    MULTIPLE_CONCEPT_INDICATORS = [
        r"^#{1,2}\s+.+$",
    ]

    SECTION_HEADERS = re.compile(r"^##\s+.+$", re.MULTILINE)

    def __init__(
        self,
        min_tokens: int = MIN_MEMORY_TOKENS,
        max_tokens: int = MAX_MEMORY_TOKENS,
        max_tokens_hard: int = MAX_MEMORY_TOKENS_HARD,
    ) -> None:
        """Initialize the quality checker.
        
        Args:
            min_tokens: Minimum recommended token count.
            max_tokens: Maximum recommended token count.
            max_tokens_hard: Hard maximum token count.
        """
        self._min_tokens = min_tokens
        self._max_tokens = max_tokens
        self._max_tokens_hard = max_tokens_hard
        self._encoding = tiktoken.get_encoding("cl100k_base")

    def check(self, content: str) -> list[ValidationIssue]:
        """Check content quality.
        
        Args:
            content: Full markdown content including frontmatter.
            
        Returns:
            List of validation issues found.
        """
        issues: list[ValidationIssue] = []

        try:
            post = frontmatter.loads(content)
        except Exception:
            issues.append(ValidationIssue(
                code="parse_error",
                message="Cannot parse content for quality check",
                severity="error",
                field="content",
            ))
            return issues

        body = post.content
        metadata = post.metadata

        issues.extend(self._check_token_count(body))

        issues.extend(self._check_single_concept(body))

        issues.extend(self._check_title_quality(body))

        issues.extend(self._check_body_quality(body))

        issues.extend(self._check_tag_quality(metadata))

        issues.extend(self._check_coherence(body, metadata))

        return issues

    def _check_token_count(self, body: str) -> list[ValidationIssue]:
        """Check token count is within limits.
        
        Args:
            body: The markdown body.
            
        Returns:
            List of validation issues.
        """
        issues: list[ValidationIssue] = []
        
        token_count = len(self._encoding.encode(body))

        if token_count > self._max_tokens_hard:
            issues.append(ValidationIssue(
                code="token_count_hard_limit",
                message=f"Token count {token_count} exceeds hard limit {self._max_tokens_hard}",
                severity="error",
                field="body",
                suggestion="Split this memory into multiple smaller memories",
            ))
        elif token_count > self._max_tokens:
            issues.append(ValidationIssue(
                code="token_count_high",
                message=f"Token count {token_count} exceeds recommended maximum {self._max_tokens}",
                severity="warning",
                field="body",
                suggestion="Consider splitting into multiple memories for better retrieval",
            ))
        elif token_count < self._min_tokens:
            issues.append(ValidationIssue(
                code="token_count_low",
                message=f"Token count {token_count} below recommended minimum {self._min_tokens}",
                severity="warning",
                field="body",
                suggestion="Consider adding more context or rationale",
            ))

        return issues

    def _check_single_concept(self, body: str) -> list[ValidationIssue]:
        """Check that the memory focuses on a single concept.
        
        Args:
            body: The markdown body.
            
        Returns:
            List of validation issues.
        """
        issues: list[ValidationIssue] = []

        h1_matches = re.findall(r"^#\s+.+$", body, re.MULTILINE)
        if len(h1_matches) > 1:
            issues.append(ValidationIssue(
                code="multiple_concepts",
                message=f"Found {len(h1_matches)} H1 headings - memory should have single main topic",
                severity="error",
                field="body",
                suggestion="Split into separate memories, one per main concept",
            ))

        h2_matches = self.SECTION_HEADERS.findall(body)
        if len(h2_matches) > 5:
            issues.append(ValidationIssue(
                code="too_many_sections",
                message=f"Found {len(h2_matches)} sections - memory may be too broad",
                severity="warning",
                field="body",
                suggestion="Consider focusing on fewer aspects or splitting into multiple memories",
            ))

        return issues

    def _check_title_quality(self, body: str) -> list[ValidationIssue]:
        """Check title quality.
        
        Args:
            body: The markdown body.
            
        Returns:
            List of validation issues.
        """
        issues: list[ValidationIssue] = []

        title_match = re.search(r"^#\s+(.+?)(?:\s*#*)?$", body, re.MULTILINE)
        
        if not title_match:
            issues.append(ValidationIssue(
                code="missing_title",
                message="No H1 title found",
                severity="warning",
                field="body",
                suggestion="Add a descriptive title using # Heading syntax",
            ))
            return issues

        title = title_match.group(1).strip()

        if len(title) > QUALITY_MAX_TITLE_LENGTH:
            issues.append(ValidationIssue(
                code="title_too_long",
                message=f"Title length {len(title)} exceeds maximum {QUALITY_MAX_TITLE_LENGTH}",
                severity="warning",
                field="body",
                suggestion="Use a shorter, more concise title",
            ))

        if len(title) < 5:
            issues.append(ValidationIssue(
                code="title_too_short",
                message="Title is too short to be descriptive",
                severity="warning",
                field="body",
                suggestion="Use a more descriptive title",
            ))

        vague_titles = ["note", "notes", "info", "information", "stuff", "things", "misc"]
        if title.lower() in vague_titles:
            issues.append(ValidationIssue(
                code="vague_title",
                message=f"Title '{title}' is too vague",
                severity="warning",
                field="body",
                suggestion="Use a specific, descriptive title",
            ))

        return issues

    def _check_body_quality(self, body: str) -> list[ValidationIssue]:
        """Check body content quality.
        
        Args:
            body: The markdown body.
            
        Returns:
            List of validation issues.
        """
        issues: list[ValidationIssue] = []

        body_without_title = re.sub(r"^#\s+.+$", "", body, count=1, flags=re.MULTILINE)
        body_text = body_without_title.strip()

        if len(body_text) < QUALITY_MIN_BODY_LENGTH:
            issues.append(ValidationIssue(
                code="body_too_short",
                message=f"Body content is too short ({len(body_text)} chars)",
                severity="warning",
                field="body",
                suggestion="Add more context, rationale, or details",
            ))

        rationale_patterns = [
            r"##\s*rationale",
            r"##\s*why",
            r"##\s*reason",
            r"##\s*background",
            r"##\s*context",
            r"because\s",
            r"this\s+(is\s+)?(because|due\s+to|since)",
            r"the\s+reason\s+(is|for)",
        ]
        
        has_rationale = any(
            re.search(pattern, body, re.IGNORECASE)
            for pattern in rationale_patterns
        )
        
        if not has_rationale:
            issues.append(ValidationIssue(
                code="missing_rationale",
                message="No rationale or reasoning found",
                severity="info",
                field="body",
                suggestion="Consider adding a Rationale section explaining why",
            ))

        return issues

    def _check_tag_quality(self, metadata: dict[str, Any]) -> list[ValidationIssue]:
        """Check tag quality.
        
        Args:
            metadata: The frontmatter metadata.
            
        Returns:
            List of validation issues.
        """
        issues: list[ValidationIssue] = []

        tags = metadata.get("tags", [])
        if not isinstance(tags, list):
            return issues

        if len(tags) < QUALITY_MIN_TAGS:
            issues.append(ValidationIssue(
                code="too_few_tags",
                message=f"Only {len(tags)} tag(s) - minimum recommended is {QUALITY_MIN_TAGS}",
                severity="warning",
                field="tags",
                suggestion="Add more relevant tags for better retrieval",
            ))

        if len(tags) > QUALITY_MAX_TAGS:
            issues.append(ValidationIssue(
                code="too_many_tags",
                message=f"Found {len(tags)} tags - maximum recommended is {QUALITY_MAX_TAGS}",
                severity="warning",
                field="tags",
                suggestion="Focus on the most relevant tags",
            ))

        vague_tags = {"misc", "other", "general", "stuff", "info", "note"}
        for tag in tags:
            if isinstance(tag, str) and tag.lower() in vague_tags:
                issues.append(ValidationIssue(
                    code="vague_tag",
                    message=f"Tag '{tag}' is too vague",
                    severity="info",
                    field="tags",
                    suggestion="Use more specific, descriptive tags",
                ))

        if len(tags) != len(set(tags)):
            issues.append(ValidationIssue(
                code="duplicate_tags",
                message="Duplicate tags found",
                severity="warning",
                field="tags",
                suggestion="Remove duplicate tags",
            ))

        return issues

    def _check_coherence(
        self,
        body: str,
        metadata: dict[str, Any],
    ) -> list[ValidationIssue]:
        """Check coherence between title, tags, and content.
        
        Args:
            body: The markdown body.
            metadata: The frontmatter metadata.
            
        Returns:
            List of validation issues.
        """
        issues: list[ValidationIssue] = []

        title_match = re.search(r"^#\s+(.+?)(?:\s*#*)?$", body, re.MULTILINE)
        if not title_match:
            return issues

        title = title_match.group(1).strip().lower()
        title_words = set(re.findall(r"\b[a-z]{3,}\b", title))

        tags = metadata.get("tags", [])
        if isinstance(tags, list):
            tag_words = set()
            for tag in tags:
                if isinstance(tag, str):
                    tag_words.update(re.findall(r"\b[a-z]{3,}\b", tag.lower()))

            common_words = {"the", "and", "for", "with", "this", "that", "from", "have", "are"}
            title_words = title_words - common_words
            tag_words = tag_words - common_words

            if title_words and tag_words:
                overlap = title_words & tag_words
                if not overlap and len(title_words) > 2 and len(tag_words) > 2:
                    issues.append(ValidationIssue(
                        code="low_coherence",
                        message="Title and tags appear unrelated",
                        severity="info",
                        field="tags",
                        suggestion="Ensure tags reflect the main topic in the title",
                    ))

        return issues

    def count_tokens(self, text: str) -> int:
        """Count tokens in text.
        
        Args:
            text: The text to count.
            
        Returns:
            Token count.
        """
        return len(self._encoding.encode(text))
