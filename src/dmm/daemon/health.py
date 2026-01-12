"""Health check and status functionality for the daemon."""

from datetime import datetime
from typing import Any

from dmm.models.query import HealthResponse, StatusResponse


class HealthChecker:
    """Tracks daemon health and provides status information."""

    def __init__(self, version: str = "1.0.0") -> None:
        """
        Initialize health checker.

        Args:
            version: Daemon version string
        """
        self._version = version
        self._start_time: datetime | None = None
        self._indexed_count = 0
        self._baseline_tokens = 0
        self._last_reindex: datetime | None = None
        self._watcher_active = False
        self._memory_root: str = ""
        self._daemon_pid: int | None = None
        self._healthy = True
        self._error_message: str | None = None

    def mark_started(self, pid: int | None = None) -> None:
        """Mark daemon as started."""
        self._start_time = datetime.now()
        self._daemon_pid = pid
        self._healthy = True

    def mark_stopped(self) -> None:
        """Mark daemon as stopped."""
        self._start_time = None
        self._daemon_pid = None

    def update_stats(
        self,
        indexed_count: int | None = None,
        baseline_tokens: int | None = None,
        last_reindex: datetime | None = None,
        watcher_active: bool | None = None,
        memory_root: str | None = None,
    ) -> None:
        """Update health statistics."""
        if indexed_count is not None:
            self._indexed_count = indexed_count
        if baseline_tokens is not None:
            self._baseline_tokens = baseline_tokens
        if last_reindex is not None:
            self._last_reindex = last_reindex
        if watcher_active is not None:
            self._watcher_active = watcher_active
        if memory_root is not None:
            self._memory_root = memory_root

    def mark_unhealthy(self, error: str) -> None:
        """Mark daemon as unhealthy with error message."""
        self._healthy = False
        self._error_message = error

    def mark_healthy(self) -> None:
        """Mark daemon as healthy."""
        self._healthy = True
        self._error_message = None

    @property
    def uptime_seconds(self) -> float:
        """Get daemon uptime in seconds."""
        if self._start_time is None:
            return 0.0
        delta = datetime.now() - self._start_time
        return delta.total_seconds()

    @property
    def is_running(self) -> bool:
        """Check if daemon is running."""
        return self._start_time is not None

    @property
    def is_healthy(self) -> bool:
        """Check if daemon is healthy."""
        return self._healthy and self.is_running

    def get_health_response(self) -> HealthResponse:
        """Get health check response."""
        return HealthResponse(
            status="healthy" if self.is_healthy else "unhealthy",
            uptime_seconds=self.uptime_seconds,
            indexed_count=self._indexed_count,
            baseline_tokens=self._baseline_tokens,
            last_reindex=self._last_reindex,
            watcher_active=self._watcher_active,
            version=self._version,
        )

    def get_status_response(self) -> StatusResponse:
        """Get detailed status response."""
        return StatusResponse(
            daemon_running=self.is_running,
            daemon_pid=self._daemon_pid,
            daemon_version=self._version,
            memory_root=self._memory_root,
            indexed_memories=self._indexed_count,
            baseline_files=0,  # Will be updated by caller
            baseline_tokens=self._baseline_tokens,
            last_reindex=self._last_reindex,
            watcher_active=self._watcher_active,
            uptime_seconds=self.uptime_seconds if self.is_running else None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "version": self._version,
            "running": self.is_running,
            "healthy": self.is_healthy,
            "uptime_seconds": self.uptime_seconds,
            "indexed_count": self._indexed_count,
            "baseline_tokens": self._baseline_tokens,
            "last_reindex": self._last_reindex.isoformat() if self._last_reindex else None,
            "watcher_active": self._watcher_active,
            "memory_root": self._memory_root,
            "pid": self._daemon_pid,
            "error": self._error_message,
        }
