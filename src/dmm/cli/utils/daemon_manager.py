"""
Daemon manager utility for auto-starting DMM daemon.

Provides transparent daemon lifecycle management for CLI commands,
ensuring the daemon is running before operations that require it.
"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from dmm.core.constants import DEFAULT_HOST, DEFAULT_PORT
from dmm.daemon.lifecycle import DaemonConfig, DaemonLifecycle, DaemonStatus


@dataclass
class DaemonManagerConfig:
    """Configuration for DaemonManager."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    pid_file: Path = Path("/tmp/dmm.pid")
    startup_timeout: float = 30.0
    health_check_interval: float = 0.5
    auto_start: bool = True
    quiet: bool = False


class DaemonManager:
    """
    Manages daemon lifecycle with auto-start capability.
    
    This class wraps DaemonLifecycle and adds:
    - Automatic daemon startup when needed
    - Health check waiting with timeout
    - Quiet mode for non-interactive use
    """

    def __init__(self, config: Optional[DaemonManagerConfig] = None) -> None:
        """
        Initialize DaemonManager.

        Args:
            config: Manager configuration. Uses defaults if not provided.
        """
        self._config = config or DaemonManagerConfig()
        self._lifecycle = DaemonLifecycle(
            DaemonConfig(
                host=self._config.host,
                port=self._config.port,
                pid_file=self._config.pid_file,
            )
        )

    @property
    def config(self) -> DaemonManagerConfig:
        """Get manager configuration."""
        return self._config

    @property
    def url(self) -> str:
        """Get daemon base URL."""
        return f"http://{self._config.host}:{self._config.port}"

    def is_running(self) -> bool:
        """
        Check if daemon is running and healthy.

        Returns:
            True if daemon is running and responding to health checks.
        """
        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.get(f"{self.url}/health")
                return response.status_code == 200
        except (httpx.RequestError, httpx.HTTPStatusError):
            return False

    def get_status(self) -> DaemonStatus:
        """
        Get detailed daemon status.

        Returns:
            DaemonStatus with running state, PID, health, etc.
        """
        return self._lifecycle.status()

    def start(self, wait: bool = True) -> bool:
        """
        Start the daemon.

        Args:
            wait: If True, wait for daemon to be healthy before returning.

        Returns:
            True if daemon started successfully (or was already running).
        """
        if self.is_running():
            return True

        try:
            result = self._lifecycle.start(foreground=False)
            if not result.success:
                return False

            if wait:
                return self._wait_for_healthy()
            return True

        except Exception:
            return False

    def stop(self) -> bool:
        """
        Stop the daemon.

        Returns:
            True if daemon stopped successfully (or was not running).
        """
        try:
            result = self._lifecycle.stop()
            return result.success
        except Exception:
            return False

    def restart(self, wait: bool = True) -> bool:
        """
        Restart the daemon.

        Args:
            wait: If True, wait for daemon to be healthy after restart.

        Returns:
            True if daemon restarted successfully.
        """
        self.stop()
        time.sleep(0.5)
        return self.start(wait=wait)

    def ensure_running(self, quiet: bool = False) -> bool:
        """
        Ensure the daemon is running, starting it if necessary.

        This is the primary method for auto-start functionality.
        Commands call this before operations that require the daemon.

        Args:
            quiet: If True, suppress output messages.

        Returns:
            True if daemon is running (was running or successfully started).
        """
        if self.is_running():
            return True

        if not self._config.auto_start:
            return False

        if not quiet and not self._config.quiet:
            _print_status("DMM daemon not running. Starting...")

        success = self.start(wait=True)

        if success and not quiet and not self._config.quiet:
            _print_status("DMM daemon started successfully.")

        return success

    def _wait_for_healthy(self) -> bool:
        """
        Wait for daemon to become healthy.

        Returns:
            True if daemon became healthy within timeout.
        """
        deadline = time.time() + self._config.startup_timeout
        
        while time.time() < deadline:
            if self.is_running():
                return True
            time.sleep(self._config.health_check_interval)

        return False


def _print_status(message: str) -> None:
    """Print status message to stderr to avoid interfering with command output."""
    import sys
    print(f"[DMM] {message}", file=sys.stderr)


def ensure_daemon_running(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    quiet: bool = False,
    auto_start: bool = True,
) -> bool:
    """
    Convenience function to ensure daemon is running.

    This is the primary interface for other CLI commands to use.

    Args:
        host: Daemon host.
        port: Daemon port.
        quiet: If True, suppress output messages.
        auto_start: If True, start daemon if not running.

    Returns:
        True if daemon is running.

    Example:
        >>> if not ensure_daemon_running():
        ...     print("Failed to start daemon")
        ...     return
        >>> # proceed with daemon-dependent operations
    """
    manager = DaemonManager(
        DaemonManagerConfig(
            host=host,
            port=port,
            auto_start=auto_start,
            quiet=quiet,
        )
    )
    return manager.ensure_running(quiet=quiet)


def get_daemon_manager(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> DaemonManager:
    """
    Get a DaemonManager instance with specified configuration.

    Args:
        host: Daemon host.
        port: Daemon port.

    Returns:
        Configured DaemonManager instance.
    """
    return DaemonManager(
        DaemonManagerConfig(
            host=host,
            port=port,
        )
    )
