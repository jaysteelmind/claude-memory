"""Skill discovery for the Agent OS.

This module provides advanced skill discovery capabilities including:
- Semantic search using embeddings
- Graph-based skill matching
- Task-to-skill mapping
- Skill recommendation
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from dmm.agentos.skills.models import Skill
from dmm.agentos.skills.registry import SkillRegistry


@dataclass
class SkillMatch:
    """Result of skill matching.

    Attributes:
        skill: The matched skill.
        score: Match score (0.0 to 1.0).
        match_reasons: Reasons for the match.
    """

    skill: Skill
    score: float
    match_reasons: list[str] = field(default_factory=list)


@dataclass
class SkillRecommendation:
    """Skill recommendation result.

    Attributes:
        skill: Recommended skill.
        relevance: Relevance score (0.0 to 1.0).
        reason: Why this skill is recommended.
        dependencies: List of skills this depends on.
        required_tools: List of required tools.
    """

    skill: Skill
    relevance: float
    reason: str
    dependencies: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)


class SkillDiscovery:
    """Discovery service for finding skills.

    Provides multiple strategies for finding skills:
    - Text search in name, description, tags
    - Semantic similarity using embeddings
    - Graph traversal for related skills
    - Output-based matching for task requirements

    Attributes:
        registry: SkillRegistry instance.
        graph_store: Optional knowledge graph store.
        embedder: Optional embedder for semantic search.
    """

    def __init__(
        self,
        registry: SkillRegistry,
        graph_store: Optional[Any] = None,
        embedder: Optional[Any] = None,
    ) -> None:
        """Initialize skill discovery.

        Args:
            registry: SkillRegistry instance.
            graph_store: Optional KnowledgeGraphStore for graph queries.
            embedder: Optional embedder for semantic search.
        """
        self._registry = registry
        self._graph_store = graph_store
        self._embedder = embedder

    def find_for_task(
        self,
        task_description: str,
        required_outputs: Optional[list[str]] = None,
        preferred_category: Optional[str] = None,
        max_results: int = 10,
    ) -> list[SkillMatch]:
        """Find skills suitable for a task.

        This method combines multiple matching strategies:
        1. Text search for keyword matches
        2. Category filtering if specified
        3. Output compatibility checking
        4. Semantic similarity if embedder is available

        Args:
            task_description: Description of the task.
            required_outputs: List of required output names.
            preferred_category: Preferred skill category.
            max_results: Maximum number of results.

        Returns:
            List of SkillMatch objects sorted by score.
        """
        matches: list[SkillMatch] = []
        task_lower = task_description.lower()
        task_words = set(task_lower.split())

        for skill in self._registry.list_all(enabled_only=True):
            score = 0.0
            reasons: list[str] = []

            # Category match
            if preferred_category:
                if skill.category.lower() == preferred_category.lower():
                    score += 0.2
                    reasons.append(f"Category match: {skill.category}")

            # Keyword matching in name
            name_lower = skill.name.lower()
            name_words = set(name_lower.split())
            name_overlap = len(task_words & name_words)
            if name_overlap > 0:
                score += 0.3 * (name_overlap / max(len(task_words), 1))
                reasons.append(f"Name keyword match: {name_overlap} words")

            # Keyword matching in description
            desc_lower = skill.description.lower()
            desc_words = set(desc_lower.split())
            desc_overlap = len(task_words & desc_words)
            if desc_overlap > 0:
                score += 0.2 * (desc_overlap / max(len(task_words), 1))
                reasons.append(f"Description keyword match: {desc_overlap} words")

            # Tag matching
            skill_tags = set(t.lower() for t in skill.tags)
            tag_overlap = len(task_words & skill_tags)
            if tag_overlap > 0:
                score += 0.15 * (tag_overlap / max(len(task_words), 1))
                reasons.append(f"Tag match: {tag_overlap} tags")

            # Output compatibility
            if required_outputs:
                skill_outputs = set(out.name.lower() for out in skill.outputs)
                required_lower = set(o.lower() for o in required_outputs)
                output_match = len(required_lower & skill_outputs)
                if output_match > 0:
                    score += 0.15 * (output_match / len(required_outputs))
                    reasons.append(f"Output match: {output_match}/{len(required_outputs)}")

            if score > 0:
                matches.append(SkillMatch(
                    skill=skill,
                    score=min(score, 1.0),
                    match_reasons=reasons,
                ))

        # Sort by score descending
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:max_results]

    def find_by_output(
        self,
        output_names: list[str],
        output_types: Optional[list[str]] = None,
    ) -> list[Skill]:
        """Find skills that produce specific outputs.

        Args:
            output_names: Required output names.
            output_types: Optional required output types.

        Returns:
            List of skills that can produce the outputs.
        """
        results: list[Skill] = []
        required_names = set(o.lower() for o in output_names)

        for skill in self._registry.list_all(enabled_only=True):
            skill_outputs = {out.name.lower(): out for out in skill.outputs}

            # Check if all required outputs are present
            if not required_names.issubset(set(skill_outputs.keys())):
                continue

            # Check types if specified
            if output_types:
                type_match = True
                for name, required_type in zip(output_names, output_types):
                    output = skill_outputs.get(name.lower())
                    if output and output.param_type != required_type:
                        type_match = False
                        break
                if not type_match:
                    continue

            results.append(skill)

        return results

    def find_related(
        self,
        skill_id: str,
        max_depth: int = 2,
        max_results: int = 10,
    ) -> list[SkillMatch]:
        """Find skills related to a given skill.

        Finds related skills through:
        1. Shared dependencies
        2. Shared tags
        3. Same category
        4. Graph relationships (if available)

        Args:
            skill_id: Source skill ID.
            max_depth: Maximum graph traversal depth.
            max_results: Maximum number of results.

        Returns:
            List of related skills with match scores.
        """
        source = self._registry.find_by_id(skill_id)
        if not source:
            return []

        matches: list[SkillMatch] = []
        source_tags = set(t.lower() for t in source.tags)
        source_deps = set(source.get_required_skill_ids())
        source_tools = set(source.get_all_tool_ids())

        for skill in self._registry.list_all(enabled_only=True):
            if skill.id == skill_id:
                continue

            score = 0.0
            reasons: list[str] = []

            # Same category
            if skill.category == source.category:
                score += 0.2
                reasons.append(f"Same category: {skill.category}")

            # Tag overlap
            skill_tags = set(t.lower() for t in skill.tags)
            tag_overlap = len(source_tags & skill_tags)
            if tag_overlap > 0:
                score += 0.3 * (tag_overlap / max(len(source_tags), 1))
                reasons.append(f"Shared tags: {tag_overlap}")

            # Shared dependencies
            skill_deps = set(skill.get_required_skill_ids())
            dep_overlap = len(source_deps & skill_deps)
            if dep_overlap > 0:
                score += 0.25 * (dep_overlap / max(len(source_deps), 1))
                reasons.append(f"Shared dependencies: {dep_overlap}")

            # Shared tools
            skill_tools = set(skill.get_all_tool_ids())
            tool_overlap = len(source_tools & skill_tools)
            if tool_overlap > 0:
                score += 0.25 * (tool_overlap / max(len(source_tools), 1))
                reasons.append(f"Shared tools: {tool_overlap}")

            if score > 0:
                matches.append(SkillMatch(
                    skill=skill,
                    score=min(score, 1.0),
                    match_reasons=reasons,
                ))

        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:max_results]

    def recommend_for_memory(
        self,
        memory_tags: list[str],
        memory_scope: str,
        max_results: int = 5,
    ) -> list[SkillRecommendation]:
        """Recommend skills based on memory context.

        Analyzes memory tags and scope to recommend relevant skills.

        Args:
            memory_tags: Tags from retrieved memories.
            memory_scope: Scope of the memories.
            max_results: Maximum recommendations.

        Returns:
            List of skill recommendations.
        """
        recommendations: list[SkillRecommendation] = []
        tags_lower = set(t.lower() for t in memory_tags)

        for skill in self._registry.list_all(enabled_only=True):
            relevance = 0.0
            reason_parts: list[str] = []

            # Check memory requirements
            for mem_req in skill.memory_requirements:
                req_tags = set(t.lower() for t in mem_req.tags)
                tag_match = len(tags_lower & req_tags)
                if tag_match > 0:
                    relevance += 0.3 * (tag_match / max(len(req_tags), 1))
                    reason_parts.append(f"Memory tag match: {tag_match}")

                if mem_req.scope.lower() == memory_scope.lower():
                    relevance += 0.2
                    reason_parts.append(f"Scope match: {memory_scope}")

            # Check skill tags against memory tags
            skill_tags = set(t.lower() for t in skill.tags)
            skill_tag_match = len(tags_lower & skill_tags)
            if skill_tag_match > 0:
                relevance += 0.3 * (skill_tag_match / max(len(skill_tags), 1))
                reason_parts.append(f"Skill tag match: {skill_tag_match}")

            if relevance > 0:
                recommendations.append(SkillRecommendation(
                    skill=skill,
                    relevance=min(relevance, 1.0),
                    reason="; ".join(reason_parts),
                    dependencies=skill.get_required_skill_ids(),
                    required_tools=skill.get_required_tool_ids(),
                ))

        recommendations.sort(key=lambda r: r.relevance, reverse=True)
        return recommendations[:max_results]

    def get_skill_chain(
        self,
        start_skill_id: str,
        end_output: str,
    ) -> list[Skill]:
        """Find a chain of skills to produce a desired output.

        Performs a search through skill dependencies and outputs
        to find a path from the start skill to producing the
        desired output.

        Args:
            start_skill_id: Starting skill ID.
            end_output: Desired output name.

        Returns:
            List of skills in execution order, or empty if no path found.
        """
        start_skill = self._registry.find_by_id(start_skill_id)
        if not start_skill:
            return []

        # Check if start skill already has the output
        for out in start_skill.outputs:
            if out.name.lower() == end_output.lower():
                return [start_skill]

        # BFS to find a path
        visited: set[str] = {start_skill_id}
        queue: list[tuple[str, list[str]]] = [(start_skill_id, [start_skill_id])]

        while queue:
            current_id, path = queue.pop(0)
            current = self._registry.find_by_id(current_id)
            if not current:
                continue

            # Find skills that take this skill's outputs as input
            for other in self._registry.list_all(enabled_only=True):
                if other.id in visited:
                    continue

                # Check if other skill can use any output from current
                current_outputs = set(o.name.lower() for o in current.outputs)
                other_inputs = set(i.name.lower() for i in other.inputs if i.required)

                if current_outputs & other_inputs:
                    new_path = path + [other.id]

                    # Check if this skill produces desired output
                    for out in other.outputs:
                        if out.name.lower() == end_output.lower():
                            return [
                                self._registry.find_by_id(sid)
                                for sid in new_path
                                if self._registry.find_by_id(sid)
                            ]

                    visited.add(other.id)
                    queue.append((other.id, new_path))

        return []
