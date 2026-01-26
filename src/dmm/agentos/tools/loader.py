"""Tool file loader for the Agent OS.

This module provides functionality to load tool definitions from
YAML files with optional Markdown content sections.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from dmm.agentos.tools.models import (
    APIConfig,
    CLIConfig,
    MCPConfig,
    Tool,
    ToolConstraints,
    ToolInput,
    ToolOutput,
    TOOL_CATEGORIES,
    TOOL_TYPES,
)


class ToolLoadError(Exception):
    """Raised when a tool file cannot be loaded."""

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        self.message = message
        super().__init__(f"Failed to load tool from {path}: {message}")


class ToolValidationError(Exception):
    """Raised when a tool definition is invalid."""

    def __init__(self, tool_id: str, errors: list[str]) -> None:
        self.tool_id = tool_id
        self.errors = errors
        super().__init__(f"Invalid tool '{tool_id}': {'; '.join(errors)}")


class ToolLoader:
    """Loader for tool definition files.

    Handles parsing of .tool.yaml files which contain:
    - YAML configuration block
    - Optional Markdown documentation section
    """

    def __init__(self, strict: bool = False) -> None:
        """Initialize the tool loader.

        Args:
            strict: If True, raise errors on validation failures.
        """
        self.strict = strict

    def load(self, path: Path) -> Tool:
        """Load a tool from a file.

        Args:
            path: Path to the .tool.yaml file.

        Returns:
            Parsed Tool object.

        Raises:
            ToolLoadError: If file cannot be read or parsed.
            ToolValidationError: If tool definition is invalid (strict mode).
        """
        if not path.exists():
            raise ToolLoadError(path, "File not found")

        if not path.suffix == ".yaml" and not str(path).endswith(".tool.yaml"):
            raise ToolLoadError(path, "File must have .tool.yaml extension")

        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            raise ToolLoadError(path, f"Cannot read file: {e}")

        return self.parse(content, path)

    def parse(self, content: str, path: Optional[Path] = None) -> Tool:
        """Parse tool definition from content string.

        Args:
            content: File content to parse.
            path: Optional path for error reporting.

        Returns:
            Parsed Tool object.
        """
        file_path = path or Path("<string>")
        yaml_content, markdown_content = self._split_content(content)

        try:
            data = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            raise ToolLoadError(file_path, f"Invalid YAML: {e}")

        if not isinstance(data, dict):
            raise ToolLoadError(file_path, "YAML must be a dictionary")

        # Validate required fields
        errors = self._validate_required_fields(data)
        if errors:
            if self.strict:
                raise ToolValidationError(data.get("id", "unknown"), errors)
            if "id" not in data:
                raise ToolLoadError(file_path, "Missing required field: id")

        # Parse the tool
        tool = self._parse_tool(data, markdown_content, file_path)
        return tool

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
            tool_id = data["id"]
            if not isinstance(tool_id, str):
                errors.append("Field 'id' must be a string")
            elif not tool_id.startswith("tool_"):
                errors.append("Field 'id' must start with 'tool_'")

        if "type" in data or "tool_type" in data:
            tool_type = data.get("tool_type", data.get("type"))
            if tool_type not in TOOL_TYPES:
                errors.append(f"Invalid tool_type: {tool_type}")

        return errors

    def _parse_tool(
        self,
        data: dict[str, Any],
        markdown_content: str,
        file_path: Path,
    ) -> Tool:
        """Parse a Tool object from validated data."""
        # Parse inputs
        inputs: list[ToolInput] = []
        for inp_data in data.get("inputs", []):
            try:
                inputs.append(ToolInput.from_dict(inp_data))
            except (ValueError, KeyError) as e:
                if self.strict:
                    raise ToolValidationError(data["id"], [f"Invalid input: {e}"])

        # Parse outputs
        outputs: list[ToolOutput] = []
        for out_data in data.get("outputs", []):
            try:
                outputs.append(ToolOutput.from_dict(out_data))
            except (ValueError, KeyError) as e:
                if self.strict:
                    raise ToolValidationError(data["id"], [f"Invalid output: {e}"])

        # Parse constraints
        constraints = ToolConstraints.from_dict(data.get("constraints", {}))

        # Determine tool type
        tool_type = data.get("tool_type", data.get("type", "cli"))
        if tool_type not in TOOL_TYPES:
            tool_type = "cli"

        # Parse type-specific configs
        cli_config = None
        api_config = None
        mcp_config = None

        if tool_type == "cli":
            cli_config = self._parse_cli_config(data)
        elif tool_type == "api":
            api_config = self._parse_api_config(data)
        elif tool_type == "mcp":
            mcp_config = self._parse_mcp_config(data)

        # Parse timestamps
        created = self._parse_datetime(data.get("created"))
        updated = self._parse_datetime(data.get("updated"))

        # Get category with fallback
        category = data.get("category", "general")
        if category not in TOOL_CATEGORIES:
            category = "general"

        return Tool(
            id=data["id"],
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            tool_type=tool_type,
            description=data.get("description", ""),
            category=category,
            tags=data.get("tags", []),
            enabled=data.get("enabled", True),
            inputs=inputs,
            outputs=outputs,
            constraints=constraints,
            cli_config=cli_config,
            api_config=api_config,
            mcp_config=mcp_config,
            markdown_content=markdown_content,
            file_path=str(file_path),
            created=created,
            updated=updated,
        )

    def _parse_cli_config(self, data: dict[str, Any]) -> Optional[CLIConfig]:
        """Parse CLI configuration from data."""
        cmd_data = data.get("command", {})
        avail_data = data.get("availability", {})

        if not cmd_data and not avail_data:
            return None

        template = cmd_data.get("template", "")
        working_dir = cmd_data.get("working_dir", "project_root")

        return CLIConfig(
            command_template=template,
            working_dir=working_dir,
            shell=cmd_data.get("shell", True),
            env_vars=cmd_data.get("env_vars", {}),
            check_command=avail_data.get("check_command"),
            required_files=avail_data.get("required_files", []),
            platforms=avail_data.get("platforms", ["linux", "macos", "windows"]),
        )

    def _parse_api_config(self, data: dict[str, Any]) -> Optional[APIConfig]:
        """Parse API configuration from data."""
        api_data = data.get("api", {})

        if not api_data:
            return None

        auth_data = api_data.get("auth", {})

        config = APIConfig(
            base_url=api_data.get("base_url", ""),
            auth_type=auth_data.get("type", "none"),
            auth_env_var=auth_data.get("env_var"),
            headers=api_data.get("headers", {}),
        )

        # Parse endpoints
        from dmm.agentos.tools.models import APIEndpoint
        for ep_data in data.get("endpoints", []):
            ep_inputs = [ToolInput.from_dict(i) for i in ep_data.get("inputs", [])]
            ep_outputs = [ToolOutput.from_dict(o) for o in ep_data.get("outputs", [])]
            config.endpoints.append(APIEndpoint(
                name=ep_data.get("name", ""),
                method=ep_data.get("method", "GET"),
                path=ep_data.get("path", ""),
                inputs=ep_inputs,
                outputs=ep_outputs,
                description=ep_data.get("description", ""),
            ))

        return config

    def _parse_mcp_config(self, data: dict[str, Any]) -> Optional[MCPConfig]:
        """Parse MCP configuration from data."""
        mcp_data = data.get("mcp", {})

        if not mcp_data:
            return None

        constraints_data = data.get("constraints", {})

        config = MCPConfig(
            server_command=mcp_data.get("server_command", ""),
            server_args=mcp_data.get("server_args", []),
            transport=mcp_data.get("transport", "stdio"),
            allowed_paths=constraints_data.get("allowed_paths", []),
            denied_paths=constraints_data.get("denied_paths", []),
        )

        # Parse capabilities
        from dmm.agentos.tools.models import MCPCapability
        for cap_data in data.get("capabilities", []):
            cap_inputs = [ToolInput.from_dict(i) for i in cap_data.get("inputs", [])]
            cap_outputs = [ToolOutput.from_dict(o) for o in cap_data.get("outputs", [])]
            config.capabilities.append(MCPCapability(
                name=cap_data.get("name", ""),
                description=cap_data.get("description", ""),
                inputs=cap_inputs,
                outputs=cap_outputs,
            ))

        return config

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

    def load_directory(self, directory: Path) -> list[Tool]:
        """Load all tools from a directory.

        Args:
            directory: Directory containing .tool.yaml files.

        Returns:
            List of loaded Tool objects.
        """
        tools: list[Tool] = []

        if not directory.exists():
            return tools

        for path in directory.rglob("*.tool.yaml"):
            try:
                tool = self.load(path)
                tools.append(tool)
            except (ToolLoadError, ToolValidationError):
                if self.strict:
                    raise
                continue

        return tools
