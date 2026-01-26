"""Skill data models for the Agent OS.

This module defines the complete data model for skills including:
- SkillInput: Input parameter definition
- SkillOutput: Output parameter definition
- SkillDependencies: Skill and tool dependencies
- SkillExecution: Execution configuration
- SkillExample: Example input/output pairs
- Skill: Complete skill definition
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final, Optional


# Valid skill categories
SKILL_CATEGORIES: Final[tuple[str, ...]] = (
    "quality",
    "generation",
    "analysis",
    "refactoring",
    "documentation",
    "testing",
    "security",
    "performance",
    "debugging",
    "general",
)

# Valid input/output types
PARAM_TYPES: Final[tuple[str, ...]] = (
    "string",
    "number",
    "integer",
    "boolean",
    "array",
    "object",
)


@dataclass
class SkillInput:
    """Definition of a skill input parameter.

    Attributes:
        name: Parameter name.
        param_type: Data type (string, number, boolean, array, object).
        required: Whether the parameter is required.
        default: Default value if not provided.
        description: Human-readable description.
        enum: List of allowed values (optional).
    """

    name: str
    param_type: str
    required: bool = True
    default: Any = None
    description: str = ""
    enum: Optional[list[Any]] = None

    def __post_init__(self) -> None:
        """Validate parameter type."""
        if self.param_type not in PARAM_TYPES:
            raise ValueError(
                f"Invalid param_type '{self.param_type}'. "
                f"Must be one of: {PARAM_TYPES}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        result: dict[str, Any] = {
            "name": self.name,
            "type": self.param_type,
            "required": self.required,
            "description": self.description,
        }
        if self.default is not None:
            result["default"] = self.default
        if self.enum is not None:
            result["enum"] = self.enum
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillInput":
        """Create SkillInput from dictionary."""
        return cls(
            name=data["name"],
            param_type=data.get("type", "string"),
            required=data.get("required", True),
            default=data.get("default"),
            description=data.get("description", ""),
            enum=data.get("enum"),
        )


@dataclass
class SkillOutput:
    """Definition of a skill output parameter.

    Attributes:
        name: Output name.
        param_type: Data type (string, number, boolean, array, object).
        description: Human-readable description.
    """

    name: str
    param_type: str
    description: str = ""

    def __post_init__(self) -> None:
        """Validate parameter type."""
        if self.param_type not in PARAM_TYPES:
            raise ValueError(
                f"Invalid param_type '{self.param_type}'. "
                f"Must be one of: {PARAM_TYPES}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "type": self.param_type,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillOutput":
        """Create SkillOutput from dictionary."""
        return cls(
            name=data["name"],
            param_type=data.get("type", "string"),
            description=data.get("description", ""),
        )


@dataclass
class ToolRequirements:
    """Tool requirements for a skill.

    Attributes:
        required: List of required tool IDs.
        optional: List of optional tool IDs.
    """

    required: list[str] = field(default_factory=list)
    optional: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "required": self.required,
            "optional": self.optional,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolRequirements":
        """Create ToolRequirements from dictionary."""
        if data is None:
            return cls()
        return cls(
            required=data.get("required", []),
            optional=data.get("optional", []),
        )


@dataclass
class SkillDependencies:
    """Dependencies for a skill.

    Attributes:
        skills: List of required skill IDs.
        tools: Tool requirements.
    """

    skills: list[str] = field(default_factory=list)
    tools: ToolRequirements = field(default_factory=ToolRequirements)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "skills": self.skills,
            "tools": self.tools.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillDependencies":
        """Create SkillDependencies from dictionary."""
        if data is None:
            return cls()
        tools_data = data.get("tools", {})
        return cls(
            skills=data.get("skills", []),
            tools=ToolRequirements.from_dict(tools_data),
        )


@dataclass
class MemoryRequirement:
    """Memory context requirement for a skill.

    Attributes:
        scope: Required memory scope.
        tags: Required tags.
        description: Description of what memory is needed.
        required: Whether this memory context is required.
    """

    scope: str
    tags: list[str] = field(default_factory=list)
    description: str = ""
    required: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "scope": self.scope,
            "tags": self.tags,
            "description": self.description,
            "required": self.required,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryRequirement":
        """Create MemoryRequirement from dictionary."""
        return cls(
            scope=data.get("scope", "project"),
            tags=data.get("tags", []),
            description=data.get("description", ""),
            required=data.get("required", False),
        )


@dataclass
class SkillExecution:
    """Execution configuration for a skill.

    Attributes:
        timeout_seconds: Maximum execution time.
        retry_count: Number of retries on failure.
        parallel_safe: Whether skill can run in parallel.
    """

    timeout_seconds: int = 60
    retry_count: int = 2
    parallel_safe: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "timeout_seconds": self.timeout_seconds,
            "retry_count": self.retry_count,
            "parallel_safe": self.parallel_safe,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillExecution":
        """Create SkillExecution from dictionary."""
        if data is None:
            return cls()
        return cls(
            timeout_seconds=data.get("timeout_seconds", 60),
            retry_count=data.get("retry_count", 2),
            parallel_safe=data.get("parallel_safe", True),
        )


@dataclass
class SkillExample:
    """Example input/output pair for a skill.

    Attributes:
        name: Example name.
        input_data: Example input values.
        output_data: Expected output values.
    """

    name: str
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "input": self.input_data,
            "output": self.output_data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillExample":
        """Create SkillExample from dictionary."""
        return cls(
            name=data.get("name", ""),
            input_data=data.get("input", {}),
            output_data=data.get("output", {}),
        )


@dataclass
class Skill:
    """Complete skill definition.

    A skill represents a reusable agent capability with defined inputs,
    outputs, dependencies, and execution parameters.

    Attributes:
        id: Unique skill identifier.
        name: Human-readable name.
        version: Semantic version.
        description: Detailed description.
        category: Skill category.
        tags: Semantic tags for discovery.
        enabled: Whether skill is enabled.
        inputs: Input parameter definitions.
        outputs: Output parameter definitions.
        dependencies: Skill and tool dependencies.
        memory_requirements: Memory context requirements.
        execution: Execution configuration.
        examples: Example input/output pairs.
        markdown_content: Optional extended documentation.
        file_path: Path to skill definition file.
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
    inputs: list[SkillInput] = field(default_factory=list)
    outputs: list[SkillOutput] = field(default_factory=list)
    dependencies: SkillDependencies = field(default_factory=SkillDependencies)
    memory_requirements: list[MemoryRequirement] = field(default_factory=list)
    execution: SkillExecution = field(default_factory=SkillExecution)
    examples: list[SkillExample] = field(default_factory=list)
    markdown_content: str = ""
    file_path: str = ""
    created: Optional[datetime] = None
    updated: Optional[datetime] = None

    def __post_init__(self) -> None:
        """Validate skill category."""
        if self.category not in SKILL_CATEGORIES:
            raise ValueError(
                f"Invalid category '{self.category}'. "
                f"Must be one of: {SKILL_CATEGORIES}"
            )

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
            "inputs": [inp.to_dict() for inp in self.inputs],
            "outputs": [out.to_dict() for out in self.outputs],
            "dependencies": self.dependencies.to_dict(),
            "memory_requirements": [mr.to_dict() for mr in self.memory_requirements],
            "execution": self.execution.to_dict(),
            "examples": [ex.to_dict() for ex in self.examples],
            "markdown_content": self.markdown_content,
            "file_path": self.file_path,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }

    def to_json_schemas(self) -> tuple[str, str]:
        """Convert inputs and outputs to JSON schema strings.

        Returns:
            Tuple of (inputs_schema_json, outputs_schema_json).
        """
        inputs_schema = {
            "type": "object",
            "properties": {inp.name: {"type": inp.param_type, "description": inp.description} for inp in self.inputs},
            "required": [inp.name for inp in self.inputs if inp.required],
        }
        outputs_schema = {
            "type": "object",
            "properties": {out.name: {"type": out.param_type, "description": out.description} for out in self.outputs},
        }
        return json.dumps(inputs_schema), json.dumps(outputs_schema)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Skill":
        """Create Skill from dictionary."""
        inputs = [SkillInput.from_dict(inp) for inp in data.get("inputs", [])]
        outputs = [SkillOutput.from_dict(out) for out in data.get("outputs", [])]
        dependencies = SkillDependencies.from_dict(data.get("dependencies", {}))
        memory_requirements = [
            MemoryRequirement.from_dict(mr)
            for mr in data.get("memory_requirements", [])
        ]
        execution = SkillExecution.from_dict(data.get("execution", {}))
        examples = [SkillExample.from_dict(ex) for ex in data.get("examples", [])]

        created = data.get("created")
        if isinstance(created, str):
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        updated = data.get("updated")
        if isinstance(updated, str):
            updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))

        return cls(
            id=data["id"],
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            category=data.get("category", "general"),
            tags=data.get("tags", []),
            enabled=data.get("enabled", True),
            inputs=inputs,
            outputs=outputs,
            dependencies=dependencies,
            memory_requirements=memory_requirements,
            execution=execution,
            examples=examples,
            markdown_content=data.get("markdown_content", ""),
            file_path=data.get("file_path", ""),
            created=created,
            updated=updated,
        )

    def get_required_skill_ids(self) -> list[str]:
        """Get list of required skill IDs."""
        return self.dependencies.skills

    def get_required_tool_ids(self) -> list[str]:
        """Get list of required tool IDs."""
        return self.dependencies.tools.required

    def get_optional_tool_ids(self) -> list[str]:
        """Get list of optional tool IDs."""
        return self.dependencies.tools.optional

    def get_all_tool_ids(self) -> list[str]:
        """Get list of all tool IDs (required + optional)."""
        return self.dependencies.tools.required + self.dependencies.tools.optional

    def validate_inputs(self, inputs: dict[str, Any]) -> list[str]:
        """Validate input values against schema.

        Args:
            inputs: Input values to validate.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: list[str] = []

        # Check required inputs
        for inp in self.inputs:
            if inp.required and inp.name not in inputs:
                if inp.default is None:
                    errors.append(f"Missing required input: {inp.name}")

        # Check enum values
        for inp in self.inputs:
            if inp.enum and inp.name in inputs:
                if inputs[inp.name] not in inp.enum:
                    errors.append(
                        f"Invalid value for {inp.name}: {inputs[inp.name]}. "
                        f"Must be one of: {inp.enum}"
                    )

        return errors
