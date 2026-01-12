"""Memory file parser with frontmatter validation and token counting."""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import frontmatter
import tiktoken

from dmm.core.constants import (
    MAX_MEMORY_TOKENS_HARD,
    OPTIONAL_FRONTMATTER_FIELDS,
    REQUIRED_FRONTMATTER_FIELDS,
    Confidence,
    Scope,
    Status,
)
from dmm.core.exceptions import ParseError, SchemaValidationError
from dmm.models.memory import MemoryFile


@dataclass
class ValidationWarning:
    """Warning from memory file validation."""

    path: Path
    warning_type: str
    message: str
    suggestion: str | None = None

    def __str__(self) -> str:
        msg = f"[{self.warning_type}] {self.path}: {self.message}"
        if self.suggestion:
            msg += f" (suggestion: {self.suggestion})"
        return msg


@dataclass
class ParseResult:
    """Result of parsing a memory file."""

    memory: MemoryFile | None = None
    warnings: list[ValidationWarning] = field(default_factory=list)
    error: ParseError | SchemaValidationError | None = None

    @property
    def success(self) -> bool:
        """Check if parsing succeeded."""
        return self.memory is not None and self.error is None


class TokenCounter:
    """Token counter using tiktoken."""

    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        """Initialize with specified encoding."""
        self._encoding = tiktoken.get_encoding(encoding_name)

    def count(self, text: str) -> int:
        """Count tokens in text."""
        return len(self._encoding.encode(text))

    def count_with_overhead(self, text: str, overhead: int = 10) -> int:
        """Count tokens with formatting overhead."""
        return self.count(text) + overhead


class MemoryParser:
    """Parser for memory markdown files."""

    # Valid enum values for validation
    VALID_SCOPES = {s.value for s in Scope}
    VALID_CONFIDENCES = {c.value for c in Confidence}
    VALID_STATUSES = {s.value for s in Status}

    def __init__(
        self,
        token_counter: TokenCounter | None = None,
        min_tokens: int = 300,
        max_tokens: int = 800,
    ) -> None:
        """Initialize parser with token counter and limits."""
        self._token_counter = token_counter or TokenCounter()
        self._min_tokens = min_tokens
        self._max_tokens = max_tokens

    def parse(self, path: Path) -> ParseResult:
        """
        Parse a memory file.

        Returns ParseResult with either a MemoryFile or an error.
        """
        warnings: list[ValidationWarning] = []

        # Read file
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            return ParseResult(
                error=ParseError(
                    f"Failed to read file: {e}",
                    path=path,
                    error_type="io",
                )
            )

        # Parse frontmatter
        try:
            post = frontmatter.loads(content)
        except Exception as e:
            return ParseResult(
                error=ParseError(
                    f"Failed to parse YAML frontmatter: {e}",
                    path=path,
                    error_type="yaml",
                )
            )

        # Validate schema
        schema_result = self._validate_schema(path, post.metadata)
        if schema_result is not None:
            return ParseResult(error=schema_result)

        # Extract title from first H1
        title = self._extract_title(post.content)
        if title is None:
            warnings.append(
                ValidationWarning(
                    path=path,
                    warning_type="missing_title",
                    message="No H1 heading found in content",
                    suggestion="Add a title using # Heading syntax",
                )
            )
            # Use filename as fallback title
            title = path.stem.replace("_", " ").replace("-", " ").title()

        # Count tokens
        token_count = self._token_counter.count(post.content)

        # Token count warnings
        if token_count < self._min_tokens:
            warnings.append(
                ValidationWarning(
                    path=path,
                    warning_type="low_token_count",
                    message=f"Token count {token_count} below recommended minimum {self._min_tokens}",
                    suggestion="Consider expanding the content with more context",
                )
            )
        elif token_count > self._max_tokens:
            warnings.append(
                ValidationWarning(
                    path=path,
                    warning_type="high_token_count",
                    message=f"Token count {token_count} exceeds recommended maximum {self._max_tokens}",
                    suggestion="Consider splitting into multiple memory files",
                )
            )

        # Hard limit check
        if token_count > MAX_MEMORY_TOKENS_HARD:
            return ParseResult(
                error=ParseError(
                    f"Token count {token_count} exceeds hard limit {MAX_MEMORY_TOKENS_HARD}",
                    path=path,
                    error_type="content",
                ),
                warnings=warnings,
            )

        # Parse metadata
        metadata = post.metadata
        try:
            memory = MemoryFile(
                id=metadata["id"],
                path=self._normalize_path(path),
                title=title,
                body=post.content,
                token_count=token_count,
                tags=self._parse_tags(metadata.get("tags", [])),
                scope=Scope(metadata["scope"]),
                priority=float(metadata["priority"]),
                confidence=Confidence(metadata["confidence"]),
                status=Status(metadata["status"]),
                created=self._parse_datetime(metadata.get("created")),
                last_used=self._parse_datetime(metadata.get("last_used")),
                usage_count=int(metadata.get("usage_count", 0)),
                supersedes=self._parse_list(metadata.get("supersedes", [])),
                related=self._parse_list(metadata.get("related", [])),
                expires=self._parse_datetime(metadata.get("expires")),
            )
        except (ValueError, TypeError, KeyError) as e:
            return ParseResult(
                error=ParseError(
                    f"Failed to construct MemoryFile: {e}",
                    path=path,
                    error_type="content",
                ),
                warnings=warnings,
            )

        # Check optional field warnings
        for opt_field in OPTIONAL_FRONTMATTER_FIELDS:
            if opt_field not in metadata:
                if opt_field == "expires" and memory.scope == Scope.EPHEMERAL:
                    warnings.append(
                        ValidationWarning(
                            path=path,
                            warning_type="missing_optional",
                            message=f"Ephemeral memory missing '{opt_field}' field",
                            suggestion="Add an expiration date for ephemeral memories",
                        )
                    )

        return ParseResult(memory=memory, warnings=warnings)

    def validate(self, memory: MemoryFile) -> list[ValidationWarning]:
        """Validate a parsed memory file and return warnings."""
        warnings: list[ValidationWarning] = []
        path = Path(memory.path)

        # Token count validation
        if memory.token_count < self._min_tokens:
            warnings.append(
                ValidationWarning(
                    path=path,
                    warning_type="low_token_count",
                    message=f"Token count {memory.token_count} below minimum {self._min_tokens}",
                )
            )
        elif memory.token_count > self._max_tokens:
            warnings.append(
                ValidationWarning(
                    path=path,
                    warning_type="high_token_count",
                    message=f"Token count {memory.token_count} exceeds maximum {self._max_tokens}",
                )
            )

        # Priority validation
        if not 0.0 <= memory.priority <= 1.0:
            warnings.append(
                ValidationWarning(
                    path=path,
                    warning_type="invalid_priority",
                    message=f"Priority {memory.priority} outside valid range [0.0, 1.0]",
                )
            )

        # Empty tags warning
        if not memory.tags:
            warnings.append(
                ValidationWarning(
                    path=path,
                    warning_type="empty_tags",
                    message="No tags specified",
                    suggestion="Add relevant tags for better retrieval",
                )
            )

        # Ephemeral without expiry
        if memory.scope == Scope.EPHEMERAL and memory.expires is None:
            warnings.append(
                ValidationWarning(
                    path=path,
                    warning_type="ephemeral_no_expiry",
                    message="Ephemeral memory without expiration date",
                    suggestion="Add an 'expires' field",
                )
            )

        # Deprecated status mismatch
        if memory.confidence == Confidence.DEPRECATED and memory.status != Status.DEPRECATED:
            warnings.append(
                ValidationWarning(
                    path=path,
                    warning_type="status_mismatch",
                    message="Confidence is 'deprecated' but status is not",
                    suggestion="Set status to 'deprecated'",
                )
            )

        return warnings

    def compute_file_hash(self, path: Path) -> str:
        """Compute SHA256 hash of file contents."""
        content = path.read_bytes()
        return hashlib.sha256(content).hexdigest()

    def _validate_schema(
        self, path: Path, metadata: dict[str, Any]
    ) -> SchemaValidationError | None:
        """Validate frontmatter schema. Returns error if invalid."""
        missing_fields: list[str] = []
        invalid_fields: dict[str, str] = {}

        # Check required fields
        for field_name in REQUIRED_FRONTMATTER_FIELDS:
            if field_name not in metadata:
                missing_fields.append(field_name)

        if missing_fields:
            return SchemaValidationError(
                f"Missing required fields: {', '.join(missing_fields)}",
                path=path,
                missing_fields=missing_fields,
            )

        # Validate field values
        # id: must be string
        if not isinstance(metadata.get("id"), str):
            invalid_fields["id"] = "must be a string"

        # tags: must be list
        if not isinstance(metadata.get("tags"), list):
            invalid_fields["tags"] = "must be a list"

        # scope: must be valid enum
        scope = metadata.get("scope")
        if scope not in self.VALID_SCOPES:
            invalid_fields["scope"] = f"must be one of {self.VALID_SCOPES}"

        # priority: must be float 0.0-1.0
        priority = metadata.get("priority")
        try:
            priority_val = float(priority)
            if not 0.0 <= priority_val <= 1.0:
                invalid_fields["priority"] = "must be between 0.0 and 1.0"
        except (TypeError, ValueError):
            invalid_fields["priority"] = "must be a number between 0.0 and 1.0"

        # confidence: must be valid enum
        confidence = metadata.get("confidence")
        if confidence not in self.VALID_CONFIDENCES:
            invalid_fields["confidence"] = f"must be one of {self.VALID_CONFIDENCES}"

        # status: must be valid enum
        status = metadata.get("status")
        if status not in self.VALID_STATUSES:
            invalid_fields["status"] = f"must be one of {self.VALID_STATUSES}"

        if invalid_fields:
            return SchemaValidationError(
                f"Invalid field values: {invalid_fields}",
                path=path,
                invalid_fields=invalid_fields,
            )

        return None

    def _extract_title(self, content: str) -> str | None:
        """Extract title from first H1 heading."""
        # Match # Title at start of line
        match = re.search(r"^#\s+(.+?)(?:\s*#*)?$", content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return None

    def _normalize_path(self, path: Path) -> str:
        """Normalize path to relative string from memory root."""
        # Convert to string and normalize
        path_str = str(path)

        # Find memory/ in path and return everything after
        if "/memory/" in path_str:
            return path_str.split("/memory/", 1)[1]
        if "\\memory\\" in path_str:
            return path_str.split("\\memory\\", 1)[1].replace("\\", "/")

        # Fallback to filename
        return path.name

    def _parse_tags(self, tags: Any) -> list[str]:
        """Parse tags field to list of strings."""
        if isinstance(tags, list):
            return [str(t).strip() for t in tags if t]
        if isinstance(tags, str):
            return [t.strip() for t in tags.split(",") if t.strip()]
        return []

    def _parse_list(self, value: Any) -> list[str]:
        """Parse list field."""
        if isinstance(value, list):
            return [str(v) for v in value]
        return []

    def _parse_datetime(self, value: Any) -> datetime | None:
        """Parse datetime from various formats."""
        from datetime import date as date_type
        
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, date_type):
            # Convert date to datetime
            return datetime.combine(value, datetime.min.time())
        if isinstance(value, str):
            # Try common formats
            for fmt in [
                "%Y-%m-%d",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d %H:%M:%S",
            ]:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
        return None
