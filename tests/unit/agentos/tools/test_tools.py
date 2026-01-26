"""Unit tests for tools module."""

import pytest
from pathlib import Path
import tempfile

from dmm.agentos.tools.models import (
    TOOL_TYPES,
    TOOL_CATEGORIES,
    Tool,
    ToolInput,
    ToolOutput,
    ToolConstraints,
    CLIConfig,
    APIConfig,
    MCPConfig,
    AvailabilityResult,
)
from dmm.agentos.tools.loader import (
    ToolLoader,
    ToolLoadError,
    ToolValidationError,
)
from dmm.agentos.tools.registry import (
    ToolRegistry,
    ToolRegistryStats,
    SyncResult,
)


class TestToolInput:
    """Tests for ToolInput dataclass."""

    def test_create_basic(self):
        """Test creating a basic tool input."""
        inp = ToolInput(name="file", param_type="string")
        assert inp.name == "file"
        assert inp.param_type == "string"
        assert inp.required is True

    def test_to_dict(self):
        """Test serialization to dict."""
        inp = ToolInput(name="path", param_type="string", required=True)
        data = inp.to_dict()
        assert data["name"] == "path"
        assert data["type"] == "string"

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {"name": "files", "type": "array", "required": False}
        inp = ToolInput.from_dict(data)
        assert inp.name == "files"
        assert inp.required is False


class TestToolOutput:
    """Tests for ToolOutput dataclass."""

    def test_create_basic(self):
        """Test creating a basic tool output."""
        out = ToolOutput(name="result", param_type="string")
        assert out.name == "result"

    def test_to_from_dict(self):
        """Test round-trip serialization."""
        out = ToolOutput(name="issues", param_type="array", description="Found issues")
        data = out.to_dict()
        restored = ToolOutput.from_dict(data)
        assert restored.name == out.name
        assert restored.param_type == out.param_type


class TestToolConstraints:
    """Tests for ToolConstraints dataclass."""

    def test_defaults(self):
        """Test default constraints."""
        constraints = ToolConstraints()
        assert constraints.timeout_seconds == 60
        assert constraints.max_retries == 2
        assert constraints.requires_auth is False

    def test_custom_values(self):
        """Test custom constraint values."""
        constraints = ToolConstraints(
            timeout_seconds=120,
            max_retries=5,
            rate_limit_per_hour=100,
        )
        assert constraints.timeout_seconds == 120
        assert constraints.rate_limit_per_hour == 100


class TestCLIConfig:
    """Tests for CLIConfig dataclass."""

    def test_create_basic(self):
        """Test creating basic CLI config."""
        config = CLIConfig(command_template="ruff check {files}")
        assert config.command_template == "ruff check {files}"
        assert config.working_dir == "project_root"
        assert config.shell is True

    def test_with_env_vars(self):
        """Test CLI config with env vars."""
        config = CLIConfig(
            command_template="mycommand",
            env_vars={"DEBUG": "1"},
        )
        assert config.env_vars["DEBUG"] == "1"

    def test_to_from_dict(self):
        """Test round-trip serialization."""
        config = CLIConfig(
            command_template="test {arg}",
            check_command="test --version",
            platforms=["linux", "macos"],
        )
        data = config.to_dict()
        restored = CLIConfig.from_dict(data)
        assert restored.command_template == config.command_template
        assert restored.check_command == config.check_command


class TestAPIConfig:
    """Tests for APIConfig dataclass."""

    def test_create_basic(self):
        """Test creating basic API config."""
        config = APIConfig(base_url="https://api.example.com")
        assert config.base_url == "https://api.example.com"
        assert config.auth_type == "none"

    def test_with_auth(self):
        """Test API config with authentication."""
        config = APIConfig(
            base_url="https://api.example.com",
            auth_type="bearer",
            auth_env_var="API_TOKEN",
        )
        assert config.auth_type == "bearer"
        assert config.auth_env_var == "API_TOKEN"


class TestMCPConfig:
    """Tests for MCPConfig dataclass."""

    def test_create_basic(self):
        """Test creating basic MCP config."""
        config = MCPConfig(server_command="npx @modelcontextprotocol/server-filesystem")
        assert "filesystem" in config.server_command
        assert config.transport == "stdio"

    def test_with_constraints(self):
        """Test MCP config with path constraints."""
        config = MCPConfig(
            server_command="mcp-server",
            allowed_paths=["/home/user/projects"],
            denied_paths=["/etc", "/root"],
        )
        assert len(config.allowed_paths) == 1
        assert len(config.denied_paths) == 2


class TestTool:
    """Tests for Tool dataclass."""

    def test_create_cli_tool(self):
        """Test creating a CLI tool."""
        tool = Tool(
            id="tool_ruff",
            name="Ruff",
            version="1.0.0",
            tool_type="cli",
            description="Python linter",
            category="linting",
            cli_config=CLIConfig(command_template="ruff check {files}"),
        )
        assert tool.id == "tool_ruff"
        assert tool.tool_type == "cli"
        assert tool.cli_config is not None

    def test_create_api_tool(self):
        """Test creating an API tool."""
        tool = Tool(
            id="tool_api",
            name="API Tool",
            version="1.0.0",
            tool_type="api",
            description="HTTP API tool",
            category="api",
            api_config=APIConfig(base_url="https://api.example.com"),
        )
        assert tool.tool_type == "api"
        assert tool.api_config is not None

    def test_invalid_tool_type(self):
        """Test that invalid tool type raises error."""
        with pytest.raises(ValueError, match="Invalid tool_type"):
            Tool(
                id="tool_test",
                name="Test",
                version="1.0.0",
                tool_type="invalid",
                description="Test",
                category="general",
            )

    def test_invalid_category(self):
        """Test that invalid category raises error."""
        with pytest.raises(ValueError, match="Invalid category"):
            Tool(
                id="tool_test",
                name="Test",
                version="1.0.0",
                tool_type="cli",
                description="Test",
                category="invalid_category",
            )

    def test_to_dict(self):
        """Test serialization to dict."""
        tool = Tool(
            id="tool_test",
            name="Test",
            version="1.0.0",
            tool_type="cli",
            description="Test tool",
            category="general",
        )
        data = tool.to_dict()
        assert data["id"] == "tool_test"
        assert data["tool_type"] == "cli"

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "id": "tool_test",
            "name": "Test",
            "version": "1.0.0",
            "tool_type": "cli",
            "description": "Test tool",
            "category": "general",
        }
        tool = Tool.from_dict(data)
        assert tool.id == "tool_test"

    def test_to_json_schemas(self):
        """Test JSON schema generation."""
        tool = Tool(
            id="tool_test",
            name="Test",
            version="1.0.0",
            tool_type="cli",
            description="Test",
            category="general",
            inputs=[ToolInput(name="file", param_type="string")],
            outputs=[ToolOutput(name="result", param_type="string")],
        )
        inputs_schema, outputs_schema = tool.to_json_schemas()
        assert "file" in inputs_schema
        assert "result" in outputs_schema

    def test_requires_authentication(self):
        """Test authentication requirement check."""
        tool_no_auth = Tool(
            id="tool_test",
            name="Test",
            version="1.0.0",
            tool_type="cli",
            description="Test",
            category="general",
        )
        assert tool_no_auth.requires_authentication() is False

        tool_with_auth = Tool(
            id="tool_api",
            name="API",
            version="1.0.0",
            tool_type="api",
            description="API tool",
            category="api",
            api_config=APIConfig(
                base_url="https://api.example.com",
                auth_type="bearer",
            ),
        )
        assert tool_with_auth.requires_authentication() is True


class TestToolLoader:
    """Tests for ToolLoader class."""

    def test_parse_minimal(self):
        """Test parsing minimal tool YAML."""
        loader = ToolLoader()
        content = """
id: tool_test
name: Test Tool
description: A test tool
type: cli
category: general
"""
        tool = loader.parse(content)
        assert tool.id == "tool_test"
        assert tool.tool_type == "cli"

    def test_parse_cli_tool(self):
        """Test parsing CLI tool."""
        loader = ToolLoader()
        content = """
id: tool_ruff
name: Ruff
description: Python linter
type: cli
category: linting
command:
  template: "ruff check {files}"
  working_dir: project_root
availability:
  check_command: "ruff --version"
  platforms:
    - linux
    - macos
"""
        tool = loader.parse(content)
        assert tool.cli_config is not None
        assert "ruff check" in tool.cli_config.command_template
        assert tool.cli_config.check_command == "ruff --version"

    def test_parse_api_tool(self):
        """Test parsing API tool."""
        loader = ToolLoader()
        content = """
id: tool_api
name: API Tool
description: HTTP API tool
type: api
category: api
api:
  base_url: https://api.example.com
  auth:
    type: bearer
    env_var: API_TOKEN
endpoints:
  - name: get_data
    method: GET
    path: /data/{id}
"""
        tool = loader.parse(content)
        assert tool.api_config is not None
        assert tool.api_config.base_url == "https://api.example.com"
        assert len(tool.api_config.endpoints) == 1

    def test_parse_missing_id(self):
        """Test that missing ID raises error."""
        loader = ToolLoader()
        content = """
name: Test Tool
description: A test tool
type: cli
category: general
"""
        with pytest.raises(ToolLoadError, match="Missing required field: id"):
            loader.parse(content)

    def test_load_directory(self):
        """Test loading tools from directory."""
        loader = ToolLoader()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            tool1 = tmppath / "tool1.tool.yaml"
            tool1.write_text("""
id: tool_one
name: Tool One
description: First tool
type: cli
category: general
""")
            
            tools = loader.load_directory(tmppath)
            assert len(tools) == 1


class TestToolRegistry:
    """Tests for ToolRegistry class."""

    def create_temp_tools_dir(self, tmpdir: Path) -> Path:
        """Create a temporary tools directory with test tools."""
        tools_dir = tmpdir / "tools"
        cli_dir = tools_dir / "cli"
        cli_dir.mkdir(parents=True)

        tool1 = cli_dir / "tool1.tool.yaml"
        tool1.write_text("""
id: tool_one
name: Tool One
description: First test tool
type: cli
category: linting
tags:
  - python
  - linting
""")

        return tools_dir

    def test_load_all(self):
        """Test loading all tools."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = self.create_temp_tools_dir(Path(tmpdir))
            registry = ToolRegistry(tools_dir)
            
            tools = registry.load_all()
            assert len(tools) == 1
            assert registry.is_loaded is True

    def test_find_by_id(self):
        """Test finding tool by ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = self.create_temp_tools_dir(Path(tmpdir))
            registry = ToolRegistry(tools_dir)
            registry.load_all()
            
            tool = registry.find_by_id("tool_one")
            assert tool is not None
            assert tool.name == "Tool One"

    def test_find_by_type(self):
        """Test finding tools by type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = self.create_temp_tools_dir(Path(tmpdir))
            registry = ToolRegistry(tools_dir)
            registry.load_all()
            
            tools = registry.find_by_type("cli")
            assert len(tools) == 1

    def test_find_by_tags(self):
        """Test finding tools by tags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = self.create_temp_tools_dir(Path(tmpdir))
            registry = ToolRegistry(tools_dir)
            registry.load_all()
            
            tools = registry.find_by_tags(["python"])
            assert len(tools) == 1

    def test_search(self):
        """Test searching tools."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = self.create_temp_tools_dir(Path(tmpdir))
            registry = ToolRegistry(tools_dir)
            registry.load_all()
            
            results = registry.search("One")
            assert len(results) >= 1

    def test_enable_disable(self):
        """Test enabling and disabling tools."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = self.create_temp_tools_dir(Path(tmpdir))
            registry = ToolRegistry(tools_dir)
            registry.load_all()
            
            assert registry.disable("tool_one") is True
            tool = registry.find_by_id("tool_one")
            assert tool.enabled is False
            
            assert registry.enable("tool_one") is True
            tool = registry.find_by_id("tool_one")
            assert tool.enabled is True

    def test_get_stats(self):
        """Test getting registry statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = self.create_temp_tools_dir(Path(tmpdir))
            registry = ToolRegistry(tools_dir)
            registry.load_all()
            
            stats = registry.get_stats()
            assert stats.total_tools == 1
            assert "cli" in stats.tools_by_type


class TestAvailabilityResult:
    """Tests for AvailabilityResult dataclass."""

    def test_available(self):
        """Test available result."""
        result = AvailabilityResult(available=True, version="1.0.0")
        assert result.available is True
        assert result.version == "1.0.0"

    def test_not_available(self):
        """Test not available result."""
        result = AvailabilityResult(
            available=False,
            message="Not installed",
            missing_requirements=["ruff"],
        )
        assert result.available is False
        assert "ruff" in result.missing_requirements


class TestConstants:
    """Tests for module constants."""

    def test_tool_types(self):
        """Test TOOL_TYPES contains expected values."""
        assert "cli" in TOOL_TYPES
        assert "api" in TOOL_TYPES
        assert "mcp" in TOOL_TYPES
        assert "function" in TOOL_TYPES

    def test_tool_categories(self):
        """Test TOOL_CATEGORIES contains expected values."""
        assert "linting" in TOOL_CATEGORIES
        assert "testing" in TOOL_CATEGORIES
        assert "general" in TOOL_CATEGORIES
