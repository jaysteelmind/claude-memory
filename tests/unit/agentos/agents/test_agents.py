"""Unit tests for agents module."""

import pytest
from pathlib import Path
import tempfile

from dmm.agentos.agents.models import (
    AGENT_CATEGORIES,
    BEHAVIOR_TONES,
    VERBOSITY_LEVELS,
    Agent,
    AgentConstraints,
    BehaviorConfig,
    MemoryConfig,
    SkillsConfig,
    ToolsConfig,
)
from dmm.agentos.agents.loader import (
    AgentLoader,
    AgentLoadError,
    AgentValidationError,
)
from dmm.agentos.agents.registry import (
    AgentRegistry,
    AgentRegistryStats,
    ValidationResult,
)
from dmm.agentos.agents.matcher import (
    AgentMatch,
    AgentMatcher,
)


class TestSkillsConfig:
    """Tests for SkillsConfig dataclass."""

    def test_create_empty(self):
        """Test creating empty skills config."""
        config = SkillsConfig()
        assert config.primary == []
        assert config.secondary == []
        assert config.disabled == []

    def test_create_with_skills(self):
        """Test creating with skill lists."""
        config = SkillsConfig(
            primary=["skill_review"],
            secondary=["skill_format"],
            disabled=["skill_deprecated"],
        )
        assert "skill_review" in config.primary
        assert "skill_format" in config.secondary

    def test_get_all_enabled(self):
        """Test getting all enabled skills."""
        config = SkillsConfig(
            primary=["skill_a"],
            secondary=["skill_b"],
        )
        enabled = config.get_all_enabled()
        assert "skill_a" in enabled
        assert "skill_b" in enabled

    def test_is_enabled(self):
        """Test checking if skill is enabled."""
        config = SkillsConfig(
            primary=["skill_a"],
            disabled=["skill_c"],
        )
        assert config.is_enabled("skill_a") is True
        assert config.is_enabled("skill_c") is False
        assert config.is_enabled("skill_unknown") is False


class TestToolsConfig:
    """Tests for ToolsConfig dataclass."""

    def test_create_empty(self):
        """Test creating empty tools config."""
        config = ToolsConfig()
        assert config.enabled == []
        assert config.disabled == []

    def test_is_enabled_explicit(self):
        """Test checking explicitly enabled tool."""
        config = ToolsConfig(enabled=["tool_a"])
        assert config.is_enabled("tool_a") is True
        assert config.is_enabled("tool_b") is False

    def test_is_enabled_all_allowed(self):
        """Test that empty enabled list allows all."""
        config = ToolsConfig()
        assert config.is_enabled("tool_any") is True

    def test_is_enabled_disabled(self):
        """Test that disabled tools are not enabled."""
        config = ToolsConfig(disabled=["tool_blocked"])
        assert config.is_enabled("tool_blocked") is False
        assert config.is_enabled("tool_other") is True


class TestMemoryConfig:
    """Tests for MemoryConfig dataclass."""

    def test_defaults(self):
        """Test default memory config."""
        config = MemoryConfig()
        assert config.max_context_tokens == 8000
        assert config.required_scopes == []

    def test_with_scopes(self):
        """Test memory config with scopes."""
        config = MemoryConfig(
            required_scopes=["project"],
            preferred_scopes=["user"],
            excluded_scopes=["global"],
        )
        assert "project" in config.required_scopes
        assert "global" in config.excluded_scopes


class TestBehaviorConfig:
    """Tests for BehaviorConfig dataclass."""

    def test_defaults(self):
        """Test default behavior config."""
        config = BehaviorConfig()
        assert config.tone == "professional"
        assert config.verbosity == "normal"

    def test_invalid_tone_fallback(self):
        """Test that invalid tone falls back to professional."""
        config = BehaviorConfig(tone="invalid")
        assert config.tone == "professional"

    def test_with_guidelines(self):
        """Test behavior with guidelines."""
        config = BehaviorConfig(
            tone="technical",
            guidelines=["Be precise", "Use examples"],
        )
        assert config.tone == "technical"
        assert len(config.guidelines) == 2


class TestAgentConstraints:
    """Tests for AgentConstraints dataclass."""

    def test_defaults(self):
        """Test default constraints."""
        constraints = AgentConstraints()
        assert constraints.max_context_tokens == 8000
        assert constraints.allow_tool_execution is True
        assert constraints.allow_memory_write is True

    def test_restricted(self):
        """Test restricted constraints."""
        constraints = AgentConstraints(
            allow_tool_execution=False,
            allow_memory_write=False,
            allowed_scopes=["project"],
        )
        assert constraints.allow_tool_execution is False
        assert "project" in constraints.allowed_scopes


class TestAgent:
    """Tests for Agent dataclass."""

    def test_create_minimal(self):
        """Test creating minimal agent."""
        agent = Agent(
            id="agent_test",
            name="Test Agent",
            version="1.0.0",
            description="A test agent",
            category="general",
        )
        assert agent.id == "agent_test"
        assert agent.enabled is True

    def test_create_full(self):
        """Test creating fully configured agent."""
        agent = Agent(
            id="agent_reviewer",
            name="Code Reviewer",
            version="1.0.0",
            description="Reviews code",
            category="quality",
            skills=SkillsConfig(primary=["skill_review"]),
            tools=ToolsConfig(enabled=["tool_ruff"]),
            behavior=BehaviorConfig(tone="professional"),
        )
        assert agent.category == "quality"
        assert "skill_review" in agent.skills.primary

    def test_invalid_category_fallback(self):
        """Test that invalid category falls back to general."""
        agent = Agent(
            id="agent_test",
            name="Test",
            version="1.0.0",
            description="Test",
            category="invalid",
        )
        assert agent.category == "general"

    def test_to_dict(self):
        """Test serialization to dict."""
        agent = Agent(
            id="agent_test",
            name="Test",
            version="1.0.0",
            description="Test",
            category="general",
        )
        data = agent.to_dict()
        assert data["id"] == "agent_test"
        assert "skills" in data
        assert "behavior" in data

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "id": "agent_test",
            "name": "Test",
            "version": "1.0.0",
            "description": "Test agent",
            "category": "general",
            "tags": ["test"],
        }
        agent = Agent.from_dict(data)
        assert agent.id == "agent_test"
        assert "test" in agent.tags

    def test_can_use_skill(self):
        """Test skill access check."""
        agent = Agent(
            id="agent_test",
            name="Test",
            version="1.0.0",
            description="Test",
            category="general",
            skills=SkillsConfig(
                primary=["skill_a"],
                disabled=["skill_c"],
            ),
        )
        assert agent.can_use_skill("skill_a") is True
        assert agent.can_use_skill("skill_c") is False

    def test_can_use_tool(self):
        """Test tool access check."""
        agent = Agent(
            id="agent_test",
            name="Test",
            version="1.0.0",
            description="Test",
            category="general",
            tools=ToolsConfig(disabled=["tool_blocked"]),
        )
        assert agent.can_use_tool("tool_any") is True
        assert agent.can_use_tool("tool_blocked") is False

    def test_can_access_scope(self):
        """Test scope access check."""
        agent = Agent(
            id="agent_test",
            name="Test",
            version="1.0.0",
            description="Test",
            category="general",
            memory=MemoryConfig(excluded_scopes=["secret"]),
        )
        assert agent.can_access_scope("project") is True
        assert agent.can_access_scope("secret") is False

    def test_get_system_prompt_additions(self):
        """Test system prompt generation."""
        agent = Agent(
            id="agent_test",
            name="Test",
            version="1.0.0",
            description="Test",
            category="general",
            behavior=BehaviorConfig(
                tone="technical",
                focus_areas=["security"],
                guidelines=["Be thorough"],
            ),
        )
        prompt = agent.get_system_prompt_additions()
        assert "technical" in prompt
        assert "security" in prompt
        assert "Be thorough" in prompt


class TestAgentLoader:
    """Tests for AgentLoader class."""

    def test_parse_minimal(self):
        """Test parsing minimal agent YAML."""
        loader = AgentLoader()
        content = """
id: agent_test
name: Test Agent
description: A test agent
category: general
"""
        agent = loader.parse(content)
        assert agent.id == "agent_test"
        assert agent.category == "general"

    def test_parse_full(self):
        """Test parsing full agent YAML."""
        loader = AgentLoader()
        content = """
id: agent_reviewer
name: Code Reviewer
description: Reviews code quality
category: quality
tags:
  - code-review
  - quality
skills:
  primary:
    - skill_review
  secondary:
    - skill_format
tools:
  enabled:
    - tool_ruff
memory:
  required_scopes:
    - project
  preferred_tags:
    - standards
behavior:
  tone: professional
  verbosity: detailed
  focus_areas:
    - code quality
  guidelines:
    - Be constructive
constraints:
  allow_tool_execution: true
  max_context_tokens: 8000
"""
        agent = loader.parse(content)
        assert agent.id == "agent_reviewer"
        assert "skill_review" in agent.skills.primary
        assert "tool_ruff" in agent.tools.enabled
        assert agent.behavior.tone == "professional"

    def test_parse_missing_id(self):
        """Test that missing ID raises error."""
        loader = AgentLoader()
        content = """
name: Test Agent
description: A test agent
category: general
"""
        with pytest.raises(AgentLoadError, match="Missing required field: id"):
            loader.parse(content)

    def test_parse_invalid_id_prefix(self):
        """Test that invalid ID prefix raises error in strict mode."""
        loader = AgentLoader(strict=True)
        content = """
id: test_agent
name: Test Agent
description: A test agent
category: general
"""
        with pytest.raises(AgentValidationError, match="must start with 'agent_'"):
            loader.parse(content)

    def test_load_directory(self):
        """Test loading agents from directory."""
        loader = AgentLoader()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            agent1 = tmppath / "agent1.agent.yaml"
            agent1.write_text("""
id: agent_one
name: Agent One
description: First agent
category: general
""")
            
            agents = loader.load_directory(tmppath)
            assert len(agents) == 1


class TestAgentRegistry:
    """Tests for AgentRegistry class."""

    def create_temp_agents_dir(self, tmpdir: Path) -> Path:
        """Create a temporary agents directory with test agents."""
        agents_dir = tmpdir / "agents"
        agents_dir.mkdir(parents=True)

        agent1 = agents_dir / "agent1.agent.yaml"
        agent1.write_text("""
id: agent_one
name: Agent One
description: First test agent
category: general
tags:
  - test
skills:
  primary:
    - skill_basic
""")

        agent2 = agents_dir / "agent2.agent.yaml"
        agent2.write_text("""
id: agent_two
name: Agent Two
description: Second test agent
category: quality
tags:
  - test
  - quality
skills:
  primary:
    - skill_review
tools:
  enabled:
    - tool_ruff
""")

        return agents_dir

    def test_load_all(self):
        """Test loading all agents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = self.create_temp_agents_dir(Path(tmpdir))
            registry = AgentRegistry(agents_dir)
            
            agents = registry.load_all()
            assert len(agents) == 2
            assert registry.is_loaded is True

    def test_find_by_id(self):
        """Test finding agent by ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = self.create_temp_agents_dir(Path(tmpdir))
            registry = AgentRegistry(agents_dir)
            registry.load_all()
            
            agent = registry.find_by_id("agent_one")
            assert agent is not None
            assert agent.name == "Agent One"

    def test_find_by_category(self):
        """Test finding agents by category."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = self.create_temp_agents_dir(Path(tmpdir))
            registry = AgentRegistry(agents_dir)
            registry.load_all()
            
            agents = registry.find_by_category("quality")
            assert len(agents) == 1
            assert agents[0].id == "agent_two"

    def test_find_by_skill(self):
        """Test finding agents by skill."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = self.create_temp_agents_dir(Path(tmpdir))
            registry = AgentRegistry(agents_dir)
            registry.load_all()
            
            agents = registry.find_by_skill("skill_review")
            assert len(agents) == 1
            assert agents[0].id == "agent_two"

    def test_find_by_tool(self):
        """Test finding agents by tool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = self.create_temp_agents_dir(Path(tmpdir))
            registry = AgentRegistry(agents_dir)
            registry.load_all()
            
            # Both agents can use tool_ruff - agent_two explicitly enables it,
            # agent_one has empty enabled list which allows all tools
            agents = registry.find_by_tool("tool_ruff")
            assert len(agents) == 2

    def test_search(self):
        """Test searching agents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = self.create_temp_agents_dir(Path(tmpdir))
            registry = AgentRegistry(agents_dir)
            registry.load_all()
            
            results = registry.search("One")
            assert len(results) >= 1

    def test_get_default_agent(self):
        """Test getting default agent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = self.create_temp_agents_dir(Path(tmpdir))
            registry = AgentRegistry(agents_dir)
            registry.load_all()
            
            default = registry.get_default_agent()
            assert default is not None

    def test_enable_disable(self):
        """Test enabling and disabling agents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = self.create_temp_agents_dir(Path(tmpdir))
            registry = AgentRegistry(agents_dir)
            registry.load_all()
            
            assert registry.disable("agent_one") is True
            agent = registry.find_by_id("agent_one")
            assert agent.enabled is False

    def test_get_stats(self):
        """Test getting registry statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = self.create_temp_agents_dir(Path(tmpdir))
            registry = AgentRegistry(agents_dir)
            registry.load_all()
            
            stats = registry.get_stats()
            assert stats.total_agents == 2
            assert "general" in stats.agents_by_category


class TestAgentMatcher:
    """Tests for AgentMatcher class."""

    def create_registry_with_agents(self, tmpdir: Path) -> AgentRegistry:
        """Create a registry with test agents."""
        agents_dir = tmpdir / "agents"
        agents_dir.mkdir(parents=True)

        agent1 = agents_dir / "reviewer.agent.yaml"
        agent1.write_text("""
id: agent_reviewer
name: Code Reviewer
description: Reviews code for quality and best practices
category: quality
tags:
  - review
  - quality
skills:
  primary:
    - skill_review
behavior:
  focus_areas:
    - code quality
    - best practices
""")

        agent2 = agents_dir / "writer.agent.yaml"
        agent2.write_text("""
id: agent_writer
name: Documentation Writer
description: Writes documentation and guides
category: documentation
tags:
  - docs
  - writing
skills:
  primary:
    - skill_docs
behavior:
  focus_areas:
    - documentation
    - clarity
""")

        registry = AgentRegistry(agents_dir)
        registry.load_all()
        return registry

    def test_find_for_task(self):
        """Test finding agents for a task."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = self.create_registry_with_agents(Path(tmpdir))
            matcher = AgentMatcher(registry)
            
            matches = matcher.find_for_task("review code quality")
            assert len(matches) >= 1
            # Code reviewer should rank high for this task
            assert any(m.agent.id == "agent_reviewer" for m in matches)

    def test_find_for_task_with_category(self):
        """Test finding agents with category preference."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = self.create_registry_with_agents(Path(tmpdir))
            matcher = AgentMatcher(registry)
            
            matches = matcher.find_for_task(
                "write something",
                preferred_category="documentation",
            )
            assert len(matches) >= 1

    def test_match_by_skills(self):
        """Test matching by skills."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = self.create_registry_with_agents(Path(tmpdir))
            matcher = AgentMatcher(registry)
            
            matches = matcher.match_by_skills(["skill_review"])
            assert len(matches) == 1
            assert matches[0].agent.id == "agent_reviewer"

    def test_match_by_capability(self):
        """Test matching by capability."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = self.create_registry_with_agents(Path(tmpdir))
            matcher = AgentMatcher(registry)
            
            matches = matcher.match_by_capability(["quality", "review"])
            assert len(matches) >= 1

    def test_get_best_agent(self):
        """Test getting best agent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = self.create_registry_with_agents(Path(tmpdir))
            matcher = AgentMatcher(registry)
            
            best = matcher.get_best_agent("review my code")
            assert best is not None


class TestConstants:
    """Tests for module constants."""

    def test_agent_categories(self):
        """Test AGENT_CATEGORIES contains expected values."""
        assert "general" in AGENT_CATEGORIES
        assert "quality" in AGENT_CATEGORIES
        assert "documentation" in AGENT_CATEGORIES

    def test_behavior_tones(self):
        """Test BEHAVIOR_TONES contains expected values."""
        assert "professional" in BEHAVIOR_TONES
        assert "technical" in BEHAVIOR_TONES

    def test_verbosity_levels(self):
        """Test VERBOSITY_LEVELS contains expected values."""
        assert "normal" in VERBOSITY_LEVELS
        assert "detailed" in VERBOSITY_LEVELS
