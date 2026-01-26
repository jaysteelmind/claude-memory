"""
Tests for Phase 7: Automated Bootstrap System.

Tests cover:
- DaemonManager utility
- Bootstrap command
- Remember command
- Forget command
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dmm.cli.utils.daemon_manager import (
    DaemonManager,
    DaemonManagerConfig,
    ensure_daemon_running,
    get_daemon_manager,
)


# =============================================================================
# DaemonManager Tests
# =============================================================================

class TestDaemonManagerConfig:
    """Tests for DaemonManagerConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = DaemonManagerConfig()
        assert config.host == "127.0.0.1"
        assert config.port == 7433
        assert config.startup_timeout == 30.0
        assert config.health_check_interval == 0.5
        assert config.auto_start is True
        assert config.quiet is False

    def test_custom_config(self):
        """Test custom configuration values."""
        config = DaemonManagerConfig(
            host="localhost",
            port=8080,
            startup_timeout=60.0,
            auto_start=False,
            quiet=True,
        )
        assert config.host == "localhost"
        assert config.port == 8080
        assert config.startup_timeout == 60.0
        assert config.auto_start is False
        assert config.quiet is True


class TestDaemonManager:
    """Tests for DaemonManager class."""

    def test_init_default(self):
        """Test initialization with default config."""
        manager = DaemonManager()
        assert manager.config.host == "127.0.0.1"
        assert manager.config.port == 7433

    def test_init_custom_config(self):
        """Test initialization with custom config."""
        config = DaemonManagerConfig(host="localhost", port=9000)
        manager = DaemonManager(config)
        assert manager.config.host == "localhost"
        assert manager.config.port == 9000

    def test_url_property(self):
        """Test URL property generation."""
        manager = DaemonManager(DaemonManagerConfig(host="localhost", port=8080))
        assert manager.url == "http://localhost:8080"

    @patch("dmm.cli.utils.daemon_manager.httpx.Client")
    def test_is_running_true(self, mock_client_class):
        """Test is_running returns True when daemon responds."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        manager = DaemonManager()
        assert manager.is_running() is True

    @patch("dmm.cli.utils.daemon_manager.httpx.Client")
    def test_is_running_false_on_error(self, mock_client_class):
        """Test is_running returns False on connection error."""
        import httpx
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        manager = DaemonManager()
        assert manager.is_running() is False

    @patch.object(DaemonManager, "is_running")
    def test_ensure_running_already_running(self, mock_is_running):
        """Test ensure_running when daemon is already running."""
        mock_is_running.return_value = True

        manager = DaemonManager()
        result = manager.ensure_running(quiet=True)

        assert result is True
        mock_is_running.assert_called()

    @patch.object(DaemonManager, "is_running")
    @patch.object(DaemonManager, "start")
    def test_ensure_running_starts_daemon(self, mock_start, mock_is_running):
        """Test ensure_running starts daemon when not running."""
        mock_is_running.return_value = False
        mock_start.return_value = True

        manager = DaemonManager()
        result = manager.ensure_running(quiet=True)

        assert result is True
        mock_start.assert_called_once_with(wait=True)

    @patch.object(DaemonManager, "is_running")
    def test_ensure_running_disabled(self, mock_is_running):
        """Test ensure_running returns False when auto_start disabled."""
        mock_is_running.return_value = False

        config = DaemonManagerConfig(auto_start=False)
        manager = DaemonManager(config)
        result = manager.ensure_running(quiet=True)

        assert result is False


class TestDaemonManagerFunctions:
    """Tests for module-level convenience functions."""

    @patch("dmm.cli.utils.daemon_manager.DaemonManager")
    def test_ensure_daemon_running(self, mock_manager_class):
        """Test ensure_daemon_running convenience function."""
        mock_manager = MagicMock()
        mock_manager.ensure_running.return_value = True
        mock_manager_class.return_value = mock_manager

        result = ensure_daemon_running(quiet=True)

        assert result is True
        mock_manager.ensure_running.assert_called_once_with(quiet=True)

    def test_get_daemon_manager(self):
        """Test get_daemon_manager returns configured manager."""
        manager = get_daemon_manager(host="localhost", port=9000)

        assert isinstance(manager, DaemonManager)
        assert manager.config.host == "localhost"
        assert manager.config.port == 9000


# =============================================================================
# Remember Command Tests
# =============================================================================

class TestRememberCommand:
    """Tests for the remember command helpers."""

    def test_generate_memory_id(self):
        """Test memory ID generation."""
        from dmm.cli.commands.remember import _generate_memory_id

        memory_id = _generate_memory_id()

        assert memory_id.startswith("mem_")
        parts = memory_id.split("_")
        # Format: mem_YYYY_MM_DD_NNN (5 parts)
        assert len(parts) == 5
        assert parts[0] == "mem"
        assert len(parts[1]) == 4  # Year
        assert len(parts[2]) == 2  # Month
        assert len(parts[3]) == 2  # Day
        assert len(parts[4]) == 3  # Sequence

    def test_extract_title_from_header(self):
        """Test title extraction from markdown header."""
        from dmm.cli.commands.remember import _extract_title

        content = "# My Important Decision\n\nSome content here."
        title = _extract_title(content)

        assert title == "My Important Decision"

    def test_extract_title_from_content(self):
        """Test title extraction from plain content."""
        from dmm.cli.commands.remember import _extract_title

        content = "We decided to use Redis for caching."
        title = _extract_title(content)

        assert title == "We decided to use Redis for caching."

    def test_extract_title_truncates_long_content(self):
        """Test title truncation for long content."""
        from dmm.cli.commands.remember import _extract_title

        content = "A" * 100
        title = _extract_title(content)

        assert len(title) == 60
        assert title.endswith("...")

    def test_extract_tags_finds_keywords(self):
        """Test tag extraction from content."""
        from dmm.cli.commands.remember import _extract_tags

        content = "We use Redis for caching API responses with authentication tokens."
        tags = _extract_tags(content, "Caching Strategy")

        assert "api" in tags or "authentication" in tags
        assert len(tags) <= 5

    def test_extract_tags_default(self):
        """Test default tag when no keywords found."""
        from dmm.cli.commands.remember import _extract_tags

        content = "Just some random text here."
        tags = _extract_tags(content, "Random")

        assert tags == ["note"]

    def test_sanitize_filename(self):
        """Test filename sanitization."""
        from dmm.cli.commands.remember import _sanitize_filename

        assert _sanitize_filename("My Decision!") == "my_decision"
        assert _sanitize_filename("API v2.0 Design") == "api_v20_design"
        assert _sanitize_filename("  spaces  ") == "spaces"

    def test_sanitize_filename_truncates(self):
        """Test filename truncation."""
        from dmm.cli.commands.remember import _sanitize_filename

        long_title = "A" * 100
        filename = _sanitize_filename(long_title)

        assert len(filename) <= 50

    def test_count_tokens(self):
        """Test token count estimation."""
        from dmm.cli.commands.remember import _count_tokens

        # ~4 chars per token
        text = "A" * 400
        tokens = _count_tokens(text)

        assert tokens == 100


# =============================================================================
# Forget Command Tests
# =============================================================================

class TestForgetCommand:
    """Tests for the forget command helpers."""

    def test_find_memory_by_id(self, tmp_path):
        """Test finding memory by ID."""
        from dmm.cli.commands.forget import _find_memory_by_id

        # Create test memory
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        memory_file = project_dir / "test.md"
        memory_file.write_text("---\nid: mem_2025_01_20_001\n---\n# Test")

        result = _find_memory_by_id(tmp_path, "mem_2025_01_20_001")

        assert result == memory_file

    def test_find_memory_by_id_not_found(self, tmp_path):
        """Test finding non-existent memory by ID."""
        from dmm.cli.commands.forget import _find_memory_by_id

        # Create empty structure
        (tmp_path / "project").mkdir()

        result = _find_memory_by_id(tmp_path, "mem_2025_01_20_999")

        assert result is None

    def test_find_memory_by_path_absolute(self, tmp_path):
        """Test finding memory by absolute path."""
        from dmm.cli.commands.forget import _find_memory_by_path

        memory_file = tmp_path / "test.md"
        memory_file.write_text("# Test")

        result = _find_memory_by_path(tmp_path, str(memory_file))

        assert result == memory_file

    def test_find_memory_by_path_relative(self, tmp_path):
        """Test finding memory by relative path."""
        from dmm.cli.commands.forget import _find_memory_by_path

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        memory_file = project_dir / "test.md"
        memory_file.write_text("# Test")

        result = _find_memory_by_path(tmp_path, "project/test.md")

        assert result == memory_file

    def test_find_memory_by_path_filename_only(self, tmp_path):
        """Test finding memory by filename only."""
        from dmm.cli.commands.forget import _find_memory_by_path

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        memory_file = project_dir / "unique_name.md"
        memory_file.write_text("# Test")

        result = _find_memory_by_path(tmp_path, "unique_name")

        assert result == memory_file

    def test_update_memory_status(self, tmp_path):
        """Test memory status update."""
        from dmm.cli.commands.forget import _update_memory_status

        memory_file = tmp_path / "test.md"
        memory_file.write_text(
            "---\nid: mem_2025_01_20_001\nstatus: active\nconfidence: stable\n---\n# Test"
        )

        updated = _update_memory_status(memory_file)

        assert "status: deprecated" in updated
        assert "deprecated_at:" in updated


# =============================================================================
# Bootstrap Command Tests
# =============================================================================

class TestBootstrapHelpers:
    """Tests for bootstrap command helpers."""

    def test_create_boot_md(self, tmp_path):
        """Test BOOT.md creation."""
        from dmm.cli.commands.bootstrap import _create_boot_md

        boot_path = tmp_path / "BOOT.md"
        _create_boot_md(boot_path)

        assert boot_path.exists()
        content = boot_path.read_text()
        assert "DMM Boot Instructions" in content
        assert "dmm query" in content

    def test_create_policy_md(self, tmp_path):
        """Test policy.md creation."""
        from dmm.cli.commands.bootstrap import _create_policy_md

        policy_path = tmp_path / "policy.md"
        _create_policy_md(policy_path)

        assert policy_path.exists()
        content = policy_path.read_text()
        assert "DMM Policies" in content
        assert "Write Policy" in content

    def test_create_daemon_config(self, tmp_path):
        """Test daemon.config.json creation."""
        from dmm.cli.commands.bootstrap import _create_daemon_config

        config_path = tmp_path / "daemon.config.json"
        _create_daemon_config(config_path)

        assert config_path.exists()
        config = json.loads(config_path.read_text())
        assert "daemon" in config
        assert "indexer" in config
        assert "retrieval" in config
        assert config["daemon"]["port"] == 7433

    def test_initialize_dmm_creates_structure(self, tmp_path):
        """Test DMM directory structure creation."""
        from dmm.cli.commands.bootstrap import _initialize_dmm

        dmm_dir = tmp_path / ".dmm"
        result = _initialize_dmm(dmm_dir, force=False, quiet=True)

        assert result is True
        assert dmm_dir.exists()
        assert (dmm_dir / "memory" / "baseline").exists()
        assert (dmm_dir / "memory" / "project").exists()
        assert (dmm_dir / "index").exists()
        assert (dmm_dir / "BOOT.md").exists()
        assert (dmm_dir / "policy.md").exists()
        assert (dmm_dir / "daemon.config.json").exists()

    def test_initialize_dmm_skips_existing(self, tmp_path):
        """Test DMM initialization skips existing directory."""
        from dmm.cli.commands.bootstrap import _initialize_dmm

        dmm_dir = tmp_path / ".dmm"
        dmm_dir.mkdir()
        marker_file = dmm_dir / "existing_marker.txt"
        marker_file.write_text("marker")

        result = _initialize_dmm(dmm_dir, force=False, quiet=True)

        assert result is True
        assert marker_file.exists()  # Original content preserved


# =============================================================================
# Integration Tests
# =============================================================================

class TestCLIIntegration:
    """Integration tests for CLI commands."""

    def test_remember_command_dry_run(self, tmp_path, monkeypatch):
        """Test remember command with dry-run flag."""
        from typer.testing import CliRunner
        from dmm.cli.main import app

        # Patch get_memory_root to use temp directory
        monkeypatch.setattr(
            "dmm.core.constants.get_memory_root",
            lambda: tmp_path,
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["remember", "Test content for memory", "--dry-run", "--no-daemon"],
        )

        assert result.exit_code == 0
        assert "Dry Run" in result.stdout
        # No file should be created
        assert not list(tmp_path.rglob("*.md"))

    def test_remember_command_creates_file(self, tmp_path, monkeypatch):
        """Test remember command creates memory file."""
        from typer.testing import CliRunner
        from dmm.cli.main import app

        # Create project scope directory
        (tmp_path / "project").mkdir(parents=True)

        # Patch get_memory_root
        monkeypatch.setattr(
            "dmm.core.constants.get_memory_root",
            lambda: tmp_path,
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "remember",
                "We use PostgreSQL for the main database",
                "--scope", "project",
                "--no-daemon",
            ],
        )

        assert result.exit_code == 0
        assert "Memory created" in result.stdout

        # Check file was created
        md_files = list((tmp_path / "project").rglob("*.md"))
        assert len(md_files) == 1

        content = md_files[0].read_text()
        assert "PostgreSQL" in content
        assert "scope: project" in content

    def test_forget_command_not_found(self, tmp_path, monkeypatch):
        """Test forget command with non-existent memory."""
        from typer.testing import CliRunner
        from dmm.cli.main import app

        # Create empty structure
        (tmp_path / "project").mkdir(parents=True)

        monkeypatch.setattr(
            "dmm.core.constants.get_memory_root",
            lambda: tmp_path,
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["forget", "mem_2025_01_20_999", "--no-daemon"],
        )

        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_bootstrap_command_initializes(self, tmp_path, monkeypatch):
        """Test bootstrap command initializes project."""
        from typer.testing import CliRunner
        from dmm.cli.main import app

        # Change to temp directory
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["bootstrap", "--no-daemon", "--no-claude-md", "--quiet"],
        )

        assert result.exit_code == 0
        assert (tmp_path / ".dmm").exists()
        assert (tmp_path / ".dmm" / "BOOT.md").exists()


# =============================================================================
# Test __init__.py files
# =============================================================================

class TestModuleImports:
    """Test that modules can be imported correctly."""

    def test_import_daemon_manager(self):
        """Test daemon_manager module imports."""
        from dmm.cli.utils import DaemonManager, ensure_daemon_running
        
        assert DaemonManager is not None
        assert ensure_daemon_running is not None

    def test_import_commands(self):
        """Test command modules import."""
        from dmm.cli.commands.bootstrap import bootstrap_app
        from dmm.cli.commands.remember import remember_command
        from dmm.cli.commands.forget import forget_command

        assert bootstrap_app is not None
        assert remember_command is not None
        assert forget_command is not None
