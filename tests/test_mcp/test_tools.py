"""
Unit tests for DMM MCP tools.

Tests cover:
- Query tool functionality
- Remember tool functionality
- Forget tool functionality
- Status tool functionality
- Conflicts tool functionality
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import modules first to ensure they are loaded before patching
from dmm.mcp.tools import query, remember, forget, status, conflicts
from dmm.mcp.tools.query import execute_query
from dmm.mcp.tools.remember import execute_remember
from dmm.mcp.tools.forget import execute_forget
from dmm.mcp.tools.status import execute_status
from dmm.mcp.tools.conflicts import execute_conflicts


class TestQueryTool:
    """Tests for dmm_query MCP tool."""

    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> Generator[dict[str, Any], None, None]:
        """Create mock configuration."""
        config = {
            "daemon": {"host": "127.0.0.1", "port": 7437},
            "memory_root": str(tmp_path / "memory"),
            "project_root": str(tmp_path),
        }
        with patch.object(query, "get_config", return_value=config):
            yield config

    @pytest.mark.asyncio
    async def test_query_empty_string_returns_error(self, mock_config: dict) -> None:
        """Query with empty string should return error."""
        result = await execute_query("")
        assert "Error" in result
        assert "empty" in result.lower()

    @pytest.mark.asyncio
    async def test_query_whitespace_only_returns_error(self, mock_config: dict) -> None:
        """Query with whitespace only should return error."""
        result = await execute_query("   ")
        assert "Error" in result
        assert "empty" in result.lower()

    @pytest.mark.asyncio
    async def test_query_invalid_scope_returns_error(self, mock_config: dict) -> None:
        """Query with invalid scope should return error."""
        result = await execute_query("test query", scope="invalid_scope")
        assert "Error" in result
        assert "Invalid scope" in result

    @pytest.mark.asyncio
    async def test_query_valid_scopes_accepted(self, mock_config: dict) -> None:
        """Query with valid scopes should not return scope error."""
        valid_scopes = ["baseline", "global", "agent", "project", "ephemeral"]

        for scope in valid_scopes:
            # Mock the daemon interaction to avoid recursion
            with patch.object(query, "_query_with_daemon_start", new_callable=AsyncMock) as mock_start:
                mock_start.return_value = "Daemon not available"
                
                # The httpx call will fail, triggering _query_with_daemon_start
                # But we just want to verify scope validation passes
                result = await execute_query("test", scope=scope)
                assert "Invalid scope" not in result

    @pytest.mark.asyncio
    async def test_query_formats_memories_correctly(self, mock_config: dict) -> None:
        """Query should format returned memories as markdown."""
        from dmm.mcp.tools.query import _format_query_response

        mock_data = {
            "memories": [],
            "pack": {
                "entries": [
                    {
                        "id": "mem_2026_01_26_001",
                        "title": "Test Memory",
                        "scope": "project",
                        "score": 0.95,
                        "content": "# Test Memory\n\nThis is test content.",
                    }
                ],
                "total_tokens": 50,
            },
        }

        result = _format_query_response(mock_data, "test query")

        assert "Relevant Memories" in result
        assert "Test Memory" in result
        assert "project" in result
        assert "0.95" in result

    @pytest.mark.asyncio
    async def test_query_handles_no_results(self, mock_config: dict) -> None:
        """Query should handle empty results gracefully."""
        from dmm.mcp.tools.query import _format_query_response

        mock_data = {"memories": [], "pack": {"entries": []}}
        result = _format_query_response(mock_data, "nonexistent topic xyz")
        assert "No relevant memories" in result


class TestRememberTool:
    """Tests for dmm_remember MCP tool."""

    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> Generator[dict[str, Any], None, None]:
        """Create mock configuration with real temp directory."""
        memory_root = tmp_path / "memory"
        memory_root.mkdir(parents=True)

        config = {
            "daemon": {"host": "127.0.0.1", "port": 7437},
            "memory_root": str(memory_root),
            "project_root": str(tmp_path),
        }
        with patch.object(remember, "get_config", return_value=config):
            yield config

    @pytest.mark.asyncio
    async def test_remember_empty_content_returns_error(self, mock_config: dict) -> None:
        """Remember with empty content should return error."""
        result = await execute_remember("")
        assert "Error" in result
        assert "empty" in result.lower()

    @pytest.mark.asyncio
    async def test_remember_short_content_returns_error(self, mock_config: dict) -> None:
        """Remember with too short content should return error."""
        result = await execute_remember("Too short")
        assert "Error" in result
        assert "short" in result.lower()

    @pytest.mark.asyncio
    async def test_remember_invalid_scope_returns_error(self, mock_config: dict) -> None:
        """Remember with invalid scope should return error."""
        result = await execute_remember(
            "This is valid content that is long enough to be remembered",
            scope="invalid",
        )
        assert "Error" in result
        assert "Invalid scope" in result

    @pytest.mark.asyncio
    async def test_remember_invalid_priority_returns_error(self, mock_config: dict) -> None:
        """Remember with invalid priority should return error."""
        result = await execute_remember(
            "This is valid content that is long enough to be remembered",
            priority=1.5,
        )
        assert "Error" in result
        assert "Priority" in result

    @pytest.mark.asyncio
    async def test_remember_creates_file(self, mock_config: dict, tmp_path: Path) -> None:
        """Remember should create a memory file."""
        content = "We use PostgreSQL for the database. This is an important architectural decision."

        with patch.object(remember, "_trigger_reindex", new_callable=AsyncMock):
            result = await execute_remember(content, scope="project", tags=["database"])

        assert "Memory created" in result
        assert "mem_" in result

        project_dir = tmp_path / "memory" / "project"
        assert project_dir.exists()
        md_files = list(project_dir.glob("*.md"))
        assert len(md_files) == 1

        file_content = md_files[0].read_text()
        assert "PostgreSQL" in file_content
        assert "scope: project" in file_content
        assert "database" in file_content

    @pytest.mark.asyncio
    async def test_remember_auto_generates_tags(self, mock_config: dict, tmp_path: Path) -> None:
        """Remember should auto-generate tags from content."""
        content = "The API endpoint for authentication uses JWT tokens with 15-minute expiry."

        with patch.object(remember, "_trigger_reindex", new_callable=AsyncMock):
            result = await execute_remember(content, scope="project")

        assert "Memory created" in result

        project_dir = tmp_path / "memory" / "project"
        md_files = list(project_dir.glob("*.md"))
        file_content = md_files[0].read_text()

        assert "api" in file_content.lower() or "authentication" in file_content.lower()


class TestForgetTool:
    """Tests for dmm_forget MCP tool."""

    @pytest.fixture
    def mock_config_with_memory(
        self, tmp_path: Path
    ) -> Generator[tuple[dict[str, Any], Path], None, None]:
        """Create mock configuration with a test memory file."""
        memory_root = tmp_path / "memory"
        project_dir = memory_root / "project"
        project_dir.mkdir(parents=True)

        memory_file = project_dir / "test_memory.md"
        memory_file.write_text(
            """---
id: mem_2026_01_26_001
tags: [test, example]
scope: project
priority: 0.6
confidence: active
status: active
created: 2026-01-26
---

# Test Memory

This is a test memory for testing the forget tool.
"""
        )

        config = {
            "daemon": {"host": "127.0.0.1", "port": 7437},
            "memory_root": str(memory_root),
            "project_root": str(tmp_path),
        }
        with patch.object(forget, "get_config", return_value=config):
            yield config, memory_file

    @pytest.mark.asyncio
    async def test_forget_empty_id_returns_error(self, tmp_path: Path) -> None:
        """Forget with empty ID should return error."""
        config = {"memory_root": str(tmp_path), "project_root": str(tmp_path)}
        with patch.object(forget, "get_config", return_value=config):
            result = await execute_forget("", "test reason here")

        assert "Error" in result
        assert "empty" in result.lower()

    @pytest.mark.asyncio
    async def test_forget_invalid_id_format_returns_error(self, tmp_path: Path) -> None:
        """Forget with invalid ID format should return error."""
        config = {"memory_root": str(tmp_path), "project_root": str(tmp_path)}
        with patch.object(forget, "get_config", return_value=config):
            result = await execute_forget("invalid_id", "test reason here")

        assert "Error" in result
        assert "Invalid memory ID" in result

    @pytest.mark.asyncio
    async def test_forget_short_reason_returns_error(self, tmp_path: Path) -> None:
        """Forget with too short reason should return error."""
        config = {"memory_root": str(tmp_path), "project_root": str(tmp_path)}
        with patch.object(forget, "get_config", return_value=config):
            result = await execute_forget("mem_2026_01_26_001", "short")

        assert "Error" in result
        assert "short" in result.lower()

    @pytest.mark.asyncio
    async def test_forget_marks_memory_deprecated(
        self, mock_config_with_memory: tuple[dict[str, Any], Path]
    ) -> None:
        """Forget should mark memory as deprecated."""
        config, memory_file = mock_config_with_memory

        with patch.object(forget, "_trigger_reindex", new_callable=AsyncMock):
            result = await execute_forget(
                "mem_2026_01_26_001", "This information is outdated"
            )

        assert "deprecated" in result.lower()

        updated_content = memory_file.read_text()
        assert "status: deprecated" in updated_content
        assert "deprecation_reason" in updated_content


class TestStatusTool:
    """Tests for dmm_status MCP tool."""

    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> Generator[dict[str, Any], None, None]:
        """Create mock configuration."""
        memory_root = tmp_path / "memory"
        index_root = tmp_path / "index"

        for scope in ["baseline", "project", "agent"]:
            (memory_root / scope).mkdir(parents=True)

        index_root.mkdir(parents=True)
        (index_root / "embeddings.db").write_text("")

        config = {
            "daemon": {"host": "127.0.0.1", "port": 7437},
            "memory_root": str(memory_root),
            "index_root": str(index_root),
            "project_root": str(tmp_path),
        }
        with patch.object(status, "get_config", return_value=config):
            yield config

    @pytest.mark.asyncio
    async def test_status_returns_formatted_output(self, mock_config: dict) -> None:
        """Status should return formatted markdown output."""
        from dmm.mcp.tools.status import _format_status_response
        
        status_data = {
            "daemon": {"running": False, "host": "127.0.0.1", "port": 7437, "error": "Not running"},
            "memory": {"exists": True, "total_files": 5, "total_bytes": 1000, "scopes": {}},
            "index": {"exists": True, "databases": {}},
        }
        
        result = _format_status_response(status_data, verbose=False)

        assert "DMM System Status" in result
        assert "Daemon" in result
        assert "Memory" in result

    @pytest.mark.asyncio
    async def test_status_verbose_includes_config(self, mock_config: dict) -> None:
        """Status with verbose flag should include configuration."""
        from dmm.mcp.tools.status import _format_status_response
        
        status_data = {
            "daemon": {"running": False, "host": "127.0.0.1", "port": 7437},
            "memory": {"exists": True, "total_files": 5, "total_bytes": 1000, "scopes": {}},
            "index": {"exists": True, "databases": {}},
            "config": {"project_root": "/test", "memory_root": "/test/memory"},
        }
        
        result = _format_status_response(status_data, verbose=True)

        assert "Configuration" in result


class TestConflictsTool:
    """Tests for dmm_conflicts MCP tool."""

    @pytest.mark.asyncio
    async def test_conflicts_invalid_severity_returns_error(self, tmp_path: Path) -> None:
        """Conflicts with invalid severity should return error."""
        config = {"memory_root": str(tmp_path), "project_root": str(tmp_path)}
        with patch.object(conflicts, "get_config", return_value=config):
            result = await execute_conflicts(min_severity="invalid")

        assert "Error" in result
        assert "Invalid severity" in result

    @pytest.mark.asyncio
    async def test_conflicts_no_memories_returns_no_conflicts(self, tmp_path: Path) -> None:
        """Conflicts with no memories should return no conflicts."""
        memory_root = tmp_path / "memory"
        memory_root.mkdir(parents=True)

        config = {"memory_root": str(memory_root), "project_root": str(tmp_path)}
        with patch.object(conflicts, "get_config", return_value=config):
            with patch.object(
                conflicts, "_fetch_daemon_conflicts",
                new_callable=AsyncMock,
                return_value=None,
            ):
                result = await execute_conflicts()

        assert "No Conflicts" in result
