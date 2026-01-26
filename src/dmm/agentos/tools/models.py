"""Tool data models for the Agent OS.

This module defines the complete data model for tools including:
- ToolInput: Input parameter definition
- ToolOutput: Output parameter definition
- ToolConstraints: Execution constraints
- CLIConfig: CLI tool configuration
- APIConfig: HTTP API configuration
- MCPConfig: MCP server configuration
- Tool: Complete tool definition
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final, Optional


# Valid tool types
TOOL_TYPES: Final[tuple[str, ...]] = (
    "cli",
    "api",
    "mcp",
    "function",
)

# Valid tool categories
TOOL_CATEGORIES: Final[tuple[str, ...]] = (
    "linting",
    "testing",
    "formatting",
    "vcs",
    "filesystem",
    "database",
    "api",
    "build",
    "deployment",
    "monitoring",
    "security",
    "general",
)

# Valid parameter types
PARAM_TYPES: Final[tuple[str, ...]] = (
    "string",
    "number",
    "integer",
    "boolean",
    "array",
    "object",
    "json",
)


@dataclass
class ToolInput:
    """Definition of a tool input parameter.

    Attributes:
        name: Parameter name.
        param_type: Data type.
        required: Whether the parameter is required.
        default: Default value if not provided.
        description: Human-readable description.
        enum: List of allowed values.
    """

    name: str
    param_type: str
    required: bool = True
    default: Any = None
    description: str = ""
    enum: Optional[list[Any]] = None

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
    def from_dict(cls, data: dict[str, Any]) -> "ToolInput":
        """Create ToolInput from dictionary."""
        return cls(
            name=data["name"],
            param_type=data.get("type", "string"),
            required=data.get("required", True),
            default=data.get("default"),
            description=data.get("description", ""),
            enum=data.get("enum"),
        )


@dataclass
class ToolOutput:
    """Definition of a tool output.

    Attributes:
        name: Output name.
        param_type: Data type.
        description: Human-readable description.
    """

    name: str
    param_type: str
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "type": self.param_type,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolOutput":
        """Create ToolOutput from dictionary."""
        return cls(
            name=data["name"],
            param_type=data.get("type", "string"),
            description=data.get("description", ""),
        )


@dataclass
class ToolConstraints:
    """Execution constraints for a tool.

    Attributes:
        timeout_seconds: Maximum execution time.
        max_retries: Number of retries on failure.
        rate_limit_per_hour: Maximum calls per hour (None = unlimited).
        max_input_size_bytes: Maximum input size.
        max_output_size_bytes: Maximum output size.
        requires_auth: Whether authentication is required.
    """

    timeout_seconds: int = 60
    max_retries: int = 2
    rate_limit_per_hour: Optional[int] = None
    max_input_size_bytes: Optional[int] = None
    max_output_size_bytes: Optional[int] = None
    requires_auth: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "rate_limit_per_hour": self.rate_limit_per_hour,
            "max_input_size_bytes": self.max_input_size_bytes,
            "max_output_size_bytes": self.max_output_size_bytes,
            "requires_auth": self.requires_auth,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolConstraints":
        """Create ToolConstraints from dictionary."""
        if data is None:
            return cls()
        return cls(
            timeout_seconds=data.get("timeout_seconds", 60),
            max_retries=data.get("max_retries", 2),
            rate_limit_per_hour=data.get("rate_limit_per_hour"),
            max_input_size_bytes=data.get("max_input_size_bytes"),
            max_output_size_bytes=data.get("max_output_size_bytes"),
            requires_auth=data.get("requires_auth", False),
        )


@dataclass
class CLIConfig:
    """Configuration for CLI tools.

    Attributes:
        command_template: Command template with placeholders.
        working_dir: Working directory (project_root, cwd, or path).
        shell: Whether to run in shell.
        env_vars: Environment variables to set.
        check_command: Command to check availability.
        required_files: Files that must exist.
        platforms: Supported platforms.
    """

    command_template: str
    working_dir: str = "project_root"
    shell: bool = True
    env_vars: dict[str, str] = field(default_factory=dict)
    check_command: Optional[str] = None
    required_files: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=lambda: ["linux", "macos", "windows"])

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "command_template": self.command_template,
            "working_dir": self.working_dir,
            "shell": self.shell,
            "env_vars": self.env_vars,
            "check_command": self.check_command,
            "required_files": self.required_files,
            "platforms": self.platforms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CLIConfig":
        """Create CLIConfig from dictionary."""
        if data is None:
            return cls(command_template="")
        
        # Handle both 'command' and 'template' key variations
        template = data.get("command_template") or data.get("template", "")
        
        return cls(
            command_template=template,
            working_dir=data.get("working_dir", "project_root"),
            shell=data.get("shell", True),
            env_vars=data.get("env_vars", {}),
            check_command=data.get("check_command"),
            required_files=data.get("required_files", []),
            platforms=data.get("platforms", ["linux", "macos", "windows"]),
        )


@dataclass
class APIEndpoint:
    """Definition of an API endpoint.

    Attributes:
        name: Endpoint name.
        method: HTTP method.
        path: URL path with placeholders.
        inputs: Input parameters.
        outputs: Output definitions.
        description: Endpoint description.
    """

    name: str
    method: str
    path: str
    inputs: list[ToolInput] = field(default_factory=list)
    outputs: list[ToolOutput] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "method": self.method,
            "path": self.path,
            "inputs": [i.to_dict() for i in self.inputs],
            "outputs": [o.to_dict() for o in self.outputs],
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "APIEndpoint":
        """Create APIEndpoint from dictionary."""
        return cls(
            name=data.get("name", ""),
            method=data.get("method", "GET"),
            path=data.get("path", ""),
            inputs=[ToolInput.from_dict(i) for i in data.get("inputs", [])],
            outputs=[ToolOutput.from_dict(o) for o in data.get("outputs", [])],
            description=data.get("description", ""),
        )


@dataclass
class APIConfig:
    """Configuration for HTTP API tools.

    Attributes:
        base_url: Base URL for the API.
        auth_type: Authentication type (bearer, basic, api_key, none).
        auth_env_var: Environment variable containing credentials.
        headers: Default headers.
        endpoints: List of API endpoints.
    """

    base_url: str
    auth_type: str = "none"
    auth_env_var: Optional[str] = None
    headers: dict[str, str] = field(default_factory=dict)
    endpoints: list[APIEndpoint] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "base_url": self.base_url,
            "auth_type": self.auth_type,
            "auth_env_var": self.auth_env_var,
            "headers": self.headers,
            "endpoints": [e.to_dict() for e in self.endpoints],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "APIConfig":
        """Create APIConfig from dictionary."""
        if data is None:
            return cls(base_url="")
        
        # Parse auth section
        auth_data = data.get("auth", {})
        auth_type = auth_data.get("type", "none") if isinstance(auth_data, dict) else "none"
        auth_env_var = auth_data.get("env_var") if isinstance(auth_data, dict) else None
        
        return cls(
            base_url=data.get("base_url", ""),
            auth_type=auth_type,
            auth_env_var=auth_env_var,
            headers=data.get("headers", {}),
            endpoints=[APIEndpoint.from_dict(e) for e in data.get("endpoints", [])],
        )


@dataclass
class MCPCapability:
    """Definition of an MCP server capability.

    Attributes:
        name: Capability name.
        description: Capability description.
        inputs: Input parameters.
        outputs: Output definitions.
    """

    name: str
    description: str = ""
    inputs: list[ToolInput] = field(default_factory=list)
    outputs: list[ToolOutput] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "description": self.description,
            "inputs": [i.to_dict() for i in self.inputs],
            "outputs": [o.to_dict() for o in self.outputs],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MCPCapability":
        """Create MCPCapability from dictionary."""
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            inputs=[ToolInput.from_dict(i) for i in data.get("inputs", [])],
            outputs=[ToolOutput.from_dict(o) for o in data.get("outputs", [])],
        )


@dataclass
class MCPConfig:
    """Configuration for MCP server tools.

    Attributes:
        server_command: Command to start the MCP server.
        server_args: Arguments to pass to the server.
        transport: Transport type (stdio, http).
        capabilities: List of server capabilities.
        allowed_paths: Allowed file paths.
        denied_paths: Denied file paths.
    """

    server_command: str
    server_args: list[str] = field(default_factory=list)
    transport: str = "stdio"
    capabilities: list[MCPCapability] = field(default_factory=list)
    allowed_paths: list[str] = field(default_factory=list)
    denied_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "server_command": self.server_command,
            "server_args": self.server_args,
            "transport": self.transport,
            "capabilities": [c.to_dict() for c in self.capabilities],
            "allowed_paths": self.allowed_paths,
            "denied_paths": self.denied_paths,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MCPConfig":
        """Create MCPConfig from dictionary."""
        if data is None:
            return cls(server_command="")
        
        # Parse constraints for paths
        constraints = data.get("constraints", {})
        
        return cls(
            server_command=data.get("server_command", ""),
            server_args=data.get("server_args", []),
            transport=data.get("transport", "stdio"),
            capabilities=[MCPCapability.from_dict(c) for c in data.get("capabilities", [])],
            allowed_paths=constraints.get("allowed_paths", []),
            denied_paths=constraints.get("denied_paths", []),
        )


@dataclass
class AvailabilityResult:
    """Result of checking tool availability.

    Attributes:
        available: Whether the tool is available.
        version: Detected version if available.
        message: Status message.
        missing_requirements: List of missing requirements.
    """

    available: bool
    version: Optional[str] = None
    message: str = ""
    missing_requirements: list[str] = field(default_factory=list)


@dataclass
class Tool:
    """Complete tool definition.

    A tool represents an external capability the agent can invoke,
    supporting CLI commands, HTTP APIs, MCP servers, and local functions.

    Attributes:
        id: Unique tool identifier.
        name: Human-readable name.
        version: Tool version.
        tool_type: Type of tool (cli, api, mcp, function).
        description: Detailed description.
        category: Tool category.
        tags: Semantic tags for discovery.
        enabled: Whether tool is enabled.
        inputs: Input parameter definitions.
        outputs: Output definitions.
        constraints: Execution constraints.
        cli_config: CLI-specific configuration.
        api_config: API-specific configuration.
        mcp_config: MCP-specific configuration.
        markdown_content: Optional extended documentation.
        file_path: Path to tool definition file.
        created: Creation timestamp.
        updated: Last update timestamp.
    """

    id: str
    name: str
    version: str
    tool_type: str
    description: str
    category: str
    tags: list[str] = field(default_factory=list)
    enabled: bool = True
    inputs: list[ToolInput] = field(default_factory=list)
    outputs: list[ToolOutput] = field(default_factory=list)
    constraints: ToolConstraints = field(default_factory=ToolConstraints)
    cli_config: Optional[CLIConfig] = None
    api_config: Optional[APIConfig] = None
    mcp_config: Optional[MCPConfig] = None
    markdown_content: str = ""
    file_path: str = ""
    created: Optional[datetime] = None
    updated: Optional[datetime] = None

    def __post_init__(self) -> None:
        """Validate tool type and category."""
        if self.tool_type not in TOOL_TYPES:
            raise ValueError(
                f"Invalid tool_type '{self.tool_type}'. "
                f"Must be one of: {TOOL_TYPES}"
            )
        if self.category not in TOOL_CATEGORIES:
            raise ValueError(
                f"Invalid category '{self.category}'. "
                f"Must be one of: {TOOL_CATEGORIES}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "tool_type": self.tool_type,
            "description": self.description,
            "category": self.category,
            "tags": self.tags,
            "enabled": self.enabled,
            "inputs": [i.to_dict() for i in self.inputs],
            "outputs": [o.to_dict() for o in self.outputs],
            "constraints": self.constraints.to_dict(),
            "markdown_content": self.markdown_content,
            "file_path": self.file_path,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }

        if self.cli_config:
            result["cli_config"] = self.cli_config.to_dict()
        if self.api_config:
            result["api_config"] = self.api_config.to_dict()
        if self.mcp_config:
            result["mcp_config"] = self.mcp_config.to_dict()

        return result

    def to_json_schemas(self) -> tuple[str, str]:
        """Convert inputs and outputs to JSON schema strings.

        Returns:
            Tuple of (inputs_schema_json, outputs_schema_json).
        """
        inputs_schema = {
            "type": "object",
            "properties": {
                inp.name: {"type": inp.param_type, "description": inp.description}
                for inp in self.inputs
            },
            "required": [inp.name for inp in self.inputs if inp.required],
        }
        outputs_schema = {
            "type": "object",
            "properties": {
                out.name: {"type": out.param_type, "description": out.description}
                for out in self.outputs
            },
        }
        return json.dumps(inputs_schema), json.dumps(outputs_schema)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Tool":
        """Create Tool from dictionary."""
        # Parse inputs and outputs
        inputs = [ToolInput.from_dict(i) for i in data.get("inputs", [])]
        outputs = [ToolOutput.from_dict(o) for o in data.get("outputs", [])]
        constraints = ToolConstraints.from_dict(data.get("constraints", {}))

        # Parse type-specific configs
        cli_config = None
        api_config = None
        mcp_config = None

        tool_type = data.get("tool_type", data.get("type", "cli"))

        if tool_type == "cli":
            cmd_data = data.get("cli_config") or data.get("command", {})
            if cmd_data:
                cli_config = CLIConfig.from_dict(cmd_data)
            # Also check availability section
            avail_data = data.get("availability", {})
            if avail_data and cli_config:
                cli_config.check_command = avail_data.get("check_command", cli_config.check_command)
                cli_config.required_files = avail_data.get("required_files", cli_config.required_files)
                cli_config.platforms = avail_data.get("platforms", cli_config.platforms)
        elif tool_type == "api":
            api_data = data.get("api_config") or data.get("api", {})
            if api_data:
                api_config = APIConfig.from_dict(api_data)
            # Also parse endpoints at top level
            if "endpoints" in data and api_config:
                api_config.endpoints = [APIEndpoint.from_dict(e) for e in data["endpoints"]]
        elif tool_type == "mcp":
            mcp_data = data.get("mcp_config") or data.get("mcp", {})
            if mcp_data:
                mcp_config = MCPConfig.from_dict(mcp_data)
            # Also parse capabilities at top level
            if "capabilities" in data and mcp_config:
                mcp_config.capabilities = [MCPCapability.from_dict(c) for c in data["capabilities"]]

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

        # Get category with fallback
        category = data.get("category", "general")
        if category not in TOOL_CATEGORIES:
            category = "general"

        return cls(
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
            markdown_content=data.get("markdown_content", ""),
            file_path=data.get("file_path", ""),
            created=created,
            updated=updated,
        )

    def get_check_command(self) -> Optional[str]:
        """Get the availability check command for CLI tools."""
        if self.cli_config:
            return self.cli_config.check_command
        return None

    def get_required_files(self) -> list[str]:
        """Get required files for CLI tools."""
        if self.cli_config:
            return self.cli_config.required_files
        return []

    def requires_authentication(self) -> bool:
        """Check if the tool requires authentication."""
        if self.constraints.requires_auth:
            return True
        if self.api_config and self.api_config.auth_type != "none":
            return True
        return False
