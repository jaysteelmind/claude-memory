"""Tools module for the Agent OS.

This module provides tool management capabilities including:
- Tool data models (Tool, ToolInput, ToolOutput, etc.)
- Tool file loading from YAML
- Tool registry for management and caching
- Tool execution for CLI, API, and MCP tools
- Tool discovery for capability matching
"""

from dmm.agentos.tools.models import (
    PARAM_TYPES,
    TOOL_CATEGORIES,
    TOOL_TYPES,
    APIConfig,
    APIEndpoint,
    AvailabilityResult,
    CLIConfig,
    MCPCapability,
    MCPConfig,
    Tool,
    ToolConstraints,
    ToolInput,
    ToolOutput,
)
from dmm.agentos.tools.loader import (
    ToolLoader,
    ToolLoadError,
    ToolValidationError,
)
from dmm.agentos.tools.registry import (
    SyncResult,
    ToolRegistry,
    ToolRegistryStats,
    ToolRequirements,
)
from dmm.agentos.tools.executor import (
    ToolDisabledError,
    ToolExecutionError,
    ToolExecutor,
    ToolNotFoundError,
    ToolResult,
    ToolTimeoutError,
)
from dmm.agentos.tools.discovery import (
    ToolDiscovery,
    ToolMatch,
)

__all__ = [
    # Constants
    "PARAM_TYPES",
    "TOOL_CATEGORIES",
    "TOOL_TYPES",
    # Models
    "APIConfig",
    "APIEndpoint",
    "AvailabilityResult",
    "CLIConfig",
    "MCPCapability",
    "MCPConfig",
    "Tool",
    "ToolConstraints",
    "ToolInput",
    "ToolOutput",
    # Loader
    "ToolLoader",
    "ToolLoadError",
    "ToolValidationError",
    # Registry
    "SyncResult",
    "ToolRegistry",
    "ToolRegistryStats",
    "ToolRequirements",
    # Executor
    "ToolDisabledError",
    "ToolExecutionError",
    "ToolExecutor",
    "ToolNotFoundError",
    "ToolResult",
    "ToolTimeoutError",
    # Discovery
    "ToolDiscovery",
    "ToolMatch",
]
