"""DMM custom exception hierarchy."""

from pathlib import Path
from typing import Any


class DMMError(Exception):
    """Base exception for all DMM errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            detail_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({detail_str})"
        return self.message


class ConfigurationError(DMMError):
    """Raised when configuration is invalid or missing."""

    pass


class MemoryFileError(DMMError):
    """Base exception for memory file operations."""

    def __init__(
        self, message: str, path: Path | None = None, details: dict[str, Any] | None = None
    ) -> None:
        details = details or {}
        if path:
            details["path"] = str(path)
        super().__init__(message, details)
        self.path = path


class ParseError(MemoryFileError):
    """Raised when a memory file cannot be parsed."""

    def __init__(
        self,
        message: str,
        path: Path | None = None,
        line: int | None = None,
        error_type: str = "parse",
        details: dict[str, Any] | None = None,
    ) -> None:
        details = details or {}
        if line is not None:
            details["line"] = line
        details["error_type"] = error_type
        super().__init__(message, path, details)
        self.line = line
        self.error_type = error_type


class SchemaValidationError(MemoryFileError):
    """Raised when frontmatter schema validation fails."""

    def __init__(
        self,
        message: str,
        path: Path | None = None,
        missing_fields: list[str] | None = None,
        invalid_fields: dict[str, str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        details = details or {}
        if missing_fields:
            details["missing_fields"] = missing_fields
        if invalid_fields:
            details["invalid_fields"] = invalid_fields
        super().__init__(message, path, details)
        self.missing_fields = missing_fields or []
        self.invalid_fields = invalid_fields or {}


class TokenCountError(MemoryFileError):
    """Raised when token count is outside valid range."""

    def __init__(
        self,
        message: str,
        path: Path | None = None,
        token_count: int | None = None,
        min_tokens: int | None = None,
        max_tokens: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        details = details or {}
        if token_count is not None:
            details["token_count"] = token_count
        if min_tokens is not None:
            details["min_tokens"] = min_tokens
        if max_tokens is not None:
            details["max_tokens"] = max_tokens
        super().__init__(message, path, details)
        self.token_count = token_count
        self.min_tokens = min_tokens
        self.max_tokens = max_tokens


class IndexError(DMMError):
    """Base exception for indexing operations."""

    pass


class EmbeddingError(IndexError):
    """Raised when embedding generation fails."""

    pass


class StoreError(IndexError):
    """Raised when database operations fail."""

    def __init__(
        self,
        message: str,
        operation: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        details = details or {}
        if operation:
            details["operation"] = operation
        super().__init__(message, details)
        self.operation = operation


class RetrievalError(DMMError):
    """Base exception for retrieval operations."""

    pass


class BaselineError(RetrievalError):
    """Raised when baseline pack operations fail."""

    def __init__(
        self,
        message: str,
        total_tokens: int | None = None,
        budget: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        details = details or {}
        if total_tokens is not None:
            details["total_tokens"] = total_tokens
        if budget is not None:
            details["budget"] = budget
        super().__init__(message, details)
        self.total_tokens = total_tokens
        self.budget = budget


class BudgetExceededError(RetrievalError):
    """Raised when token budget is exceeded."""

    def __init__(
        self,
        message: str,
        requested: int | None = None,
        available: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        details = details or {}
        if requested is not None:
            details["requested"] = requested
        if available is not None:
            details["available"] = available
        super().__init__(message, details)
        self.requested = requested
        self.available = available


class DaemonError(DMMError):
    """Base exception for daemon operations."""

    pass


class DaemonNotRunningError(DaemonError):
    """Raised when daemon is not running but should be."""

    pass


class DaemonAlreadyRunningError(DaemonError):
    """Raised when attempting to start daemon that is already running."""

    def __init__(
        self,
        message: str,
        pid: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        details = details or {}
        if pid is not None:
            details["pid"] = pid
        super().__init__(message, details)
        self.pid = pid


class DaemonStartError(DaemonError):
    """Raised when daemon fails to start."""

    pass


class DaemonStopError(DaemonError):
    """Raised when daemon fails to stop gracefully."""

    pass


class QueryError(DMMError):
    """Raised when a query operation fails."""

    pass


class WatcherError(DMMError):
    """Raised when file watcher encounters an error."""

    pass
