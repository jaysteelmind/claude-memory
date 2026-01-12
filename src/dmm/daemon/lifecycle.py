"""Daemon lifecycle management - start, stop, status."""

import os
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from dmm.core.constants import DEFAULT_GRACEFUL_SHUTDOWN_TIMEOUT, DEFAULT_HOST, DEFAULT_PORT
from dmm.core.exceptions import (
    DaemonAlreadyRunningError,
    DaemonNotRunningError,
    DaemonStartError,
    DaemonStopError,
)


@dataclass
class DaemonConfig:
    """Daemon configuration."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    pid_file: Path = Path("/tmp/dmm.pid")
    log_file: Path | None = None
    auto_start: bool = True
    graceful_shutdown_timeout: float = DEFAULT_GRACEFUL_SHUTDOWN_TIMEOUT


@dataclass
class StartResult:
    """Result of daemon start operation."""

    success: bool
    pid: int | None
    message: str
    url: str | None = None


@dataclass
class StopResult:
    """Result of daemon stop operation."""

    success: bool
    message: str
    was_running: bool = False


@dataclass
class DaemonStatus:
    """Current daemon status."""

    running: bool
    pid: int | None
    uptime_seconds: float | None
    health: str | None  # "healthy" | "unhealthy" | "unknown"
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "running": self.running,
            "pid": self.pid,
            "uptime_seconds": self.uptime_seconds,
            "health": self.health,
            "url": self.url,
        }


class DaemonLifecycle:
    """Manages daemon start/stop lifecycle."""

    def __init__(self, config: DaemonConfig | None = None) -> None:
        """
        Initialize lifecycle manager.

        Args:
            config: Daemon configuration
        """
        self._config = config or DaemonConfig()

    @property
    def config(self) -> DaemonConfig:
        """Get daemon configuration."""
        return self._config

    @property
    def url(self) -> str:
        """Get daemon base URL."""
        return f"http://{self._config.host}:{self._config.port}"

    def start(self, foreground: bool = False) -> StartResult:
        """
        Start the daemon.

        Args:
            foreground: If True, run in foreground (blocking)

        Returns:
            StartResult with PID and status
        """
        # Check if already running
        status = self.status()
        if status.running:
            raise DaemonAlreadyRunningError(
                f"Daemon already running with PID {status.pid}",
                pid=status.pid,
            )

        if foreground:
            # Foreground mode - just return info, actual run happens elsewhere
            pid = os.getpid()
            self.write_pid_file(pid)
            return StartResult(
                success=True,
                pid=pid,
                message="Running in foreground",
                url=self.url,
            )

        # Background mode - spawn subprocess
        try:
            pid = self._spawn_background()
            return StartResult(
                success=True,
                pid=pid,
                message=f"Daemon started with PID {pid}",
                url=self.url,
            )
        except Exception as e:
            raise DaemonStartError(f"Failed to start daemon: {e}") from e

    def stop(self, timeout: float | None = None) -> StopResult:
        """
        Stop the daemon gracefully.

        Args:
            timeout: Seconds to wait before force kill
        """
        timeout = timeout or self._config.graceful_shutdown_timeout

        pid = self.read_pid_file()
        if pid is None:
            return StopResult(
                success=True,
                message="Daemon not running (no PID file)",
                was_running=False,
            )

        # Check if process exists
        if not self._process_exists(pid):
            self._cleanup_pid_file()
            return StopResult(
                success=True,
                message="Daemon not running (stale PID file cleaned)",
                was_running=False,
            )

        # Try graceful shutdown first
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            self._cleanup_pid_file()
            return StopResult(
                success=True,
                message="Daemon already stopped",
                was_running=False,
            )
        except PermissionError as e:
            raise DaemonStopError(f"Permission denied stopping PID {pid}: {e}") from e

        # Wait for graceful shutdown
        import time

        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._process_exists(pid):
                self._cleanup_pid_file()
                return StopResult(
                    success=True,
                    message=f"Daemon stopped (PID {pid})",
                    was_running=True,
                )
            time.sleep(0.1)

        # Force kill if still running
        try:
            os.kill(pid, signal.SIGKILL)
            self._cleanup_pid_file()
            return StopResult(
                success=True,
                message=f"Daemon force killed (PID {pid})",
                was_running=True,
            )
        except ProcessLookupError:
            self._cleanup_pid_file()
            return StopResult(
                success=True,
                message="Daemon stopped during force kill",
                was_running=True,
            )

    def status(self) -> DaemonStatus:
        """Get current daemon status."""
        pid = self.read_pid_file()

        if pid is None:
            return DaemonStatus(
                running=False,
                pid=None,
                uptime_seconds=None,
                health=None,
            )

        # Check if process exists
        if not self._process_exists(pid):
            self._cleanup_pid_file()
            return DaemonStatus(
                running=False,
                pid=None,
                uptime_seconds=None,
                health=None,
            )

        # Try to get health from API
        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.get(f"{self.url}/health")
                if response.status_code == 200:
                    data = response.json()
                    return DaemonStatus(
                        running=True,
                        pid=pid,
                        uptime_seconds=data.get("uptime_seconds"),
                        health=data.get("status", "unknown"),
                        url=self.url,
                    )
        except (httpx.RequestError, httpx.HTTPStatusError):
            pass

        # Process exists but API not responding
        return DaemonStatus(
            running=True,
            pid=pid,
            uptime_seconds=None,
            health="unknown",
            url=self.url,
        )

    def write_pid_file(self, pid: int) -> None:
        """Write PID to file for tracking."""
        self._config.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self._config.pid_file.write_text(str(pid))

    def read_pid_file(self) -> int | None:
        """Read PID from file."""
        if not self._config.pid_file.exists():
            return None
        try:
            content = self._config.pid_file.read_text().strip()
            return int(content)
        except (ValueError, OSError):
            return None

    def _cleanup_pid_file(self) -> None:
        """Remove PID file."""
        try:
            self._config.pid_file.unlink(missing_ok=True)
        except OSError:
            pass

    def _process_exists(self, pid: int) -> bool:
        """Check if a process with given PID exists."""
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but we don't have permission
            return True

    def _spawn_background(self) -> int:
        """Spawn daemon in background."""
        # Fork to background
        pid = os.fork()
        if pid > 0:
            # Parent process - wait briefly for child to start
            import time

            time.sleep(0.5)

            # Check if child started successfully
            if self._config.pid_file.exists():
                child_pid = self.read_pid_file()
                if child_pid and self._process_exists(child_pid):
                    return child_pid

            raise DaemonStartError("Child process failed to start")

        # Child process
        try:
            # Create new session
            os.setsid()

            # Second fork to prevent zombie
            pid = os.fork()
            if pid > 0:
                os._exit(0)

            # Grandchild - the actual daemon
            self.write_pid_file(os.getpid())

            # Redirect stdio
            sys.stdin.close()
            if self._config.log_file:
                log_fd = open(self._config.log_file, "a")
                os.dup2(log_fd.fileno(), sys.stdout.fileno())
                os.dup2(log_fd.fileno(), sys.stderr.fileno())
            else:
                devnull = open(os.devnull, "w")
                os.dup2(devnull.fileno(), sys.stdout.fileno())
                os.dup2(devnull.fileno(), sys.stderr.fileno())

            # Import and run server
            from dmm.daemon.server import run_server

            run_server(
                host=self._config.host,
                port=self._config.port,
            )

        except Exception:
            os._exit(1)

        os._exit(0)


def check_daemon_running(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> bool:
    """Quick check if daemon is running and responding."""
    try:
        with httpx.Client(timeout=1.0) as client:
            response = client.get(f"http://{host}:{port}/health")
            return response.status_code == 200
    except (httpx.RequestError, httpx.HTTPStatusError):
        return False
