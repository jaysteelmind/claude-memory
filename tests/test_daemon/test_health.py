"""Tests for daemon health checker."""

from datetime import datetime

import pytest

from dmm.daemon.health import HealthChecker


class TestHealthChecker:
    """Tests for HealthChecker."""

    def test_initial_state(self) -> None:
        """Should start in non-running state."""
        checker = HealthChecker(version="1.0.0")

        assert not checker.is_running
        assert not checker.is_healthy
        assert checker.uptime_seconds == 0.0

    def test_mark_started(self) -> None:
        """Should mark as started with PID."""
        checker = HealthChecker()
        checker.mark_started(pid=12345)

        assert checker.is_running
        assert checker.is_healthy
        assert checker.uptime_seconds >= 0

    def test_mark_stopped(self) -> None:
        """Should mark as stopped."""
        checker = HealthChecker()
        checker.mark_started(pid=12345)
        checker.mark_stopped()

        assert not checker.is_running

    def test_update_stats(self) -> None:
        """Should update statistics."""
        checker = HealthChecker()
        checker.mark_started()

        checker.update_stats(
            indexed_count=42,
            baseline_tokens=650,
            watcher_active=True,
            memory_root="/path/to/memory",
        )

        health = checker.get_health_response()
        assert health.indexed_count == 42
        assert health.baseline_tokens == 650
        assert health.watcher_active is True

    def test_mark_unhealthy(self) -> None:
        """Should mark as unhealthy with error."""
        checker = HealthChecker()
        checker.mark_started()
        checker.mark_unhealthy("Database connection failed")

        assert checker.is_running
        assert not checker.is_healthy

    def test_mark_healthy(self) -> None:
        """Should recover to healthy state."""
        checker = HealthChecker()
        checker.mark_started()
        checker.mark_unhealthy("Error")
        checker.mark_healthy()

        assert checker.is_healthy

    def test_get_health_response(self) -> None:
        """Should return health response."""
        checker = HealthChecker(version="1.2.3")
        checker.mark_started()
        checker.update_stats(indexed_count=10)

        response = checker.get_health_response()

        assert response.status == "healthy"
        assert response.version == "1.2.3"
        assert response.indexed_count == 10
        assert response.uptime_seconds >= 0

    def test_get_status_response(self) -> None:
        """Should return status response."""
        checker = HealthChecker(version="1.2.3")
        checker.mark_started(pid=99999)
        checker.update_stats(
            indexed_count=25,
            baseline_tokens=500,
            memory_root="/test/path",
        )

        response = checker.get_status_response()

        assert response.daemon_running is True
        assert response.daemon_pid == 99999
        assert response.daemon_version == "1.2.3"
        assert response.indexed_memories == 25
        assert response.baseline_tokens == 500

    def test_to_dict(self) -> None:
        """Should convert to dictionary."""
        checker = HealthChecker(version="1.0.0")
        checker.mark_started(pid=12345)

        data = checker.to_dict()

        assert data["version"] == "1.0.0"
        assert data["running"] is True
        assert data["healthy"] is True
        assert data["pid"] == 12345

    def test_uptime_increases(self) -> None:
        """Uptime should increase over time."""
        import time

        checker = HealthChecker()
        checker.mark_started()

        uptime1 = checker.uptime_seconds
        time.sleep(0.1)
        uptime2 = checker.uptime_seconds

        assert uptime2 > uptime1

    def test_last_reindex_tracking(self) -> None:
        """Should track last reindex time."""
        checker = HealthChecker()
        checker.mark_started()

        now = datetime.now()
        checker.update_stats(last_reindex=now)

        response = checker.get_health_response()
        assert response.last_reindex == now
