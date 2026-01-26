"""Unit tests for skill registry."""

import pytest
from pathlib import Path
import tempfile

from dmm.agentos.skills.registry import (
    DependencyCheck,
    SkillRegistry,
    SkillRegistryStats,
    SyncResult,
)
from dmm.agentos.skills.models import Skill, SkillDependencies, ToolRequirements


class TestSkillRegistry:
    """Tests for SkillRegistry class."""

    def create_temp_skills_dir(self, tmpdir: Path) -> Path:
        """Create a temporary skills directory with test skills."""
        skills_dir = tmpdir / "skills"
        core_dir = skills_dir / "core"
        core_dir.mkdir(parents=True)

        # Create test skill files
        skill1 = core_dir / "skill1.skill.yaml"
        skill1.write_text("""
id: skill_one
name: Skill One
description: First test skill
category: general
tags:
  - test
  - basic
""")

        skill2 = core_dir / "skill2.skill.yaml"
        skill2.write_text("""
id: skill_two
name: Skill Two
description: Second test skill
category: quality
tags:
  - test
  - quality
dependencies:
  skills:
    - skill_one
  tools:
    required:
      - tool_test
""")

        return skills_dir

    def test_init(self):
        """Test registry initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / "skills"
            skills_dir.mkdir()
            
            registry = SkillRegistry(skills_dir)
            assert registry.skills_dir == skills_dir
            assert registry.is_loaded is False

    def test_load_all(self):
        """Test loading all skills."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            
            skills = registry.load_all()
            assert len(skills) == 2
            assert registry.is_loaded is True

    def test_load_skill_by_id(self):
        """Test loading a specific skill."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            
            skill = registry.load_skill("skill_one")
            assert skill is not None
            assert skill.id == "skill_one"

    def test_load_skill_not_found(self):
        """Test loading non-existent skill returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            
            skill = registry.load_skill("skill_nonexistent")
            assert skill is None

    def test_reload(self):
        """Test reloading skills."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            
            registry.load_all()
            assert registry.is_loaded is True
            
            skills = registry.reload()
            assert len(skills) == 2
            assert registry.is_loaded is True

    def test_find_by_id(self):
        """Test finding skill by ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            registry.load_all()
            
            skill = registry.find_by_id("skill_one")
            assert skill is not None
            assert skill.name == "Skill One"

    def test_find_by_id_not_found(self):
        """Test finding non-existent skill returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            registry.load_all()
            
            skill = registry.find_by_id("skill_nonexistent")
            assert skill is None

    def test_find_by_tags_any(self):
        """Test finding skills by tags (any match)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            registry.load_all()
            
            skills = registry.find_by_tags(["test"])
            assert len(skills) == 2

    def test_find_by_tags_all(self):
        """Test finding skills by tags (all must match)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            registry.load_all()
            
            skills = registry.find_by_tags(["test", "quality"], match_all=True)
            assert len(skills) == 1
            assert skills[0].id == "skill_two"

    def test_find_by_category(self):
        """Test finding skills by category."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            registry.load_all()
            
            skills = registry.find_by_category("quality")
            assert len(skills) == 1
            assert skills[0].id == "skill_two"

    def test_search(self):
        """Test searching skills."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            registry.load_all()
            
            results = registry.search("One")
            assert len(results) >= 1
            assert results[0].id == "skill_one"

    def test_search_with_filters(self):
        """Test searching with filters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            registry.load_all()
            
            results = registry.search("skill", category="quality")
            assert len(results) == 1
            assert results[0].category == "quality"

    def test_get_dependencies_direct(self):
        """Test getting direct dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            registry.load_all()
            
            deps = registry.get_dependencies("skill_two", transitive=False)
            assert len(deps) == 1
            assert deps[0].id == "skill_one"

    def test_get_dependencies_transitive(self):
        """Test getting transitive dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            registry.load_all()
            
            deps = registry.get_dependencies("skill_two", transitive=True)
            assert len(deps) == 1  # skill_one has no deps

    def test_get_execution_order(self):
        """Test getting execution order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            registry.load_all()
            
            order = registry.get_execution_order(["skill_two"])
            assert len(order) >= 1
            # skill_one should come before skill_two
            ids = [s.id for s in order]
            if "skill_one" in ids and "skill_two" in ids:
                assert ids.index("skill_one") < ids.index("skill_two")

    def test_check_dependencies_satisfied(self):
        """Test checking satisfied dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            registry.load_all()
            
            check = registry.check_dependencies(
                "skill_two",
                available_tools=["tool_test"],
            )
            assert check.satisfied is True
            assert "skill_one" in check.available_skills

    def test_check_dependencies_missing_tool(self):
        """Test checking with missing tool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            registry.load_all()
            
            check = registry.check_dependencies(
                "skill_two",
                available_tools=[],
            )
            assert check.satisfied is False
            assert "tool_test" in check.missing_tools

    def test_enable_disable(self):
        """Test enabling and disabling skills."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            registry.load_all()
            
            assert registry.disable("skill_one") is True
            skill = registry.find_by_id("skill_one")
            assert skill.enabled is False
            
            assert registry.enable("skill_one") is True
            skill = registry.find_by_id("skill_one")
            assert skill.enabled is True

    def test_enable_nonexistent(self):
        """Test enabling non-existent skill."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            registry.load_all()
            
            assert registry.enable("skill_nonexistent") is False

    def test_list_all(self):
        """Test listing all skills."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            registry.load_all()
            
            all_skills = registry.list_all()
            assert len(all_skills) == 2

    def test_list_all_enabled_only(self):
        """Test listing only enabled skills."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            registry.load_all()
            
            registry.disable("skill_one")
            enabled = registry.list_all(enabled_only=True)
            assert len(enabled) == 1

    def test_get_stats(self):
        """Test getting registry statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            registry.load_all()
            
            stats = registry.get_stats()
            assert stats.total_skills == 2
            assert stats.enabled_skills == 2
            assert stats.disabled_skills == 0
            assert "general" in stats.skills_by_category
            assert "quality" in stats.skills_by_category

    def test_sync_to_graph_no_store(self):
        """Test syncing without graph store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = self.create_temp_skills_dir(Path(tmpdir))
            registry = SkillRegistry(skills_dir)
            registry.load_all()
            
            result = registry.sync_to_graph()
            assert result.skills_synced == 0
            assert "No graph store configured" in result.errors


class TestDependencyCheck:
    """Tests for DependencyCheck dataclass."""

    def test_default_satisfied(self):
        """Test default is satisfied."""
        check = DependencyCheck()
        assert check.satisfied is True
        assert check.missing_skills == []
        assert check.missing_tools == []


class TestSyncResult:
    """Tests for SyncResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = SyncResult()
        assert result.skills_synced == 0
        assert result.edges_created == 0
        assert result.errors == []


class TestSkillRegistryStats:
    """Tests for SkillRegistryStats dataclass."""

    def test_default_values(self):
        """Test default values."""
        stats = SkillRegistryStats()
        assert stats.total_skills == 0
        assert stats.enabled_skills == 0
        assert stats.skills_by_category == {}
