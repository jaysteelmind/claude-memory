"""Tests for MemoryCuratorAgent."""

import tempfile
from pathlib import Path

import pytest

from examples.agents.memory_curator_agent import (
    ConflictInfo,
    MemoryCuratorAgent,
    MemoryCuratorConfig,
    MemoryHealthStatus,
    MemoryStats,
)


class TestMemoryCuratorAgent:
    """Tests for MemoryCuratorAgent."""

    @pytest.fixture
    def temp_memory_dir(self) -> Path:
        """Create a temporary memory directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = Path(tmpdir)
            
            baseline_dir = memory_dir / "baseline"
            baseline_dir.mkdir(parents=True)
            
            project_dir = memory_dir / "project"
            project_dir.mkdir(parents=True)
            
            yield memory_dir

    @pytest.fixture
    def sample_memory_file(self, temp_memory_dir: Path) -> Path:
        """Create a sample memory file."""
        memory_file = temp_memory_dir / "project" / "test_memory.md"
        memory_file.write_text('''---
id: mem_test_001
tags: [test, sample]
scope: project
priority: 0.7
confidence: active
status: active
created: 2026-01-01
last_used: 2026-01-20
---

# Test Memory

This is a test memory file for testing purposes.
''')
        return memory_file

    def test_init_default_config(self, temp_memory_dir: Path) -> None:
        """Agent initializes with default config."""
        agent = MemoryCuratorAgent(memory_dir=temp_memory_dir)
        
        assert agent.config.stale_threshold_days == 30
        assert agent.config.conflict_confidence_threshold == 0.7

    def test_init_custom_config(self, temp_memory_dir: Path) -> None:
        """Agent initializes with custom config."""
        config = MemoryCuratorConfig(
            stale_threshold_days=14,
            conflict_confidence_threshold=0.8,
        )
        agent = MemoryCuratorAgent(
            memory_dir=temp_memory_dir,
            config=config,
        )
        
        assert agent.config.stale_threshold_days == 14

    def test_scan_memories_empty(self, temp_memory_dir: Path) -> None:
        """Scan returns zero for empty directory."""
        agent = MemoryCuratorAgent(memory_dir=temp_memory_dir)
        
        count = agent.scan_memories()
        
        assert count == 0

    def test_scan_memories_finds_files(
        self,
        temp_memory_dir: Path,
        sample_memory_file: Path,
    ) -> None:
        """Scan finds memory files."""
        agent = MemoryCuratorAgent(memory_dir=temp_memory_dir)
        
        count = agent.scan_memories()
        
        assert count == 1

    def test_scan_memories_caches_results(
        self,
        temp_memory_dir: Path,
        sample_memory_file: Path,
    ) -> None:
        """Scan caches results for quick access."""
        agent = MemoryCuratorAgent(memory_dir=temp_memory_dir)
        
        agent.scan_memories()
        
        assert len(agent._memory_cache) == 1
        assert "mem_test_001" in agent._memory_cache

    def test_get_stats(
        self,
        temp_memory_dir: Path,
        sample_memory_file: Path,
    ) -> None:
        """Get statistics about memories."""
        agent = MemoryCuratorAgent(memory_dir=temp_memory_dir)
        
        stats = agent.get_stats()
        
        assert isinstance(stats, MemoryStats)
        assert stats.total_memories == 1
        assert stats.by_scope.get("project", 0) == 1

    def test_check_health_healthy(
        self,
        temp_memory_dir: Path,
        sample_memory_file: Path,
    ) -> None:
        """Check health returns healthy status."""
        agent = MemoryCuratorAgent(memory_dir=temp_memory_dir)
        
        status, issues = agent.check_health()
        
        assert status == MemoryHealthStatus.HEALTHY
        assert len(issues) == 0

    def test_check_health_baseline_overflow(
        self,
        temp_memory_dir: Path,
    ) -> None:
        """Check health detects baseline overflow."""
        baseline_dir = temp_memory_dir / "baseline"
        
        large_content = "word " * 1000
        memory_file = baseline_dir / "large_memory.md"
        memory_file.write_text(f'''---
id: mem_large_001
tags: [test]
scope: baseline
priority: 0.9
confidence: stable
status: active
---

# Large Memory

{large_content}
''')
        
        config = MemoryCuratorConfig(max_baseline_tokens=100)
        agent = MemoryCuratorAgent(
            memory_dir=temp_memory_dir,
            config=config,
        )
        
        status, issues = agent.check_health()
        
        assert status in (MemoryHealthStatus.DEGRADED, MemoryHealthStatus.CRITICAL)
        assert any("baseline" in issue.lower() for issue in issues)

    def test_search_memories_by_query(
        self,
        temp_memory_dir: Path,
        sample_memory_file: Path,
    ) -> None:
        """Search memories by query text."""
        agent = MemoryCuratorAgent(memory_dir=temp_memory_dir)
        
        results = agent.search_memories(query="test")
        
        assert len(results) == 1
        assert results[0]["id"] == "mem_test_001"

    def test_search_memories_by_scope(
        self,
        temp_memory_dir: Path,
        sample_memory_file: Path,
    ) -> None:
        """Search memories filtered by scope."""
        agent = MemoryCuratorAgent(memory_dir=temp_memory_dir)
        
        project_results = agent.search_memories(scope="project")
        baseline_results = agent.search_memories(scope="baseline")
        
        assert len(project_results) == 1
        assert len(baseline_results) == 0

    def test_search_memories_by_tags(
        self,
        temp_memory_dir: Path,
        sample_memory_file: Path,
    ) -> None:
        """Search memories filtered by tags."""
        agent = MemoryCuratorAgent(memory_dir=temp_memory_dir)
        
        results = agent.search_memories(tags=["test"])
        no_results = agent.search_memories(tags=["nonexistent"])
        
        assert len(results) == 1
        assert len(no_results) == 0

    def test_search_memories_by_priority(
        self,
        temp_memory_dir: Path,
        sample_memory_file: Path,
    ) -> None:
        """Search memories filtered by minimum priority."""
        agent = MemoryCuratorAgent(memory_dir=temp_memory_dir)
        
        results = agent.search_memories(min_priority=0.5)
        no_results = agent.search_memories(min_priority=0.9)
        
        assert len(results) == 1
        assert len(no_results) == 0

    def test_find_potential_conflicts(
        self,
        temp_memory_dir: Path,
    ) -> None:
        """Find potential conflicts between memories."""
        project_dir = temp_memory_dir / "project"
        
        (project_dir / "mem1.md").write_text('''---
id: mem_001
tags: [config, settings, database]
scope: project
priority: 0.7
confidence: active
status: active
---

# Database Config

Always use connection pooling.
''')
        
        (project_dir / "mem2.md").write_text('''---
id: mem_002
tags: [config, settings, database]
scope: project
priority: 0.7
confidence: active
status: active
---

# Database Settings

Never use connection pooling.
''')
        
        agent = MemoryCuratorAgent(memory_dir=temp_memory_dir)
        
        conflicts = agent.find_potential_conflicts()
        
        assert len(conflicts) >= 1
        assert isinstance(conflicts[0], ConflictInfo)

    def test_get_stale_memories(
        self,
        temp_memory_dir: Path,
    ) -> None:
        """Get memories that haven't been used recently."""
        project_dir = temp_memory_dir / "project"
        
        (project_dir / "stale.md").write_text('''---
id: mem_stale_001
tags: [old]
scope: project
priority: 0.5
confidence: active
status: active
last_used: 2020-01-01
---

# Stale Memory

This is very old.
''')
        
        agent = MemoryCuratorAgent(memory_dir=temp_memory_dir)
        
        stale = agent.get_stale_memories()
        
        assert len(stale) >= 1

    def test_suggest_consolidation(
        self,
        temp_memory_dir: Path,
    ) -> None:
        """Suggest memories that could be consolidated."""
        project_dir = temp_memory_dir / "project"
        
        for i in range(4):
            (project_dir / f"mem_{i}.md").write_text(f'''---
id: mem_consolidate_{i}
tags: [common-tag, testing]
scope: project
priority: 0.5
confidence: active
status: active
---

# Memory {i}

Content for memory {i}.
''')
        
        agent = MemoryCuratorAgent(memory_dir=temp_memory_dir)
        
        suggestions = agent.suggest_consolidation()
        
        assert len(suggestions) >= 1

    def test_generate_health_report(
        self,
        temp_memory_dir: Path,
        sample_memory_file: Path,
    ) -> None:
        """Generate health report."""
        agent = MemoryCuratorAgent(memory_dir=temp_memory_dir)
        
        report = agent.generate_health_report()
        
        assert "# Memory System Health Report" in report
        assert "## Overall Status" in report
        assert "## Statistics" in report


class TestMemoryStats:
    """Tests for MemoryStats dataclass."""

    def test_to_dict(self) -> None:
        """MemoryStats converts to dictionary."""
        stats = MemoryStats(
            total_memories=10,
            by_scope={"project": 5, "global": 5},
            by_status={"active": 10},
            total_tokens=5000,
            avg_tokens_per_memory=500.0,
            conflicts_unresolved=2,
            stale_memories=3,
        )
        
        data = stats.to_dict()
        
        assert data["total_memories"] == 10
        assert data["by_scope"]["project"] == 5
        assert data["conflicts_unresolved"] == 2
