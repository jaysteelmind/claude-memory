"""Skill file loader for the Agent OS.

This module provides functionality to load skill definitions from
YAML files with optional Markdown content sections.

Skill files follow the format:
- YAML frontmatter with metadata and configuration
- Optional Markdown content after the YAML for extended documentation
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from dmm.agentos.skills.models import (
    MemoryRequirement,
    Skill,
    SkillDependencies,
    SkillExample,
    SkillExecution,
    SkillInput,
    SkillOutput,
    ToolRequirements,
)


class SkillLoadError(Exception):
    """Raised when a skill file cannot be loaded."""

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        self.message = message
        super().__init__(f"Failed to load skill from {path}: {message}")


class SkillValidationError(Exception):
    """Raised when a skill definition is invalid."""

    def __init__(self, skill_id: str, errors: list[str]) -> None:
        self.skill_id = skill_id
        self.errors = errors
        super().__init__(f"Invalid skill '{skill_id}': {'; '.join(errors)}")


class SkillLoader:
    """Loader for skill definition files.

    Handles parsing of .skill.yaml files which contain:
    - YAML configuration block
    - Optional Markdown documentation section

    The file format supports either:
    1. Pure YAML (entire file is YAML)
    2. YAML with Markdown (YAML block followed by --- and Markdown)
    """

    # Pattern to split YAML frontmatter from Markdown content
    YAML_MARKDOWN_PATTERN = re.compile(
        r"^---\s*\n(.*?)\n---\s*\n(.*)$",
        re.DOTALL,
    )

    # Alternative pattern for files starting with YAML directly
    YAML_ONLY_PATTERN = re.compile(
        r"^(.*?)\n---\s*\n(.*)$",
        re.DOTALL,
    )

    def __init__(self, strict: bool = False) -> None:
        """Initialize the skill loader.

        Args:
            strict: If True, raise errors on validation failures.
                   If False, log warnings and skip invalid skills.
        """
        self.strict = strict

    def load(self, path: Path) -> Skill:
        """Load a skill from a file.

        Args:
            path: Path to the .skill.yaml file.

        Returns:
            Parsed Skill object.

        Raises:
            SkillLoadError: If file cannot be read or parsed.
            SkillValidationError: If skill definition is invalid (strict mode).
        """
        if not path.exists():
            raise SkillLoadError(path, "File not found")

        if not path.suffix == ".yaml" and not str(path).endswith(".skill.yaml"):
            raise SkillLoadError(path, "File must have .skill.yaml extension")

        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            raise SkillLoadError(path, f"Cannot read file: {e}")

        return self.parse(content, path)

    def parse(self, content: str, path: Optional[Path] = None) -> Skill:
        """Parse skill definition from content string.

        Args:
            content: File content to parse.
            path: Optional path for error reporting.

        Returns:
            Parsed Skill object.

        Raises:
            SkillLoadError: If content cannot be parsed.
            SkillValidationError: If skill definition is invalid (strict mode).
        """
        file_path = path or Path("<string>")
        yaml_content, markdown_content = self._split_content(content)

        try:
            data = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            raise SkillLoadError(file_path, f"Invalid YAML: {e}")

        if not isinstance(data, dict):
            raise SkillLoadError(file_path, "YAML must be a dictionary")

        # Validate required fields
        errors = self._validate_required_fields(data)
        if errors:
            if self.strict:
                raise SkillValidationError(data.get("id", "unknown"), errors)
            # In non-strict mode, we still need an ID
            if "id" not in data:
                raise SkillLoadError(file_path, "Missing required field: id")

        # Parse the skill
        skill = self._parse_skill(data, markdown_content, file_path)
        return skill

    def _split_content(self, content: str) -> tuple[str, str]:
        """Split content into YAML and Markdown sections.

        Args:
            content: Raw file content.

        Returns:
            Tuple of (yaml_content, markdown_content).
        """
        content = content.strip()

        # Check if content starts with ---
        if content.startswith("---"):
            # Remove leading ---
            content = content[3:].lstrip("\n")
            # Find the closing ---
            match = re.search(r"\n---\s*\n", content)
            if match:
                yaml_content = content[: match.start()]
                markdown_content = content[match.end() :].strip()
                return yaml_content, markdown_content
            else:
                # No closing ---, entire content is YAML
                return content, ""
        else:
            # Check for embedded --- separator
            match = self.YAML_ONLY_PATTERN.match(content)
            if match:
                return match.group(1).strip(), match.group(2).strip()
            # Entire content is YAML
            return content, ""

    def _validate_required_fields(self, data: dict[str, Any]) -> list[str]:
        """Validate that required fields are present.

        Args:
            data: Parsed YAML data.

        Returns:
            List of validation error messages.
        """
        errors: list[str] = []
        required_fields = ["id", "name", "description"]

        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")

        # Validate ID format
        if "id" in data:
            skill_id = data["id"]
            if not isinstance(skill_id, str):
                errors.append("Field 'id' must be a string")
            elif not skill_id.startswith("skill_"):
                errors.append("Field 'id' must start with 'skill_'")

        return errors

    def _parse_skill(
        self,
        data: dict[str, Any],
        markdown_content: str,
        file_path: Path,
    ) -> Skill:
        """Parse a Skill object from validated data.

        Args:
            data: Parsed and validated YAML data.
            markdown_content: Optional Markdown documentation.
            file_path: Path to source file.

        Returns:
            Parsed Skill object.
        """
        # Parse inputs
        inputs: list[SkillInput] = []
        for inp_data in data.get("inputs", []):
            try:
                inputs.append(SkillInput.from_dict(inp_data))
            except (ValueError, KeyError) as e:
                if self.strict:
                    raise SkillValidationError(data["id"], [f"Invalid input: {e}"])

        # Parse outputs
        outputs: list[SkillOutput] = []
        for out_data in data.get("outputs", []):
            try:
                outputs.append(SkillOutput.from_dict(out_data))
            except (ValueError, KeyError) as e:
                if self.strict:
                    raise SkillValidationError(data["id"], [f"Invalid output: {e}"])

        # Parse dependencies
        deps_data = data.get("dependencies", {})
        dependencies = SkillDependencies(
            skills=deps_data.get("skills", []),
            tools=ToolRequirements(
                required=deps_data.get("tools", {}).get("required", []),
                optional=deps_data.get("tools", {}).get("optional", []),
            ),
        )

        # Parse memory requirements
        memory_requirements: list[MemoryRequirement] = []
        mem_req_data = data.get("memory_requirements", {})
        for req in mem_req_data.get("required", []):
            memory_requirements.append(
                MemoryRequirement(
                    scope=req.get("scope", "project"),
                    tags=req.get("tags", []),
                    description=req.get("description", ""),
                    required=True,
                )
            )
        for req in mem_req_data.get("optional", []):
            memory_requirements.append(
                MemoryRequirement(
                    scope=req.get("scope", "project"),
                    tags=req.get("tags", []),
                    description=req.get("description", ""),
                    required=False,
                )
            )

        # Parse execution config
        exec_data = data.get("execution", {})
        execution = SkillExecution(
            timeout_seconds=exec_data.get("timeout_seconds", 60),
            retry_count=exec_data.get("retry_count", 2),
            parallel_safe=exec_data.get("parallel_safe", True),
        )

        # Parse examples
        examples: list[SkillExample] = []
        for ex_data in data.get("examples", []):
            examples.append(
                SkillExample(
                    name=ex_data.get("name", ""),
                    input_data=ex_data.get("input", {}),
                    output_data=ex_data.get("output", {}),
                )
            )

        # Parse timestamps
        created = data.get("created")
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                created = None
        elif isinstance(created, datetime):
            pass
        else:
            created = None

        updated = data.get("updated")
        if isinstance(updated, str):
            try:
                updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            except ValueError:
                updated = None
        elif isinstance(updated, datetime):
            pass
        else:
            updated = None

        # Get category with fallback
        category = data.get("category", "general")
        from dmm.agentos.skills.models import SKILL_CATEGORIES
        if category not in SKILL_CATEGORIES:
            category = "general"

        return Skill(
            id=data["id"],
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            category=category,
            tags=data.get("tags", []),
            enabled=data.get("enabled", True),
            inputs=inputs,
            outputs=outputs,
            dependencies=dependencies,
            memory_requirements=memory_requirements,
            execution=execution,
            examples=examples,
            markdown_content=markdown_content,
            file_path=str(file_path),
            created=created,
            updated=updated,
        )

    def load_directory(self, directory: Path) -> list[Skill]:
        """Load all skills from a directory.

        Args:
            directory: Directory containing .skill.yaml files.

        Returns:
            List of loaded Skill objects.
        """
        skills: list[Skill] = []

        if not directory.exists():
            return skills

        for path in directory.rglob("*.skill.yaml"):
            try:
                skill = self.load(path)
                skills.append(skill)
            except (SkillLoadError, SkillValidationError) as e:
                if self.strict:
                    raise
                # In non-strict mode, skip invalid files
                continue

        return skills
