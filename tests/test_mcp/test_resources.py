"""
Unit tests for DMM MCP resources.

Tests cover:
- Baseline resource functionality
- Recent resource functionality
- Conflicts resource functionality
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Generator
from unittest.mock import AsyncMock, patch

import pytest

# Import modules first to ensure they are loaded before patching
from dmm.mcp.resources import baseline, recent, conflicts as conflicts_resource
from dmm.mcp.resources.baseline import get_baseline, clear_baseline_cache
from dmm.mcp.resources.recent import get_recent, clear_recent_cache
from dmm.mcp.resources.conflicts import get_conflicts, clear_conflicts_cache


class TestBaselineResource:
    """Tests for memory://baseline resource."""

    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> Generator[dict[str, Any], None, None]:
        """Create mock configuration."""
        config = {
            "memory_root": str(tmp_path / "memory"),
            "project_root": str(tmp_path),
        }
        with patch.object(baseline, "get_config", return_value=config):
            yield config

    @pytest.fixture
    def baseline_with_memories(self, tmp_path: Path) -> Path:
        """Create baseline directory with test memories."""
        baseline_dir = tmp_path / "memory" / "baseline"
        baseline_dir.mkdir(parents=True)

        (baseline_dir / "identity.md").write_text(
            """---
id: mem_baseline_001
tags: [identity, core]
scope: baseline
priority: 1.0
status: active
---

# Project Identity

This is the DMM project - a cognitive memory system for AI agents.
"""
        )

        (baseline_dir / "constraints.md").write_text(
            """---
id: mem_baseline_002
tags: [constraints, rules]
scope: baseline
priority: 0.9
status: active
---

# Core Constraints

Never use eval() or exec() in production code.
"""
        )

        return baseline_dir

    @pytest.mark.asyncio
    async def test_baseline_no_directory_returns_message(
        self, mock_config: dict
    ) -> None:
        """Baseline with no directory should return helpful message."""
        clear_baseline_cache()
        result = await get_baseline()

        assert "No baseline memories" in result or "Baseline Context" in result

    @pytest.mark.asyncio
    async def test_baseline_returns_formatted_markdown(
        self, mock_config: dict, baseline_with_memories: Path
    ) -> None:
        """Baseline should return formatted markdown content."""
        clear_baseline_cache()
        result = await get_baseline()

        assert "Baseline Context" in result
        assert "Project Identity" in result or "Core Constraints" in result

    @pytest.mark.asyncio
    async def test_baseline_sorts_by_priority(
        self, mock_config: dict, baseline_with_memories: Path
    ) -> None:
        """Baseline should sort memories by priority (highest first)."""
        clear_baseline_cache()
        result = await get_baseline()

        identity_pos = result.find("Project Identity")
        constraints_pos = result.find("Core Constraints")

        if identity_pos != -1 and constraints_pos != -1:
            assert identity_pos < constraints_pos

    @pytest.mark.asyncio
    async def test_baseline_excludes_deprecated(
        self, mock_config: dict, tmp_path: Path
    ) -> None:
        """Baseline should exclude deprecated memories."""
        baseline_dir = tmp_path / "memory" / "baseline"
        baseline_dir.mkdir(parents=True)

        (baseline_dir / "deprecated.md").write_text(
            """---
id: mem_baseline_deprecated
tags: [old]
scope: baseline
priority: 1.0
status: deprecated
---

# Old Memory

This should not appear.
"""
        )

        clear_baseline_cache()
        result = await get_baseline()

        assert "Old Memory" not in result

    @pytest.mark.asyncio
    async def test_baseline_caches_results(
        self, mock_config: dict, baseline_with_memories: Path
    ) -> None:
        """Baseline should cache results for performance."""
        clear_baseline_cache()

        result1 = await get_baseline()
        result2 = await get_baseline()

        assert result1 == result2


class TestRecentResource:
    """Tests for memory://recent resource."""

    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> Generator[dict[str, Any], None, None]:
        """Create mock configuration."""
        config = {
            "memory_root": str(tmp_path / "memory"),
            "project_root": str(tmp_path),
        }
        with patch.object(recent, "get_config", return_value=config):
            yield config

    @pytest.fixture
    def recent_memories(self, tmp_path: Path) -> Path:
        """Create memories with recent timestamps."""
        project_dir = tmp_path / "memory" / "project"
        project_dir.mkdir(parents=True)

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        (project_dir / "recent1.md").write_text(
            f"""---
id: mem_recent_001
tags: [recent, test]
scope: project
priority: 0.6
status: active
created: {today}
last_used: {today}
---

# Recent Memory 1

This is a recent memory.
"""
        )

        return project_dir

    @pytest.mark.asyncio
    async def test_recent_no_memories_returns_message(
        self, mock_config: dict
    ) -> None:
        """Recent with no memories should return helpful message."""
        clear_recent_cache()
        result = await get_recent()

        assert "Recent" in result

    @pytest.mark.asyncio
    async def test_recent_returns_formatted_markdown(
        self, mock_config: dict, recent_memories: Path
    ) -> None:
        """Recent should return formatted markdown content."""
        clear_recent_cache()
        result = await get_recent()

        assert "Recent Memories" in result

    @pytest.mark.asyncio
    async def test_recent_respects_hours_parameter(
        self, mock_config: dict, tmp_path: Path
    ) -> None:
        """Recent should filter by hours parameter."""
        project_dir = tmp_path / "memory" / "project"
        project_dir.mkdir(parents=True)

        old_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")

        (project_dir / "old.md").write_text(
            f"""---
id: mem_old_001
tags: [old]
scope: project
status: active
created: {old_date}
last_used: {old_date}
---

# Old Memory

This is an old memory.
"""
        )

        clear_recent_cache()
        result = await get_recent(hours=24)

        assert "Old Memory" not in result or "No recent" in result


class TestConflictsResource:
    """Tests for memory://conflicts resource."""

    @pytest.mark.asyncio
    async def test_conflicts_resource_returns_formatted_output(self) -> None:
        """Conflicts resource should return formatted output."""
        clear_conflicts_cache()

        with patch.object(
            conflicts_resource, "execute_conflicts",
            new_callable=AsyncMock,
            return_value="## No Conflicts Detected\n\nAll good.",
        ):
            result = await get_conflicts()

        assert "Conflicts" in result or "Status" in result

    @pytest.mark.asyncio
    async def test_conflicts_resource_caches_results(self) -> None:
        """Conflicts resource should cache results."""
        clear_conflicts_cache()

        with patch.object(
            conflicts_resource, "execute_conflicts",
            new_callable=AsyncMock,
            return_value="## No Conflicts Detected",
        ) as mock_execute:
            result1 = await get_conflicts()
            result2 = await get_conflicts()

            assert mock_execute.call_count == 1

    @pytest.mark.asyncio
    async def test_conflicts_helper_functions(self) -> None:
        """Test conflicts helper functions."""
        from dmm.mcp.resources.conflicts import (
            get_conflict_count,
            has_critical_conflicts,
        )

        clear_conflicts_cache()

        assert get_conflict_count() == -1
        assert has_critical_conflicts() is False
