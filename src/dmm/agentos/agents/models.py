"""Agent data models for the Agent OS.

This module defines the complete data model for agents including:
- SkillsConfig: Skills configuration for an agent
- ToolsConfig: Tools configuration for an agent
- MemoryConfig: Memory context preferences
- BehaviorConfig: Behavioral guidelines
- AgentConstraints: Agent constraints
- Agent: Complete agent definition
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final, Optional


# Valid agent categories
AGENT_CATEGORIES: Final[tuple[str, ...]] = (
    "general",
    "quality",
    "implementation",
    "research",
    "documentation",
    "testing",
    "security",
    "operations",
    "design",
)

# Valid behavior tones
BEHAVIOR_TONES: Final[tuple[str, ...]] = (
    "professional",
    "casual",
    "technical",
    "friendly",
    "concise",
    "detailed",
)

# Valid verbosity levels
VERBOSITY_LEVELS: Final[tuple[str, ...]] = (
    "minimal",
    "concise",
    "normal",
    "detailed",
    "verbose",
)


@dataclass
class SkillsConfig:
    """Skills configuration for an agent.

    Attributes:
        primary: Primary skills the agent excels at.
        secondary: Secondary skills the agent can use.
        disabled: Skills explicitly disabled for this agent.
    """

    primary: list[str] = field(default_factory=list)
    secondary: list[str] = field(default_factory=list)
    disabled: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "primary": self.primary,
            "secondary": self.secondary,
            "disabled": self.disabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillsConfig":
        """Create SkillsConfig from dictionary."""
        if data is None:
            return cls()
        return cls(
            primary=data.get("primary", []),
            secondary=data.get("secondary", []),
            disabled=data.get("disabled", []),
        )

    def get_all_enabled(self) -> list[str]:
        """Get all enabled skill IDs."""
        return self.primary + self.secondary

    def is_enabled(self, skill_id: str) -> bool:
        """Check if a skill is enabled for this agent."""
        if skill_id in self.disabled:
            return False
        return skill_id in self.primary or skill_id in self.secondary


@dataclass
class ToolsConfig:
    """Tools configuration for an agent.

    Attributes:
        enabled: Tools explicitly enabled for this agent.
        disabled: Tools explicitly disabled for this agent.
    """

    enabled: list[str] = field(default_factory=list)
    disabled: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "enabled": self.enabled,
            "disabled": self.disabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolsConfig":
        """Create ToolsConfig from dictionary."""
        if data is None:
            return cls()
        return cls(
            enabled=data.get("enabled", []),
            disabled=data.get("disabled", []),
        )

    def is_enabled(self, tool_id: str) -> bool:
        """Check if a tool is enabled for this agent."""
        if tool_id in self.disabled:
            return False
        return len(self.enabled) == 0 or tool_id in self.enabled


@dataclass
class MemoryConfig:
    """Memory context preferences for an agent.

    Attributes:
        required_scopes: Scopes that must be included.
        preferred_scopes: Scopes to prioritize.
        excluded_scopes: Scopes to exclude.
        required_tags: Tags that must be present.
        preferred_tags: Tags to prioritize.
        excluded_tags: Tags to exclude.
        max_context_tokens: Maximum context window size.
    """

    required_scopes: list[str] = field(default_factory=list)
    preferred_scopes: list[str] = field(default_factory=list)
    excluded_scopes: list[str] = field(default_factory=list)
    required_tags: list[str] = field(default_factory=list)
    preferred_tags: list[str] = field(default_factory=list)
    excluded_tags: list[str] = field(default_factory=list)
    max_context_tokens: int = 8000

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "required_scopes": self.required_scopes,
            "preferred_scopes": self.preferred_scopes,
            "excluded_scopes": self.excluded_scopes,
            "required_tags": self.required_tags,
            "preferred_tags": self.preferred_tags,
            "excluded_tags": self.excluded_tags,
            "max_context_tokens": self.max_context_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryConfig":
        """Create MemoryConfig from dictionary."""
        if data is None:
            return cls()
        return cls(
            required_scopes=data.get("required_scopes", []),
            preferred_scopes=data.get("preferred_scopes", []),
            excluded_scopes=data.get("excluded_scopes", []),
            required_tags=data.get("required_tags", []),
            preferred_tags=data.get("preferred_tags", []),
            excluded_tags=data.get("excluded_tags", []),
            max_context_tokens=data.get("max_context_tokens", 8000),
        )


@dataclass
class BehaviorConfig:
    """Behavioral guidelines for an agent.

    Attributes:
        tone: Communication tone.
        verbosity: Response verbosity level.
        focus_areas: Areas the agent should focus on.
        avoid_areas: Areas the agent should avoid.
        guidelines: Additional behavioral guidelines.
    """

    tone: str = "professional"
    verbosity: str = "normal"
    focus_areas: list[str] = field(default_factory=list)
    avoid_areas: list[str] = field(default_factory=list)
    guidelines: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate tone and verbosity."""
        if self.tone not in BEHAVIOR_TONES:
            self.tone = "professional"
        if self.verbosity not in VERBOSITY_LEVELS:
            self.verbosity = "normal"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "tone": self.tone,
            "verbosity": self.verbosity,
            "focus_areas": self.focus_areas,
            "avoid_areas": self.avoid_areas,
            "guidelines": self.guidelines,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BehaviorConfig":
        """Create BehaviorConfig from dictionary."""
        if data is None:
            return cls()
        return cls(
            tone=data.get("tone", "professional"),
            verbosity=data.get("verbosity", "normal"),
            focus_areas=data.get("focus_areas", []),
            avoid_areas=data.get("avoid_areas", data.get("avoid", [])),
            guidelines=data.get("guidelines", []),
        )


@dataclass
class AgentConstraints:
    """Constraints for an agent.

    Attributes:
        max_context_tokens: Maximum context tokens.
        max_response_tokens: Maximum response tokens.
        allow_tool_execution: Whether agent can execute tools.
        allow_memory_write: Whether agent can write to memory.
        allow_skill_chaining: Whether agent can chain skills.
        allowed_scopes: Scopes agent can access (empty = all).
        rate_limit_per_minute: Maximum operations per minute.
    """

    max_context_tokens: int = 8000
    max_response_tokens: int = 4000
    allow_tool_execution: bool = True
    allow_memory_write: bool = True
    allow_skill_chaining: bool = True
    allowed_scopes: list[str] = field(default_factory=list)
    rate_limit_per_minute: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "max_context_tokens": self.max_context_tokens,
            "max_response_tokens": self.max_response_tokens,
            "allow_tool_execution": self.allow_tool_execution,
            "allow_memory_write": self.allow_memory_write,
            "allow_skill_chaining": self.allow_skill_chaining,
            "allowed_scopes": self.allowed_scopes,
            "rate_limit_per_minute": self.rate_limit_per_minute,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentConstraints":
        """Create AgentConstraints from dictionary."""
        if data is None:
            return cls()
        return cls(
            max_context_tokens=data.get("max_context_tokens", 8000),
            max_response_tokens=data.get("max_response_tokens", 4000),
            allow_tool_execution=data.get("allow_tool_execution", True),
            allow_memory_write=data.get("allow_memory_write", True),
            allow_skill_chaining=data.get("allow_skill_chaining", True),
            allowed_scopes=data.get("allowed_scopes", []),
            rate_limit_per_minute=data.get("rate_limit_per_minute"),
        )


@dataclass
class Agent:
    """Complete agent definition.

    An agent is a specialized persona with specific skills, tools,
    memory preferences, and behavioral guidelines.

    Attributes:
        id: Unique agent identifier.
        name: Human-readable name.
        version: Agent definition version.
        description: Detailed description.
        category: Agent category.
        tags: Semantic tags for discovery.
        enabled: Whether agent is enabled.
        skills: Skills configuration.
        tools: Tools configuration.
        memory: Memory context preferences.
        behavior: Behavioral guidelines.
        constraints: Agent constraints.
        markdown_content: Optional extended documentation.
        file_path: Path to agent definition file.
        created: Creation timestamp.
        updated: Last update timestamp.
    """

    id: str
    name: str
    version: str
    description: str
    category: str
    tags: list[str] = field(default_factory=list)
    enabled: bool = True
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)
    constraints: AgentConstraints = field(default_factory=AgentConstraints)
    markdown_content: str = ""
    file_path: str = ""
    created: Optional[datetime] = None
    updated: Optional[datetime] = None

    def __post_init__(self) -> None:
        """Validate agent category."""
        if self.category not in AGENT_CATEGORIES:
            self.category = "general"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "category": self.category,
            "tags": self.tags,
            "enabled": self.enabled,
            "skills": self.skills.to_dict(),
            "tools": self.tools.to_dict(),
            "memory": self.memory.to_dict(),
            "behavior": self.behavior.to_dict(),
            "constraints": self.constraints.to_dict(),
            "markdown_content": self.markdown_content,
            "file_path": self.file_path,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }

    def to_json_configs(self) -> tuple[str, str, str, str, str]:
        """Convert configs to JSON strings.

        Returns:
            Tuple of (skills_json, tools_json, memory_json, behavior_json, constraints_json).
        """
        return (
            json.dumps(self.skills.to_dict()),
            json.dumps(self.tools.to_dict()),
            json.dumps(self.memory.to_dict()),
            json.dumps(self.behavior.to_dict()),
            json.dumps(self.constraints.to_dict()),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Agent":
        """Create Agent from dictionary."""
        # Parse timestamps
        created = data.get("created")
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                created = None

        updated = data.get("updated")
        if isinstance(updated, str):
            try:
                updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            except ValueError:
                updated = None

        # Parse memory_context as memory (handle different key names)
        memory_data = data.get("memory") or data.get("memory_context", {})

        return cls(
            id=data["id"],
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            category=data.get("category", "general"),
            tags=data.get("tags", []),
            enabled=data.get("enabled", True),
            skills=SkillsConfig.from_dict(data.get("skills", {})),
            tools=ToolsConfig.from_dict(data.get("tools", {})),
            memory=MemoryConfig.from_dict(memory_data),
            behavior=BehaviorConfig.from_dict(data.get("behavior", {})),
            constraints=AgentConstraints.from_dict(data.get("constraints", {})),
            markdown_content=data.get("markdown_content", ""),
            file_path=data.get("file_path", ""),
            created=created,
            updated=updated,
        )

    def get_all_skill_ids(self) -> list[str]:
        """Get all enabled skill IDs."""
        return self.skills.get_all_enabled()

    def get_enabled_tool_ids(self) -> list[str]:
        """Get all enabled tool IDs."""
        return self.tools.enabled

    def can_use_skill(self, skill_id: str) -> bool:
        """Check if agent can use a skill."""
        return self.skills.is_enabled(skill_id)

    def can_use_tool(self, tool_id: str) -> bool:
        """Check if agent can use a tool."""
        return self.tools.is_enabled(tool_id)

    def can_access_scope(self, scope: str) -> bool:
        """Check if agent can access a memory scope."""
        if scope in self.memory.excluded_scopes:
            return False
        if self.constraints.allowed_scopes:
            return scope in self.constraints.allowed_scopes
        return True

    def get_system_prompt_additions(self) -> str:
        """Generate system prompt additions based on agent configuration."""
        parts: list[str] = []

        if self.behavior.tone:
            parts.append(f"Communication tone: {self.behavior.tone}")

        if self.behavior.focus_areas:
            parts.append(f"Focus areas: {', '.join(self.behavior.focus_areas)}")

        if self.behavior.avoid_areas:
            parts.append(f"Avoid: {', '.join(self.behavior.avoid_areas)}")

        if self.behavior.guidelines:
            parts.append("Guidelines:")
            for guideline in self.behavior.guidelines:
                parts.append(f"- {guideline}")

        if not self.constraints.allow_tool_execution:
            parts.append("Tool execution is disabled.")

        if not self.constraints.allow_memory_write:
            parts.append("Memory writing is disabled (read-only agent).")

        return "\n".join(parts)
