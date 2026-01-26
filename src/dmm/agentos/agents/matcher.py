"""Agent-task matching for the Agent OS.

This module provides agent matching capabilities including:
- Finding agents suitable for a task
- Matching by skills and tools
- Semantic matching
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from dmm.agentos.agents.models import Agent
from dmm.agentos.agents.registry import AgentRegistry


@dataclass
class AgentMatch:
    """Result of agent matching.

    Attributes:
        agent: The matched agent.
        score: Match score (0.0 to 1.0).
        skill_coverage: Fraction of required skills covered.
        tool_coverage: Fraction of required tools covered.
        match_reasons: Reasons for the match.
    """

    agent: Agent
    score: float
    skill_coverage: float = 1.0
    tool_coverage: float = 1.0
    match_reasons: list[str] = field(default_factory=list)


class AgentMatcher:
    """Matcher for finding agents suitable for tasks.

    Provides multiple strategies for matching agents:
    - Task description matching
    - Skill requirement matching
    - Tool requirement matching
    - Category matching
    """

    def __init__(
        self,
        registry: AgentRegistry,
        skill_registry: Optional[Any] = None,
        tool_registry: Optional[Any] = None,
    ) -> None:
        """Initialize the agent matcher.

        Args:
            registry: AgentRegistry instance.
            skill_registry: Optional SkillRegistry for skill validation.
            tool_registry: Optional ToolRegistry for tool validation.
        """
        self._registry = registry
        self._skill_registry = skill_registry
        self._tool_registry = tool_registry

    def find_for_task(
        self,
        task_description: str,
        required_skills: Optional[list[str]] = None,
        required_tools: Optional[list[str]] = None,
        preferred_category: Optional[str] = None,
        max_results: int = 5,
    ) -> list[AgentMatch]:
        """Find agents suitable for a task.

        Considers:
        - Semantic similarity to task description
        - Skill coverage
        - Tool coverage
        - Agent constraints

        Args:
            task_description: Description of the task.
            required_skills: List of required skill IDs.
            required_tools: List of required tool IDs.
            preferred_category: Preferred agent category.
            max_results: Maximum number of results.

        Returns:
            List of AgentMatch objects sorted by score.
        """
        matches: list[AgentMatch] = []
        task_lower = task_description.lower()
        task_words = set(task_lower.split())

        required_skills = required_skills or []
        required_tools = required_tools or []

        for agent in self._registry.list_all(enabled_only=True):
            score = 0.0
            reasons: list[str] = []

            # Category match
            if preferred_category:
                if agent.category.lower() == preferred_category.lower():
                    score += 0.15
                    reasons.append(f"Category match: {agent.category}")

            # Name/description keyword matching
            name_lower = agent.name.lower()
            name_words = set(name_lower.split())
            name_overlap = len(task_words & name_words)
            if name_overlap > 0:
                score += 0.2 * (name_overlap / max(len(task_words), 1))
                reasons.append(f"Name keyword match: {name_overlap}")

            desc_lower = agent.description.lower()
            desc_words = set(desc_lower.split())
            desc_overlap = len(task_words & desc_words)
            if desc_overlap > 0:
                score += 0.15 * (desc_overlap / max(len(task_words), 1))
                reasons.append(f"Description keyword match: {desc_overlap}")

            # Tag matching
            agent_tags = set(t.lower() for t in agent.tags)
            tag_overlap = len(task_words & agent_tags)
            if tag_overlap > 0:
                score += 0.1 * (tag_overlap / max(len(task_words), 1))
                reasons.append(f"Tag match: {tag_overlap}")

            # Skill coverage
            skill_coverage = 1.0
            if required_skills:
                agent_skills = set(agent.get_all_skill_ids())
                covered = len(set(required_skills) & agent_skills)
                skill_coverage = covered / len(required_skills)
                score += 0.25 * skill_coverage
                if covered > 0:
                    reasons.append(f"Skill coverage: {covered}/{len(required_skills)}")

            # Tool coverage
            tool_coverage = 1.0
            if required_tools:
                # Check if agent can use these tools
                covered = sum(1 for t in required_tools if agent.can_use_tool(t))
                tool_coverage = covered / len(required_tools)
                score += 0.15 * tool_coverage
                if covered > 0:
                    reasons.append(f"Tool coverage: {covered}/{len(required_tools)}")

            # Focus area matching
            for focus in agent.behavior.focus_areas:
                if focus.lower() in task_lower:
                    score += 0.1
                    reasons.append(f"Focus area match: {focus}")
                    break

            # Penalty for avoid areas
            for avoid in agent.behavior.avoid_areas:
                if avoid.lower() in task_lower:
                    score -= 0.2
                    reasons.append(f"Avoid area conflict: {avoid}")

            if score > 0:
                matches.append(AgentMatch(
                    agent=agent,
                    score=min(max(score, 0.0), 1.0),
                    skill_coverage=skill_coverage,
                    tool_coverage=tool_coverage,
                    match_reasons=reasons,
                ))

        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:max_results]

    def match_by_skills(
        self,
        skill_ids: list[str],
        require_all: bool = False,
    ) -> list[AgentMatch]:
        """Find agents that have specific skills.

        Args:
            skill_ids: List of skill IDs to match.
            require_all: If True, agent must have all skills.

        Returns:
            List of matching agents.
        """
        matches: list[AgentMatch] = []
        skill_set = set(skill_ids)

        for agent in self._registry.list_all(enabled_only=True):
            agent_skills = set(agent.get_all_skill_ids())
            
            if require_all:
                if not skill_set.issubset(agent_skills):
                    continue
                coverage = 1.0
            else:
                covered = len(skill_set & agent_skills)
                if covered == 0:
                    continue
                coverage = covered / len(skill_ids)

            # Calculate score based on coverage and primary/secondary
            score = coverage * 0.7
            
            # Bonus for primary skills
            primary_covered = len(skill_set & set(agent.skills.primary))
            if primary_covered > 0:
                score += 0.3 * (primary_covered / len(skill_ids))

            matches.append(AgentMatch(
                agent=agent,
                score=score,
                skill_coverage=coverage,
                match_reasons=[f"Skill match: {int(coverage * 100)}% coverage"],
            ))

        matches.sort(key=lambda m: m.score, reverse=True)
        return matches

    def match_by_tools(
        self,
        tool_ids: list[str],
        require_all: bool = False,
    ) -> list[AgentMatch]:
        """Find agents that can use specific tools.

        Args:
            tool_ids: List of tool IDs to match.
            require_all: If True, agent must support all tools.

        Returns:
            List of matching agents.
        """
        matches: list[AgentMatch] = []

        for agent in self._registry.list_all(enabled_only=True):
            covered = sum(1 for t in tool_ids if agent.can_use_tool(t))
            
            if require_all and covered < len(tool_ids):
                continue
            if covered == 0:
                continue

            coverage = covered / len(tool_ids)
            score = coverage

            matches.append(AgentMatch(
                agent=agent,
                score=score,
                tool_coverage=coverage,
                match_reasons=[f"Tool match: {covered}/{len(tool_ids)}"],
            ))

        matches.sort(key=lambda m: m.score, reverse=True)
        return matches

    def match_by_capability(
        self,
        capabilities: list[str],
    ) -> list[AgentMatch]:
        """Find agents matching capability requirements.

        Capabilities can be skill IDs, tool IDs, categories, or keywords.

        Args:
            capabilities: List of capability strings.

        Returns:
            List of matching agents.
        """
        matches: list[AgentMatch] = []
        cap_lower = [c.lower() for c in capabilities]

        for agent in self._registry.list_all(enabled_only=True):
            score = 0.0
            reasons: list[str] = []
            matches_found = 0

            for cap in cap_lower:
                # Check if it's a skill ID
                if cap.startswith("skill_") and agent.can_use_skill(cap):
                    score += 0.25
                    matches_found += 1
                    reasons.append(f"Has skill: {cap}")
                    continue

                # Check if it's a tool ID
                if cap.startswith("tool_") and agent.can_use_tool(cap):
                    score += 0.2
                    matches_found += 1
                    reasons.append(f"Has tool: {cap}")
                    continue

                # Check category
                if cap == agent.category.lower():
                    score += 0.15
                    matches_found += 1
                    reasons.append(f"Category: {agent.category}")
                    continue

                # Check tags
                if cap in [t.lower() for t in agent.tags]:
                    score += 0.1
                    matches_found += 1
                    reasons.append(f"Tag: {cap}")
                    continue

                # Check focus areas
                if cap in [f.lower() for f in agent.behavior.focus_areas]:
                    score += 0.15
                    matches_found += 1
                    reasons.append(f"Focus area: {cap}")
                    continue

                # Keyword in name/description
                if cap in agent.name.lower() or cap in agent.description.lower():
                    score += 0.1
                    matches_found += 1
                    reasons.append(f"Keyword match: {cap}")

            if matches_found > 0:
                # Normalize score
                normalized_score = min(score / len(capabilities), 1.0)
                matches.append(AgentMatch(
                    agent=agent,
                    score=normalized_score,
                    match_reasons=reasons,
                ))

        matches.sort(key=lambda m: m.score, reverse=True)
        return matches

    def get_best_agent(
        self,
        task_description: str,
        required_skills: Optional[list[str]] = None,
        required_tools: Optional[list[str]] = None,
    ) -> Optional[Agent]:
        """Get the single best agent for a task.

        Args:
            task_description: Description of the task.
            required_skills: Optional required skills.
            required_tools: Optional required tools.

        Returns:
            Best matching agent or None.
        """
        matches = self.find_for_task(
            task_description,
            required_skills=required_skills,
            required_tools=required_tools,
            max_results=1,
        )

        if matches:
            return matches[0].agent

        # Fall back to default agent
        return self._registry.get_default_agent()
