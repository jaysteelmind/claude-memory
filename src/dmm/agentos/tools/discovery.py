"""Tool discovery for the Agent OS.

This module provides tool discovery capabilities including:
- Finding tools by capability
- Matching tools to skill requirements
- Tool recommendations
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from dmm.agentos.tools.models import Tool
from dmm.agentos.tools.registry import ToolRegistry


@dataclass
class ToolMatch:
    """Result of tool matching.

    Attributes:
        tool: The matched tool.
        score: Match score (0.0 to 1.0).
        available: Whether the tool is available.
        match_reasons: Reasons for the match.
    """

    tool: Tool
    score: float
    available: bool = True
    match_reasons: list[str] = field(default_factory=list)


class ToolDiscovery:
    """Discovery service for finding tools.

    Provides strategies for finding tools:
    - Text search in name, description, tags
    - Capability matching
    - Skill requirement matching
    """

    def __init__(
        self,
        registry: ToolRegistry,
        graph_store: Optional[Any] = None,
    ) -> None:
        """Initialize tool discovery.

        Args:
            registry: ToolRegistry instance.
            graph_store: Optional KnowledgeGraphStore.
        """
        self._registry = registry
        self._graph_store = graph_store

    def find_for_capability(
        self,
        capability: str,
        tool_type: Optional[str] = None,
        available_only: bool = True,
        max_results: int = 10,
    ) -> list[ToolMatch]:
        """Find tools that provide a specific capability.

        Args:
            capability: Capability description or keywords.
            tool_type: Optional filter by tool type.
            available_only: Only return available tools.
            max_results: Maximum results to return.

        Returns:
            List of ToolMatch objects sorted by score.
        """
        matches: list[ToolMatch] = []
        cap_lower = capability.lower()
        cap_words = set(cap_lower.split())

        for tool in self._registry.list_all(enabled_only=True):
            if tool_type and tool.tool_type != tool_type:
                continue

            if available_only:
                avail = self._registry.check_availability(tool.id)
                if not avail.available:
                    continue

            score = 0.0
            reasons: list[str] = []

            # Name match
            name_lower = tool.name.lower()
            if cap_lower in name_lower:
                score += 0.4
                reasons.append("Name contains capability")
            else:
                name_words = set(name_lower.split())
                overlap = len(cap_words & name_words)
                if overlap > 0:
                    score += 0.2 * (overlap / max(len(cap_words), 1))
                    reasons.append(f"Name word match: {overlap}")

            # Description match
            desc_lower = tool.description.lower()
            if cap_lower in desc_lower:
                score += 0.3
                reasons.append("Description contains capability")
            else:
                desc_words = set(desc_lower.split())
                overlap = len(cap_words & desc_words)
                if overlap > 0:
                    score += 0.15 * (overlap / max(len(cap_words), 1))
                    reasons.append(f"Description word match: {overlap}")

            # Tag match
            tool_tags = set(t.lower() for t in tool.tags)
            tag_overlap = len(cap_words & tool_tags)
            if tag_overlap > 0:
                score += 0.15 * (tag_overlap / max(len(cap_words), 1))
                reasons.append(f"Tag match: {tag_overlap}")

            # Category match
            if cap_lower in tool.category.lower():
                score += 0.1
                reasons.append(f"Category match: {tool.category}")

            if score > 0:
                avail = self._registry.check_availability(tool.id)
                matches.append(ToolMatch(
                    tool=tool,
                    score=min(score, 1.0),
                    available=avail.available,
                    match_reasons=reasons,
                ))

        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:max_results]

    def find_alternatives(
        self,
        tool_id: str,
        max_results: int = 5,
    ) -> list[ToolMatch]:
        """Find alternative tools that provide similar functionality.

        Args:
            tool_id: Source tool ID.
            max_results: Maximum results to return.

        Returns:
            List of alternative tools.
        """
        source = self._registry.find_by_id(tool_id)
        if not source:
            return []

        matches: list[ToolMatch] = []
        source_tags = set(t.lower() for t in source.tags)

        for tool in self._registry.list_all(enabled_only=True):
            if tool.id == tool_id:
                continue

            score = 0.0
            reasons: list[str] = []

            # Same category is a strong signal
            if tool.category == source.category:
                score += 0.4
                reasons.append(f"Same category: {tool.category}")

            # Same type
            if tool.tool_type == source.tool_type:
                score += 0.2
                reasons.append(f"Same type: {tool.tool_type}")

            # Tag overlap
            tool_tags = set(t.lower() for t in tool.tags)
            tag_overlap = len(source_tags & tool_tags)
            if tag_overlap > 0:
                score += 0.3 * (tag_overlap / max(len(source_tags), 1))
                reasons.append(f"Shared tags: {tag_overlap}")

            # Similar name
            if any(word in tool.name.lower() for word in source.name.lower().split()):
                score += 0.1
                reasons.append("Similar name")

            if score > 0.2:
                avail = self._registry.check_availability(tool.id)
                matches.append(ToolMatch(
                    tool=tool,
                    score=min(score, 1.0),
                    available=avail.available,
                    match_reasons=reasons,
                ))

        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:max_results]

    def find_for_language(
        self,
        language: str,
        category: Optional[str] = None,
    ) -> list[Tool]:
        """Find tools that support a specific programming language.

        Args:
            language: Programming language name.
            category: Optional category filter.

        Returns:
            List of tools supporting the language.
        """
        language_lower = language.lower()
        results: list[Tool] = []

        for tool in self._registry.list_all(enabled_only=True):
            if category and tool.category != category:
                continue

            # Check tags for language
            tool_tags = [t.lower() for t in tool.tags]
            if language_lower in tool_tags:
                results.append(tool)
                continue

            # Check description
            if language_lower in tool.description.lower():
                results.append(tool)
                continue

            # Check common language variations
            variations = {
                "javascript": ["js", "node", "nodejs"],
                "typescript": ["ts"],
                "python": ["py"],
                "ruby": ["rb"],
                "csharp": ["c#", "dotnet"],
                "cpp": ["c++"],
            }
            if language_lower in variations:
                for var in variations[language_lower]:
                    if var in tool_tags or var in tool.description.lower():
                        results.append(tool)
                        break

        return results

    def get_tool_chain(
        self,
        input_type: str,
        output_type: str,
    ) -> list[Tool]:
        """Find a chain of tools to transform input to output type.

        Args:
            input_type: Starting data type.
            output_type: Desired output type.

        Returns:
            List of tools in execution order, or empty if no chain found.
        """
        # Simple implementation - find tools that can directly transform
        # A more sophisticated version would do graph search
        results: list[Tool] = []

        for tool in self._registry.list_all(enabled_only=True):
            # Check if tool takes input_type and produces output_type
            has_input = False
            has_output = False

            for inp in tool.inputs:
                if input_type.lower() in inp.name.lower() or input_type.lower() in inp.param_type.lower():
                    has_input = True
                    break

            for out in tool.outputs:
                if output_type.lower() in out.name.lower() or output_type.lower() in out.param_type.lower():
                    has_output = True
                    break

            if has_input and has_output:
                results.append(tool)

        return results

    def recommend_for_project(
        self,
        project_files: list[str],
        max_results: int = 10,
    ) -> list[ToolMatch]:
        """Recommend tools based on project file structure.

        Analyzes project files to recommend relevant tools.

        Args:
            project_files: List of file paths in the project.
            max_results: Maximum recommendations.

        Returns:
            List of tool recommendations.
        """
        # Detect languages and frameworks from files
        language_indicators: dict[str, list[str]] = {
            "javascript": [".js", ".jsx", "package.json"],
            "typescript": [".ts", ".tsx", "tsconfig.json"],
            "python": [".py", "requirements.txt", "pyproject.toml", "setup.py"],
            "rust": [".rs", "Cargo.toml"],
            "go": [".go", "go.mod"],
            "ruby": [".rb", "Gemfile"],
            "java": [".java", "pom.xml", "build.gradle"],
        }

        detected_languages: set[str] = set()
        for file_path in project_files:
            file_lower = file_path.lower()
            for lang, indicators in language_indicators.items():
                for indicator in indicators:
                    if file_lower.endswith(indicator):
                        detected_languages.add(lang)
                        break

        # Find tools for detected languages
        matches: list[ToolMatch] = []
        seen_tools: set[str] = set()

        for lang in detected_languages:
            for tool in self.find_for_language(lang):
                if tool.id not in seen_tools:
                    seen_tools.add(tool.id)
                    avail = self._registry.check_availability(tool.id)
                    matches.append(ToolMatch(
                        tool=tool,
                        score=0.8,
                        available=avail.available,
                        match_reasons=[f"Supports {lang}"],
                    ))

        matches.sort(key=lambda m: (m.available, m.score), reverse=True)
        return matches[:max_results]
