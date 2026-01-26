"""Skill registry for the Agent OS.

This module provides the SkillRegistry class which manages:
- Loading skills from the filesystem
- Caching loaded skills
- Syncing skills to the knowledge graph
- Skill discovery and search
- Dependency resolution
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from dmm.agentos.skills.loader import SkillLoader, SkillLoadError, SkillValidationError
from dmm.agentos.skills.models import Skill
from dmm.graph.nodes import SkillNode
from dmm.graph.edges import SkillDependsOn, UsesTool


@dataclass
class SyncResult:
    """Result of syncing skills to the graph.

    Attributes:
        skills_synced: Number of skills synced.
        edges_created: Number of edges created.
        errors: List of error messages.
        duration_ms: Sync duration in milliseconds.
    """

    skills_synced: int = 0
    edges_created: int = 0
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class DependencyCheck:
    """Result of checking skill dependencies.

    Attributes:
        satisfied: Whether all dependencies are satisfied.
        missing_skills: List of missing skill IDs.
        missing_tools: List of missing tool IDs.
        available_skills: List of available skill IDs.
        available_tools: List of available tool IDs.
    """

    satisfied: bool = True
    missing_skills: list[str] = field(default_factory=list)
    missing_tools: list[str] = field(default_factory=list)
    available_skills: list[str] = field(default_factory=list)
    available_tools: list[str] = field(default_factory=list)


@dataclass
class SkillRegistryStats:
    """Statistics about the skill registry.

    Attributes:
        total_skills: Total number of registered skills.
        enabled_skills: Number of enabled skills.
        disabled_skills: Number of disabled skills.
        skills_by_category: Count of skills per category.
        total_dependencies: Total skill-to-skill dependencies.
        total_tool_requirements: Total tool requirements.
    """

    total_skills: int = 0
    enabled_skills: int = 0
    disabled_skills: int = 0
    skills_by_category: dict[str, int] = field(default_factory=dict)
    total_dependencies: int = 0
    total_tool_requirements: int = 0


class SkillRegistry:
    """Registry for managing skills.

    The SkillRegistry is responsible for:
    - Loading skills from .dmm/skills/ directory
    - Caching loaded skills in memory
    - Syncing skills to the knowledge graph
    - Providing skill discovery and lookup
    - Resolving skill dependencies

    Attributes:
        skills_dir: Directory containing skill definitions.
        graph_store: Knowledge graph store for persistence.
    """

    def __init__(
        self,
        skills_dir: Path,
        graph_store: Optional[Any] = None,
        strict: bool = False,
    ) -> None:
        """Initialize the skill registry.

        Args:
            skills_dir: Path to the skills directory.
            graph_store: Optional KnowledgeGraphStore for graph integration.
            strict: If True, raise errors on invalid skills.
        """
        self._skills_dir = skills_dir
        self._graph_store = graph_store
        self._strict = strict
        self._loader = SkillLoader(strict=strict)
        self._cache: dict[str, Skill] = {}
        self._loaded = False

    @property
    def skills_dir(self) -> Path:
        """Get the skills directory path."""
        return self._skills_dir

    @property
    def is_loaded(self) -> bool:
        """Check if skills have been loaded."""
        return self._loaded

    # === Loading ===

    def load_all(self) -> list[Skill]:
        """Load all skills from the skills directory.

        Returns:
            List of loaded Skill objects.
        """
        self._cache.clear()
        skills: list[Skill] = []

        # Load from core directory
        core_dir = self._skills_dir / "core"
        if core_dir.exists():
            for skill in self._loader.load_directory(core_dir):
                self._cache[skill.id] = skill
                skills.append(skill)

        # Load from custom directory
        custom_dir = self._skills_dir / "custom"
        if custom_dir.exists():
            for skill in self._loader.load_directory(custom_dir):
                self._cache[skill.id] = skill
                skills.append(skill)

        self._loaded = True
        return skills

    def load_skill(self, skill_id: str) -> Optional[Skill]:
        """Load a specific skill by ID.

        Args:
            skill_id: The skill identifier.

        Returns:
            Skill object if found, None otherwise.
        """
        # Check cache first
        if skill_id in self._cache:
            return self._cache[skill_id]

        # Search in directories
        for subdir in ["core", "custom"]:
            dir_path = self._skills_dir / subdir
            if not dir_path.exists():
                continue

            for path in dir_path.rglob("*.skill.yaml"):
                try:
                    skill = self._loader.load(path)
                    if skill.id == skill_id:
                        self._cache[skill.id] = skill
                        return skill
                except (SkillLoadError, SkillValidationError):
                    continue

        return None

    def reload(self) -> list[Skill]:
        """Reload all skills from the filesystem.

        Returns:
            List of reloaded Skill objects.
        """
        self._loaded = False
        return self.load_all()

    # === Graph Integration ===

    def sync_to_graph(self) -> SyncResult:
        """Sync all loaded skills to the knowledge graph.

        Creates:
        - SkillNode for each skill
        - SKILL_DEPENDS_ON edges between skills
        - USES_TOOL edges to required tools

        Returns:
            SyncResult with statistics.
        """
        import time
        start = time.perf_counter()

        result = SyncResult()

        if self._graph_store is None:
            result.errors.append("No graph store configured")
            return result

        if not self._loaded:
            self.load_all()

        for skill in self._cache.values():
            try:
                self._index_skill(skill)
                result.skills_synced += 1

                # Create dependency edges
                for dep_skill_id in skill.get_required_skill_ids():
                    try:
                        edge = SkillDependsOn(
                            from_id=skill.id,
                            to_id=dep_skill_id,
                            execution_order=0,
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
                            f"Failed to create dependency edge {skill.id} -> {dep_skill_id}: {e}"
                        )

                # Create tool requirement edges
                for tool_id in skill.get_required_tool_ids():
                    try:
                        edge = UsesTool(
                            from_id=skill.id,
                            to_id=tool_id,
                            required=True,
                            purpose="Required tool",
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
                            f"Failed to create tool edge {skill.id} -> {tool_id}: {e}"
                        )

                # Create optional tool edges
                for tool_id in skill.get_optional_tool_ids():
                    try:
                        edge = UsesTool(
                            from_id=skill.id,
                            to_id=tool_id,
                            required=False,
                            purpose="Optional tool",
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
                            f"Failed to create optional tool edge {skill.id} -> {tool_id}: {e}"
                        )

            except Exception as e:
                result.errors.append(f"Failed to sync skill {skill.id}: {e}")

        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    def _index_skill(self, skill: Skill) -> None:
        """Index a single skill in the graph.

        Args:
            skill: Skill to index.
        """
        if self._graph_store is None:
            return

        inputs_schema, outputs_schema = skill.to_json_schemas()

        node = SkillNode(
            id=skill.id,
            name=skill.name,
            version=skill.version,
            description=skill.description,
            category=skill.category,
            tags=skill.tags,
            enabled=skill.enabled,
            inputs_schema=inputs_schema,
            outputs_schema=outputs_schema,
            dependencies_json=json.dumps(skill.dependencies.to_dict()),
            tools_json=json.dumps({
                "required": skill.get_required_tool_ids(),
                "optional": skill.get_optional_tool_ids(),
            }),
            memory_requirements_json=json.dumps(
                [mr.to_dict() for mr in skill.memory_requirements]
            ),
            execution_config_json=json.dumps(skill.execution.to_dict()),
            file_path=skill.file_path,
            created=skill.created,
            updated=skill.updated,
        )

        self._graph_store.upsert_skill_node(node)

    # === Discovery ===

    def find_by_id(self, skill_id: str) -> Optional[Skill]:
        """Find a skill by exact ID.

        Args:
            skill_id: The skill identifier.

        Returns:
            Skill if found, None otherwise.
        """
        if not self._loaded:
            self.load_all()
        return self._cache.get(skill_id)

    def find_by_tags(self, tags: list[str], match_all: bool = False) -> list[Skill]:
        """Find skills with matching tags.

        Args:
            tags: Tags to search for.
            match_all: If True, skill must have all tags.
                      If False, skill must have at least one tag.

        Returns:
            List of matching skills.
        """
        if not self._loaded:
            self.load_all()

        results: list[Skill] = []
        tags_set = set(t.lower() for t in tags)

        for skill in self._cache.values():
            skill_tags = set(t.lower() for t in skill.tags)
            if match_all:
                if tags_set.issubset(skill_tags):
                    results.append(skill)
            else:
                if tags_set & skill_tags:
                    results.append(skill)

        return results

    def find_by_category(self, category: str) -> list[Skill]:
        """Find skills in a category.

        Args:
            category: Category to search for.

        Returns:
            List of skills in the category.
        """
        if not self._loaded:
            self.load_all()

        return [
            skill for skill in self._cache.values()
            if skill.category.lower() == category.lower()
        ]

    def search(
        self,
        query: str,
        enabled_only: bool = True,
        category: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> list[Skill]:
        """Search skills by name, description, or tags.

        Args:
            query: Search query string.
            enabled_only: If True, only return enabled skills.
            category: Optional category filter.
            tags: Optional tags filter.

        Returns:
            List of matching skills sorted by relevance.
        """
        if not self._loaded:
            self.load_all()

        query_lower = query.lower()
        results: list[tuple[Skill, int]] = []

        for skill in self._cache.values():
            # Apply filters
            if enabled_only and not skill.enabled:
                continue
            if category and skill.category.lower() != category.lower():
                continue
            if tags:
                skill_tags = set(t.lower() for t in skill.tags)
                if not any(t.lower() in skill_tags for t in tags):
                    continue

            # Calculate relevance score
            score = 0

            # Exact ID match
            if query_lower == skill.id.lower():
                score += 100

            # Name match
            if query_lower in skill.name.lower():
                score += 50
            if skill.name.lower().startswith(query_lower):
                score += 25

            # Description match
            if query_lower in skill.description.lower():
                score += 20

            # Tag match
            for tag in skill.tags:
                if query_lower in tag.lower():
                    score += 10

            if score > 0:
                results.append((skill, score))

        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        return [skill for skill, _ in results]

    # === Dependency Resolution ===

    def get_dependencies(
        self,
        skill_id: str,
        transitive: bool = True,
    ) -> list[Skill]:
        """Get skill dependencies.

        Args:
            skill_id: Skill to get dependencies for.
            transitive: If True, returns full dependency tree.

        Returns:
            List of dependency skills in dependency order.
        """
        if not self._loaded:
            self.load_all()

        skill = self._cache.get(skill_id)
        if not skill:
            return []

        if not transitive:
            return [
                self._cache[dep_id]
                for dep_id in skill.get_required_skill_ids()
                if dep_id in self._cache
            ]

        # Transitive dependencies using BFS
        visited: set[str] = set()
        order: list[Skill] = []
        queue = list(skill.get_required_skill_ids())

        while queue:
            dep_id = queue.pop(0)
            if dep_id in visited:
                continue
            visited.add(dep_id)

            dep_skill = self._cache.get(dep_id)
            if dep_skill:
                order.append(dep_skill)
                queue.extend(dep_skill.get_required_skill_ids())

        return order

    def get_execution_order(self, skill_ids: list[str]) -> list[Skill]:
        """Get skills in execution order (topological sort).

        Args:
            skill_ids: List of skill IDs to order.

        Returns:
            List of skills in execution order (dependencies first).
        """
        if not self._loaded:
            self.load_all()

        # Build dependency graph
        graph: dict[str, set[str]] = {}
        all_skills: dict[str, Skill] = {}

        for skill_id in skill_ids:
            skill = self._cache.get(skill_id)
            if skill:
                all_skills[skill_id] = skill
                graph[skill_id] = set(skill.get_required_skill_ids())

                # Add transitive dependencies
                for dep in self.get_dependencies(skill_id, transitive=True):
                    all_skills[dep.id] = dep
                    graph[dep.id] = set(dep.get_required_skill_ids())

        # Topological sort using Kahn's algorithm
        in_degree: dict[str, int] = {sid: 0 for sid in graph}
        for deps in graph.values():
            for dep in deps:
                if dep in in_degree:
                    in_degree[dep] += 1

        # Start with nodes that have no dependencies
        queue = [sid for sid, degree in in_degree.items() if degree == 0]
        result: list[Skill] = []

        while queue:
            current = queue.pop(0)
            if current in all_skills:
                result.append(all_skills[current])

            for sid, deps in graph.items():
                if current in deps:
                    in_degree[sid] -= 1
                    if in_degree[sid] == 0:
                        queue.append(sid)

        # Reverse to get dependencies first
        result.reverse()
        return result

    def check_dependencies(
        self,
        skill_id: str,
        available_tools: Optional[list[str]] = None,
    ) -> DependencyCheck:
        """Check if all dependencies are satisfied.

        Args:
            skill_id: Skill to check dependencies for.
            available_tools: List of available tool IDs.

        Returns:
            DependencyCheck result.
        """
        if not self._loaded:
            self.load_all()

        result = DependencyCheck()
        skill = self._cache.get(skill_id)

        if not skill:
            result.satisfied = False
            result.missing_skills.append(skill_id)
            return result

        # Check skill dependencies
        for dep_id in skill.get_required_skill_ids():
            if dep_id in self._cache:
                result.available_skills.append(dep_id)
            else:
                result.missing_skills.append(dep_id)
                result.satisfied = False

        # Check tool dependencies
        if available_tools is not None:
            tools_set = set(available_tools)
            for tool_id in skill.get_required_tool_ids():
                if tool_id in tools_set:
                    result.available_tools.append(tool_id)
                else:
                    result.missing_tools.append(tool_id)
                    result.satisfied = False

        return result

    # === Management ===

    def enable(self, skill_id: str) -> bool:
        """Enable a skill.

        Args:
            skill_id: Skill to enable.

        Returns:
            True if skill was found and enabled.
        """
        skill = self._cache.get(skill_id)
        if skill:
            skill.enabled = True
            return True
        return False

    def disable(self, skill_id: str) -> bool:
        """Disable a skill.

        Args:
            skill_id: Skill to disable.

        Returns:
            True if skill was found and disabled.
        """
        skill = self._cache.get(skill_id)
        if skill:
            skill.enabled = False
            return True
        return False

    def list_all(
        self,
        enabled_only: bool = False,
        category: Optional[str] = None,
    ) -> list[Skill]:
        """List all registered skills.

        Args:
            enabled_only: If True, only return enabled skills.
            category: Optional category filter.

        Returns:
            List of skills.
        """
        if not self._loaded:
            self.load_all()

        results: list[Skill] = []
        for skill in self._cache.values():
            if enabled_only and not skill.enabled:
                continue
            if category and skill.category.lower() != category.lower():
                continue
            results.append(skill)

        return sorted(results, key=lambda s: s.name)

    def get_stats(self) -> SkillRegistryStats:
        """Get registry statistics.

        Returns:
            SkillRegistryStats object.
        """
        if not self._loaded:
            self.load_all()

        stats = SkillRegistryStats()
        stats.total_skills = len(self._cache)

        for skill in self._cache.values():
            if skill.enabled:
                stats.enabled_skills += 1
            else:
                stats.disabled_skills += 1

            category = skill.category
            stats.skills_by_category[category] = (
                stats.skills_by_category.get(category, 0) + 1
            )

            stats.total_dependencies += len(skill.get_required_skill_ids())
            stats.total_tool_requirements += len(skill.get_all_tool_ids())

        return stats
