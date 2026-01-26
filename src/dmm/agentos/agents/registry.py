"""Agent registry for the Agent OS.

This module provides the AgentRegistry class which manages:
- Loading agents from the filesystem
- Caching loaded agents
- Syncing agents to the knowledge graph
- Agent discovery and validation
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from dmm.agentos.agents.loader import AgentLoader, AgentLoadError, AgentValidationError
from dmm.agentos.agents.models import Agent
from dmm.graph.nodes import AgentNode
from dmm.graph.edges import HasSkill, HasTool, PrefersScope


@dataclass
class SyncResult:
    """Result of syncing agents to the graph.

    Attributes:
        agents_synced: Number of agents synced.
        edges_created: Number of edges created.
        errors: List of error messages.
        duration_ms: Sync duration in milliseconds.
    """

    agents_synced: int = 0
    edges_created: int = 0
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class ValidationResult:
    """Result of validating an agent.

    Attributes:
        valid: Whether the agent is valid.
        errors: List of error messages.
        warnings: List of warning messages.
        missing_skills: Skills referenced but not found.
        missing_tools: Tools referenced but not found.
    """

    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    missing_tools: list[str] = field(default_factory=list)


@dataclass
class AgentRegistryStats:
    """Statistics about the agent registry.

    Attributes:
        total_agents: Total number of registered agents.
        enabled_agents: Number of enabled agents.
        disabled_agents: Number of disabled agents.
        agents_by_category: Count of agents per category.
    """

    total_agents: int = 0
    enabled_agents: int = 0
    disabled_agents: int = 0
    agents_by_category: dict[str, int] = field(default_factory=dict)


class AgentRegistry:
    """Registry for managing agents.

    The AgentRegistry is responsible for:
    - Loading agents from .dmm/agents/ directory
    - Caching loaded agents in memory
    - Syncing agents to the knowledge graph
    - Validating agent configurations
    - Providing agent discovery and lookup
    """

    def __init__(
        self,
        agents_dir: Path,
        graph_store: Optional[Any] = None,
        skill_registry: Optional[Any] = None,
        tool_registry: Optional[Any] = None,
        strict: bool = False,
    ) -> None:
        """Initialize the agent registry.

        Args:
            agents_dir: Path to the agents directory.
            graph_store: Optional KnowledgeGraphStore for graph integration.
            skill_registry: Optional SkillRegistry for validation.
            tool_registry: Optional ToolRegistry for validation.
            strict: If True, raise errors on invalid agents.
        """
        self._agents_dir = agents_dir
        self._graph_store = graph_store
        self._skill_registry = skill_registry
        self._tool_registry = tool_registry
        self._strict = strict
        self._loader = AgentLoader(strict=strict)
        self._cache: dict[str, Agent] = {}
        self._loaded = False

    @property
    def agents_dir(self) -> Path:
        """Get the agents directory path."""
        return self._agents_dir

    @property
    def is_loaded(self) -> bool:
        """Check if agents have been loaded."""
        return self._loaded

    # === Loading ===

    def load_all(self) -> list[Agent]:
        """Load all agents from the agents directory.

        Returns:
            List of loaded Agent objects.
        """
        self._cache.clear()
        agents: list[Agent] = []

        if self._agents_dir.exists():
            for agent in self._loader.load_directory(self._agents_dir):
                self._cache[agent.id] = agent
                agents.append(agent)

        self._loaded = True
        return agents

    def load_agent(self, agent_id: str) -> Optional[Agent]:
        """Load a specific agent by ID.

        Args:
            agent_id: The agent identifier.

        Returns:
            Agent object if found, None otherwise.
        """
        if agent_id in self._cache:
            return self._cache[agent_id]

        if not self._agents_dir.exists():
            return None

        for path in self._agents_dir.rglob("*.agent.yaml"):
            try:
                agent = self._loader.load(path)
                if agent.id == agent_id:
                    self._cache[agent.id] = agent
                    return agent
            except (AgentLoadError, AgentValidationError):
                continue

        return None

    def reload(self) -> list[Agent]:
        """Reload all agents from the filesystem.

        Returns:
            List of reloaded Agent objects.
        """
        self._loaded = False
        return self.load_all()

    # === Graph Integration ===

    def sync_to_graph(self) -> SyncResult:
        """Sync all loaded agents to the knowledge graph.

        Creates:
        - AgentNode for each agent
        - HAS_SKILL edges to skills
        - HAS_TOOL edges to tools
        - PREFERS_SCOPE edges to scopes

        Returns:
            SyncResult with statistics.
        """
        start = time.perf_counter()
        result = SyncResult()

        if self._graph_store is None:
            result.errors.append("No graph store configured")
            return result

        if not self._loaded:
            self.load_all()

        for agent in self._cache.values():
            try:
                self._index_agent(agent)
                result.agents_synced += 1

                # Create skill edges
                for skill_id in agent.skills.primary:
                    try:
                        edge = HasSkill(
                            from_id=agent.id,
                            to_id=skill_id,
                            proficiency="primary",
                        )
                        self._graph_store.create_edge(
                            edge.edge_type,
                            edge.from_id,
                            edge.to_id,
                            edge.to_cypher_params(),
                        )
                        result.edges_created += 1
                    except Exception as e:
                        result.errors.append(
                            f"Failed to create skill edge {agent.id} -> {skill_id}: {e}"
                        )

                for skill_id in agent.skills.secondary:
                    try:
                        edge = HasSkill(
                            from_id=agent.id,
                            to_id=skill_id,
                            proficiency="secondary",
                        )
                        self._graph_store.create_edge(
                            edge.edge_type,
                            edge.from_id,
                            edge.to_id,
                            edge.to_cypher_params(),
                        )
                        result.edges_created += 1
                    except Exception as e:
                        result.errors.append(
                            f"Failed to create skill edge {agent.id} -> {skill_id}: {e}"
                        )

                # Create tool edges
                for tool_id in agent.tools.enabled:
                    try:
                        edge = HasTool(
                            from_id=agent.id,
                            to_id=tool_id,
                            enabled=True,
                        )
                        self._graph_store.create_edge(
                            edge.edge_type,
                            edge.from_id,
                            edge.to_id,
                            edge.to_cypher_params(),
                        )
                        result.edges_created += 1
                    except Exception as e:
                        result.errors.append(
                            f"Failed to create tool edge {agent.id} -> {tool_id}: {e}"
                        )

                # Create scope preference edges
                for scope in agent.memory.required_scopes:
                    try:
                        edge = PrefersScope(
                            from_id=agent.id,
                            to_id=f"scope_{scope}",
                            required=True,
                            priority=1,
                        )
                        self._graph_store.create_edge(
                            edge.edge_type,
                            edge.from_id,
                            edge.to_id,
                            edge.to_cypher_params(),
                        )
                        result.edges_created += 1
                    except Exception as e:
                        result.errors.append(
                            f"Failed to create scope edge {agent.id} -> {scope}: {e}"
                        )

                for scope in agent.memory.preferred_scopes:
                    try:
                        edge = PrefersScope(
                            from_id=agent.id,
                            to_id=f"scope_{scope}",
                            required=False,
                            priority=0,
                        )
                        self._graph_store.create_edge(
                            edge.edge_type,
                            edge.from_id,
                            edge.to_id,
                            edge.to_cypher_params(),
                        )
                        result.edges_created += 1
                    except Exception as e:
                        result.errors.append(
                            f"Failed to create scope edge {agent.id} -> {scope}: {e}"
                        )

            except Exception as e:
                result.errors.append(f"Failed to sync agent {agent.id}: {e}")

        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    def _index_agent(self, agent: Agent) -> None:
        """Index a single agent in the graph."""
        if self._graph_store is None:
            return

        skills_json, tools_json, memory_json, behavior_json, constraints_json = agent.to_json_configs()

        node = AgentNode(
            id=agent.id,
            name=agent.name,
            version=agent.version,
            description=agent.description,
            category=agent.category,
            tags=agent.tags,
            enabled=agent.enabled,
            skills_json=skills_json,
            tools_json=tools_json,
            memory_config_json=memory_json,
            behavior_json=behavior_json,
            constraints_json=constraints_json,
            file_path=agent.file_path,
            created=agent.created,
            updated=agent.updated,
        )

        self._graph_store.upsert_agent_node(node)

    # === Validation ===

    def validate_agent(self, agent_id: str) -> ValidationResult:
        """Validate an agent configuration.

        Checks:
        - All referenced skills exist
        - All referenced tools exist
        - No conflicting constraints

        Args:
            agent_id: Agent to validate.

        Returns:
            ValidationResult with errors and warnings.
        """
        result = ValidationResult()

        agent = self.find_by_id(agent_id)
        if not agent:
            result.valid = False
            result.errors.append(f"Agent not found: {agent_id}")
            return result

        # Validate skills
        if self._skill_registry:
            for skill_id in agent.get_all_skill_ids():
                skill = self._skill_registry.find_by_id(skill_id)
                if not skill:
                    result.missing_skills.append(skill_id)
                    result.warnings.append(f"Skill not found: {skill_id}")

            for skill_id in agent.skills.disabled:
                skill = self._skill_registry.find_by_id(skill_id)
                if not skill:
                    result.warnings.append(f"Disabled skill not found: {skill_id}")

        # Validate tools
        if self._tool_registry:
            for tool_id in agent.tools.enabled:
                tool = self._tool_registry.find_by_id(tool_id)
                if not tool:
                    result.missing_tools.append(tool_id)
                    result.warnings.append(f"Tool not found: {tool_id}")

            for tool_id in agent.tools.disabled:
                tool = self._tool_registry.find_by_id(tool_id)
                if not tool:
                    result.warnings.append(f"Disabled tool not found: {tool_id}")

        # Check for conflicting configurations
        if agent.constraints.allow_tool_execution and not agent.tools.enabled:
            result.warnings.append(
                "Tool execution enabled but no tools explicitly enabled"
            )

        if not agent.constraints.allow_memory_write and agent.memory.required_scopes:
            result.warnings.append(
                "Memory write disabled but agent has required memory scopes"
            )

        # Mark as invalid if there are errors (missing skills/tools can be warnings)
        if result.errors:
            result.valid = False

        return result

    # === Discovery ===

    def find_by_id(self, agent_id: str) -> Optional[Agent]:
        """Find an agent by exact ID."""
        if not self._loaded:
            self.load_all()
        return self._cache.get(agent_id)

    def find_by_category(self, category: str) -> list[Agent]:
        """Find agents by category."""
        if not self._loaded:
            self.load_all()
        return [a for a in self._cache.values() if a.category.lower() == category.lower()]

    def find_by_skill(self, skill_id: str) -> list[Agent]:
        """Find agents that have a specific skill."""
        if not self._loaded:
            self.load_all()
        return [
            a for a in self._cache.values()
            if a.can_use_skill(skill_id)
        ]

    def find_by_tool(self, tool_id: str) -> list[Agent]:
        """Find agents that can use a specific tool."""
        if not self._loaded:
            self.load_all()
        return [
            a for a in self._cache.values()
            if a.can_use_tool(tool_id)
        ]

    def search(
        self,
        query: str,
        enabled_only: bool = True,
        category: Optional[str] = None,
    ) -> list[Agent]:
        """Search agents by name, description, or tags."""
        if not self._loaded:
            self.load_all()

        query_lower = query.lower()
        results: list[tuple[Agent, int]] = []

        for agent in self._cache.values():
            if enabled_only and not agent.enabled:
                continue
            if category and agent.category.lower() != category.lower():
                continue

            score = 0
            if query_lower == agent.id.lower():
                score += 100
            if query_lower in agent.name.lower():
                score += 50
            if query_lower in agent.description.lower():
                score += 20
            for tag in agent.tags:
                if query_lower in tag.lower():
                    score += 10

            if score > 0:
                results.append((agent, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return [agent for agent, _ in results]

    def get_default_agent(self) -> Optional[Agent]:
        """Get the default agent."""
        if not self._loaded:
            self.load_all()

        # Look for agent_default
        default = self._cache.get("agent_default")
        if default:
            return default

        # Return first enabled agent
        for agent in self._cache.values():
            if agent.enabled:
                return agent

        return None

    # === Management ===

    def enable(self, agent_id: str) -> bool:
        """Enable an agent."""
        agent = self._cache.get(agent_id)
        if agent:
            agent.enabled = True
            return True
        return False

    def disable(self, agent_id: str) -> bool:
        """Disable an agent."""
        agent = self._cache.get(agent_id)
        if agent:
            agent.enabled = False
            return True
        return False

    def list_all(
        self,
        enabled_only: bool = False,
        category: Optional[str] = None,
    ) -> list[Agent]:
        """List all registered agents."""
        if not self._loaded:
            self.load_all()

        results: list[Agent] = []
        for agent in self._cache.values():
            if enabled_only and not agent.enabled:
                continue
            if category and agent.category.lower() != category.lower():
                continue
            results.append(agent)

        return sorted(results, key=lambda a: a.name)

    def get_stats(self) -> AgentRegistryStats:
        """Get registry statistics."""
        if not self._loaded:
            self.load_all()

        stats = AgentRegistryStats()
        stats.total_agents = len(self._cache)

        for agent in self._cache.values():
            if agent.enabled:
                stats.enabled_agents += 1
            else:
                stats.disabled_agents += 1

            stats.agents_by_category[agent.category] = (
                stats.agents_by_category.get(agent.category, 0) + 1
            )

        return stats
