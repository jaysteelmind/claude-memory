"""Tool registry for the Agent OS.

This module provides the ToolRegistry class which manages:
- Loading tools from the filesystem
- Caching loaded tools
- Checking tool availability
- Syncing tools to the knowledge graph
- Tool discovery and search
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from dmm.agentos.tools.loader import ToolLoader, ToolLoadError, ToolValidationError
from dmm.agentos.tools.models import AvailabilityResult, Tool
from dmm.graph.nodes import ToolNode


@dataclass
class SyncResult:
    """Result of syncing tools to the graph.

    Attributes:
        tools_synced: Number of tools synced.
        errors: List of error messages.
        duration_ms: Sync duration in milliseconds.
    """

    tools_synced: int = 0
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class ToolRequirements:
    """Tool requirements for a skill.

    Attributes:
        required: Required tools with availability status.
        optional: Optional tools with availability status.
        all_required_available: Whether all required tools are available.
    """

    required: dict[str, AvailabilityResult] = field(default_factory=dict)
    optional: dict[str, AvailabilityResult] = field(default_factory=dict)
    all_required_available: bool = True


@dataclass
class ToolRegistryStats:
    """Statistics about the tool registry.

    Attributes:
        total_tools: Total number of registered tools.
        enabled_tools: Number of enabled tools.
        disabled_tools: Number of disabled tools.
        available_tools: Number of available tools.
        tools_by_type: Count of tools per type.
        tools_by_category: Count of tools per category.
    """

    total_tools: int = 0
    enabled_tools: int = 0
    disabled_tools: int = 0
    available_tools: int = 0
    tools_by_type: dict[str, int] = field(default_factory=dict)
    tools_by_category: dict[str, int] = field(default_factory=dict)


class ToolRegistry:
    """Registry for managing tools.

    The ToolRegistry is responsible for:
    - Loading tools from .dmm/tools/ directory
    - Caching loaded tools in memory
    - Checking tool availability
    - Syncing tools to the knowledge graph
    - Providing tool discovery and lookup
    """

    def __init__(
        self,
        tools_dir: Path,
        graph_store: Optional[Any] = None,
        project_root: Optional[Path] = None,
        strict: bool = False,
    ) -> None:
        """Initialize the tool registry.

        Args:
            tools_dir: Path to the tools directory.
            graph_store: Optional KnowledgeGraphStore for graph integration.
            project_root: Project root for resolving paths.
            strict: If True, raise errors on invalid tools.
        """
        self._tools_dir = tools_dir
        self._graph_store = graph_store
        self._project_root = project_root or Path.cwd()
        self._strict = strict
        self._loader = ToolLoader(strict=strict)
        self._cache: dict[str, Tool] = {}
        self._availability_cache: dict[str, AvailabilityResult] = {}
        self._loaded = False

    @property
    def tools_dir(self) -> Path:
        """Get the tools directory path."""
        return self._tools_dir

    @property
    def is_loaded(self) -> bool:
        """Check if tools have been loaded."""
        return self._loaded

    # === Loading ===

    def load_all(self) -> list[Tool]:
        """Load all tools from the tools directory.

        Returns:
            List of loaded Tool objects.
        """
        self._cache.clear()
        self._availability_cache.clear()
        tools: list[Tool] = []

        # Load from subdirectories by type
        for subdir in ["cli", "api", "mcp", "function"]:
            dir_path = self._tools_dir / subdir
            if dir_path.exists():
                for tool in self._loader.load_directory(dir_path):
                    self._cache[tool.id] = tool
                    tools.append(tool)

        self._loaded = True
        return tools

    def load_tool(self, tool_id: str) -> Optional[Tool]:
        """Load a specific tool by ID.

        Args:
            tool_id: The tool identifier.

        Returns:
            Tool object if found, None otherwise.
        """
        if tool_id in self._cache:
            return self._cache[tool_id]

        for subdir in ["cli", "api", "mcp", "function"]:
            dir_path = self._tools_dir / subdir
            if not dir_path.exists():
                continue

            for path in dir_path.rglob("*.tool.yaml"):
                try:
                    tool = self._loader.load(path)
                    if tool.id == tool_id:
                        self._cache[tool.id] = tool
                        return tool
                except (ToolLoadError, ToolValidationError):
                    continue

        return None

    def reload(self) -> list[Tool]:
        """Reload all tools from the filesystem.

        Returns:
            List of reloaded Tool objects.
        """
        self._loaded = False
        return self.load_all()

    # === Graph Integration ===

    def sync_to_graph(self) -> SyncResult:
        """Sync all loaded tools to the knowledge graph.

        Returns:
            SyncResult with statistics.
        """
        start = time.perf_counter()
        result = SyncResult()

        if self._graph_store is None:
            result.errors.append("No graph store configured")
            return result

        if not self._loaded:
            self.load_all()

        for tool in self._cache.values():
            try:
                self._index_tool(tool)
                result.tools_synced += 1
            except Exception as e:
                result.errors.append(f"Failed to sync tool {tool.id}: {e}")

        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    def _index_tool(self, tool: Tool) -> None:
        """Index a single tool in the graph."""
        if self._graph_store is None:
            return

        inputs_schema, outputs_schema = tool.to_json_schemas()

        # Build config JSON based on tool type
        config_dict: dict[str, Any] = {}
        if tool.cli_config:
            config_dict["cli"] = tool.cli_config.to_dict()
        if tool.api_config:
            config_dict["api"] = tool.api_config.to_dict()
        if tool.mcp_config:
            config_dict["mcp"] = tool.mcp_config.to_dict()

        node = ToolNode(
            id=tool.id,
            name=tool.name,
            version=tool.version,
            tool_type=tool.tool_type,
            description=tool.description,
            category=tool.category,
            tags=tool.tags,
            enabled=tool.enabled,
            config_json=json.dumps(config_dict),
            inputs_schema=inputs_schema,
            outputs_schema=outputs_schema,
            constraints_json=json.dumps(tool.constraints.to_dict()),
            file_path=tool.file_path,
            created=tool.created,
            updated=tool.updated,
        )

        self._graph_store.upsert_tool_node(node)

    # === Availability ===

    def check_availability(self, tool_id: str, use_cache: bool = True) -> AvailabilityResult:
        """Check if a tool is available for use.

        Args:
            tool_id: Tool to check.
            use_cache: Whether to use cached results.

        Returns:
            AvailabilityResult with status.
        """
        if use_cache and tool_id in self._availability_cache:
            return self._availability_cache[tool_id]

        tool = self.find_by_id(tool_id)
        if not tool:
            result = AvailabilityResult(
                available=False,
                message=f"Tool not found: {tool_id}",
            )
            return result

        if not tool.enabled:
            result = AvailabilityResult(
                available=False,
                message="Tool is disabled",
            )
            self._availability_cache[tool_id] = result
            return result

        if tool.tool_type == "cli":
            result = self._check_cli_availability(tool)
        elif tool.tool_type == "api":
            result = self._check_api_availability(tool)
        elif tool.tool_type == "mcp":
            result = self._check_mcp_availability(tool)
        else:
            result = AvailabilityResult(
                available=True,
                message="Function tools are always available",
            )

        self._availability_cache[tool_id] = result
        return result

    def _check_cli_availability(self, tool: Tool) -> AvailabilityResult:
        """Check CLI tool availability."""
        import subprocess
        import platform

        missing: list[str] = []

        # Check platform
        if tool.cli_config:
            current_platform = platform.system().lower()
            if current_platform == "darwin":
                current_platform = "macos"
            if current_platform not in tool.cli_config.platforms:
                return AvailabilityResult(
                    available=False,
                    message=f"Not supported on {current_platform}",
                    missing_requirements=[f"Platform: {current_platform}"],
                )

            # Check required files
            for req_file in tool.cli_config.required_files:
                file_path = self._project_root / req_file.lstrip("/")
                # Handle glob patterns
                if "*" in req_file:
                    import glob
                    matches = glob.glob(str(self._project_root / req_file))
                    if not matches:
                        missing.append(f"File: {req_file}")
                elif not file_path.exists():
                    missing.append(f"File: {req_file}")

            # Run check command
            check_cmd = tool.cli_config.check_command
            if check_cmd:
                try:
                    result = subprocess.run(
                        check_cmd,
                        shell=True,
                        capture_output=True,
                        timeout=10,
                        cwd=str(self._project_root),
                    )
                    if result.returncode != 0:
                        missing.append(f"Check command failed: {check_cmd}")
                    else:
                        # Try to extract version from output
                        output = result.stdout.decode().strip()
                        if output:
                            return AvailabilityResult(
                                available=len(missing) == 0,
                                version=output.split("\n")[0],
                                message="Available" if not missing else "Missing requirements",
                                missing_requirements=missing,
                            )
                except subprocess.TimeoutExpired:
                    missing.append("Check command timed out")
                except Exception as e:
                    missing.append(f"Check command error: {e}")

        if missing:
            return AvailabilityResult(
                available=False,
                message="Missing requirements",
                missing_requirements=missing,
            )

        return AvailabilityResult(
            available=True,
            message="Available",
        )

    def _check_api_availability(self, tool: Tool) -> AvailabilityResult:
        """Check API tool availability."""
        import os

        if not tool.api_config:
            return AvailabilityResult(
                available=False,
                message="No API configuration",
            )

        missing: list[str] = []

        # Check authentication
        if tool.api_config.auth_type != "none":
            env_var = tool.api_config.auth_env_var
            if env_var and not os.environ.get(env_var):
                missing.append(f"Environment variable: {env_var}")

        if missing:
            return AvailabilityResult(
                available=False,
                message="Missing authentication",
                missing_requirements=missing,
            )

        return AvailabilityResult(
            available=True,
            message="Available (credentials configured)",
        )

    def _check_mcp_availability(self, tool: Tool) -> AvailabilityResult:
        """Check MCP server availability."""
        import shutil

        if not tool.mcp_config:
            return AvailabilityResult(
                available=False,
                message="No MCP configuration",
            )

        # Check if server command exists
        server_cmd = tool.mcp_config.server_command
        if server_cmd:
            # Extract the executable (first word)
            executable = server_cmd.split()[0]
            if not shutil.which(executable):
                # Check if it's an npx command
                if executable == "npx":
                    if not shutil.which("npx"):
                        return AvailabilityResult(
                            available=False,
                            message="npx not found",
                            missing_requirements=["npx (Node.js)"],
                        )
                else:
                    return AvailabilityResult(
                        available=False,
                        message=f"Server executable not found: {executable}",
                        missing_requirements=[executable],
                    )

        return AvailabilityResult(
            available=True,
            message="Server command available",
        )

    def check_all_availability(self) -> dict[str, AvailabilityResult]:
        """Check availability of all registered tools.

        Returns:
            Dictionary mapping tool IDs to availability results.
        """
        if not self._loaded:
            self.load_all()

        results: dict[str, AvailabilityResult] = {}
        for tool_id in self._cache:
            results[tool_id] = self.check_availability(tool_id, use_cache=False)

        return results

    def find_for_skill(
        self,
        required_tools: list[str],
        optional_tools: Optional[list[str]] = None,
    ) -> ToolRequirements:
        """Find tools required by a skill.

        Args:
            required_tools: List of required tool IDs.
            optional_tools: List of optional tool IDs.

        Returns:
            ToolRequirements with availability status.
        """
        result = ToolRequirements()

        for tool_id in required_tools:
            avail = self.check_availability(tool_id)
            result.required[tool_id] = avail
            if not avail.available:
                result.all_required_available = False

        for tool_id in optional_tools or []:
            avail = self.check_availability(tool_id)
            result.optional[tool_id] = avail

        return result

    # === Discovery ===

    def find_by_id(self, tool_id: str) -> Optional[Tool]:
        """Find a tool by exact ID."""
        if not self._loaded:
            self.load_all()
        return self._cache.get(tool_id)

    def find_by_type(self, tool_type: str) -> list[Tool]:
        """Find tools by type (cli, api, mcp, function)."""
        if not self._loaded:
            self.load_all()
        return [t for t in self._cache.values() if t.tool_type == tool_type]

    def find_by_tags(self, tags: list[str], match_all: bool = False) -> list[Tool]:
        """Find tools with matching tags."""
        if not self._loaded:
            self.load_all()

        results: list[Tool] = []
        tags_set = set(t.lower() for t in tags)

        for tool in self._cache.values():
            tool_tags = set(t.lower() for t in tool.tags)
            if match_all:
                if tags_set.issubset(tool_tags):
                    results.append(tool)
            else:
                if tags_set & tool_tags:
                    results.append(tool)

        return results

    def find_by_category(self, category: str) -> list[Tool]:
        """Find tools by category."""
        if not self._loaded:
            self.load_all()
        return [t for t in self._cache.values() if t.category.lower() == category.lower()]

    def search(
        self,
        query: str,
        enabled_only: bool = True,
        available_only: bool = False,
        tool_type: Optional[str] = None,
    ) -> list[Tool]:
        """Search tools by name, description, or tags."""
        if not self._loaded:
            self.load_all()

        query_lower = query.lower()
        results: list[tuple[Tool, int]] = []

        for tool in self._cache.values():
            if enabled_only and not tool.enabled:
                continue
            if tool_type and tool.tool_type != tool_type:
                continue
            if available_only:
                avail = self.check_availability(tool.id)
                if not avail.available:
                    continue

            score = 0
            if query_lower == tool.id.lower():
                score += 100
            if query_lower in tool.name.lower():
                score += 50
            if query_lower in tool.description.lower():
                score += 20
            for tag in tool.tags:
                if query_lower in tag.lower():
                    score += 10

            if score > 0:
                results.append((tool, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return [tool for tool, _ in results]

    # === Management ===

    def enable(self, tool_id: str) -> bool:
        """Enable a tool."""
        tool = self._cache.get(tool_id)
        if tool:
            tool.enabled = True
            self._availability_cache.pop(tool_id, None)
            return True
        return False

    def disable(self, tool_id: str) -> bool:
        """Disable a tool."""
        tool = self._cache.get(tool_id)
        if tool:
            tool.enabled = False
            self._availability_cache.pop(tool_id, None)
            return True
        return False

    def list_all(
        self,
        enabled_only: bool = False,
        available_only: bool = False,
        tool_type: Optional[str] = None,
    ) -> list[Tool]:
        """List all registered tools."""
        if not self._loaded:
            self.load_all()

        results: list[Tool] = []
        for tool in self._cache.values():
            if enabled_only and not tool.enabled:
                continue
            if tool_type and tool.tool_type != tool_type:
                continue
            if available_only:
                avail = self.check_availability(tool.id)
                if not avail.available:
                    continue
            results.append(tool)

        return sorted(results, key=lambda t: t.name)

    def get_stats(self) -> ToolRegistryStats:
        """Get registry statistics."""
        if not self._loaded:
            self.load_all()

        stats = ToolRegistryStats()
        stats.total_tools = len(self._cache)

        for tool in self._cache.values():
            if tool.enabled:
                stats.enabled_tools += 1
            else:
                stats.disabled_tools += 1

            avail = self.check_availability(tool.id)
            if avail.available:
                stats.available_tools += 1

            stats.tools_by_type[tool.tool_type] = (
                stats.tools_by_type.get(tool.tool_type, 0) + 1
            )
            stats.tools_by_category[tool.category] = (
                stats.tools_by_category.get(tool.category, 0) + 1
            )

        return stats
