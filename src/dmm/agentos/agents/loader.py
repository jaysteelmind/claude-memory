"""Agent file loader for the Agent OS.

This module provides functionality to load agent definitions from
YAML files with optional Markdown content sections.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from dmm.agentos.agents.models import (
    Agent,
    AgentConstraints,
    BehaviorConfig,
    MemoryConfig,
    SkillsConfig,
    ToolsConfig,
    AGENT_CATEGORIES,
)


class AgentLoadError(Exception):
    """Raised when an agent file cannot be loaded."""

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        self.message = message
        super().__init__(f"Failed to load agent from {path}: {message}")


class AgentValidationError(Exception):
    """Raised when an agent definition is invalid."""

    def __init__(self, agent_id: str, errors: list[str]) -> None:
        self.agent_id = agent_id
        self.errors = errors
        super().__init__(f"Invalid agent '{agent_id}': {'; '.join(errors)}")


class AgentLoader:
    """Loader for agent definition files.

    Handles parsing of .agent.yaml files which contain:
    - YAML configuration block
    - Optional Markdown documentation section
    """

    def __init__(self, strict: bool = False) -> None:
        """Initialize the agent loader.

        Args:
            strict: If True, raise errors on validation failures.
        """
        self.strict = strict

    def load(self, path: Path) -> Agent:
        """Load an agent from a file.

        Args:
            path: Path to the .agent.yaml file.

        Returns:
            Parsed Agent object.

        Raises:
            AgentLoadError: If file cannot be read or parsed.
            AgentValidationError: If agent definition is invalid (strict mode).
        """
        if not path.exists():
            raise AgentLoadError(path, "File not found")

        if not path.suffix == ".yaml" and not str(path).endswith(".agent.yaml"):
            raise AgentLoadError(path, "File must have .agent.yaml extension")

        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            raise AgentLoadError(path, f"Cannot read file: {e}")

        return self.parse(content, path)

    def parse(self, content: str, path: Optional[Path] = None) -> Agent:
        """Parse agent definition from content string.

        Args:
            content: File content to parse.
            path: Optional path for error reporting.

        Returns:
            Parsed Agent object.
        """
        file_path = path or Path("<string>")
        yaml_content, markdown_content = self._split_content(content)

        try:
            data = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            raise AgentLoadError(file_path, f"Invalid YAML: {e}")

        if not isinstance(data, dict):
            raise AgentLoadError(file_path, "YAML must be a dictionary")

        # Validate required fields
        errors = self._validate_required_fields(data)
        if errors:
            if self.strict:
                raise AgentValidationError(data.get("id", "unknown"), errors)
            if "id" not in data:
                raise AgentLoadError(file_path, "Missing required field: id")

        # Parse the agent
        agent = self._parse_agent(data, markdown_content, file_path)
        return agent

    def _split_content(self, content: str) -> tuple[str, str]:
        """Split content into YAML and Markdown sections."""
        content = content.strip()

        if content.startswith("---"):
            content = content[3:].lstrip("\n")
            match = re.search(r"\n---\s*\n", content)
            if match:
                yaml_content = content[: match.start()]
                markdown_content = content[match.end() :].strip()
                return yaml_content, markdown_content
            else:
                return content, ""
        else:
            match = re.search(r"\n---\s*\n", content)
            if match:
                return content[: match.start()].strip(), content[match.end() :].strip()
            return content, ""

    def _validate_required_fields(self, data: dict[str, Any]) -> list[str]:
        """Validate that required fields are present."""
        errors: list[str] = []
        required_fields = ["id", "name", "description"]

        for field_name in required_fields:
            if field_name not in data:
                errors.append(f"Missing required field: {field_name}")

        if "id" in data:
            agent_id = data["id"]
            if not isinstance(agent_id, str):
                errors.append("Field 'id' must be a string")
            elif not agent_id.startswith("agent_"):
                errors.append("Field 'id' must start with 'agent_'")

        return errors

    def _parse_agent(
        self,
        data: dict[str, Any],
        markdown_content: str,
        file_path: Path,
    ) -> Agent:
        """Parse an Agent object from validated data."""
        # Parse skills
        skills_data = data.get("skills", {})
        skills = SkillsConfig(
            primary=skills_data.get("primary", []),
            secondary=skills_data.get("secondary", []),
            disabled=skills_data.get("disabled", []),
        )

        # Parse tools
        tools_data = data.get("tools", {})
        tools = ToolsConfig(
            enabled=tools_data.get("enabled", []),
            disabled=tools_data.get("disabled", []),
        )

        # Parse memory (handle both 'memory' and 'memory_context' keys)
        memory_data = data.get("memory") or data.get("memory_context", {})
        memory = MemoryConfig(
            required_scopes=memory_data.get("required_scopes", []),
            preferred_scopes=memory_data.get("preferred_scopes", []),
            excluded_scopes=memory_data.get("excluded_scopes", []),
            required_tags=memory_data.get("required_tags", []),
            preferred_tags=memory_data.get("preferred_tags", []),
            excluded_tags=memory_data.get("excluded_tags", []),
            max_context_tokens=memory_data.get("max_context_tokens", 8000),
        )

        # Parse behavior
        behavior_data = data.get("behavior", {})
        behavior = BehaviorConfig(
            tone=behavior_data.get("tone", "professional"),
            verbosity=behavior_data.get("verbosity", "normal"),
            focus_areas=behavior_data.get("focus_areas", []),
            avoid_areas=behavior_data.get("avoid_areas", behavior_data.get("avoid", [])),
            guidelines=behavior_data.get("guidelines", []),
        )

        # Parse constraints
        constraints_data = data.get("constraints", {})
        constraints = AgentConstraints(
            max_context_tokens=constraints_data.get("max_context_tokens", 8000),
            max_response_tokens=constraints_data.get("max_response_tokens", 4000),
            allow_tool_execution=constraints_data.get("allow_tool_execution", True),
            allow_memory_write=constraints_data.get("allow_memory_write", True),
            allow_skill_chaining=constraints_data.get("allow_skill_chaining", True),
            allowed_scopes=constraints_data.get("allowed_scopes", []),
            rate_limit_per_minute=constraints_data.get("rate_limit_per_minute"),
        )

        # Parse timestamps
        created = self._parse_datetime(data.get("created"))
        updated = self._parse_datetime(data.get("updated"))

        # Get category with fallback
        category = data.get("category", "general")
        if category not in AGENT_CATEGORIES:
            category = "general"

        return Agent(
            id=data["id"],
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            category=category,
            tags=data.get("tags", []),
            enabled=data.get("enabled", True),
            skills=skills,
            tools=tools,
            memory=memory,
            behavior=behavior,
            constraints=constraints,
            markdown_content=markdown_content,
            file_path=str(file_path),
            created=created,
            updated=updated,
        )

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        """Parse a datetime value."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    def load_directory(self, directory: Path) -> list[Agent]:
        """Load all agents from a directory.

        Args:
            directory: Directory containing .agent.yaml files.

        Returns:
            List of loaded Agent objects.
        """
        agents: list[Agent] = []

        if not directory.exists():
            return agents

        for path in directory.rglob("*.agent.yaml"):
            try:
                agent = self.load(path)
                agents.append(agent)
            except (AgentLoadError, AgentValidationError):
                if self.strict:
                    raise
                continue

        return agents
