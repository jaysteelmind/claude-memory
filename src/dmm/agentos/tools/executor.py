"""Tool executor for the Agent OS.

This module provides the ToolExecutor class which handles:
- CLI command execution
- HTTP API calls
- MCP server communication
- Result parsing and error handling
"""

import asyncio
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from dmm.agentos.tools.models import Tool
from dmm.agentos.tools.registry import ToolRegistry


class ToolExecutionError(Exception):
    """Raised when tool execution fails."""

    def __init__(self, tool_id: str, message: str, details: Optional[dict] = None) -> None:
        self.tool_id = tool_id
        self.message = message
        self.details = details or {}
        super().__init__(f"Tool execution failed for {tool_id}: {message}")


class ToolNotFoundError(ToolExecutionError):
    """Raised when a tool is not found."""

    def __init__(self, tool_id: str) -> None:
        super().__init__(tool_id, "Tool not found")


class ToolDisabledError(ToolExecutionError):
    """Raised when a disabled tool is invoked."""

    def __init__(self, tool_id: str) -> None:
        super().__init__(tool_id, "Tool is disabled")


class ToolTimeoutError(ToolExecutionError):
    """Raised when tool execution times out."""

    def __init__(self, tool_id: str, timeout: float) -> None:
        super().__init__(tool_id, f"Execution timed out after {timeout}s")


@dataclass
class ToolResult:
    """Result of tool execution.

    Attributes:
        tool_id: ID of the executed tool.
        success: Whether execution succeeded.
        output: Tool output data.
        error: Error message if failed.
        exit_code: Exit code for CLI tools.
        duration_ms: Execution duration in milliseconds.
        metadata: Additional metadata.
    """

    tool_id: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    exit_code: Optional[int] = None
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "tool_id": self.tool_id,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


class ToolExecutor:
    """Execute tools of different types.

    Handles:
    - CLI command execution with template substitution
    - HTTP API calls with authentication
    - MCP server communication
    - Timeout and error handling
    """

    def __init__(
        self,
        registry: ToolRegistry,
        project_root: Optional[Path] = None,
    ) -> None:
        """Initialize the tool executor.

        Args:
            registry: ToolRegistry for looking up tools.
            project_root: Project root for resolving paths.
        """
        self._registry = registry
        self._project_root = project_root or Path.cwd()
        self._mcp_connections: dict[str, Any] = {}

    async def execute(
        self,
        tool_id: str,
        inputs: dict[str, Any],
        timeout: Optional[float] = None,
    ) -> ToolResult:
        """Execute a tool with given inputs.

        Args:
            tool_id: ID of the tool to execute.
            inputs: Input parameters for the tool.
            timeout: Optional timeout override.

        Returns:
            ToolResult with execution results.

        Raises:
            ToolNotFoundError: If tool is not found.
            ToolDisabledError: If tool is disabled.
            ToolTimeoutError: If execution times out.
            ToolExecutionError: If execution fails.
        """
        tool = self._registry.find_by_id(tool_id)
        if not tool:
            raise ToolNotFoundError(tool_id)

        if not tool.enabled:
            raise ToolDisabledError(tool_id)

        effective_timeout = timeout or tool.constraints.timeout_seconds

        start = time.perf_counter()
        try:
            if tool.tool_type == "cli":
                result = await self._execute_cli(tool, inputs, effective_timeout)
            elif tool.tool_type == "api":
                result = await self._execute_api(tool, inputs, effective_timeout)
            elif tool.tool_type == "mcp":
                result = await self._execute_mcp(tool, inputs, effective_timeout)
            elif tool.tool_type == "function":
                result = await self._execute_function(tool, inputs, effective_timeout)
            else:
                raise ToolExecutionError(
                    tool_id, f"Unsupported tool type: {tool.tool_type}"
                )

            result.duration_ms = (time.perf_counter() - start) * 1000
            return result

        except asyncio.TimeoutError:
            raise ToolTimeoutError(tool_id, effective_timeout)

    async def _execute_cli(
        self,
        tool: Tool,
        inputs: dict[str, Any],
        timeout: float,
    ) -> ToolResult:
        """Execute a CLI tool."""
        if not tool.cli_config:
            return ToolResult(
                tool_id=tool.id,
                success=False,
                error="No CLI configuration",
            )

        # Build command from template
        command = self._build_cli_command(tool, inputs)

        # Determine working directory
        if tool.cli_config.working_dir == "project_root":
            cwd = self._project_root
        elif tool.cli_config.working_dir == "cwd":
            cwd = Path.cwd()
        else:
            cwd = Path(tool.cli_config.working_dir)

        # Build environment
        env = os.environ.copy()
        env.update(tool.cli_config.env_vars)

        # Execute command
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                raise

            exit_code = process.returncode
            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            # Try to parse output as JSON
            output: Any = stdout_str
            try:
                output = json.loads(stdout_str)
            except json.JSONDecodeError:
                pass

            return ToolResult(
                tool_id=tool.id,
                success=exit_code == 0,
                output=output,
                error=stderr_str if exit_code != 0 else None,
                exit_code=exit_code,
                metadata={
                    "command": command,
                    "cwd": str(cwd),
                    "stderr": stderr_str if stderr_str else None,
                },
            )

        except Exception as e:
            return ToolResult(
                tool_id=tool.id,
                success=False,
                error=str(e),
                metadata={"command": command},
            )

    def _build_cli_command(self, tool: Tool, inputs: dict[str, Any]) -> str:
        """Build CLI command from template and inputs."""
        if not tool.cli_config:
            return ""

        command = tool.cli_config.command_template

        # Substitute input placeholders
        for key, value in inputs.items():
            placeholder = "{" + key + "}"
            if placeholder in command:
                # Handle different value types
                if isinstance(value, bool):
                    str_value = "true" if value else "false"
                elif isinstance(value, (list, dict)):
                    str_value = json.dumps(value)
                else:
                    str_value = str(value)
                command = command.replace(placeholder, str_value)

        # Remove unused placeholders
        import re
        command = re.sub(r"\{[^}]+\}", "", command)

        return command.strip()

    async def _execute_api(
        self,
        tool: Tool,
        inputs: dict[str, Any],
        timeout: float,
    ) -> ToolResult:
        """Execute an HTTP API tool."""
        if not tool.api_config:
            return ToolResult(
                tool_id=tool.id,
                success=False,
                error="No API configuration",
            )

        try:
            import httpx
        except ImportError:
            return ToolResult(
                tool_id=tool.id,
                success=False,
                error="httpx not installed",
            )

        # Determine which endpoint to call
        endpoint_name = inputs.pop("_endpoint", None)
        endpoint = None

        if endpoint_name:
            for ep in tool.api_config.endpoints:
                if ep.name == endpoint_name:
                    endpoint = ep
                    break
        elif tool.api_config.endpoints:
            endpoint = tool.api_config.endpoints[0]

        if not endpoint:
            return ToolResult(
                tool_id=tool.id,
                success=False,
                error="No endpoint specified or found",
            )

        # Build URL
        url = tool.api_config.base_url.rstrip("/") + endpoint.path

        # Substitute path parameters
        for key, value in list(inputs.items()):
            placeholder = "{" + key + "}"
            if placeholder in url:
                url = url.replace(placeholder, str(value))
                del inputs[key]

        # Build headers
        headers = dict(tool.api_config.headers)

        # Add authentication
        if tool.api_config.auth_type != "none" and tool.api_config.auth_env_var:
            auth_value = os.environ.get(tool.api_config.auth_env_var)
            if auth_value:
                if tool.api_config.auth_type == "bearer":
                    headers["Authorization"] = f"Bearer {auth_value}"
                elif tool.api_config.auth_type == "api_key":
                    headers["X-API-Key"] = auth_value

        # Make request
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if endpoint.method.upper() == "GET":
                    response = await client.get(url, headers=headers, params=inputs)
                elif endpoint.method.upper() == "POST":
                    response = await client.post(url, headers=headers, json=inputs)
                elif endpoint.method.upper() == "PUT":
                    response = await client.put(url, headers=headers, json=inputs)
                elif endpoint.method.upper() == "DELETE":
                    response = await client.delete(url, headers=headers, params=inputs)
                elif endpoint.method.upper() == "PATCH":
                    response = await client.patch(url, headers=headers, json=inputs)
                else:
                    return ToolResult(
                        tool_id=tool.id,
                        success=False,
                        error=f"Unsupported HTTP method: {endpoint.method}",
                    )

                # Parse response
                try:
                    output = response.json()
                except json.JSONDecodeError:
                    output = response.text

                return ToolResult(
                    tool_id=tool.id,
                    success=response.is_success,
                    output=output,
                    error=None if response.is_success else f"HTTP {response.status_code}",
                    exit_code=response.status_code,
                    metadata={
                        "url": str(url),
                        "method": endpoint.method,
                        "status_code": response.status_code,
                    },
                )

        except httpx.TimeoutException:
            raise asyncio.TimeoutError()
        except Exception as e:
            return ToolResult(
                tool_id=tool.id,
                success=False,
                error=str(e),
                metadata={"url": str(url)},
            )

    async def _execute_mcp(
        self,
        tool: Tool,
        inputs: dict[str, Any],
        timeout: float,
    ) -> ToolResult:
        """Execute via MCP server."""
        if not tool.mcp_config:
            return ToolResult(
                tool_id=tool.id,
                success=False,
                error="No MCP configuration",
            )

        # Get capability to invoke
        capability_name = inputs.pop("_capability", None)
        capability = None

        if capability_name:
            for cap in tool.mcp_config.capabilities:
                if cap.name == capability_name:
                    capability = cap
                    break
        elif tool.mcp_config.capabilities:
            capability = tool.mcp_config.capabilities[0]

        if not capability:
            return ToolResult(
                tool_id=tool.id,
                success=False,
                error="No capability specified or found",
            )

        # For now, execute MCP as a subprocess with JSON input/output
        # Full MCP protocol support would require a dedicated MCP client
        server_cmd = tool.mcp_config.server_command
        server_args = tool.mcp_config.server_args

        # Substitute project_root in args
        server_args = [
            arg.replace("{project_root}", str(self._project_root))
            for arg in server_args
        ]

        # Build full command
        full_cmd = [server_cmd] + server_args

        # Create request payload
        request = {
            "method": capability_name,
            "params": inputs,
        }

        try:
            process = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input=json.dumps(request).encode()),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                raise

            stdout_str = stdout.decode("utf-8", errors="replace")

            try:
                output = json.loads(stdout_str)
            except json.JSONDecodeError:
                output = stdout_str

            return ToolResult(
                tool_id=tool.id,
                success=process.returncode == 0,
                output=output,
                error=stderr.decode() if process.returncode != 0 else None,
                exit_code=process.returncode,
                metadata={
                    "capability": capability_name,
                    "server_command": server_cmd,
                },
            )

        except Exception as e:
            return ToolResult(
                tool_id=tool.id,
                success=False,
                error=str(e),
            )

    async def _execute_function(
        self,
        tool: Tool,
        inputs: dict[str, Any],
        timeout: float,
    ) -> ToolResult:
        """Execute a local function tool."""
        # Function tools would need to be registered separately
        # For now, return an error indicating this is not implemented
        return ToolResult(
            tool_id=tool.id,
            success=False,
            error="Function tool execution not yet implemented",
        )

    def execute_sync(
        self,
        tool_id: str,
        inputs: dict[str, Any],
        timeout: Optional[float] = None,
    ) -> ToolResult:
        """Synchronous wrapper for execute.

        Args:
            tool_id: ID of the tool to execute.
            inputs: Input parameters for the tool.
            timeout: Optional timeout override.

        Returns:
            ToolResult with execution results.
        """
        return asyncio.run(self.execute(tool_id, inputs, timeout))
