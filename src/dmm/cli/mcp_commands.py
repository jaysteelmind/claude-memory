"""
DMM MCP CLI Commands - Command-line interface for MCP server management.

This module provides CLI commands for:
- Starting the MCP server
- Installing/uninstalling MCP configuration for Claude Code
- Checking MCP status
- Testing MCP functionality
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

logger = logging.getLogger(__name__)
console = Console()

mcp_app = typer.Typer(
    name="mcp",
    help="MCP (Model Context Protocol) server management for Claude Code integration.",
    no_args_is_help=True,
)


@mcp_app.command("serve")
def serve(
    transport: Annotated[
        str,
        typer.Option(
            "--transport", "-t",
            help="Transport type: 'stdio' (default) or 'sse'",
        ),
    ] = "stdio",
    port: Annotated[
        int,
        typer.Option(
            "--port", "-p",
            help="Port for SSE transport (default 3000)",
        ),
    ] = 3000,
    log_level: Annotated[
        str,
        typer.Option(
            "--log-level", "-l",
            help="Logging level: DEBUG, INFO, WARNING, ERROR",
        ),
    ] = "INFO",
) -> None:
    """
    Start the DMM MCP server.

    This command is typically called by Claude Code via MCP configuration,
    not directly by users. The server exposes DMM tools, resources, and
    prompts through the Model Context Protocol.

    Examples:
        dmm mcp serve                    # Start with stdio (default)
        dmm mcp serve --transport sse    # Start with HTTP/SSE
        dmm mcp serve -t sse -p 8080     # SSE on custom port
    """
    valid_transports = ["stdio", "sse"]
    if transport not in valid_transports:
        console.print(f"[red]Error: Invalid transport '{transport}'[/red]")
        console.print(f"Valid transports: {', '.join(valid_transports)}")
        raise typer.Exit(1)

    valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
    log_level_upper = log_level.upper()
    if log_level_upper not in valid_log_levels:
        console.print(f"[red]Error: Invalid log level '{log_level}'[/red]")
        console.print(f"Valid levels: {', '.join(valid_log_levels)}")
        raise typer.Exit(1)

    logging.basicConfig(
        level=getattr(logging, log_level_upper),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        from dmm.mcp.server import run_server
        run_server(transport=transport, port=port)
    except KeyboardInterrupt:
        logger.info("MCP server stopped by user")
    except Exception as e:
        logger.exception("MCP server error")
        console.print(f"[red]Error: {e}[/red]", file=sys.stderr)
        raise typer.Exit(1)


@mcp_app.command("install")
def install(
    scope: Annotated[
        str,
        typer.Option(
            "--scope", "-s",
            help="Installation scope: 'user' (all projects) or 'project' (current only)",
        ),
    ] = "user",
    command_path: Annotated[
        Optional[str],
        typer.Option(
            "--command", "-c",
            help="Custom path to dmm executable",
        ),
    ] = None,
) -> None:
    """
    Install DMM MCP server configuration for Claude Code.

    This registers DMM with Claude Code so it is automatically available
    as an MCP server. After installation, restart Claude Code to activate.

    Scopes:
        user: Available across all projects (recommended)
        project: Only in current project directory

    Examples:
        dmm mcp install                  # Install for all projects
        dmm mcp install --scope project  # Install for current project only
    """
    valid_scopes = ["user", "project"]
    if scope not in valid_scopes:
        console.print(f"[red]Error: Invalid scope '{scope}'[/red]")
        console.print(f"Valid scopes: {', '.join(valid_scopes)}")
        raise typer.Exit(1)

    dmm_path = _find_dmm_executable(command_path)

    if _check_claude_cli_available():
        success = _install_via_claude_cli(dmm_path, scope)
        if success:
            return

    success = _install_via_config_file(dmm_path, scope)
    if not success:
        raise typer.Exit(1)


@mcp_app.command("uninstall")
def uninstall(
    scope: Annotated[
        str,
        typer.Option(
            "--scope", "-s",
            help="Uninstall scope: 'user' or 'project'",
        ),
    ] = "user",
) -> None:
    """
    Remove DMM MCP server from Claude Code configuration.

    Examples:
        dmm mcp uninstall                  # Remove from user config
        dmm mcp uninstall --scope project  # Remove from project config
    """
    if _check_claude_cli_available():
        success = _uninstall_via_claude_cli()
        if success:
            return

    success = _uninstall_via_config_file(scope)
    if not success:
        raise typer.Exit(1)


@mcp_app.command("status")
def status() -> None:
    """
    Check MCP server configuration status.

    Shows whether DMM is configured as an MCP server and displays
    the current configuration details.

    Examples:
        dmm mcp status
    """
    console.print("[bold]DMM MCP Status[/bold]\n")

    if _check_claude_cli_available():
        _show_status_via_cli()
    else:
        _show_status_via_config()

    console.print("")
    _show_server_info()


@mcp_app.command("test")
def test(
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose", "-v",
            help="Show detailed test output",
        ),
    ] = False,
) -> None:
    """
    Test MCP server functionality.

    Runs a quick test to verify the MCP server and tools work correctly.
    This does not require Claude Code to be running.

    Examples:
        dmm mcp test           # Quick test
        dmm mcp test -v        # Verbose output
    """
    console.print("[bold]Testing DMM MCP Server[/bold]\n")

    async def run_tests() -> bool:
        all_passed = True

        console.print("1. Testing server creation...")
        try:
            from dmm.mcp.server import create_server
            server = create_server()
            console.print("   [green]PASS[/green] - Server created successfully")
            if verbose:
                console.print(f"      Server name: {server.name}")
        except Exception as e:
            console.print(f"   [red]FAIL[/red] - {e}")
            all_passed = False

        console.print("2. Testing dmm_status tool...")
        try:
            from dmm.mcp.tools.status import execute_status
            result = await execute_status(verbose=False)
            if result and len(result) > 0:
                console.print("   [green]PASS[/green] - Status tool works")
                if verbose:
                    preview = result[:100].replace("\n", " ")
                    console.print(f"      Preview: {preview}...")
            else:
                console.print("   [yellow]WARN[/yellow] - Status returned empty")
        except Exception as e:
            console.print(f"   [red]FAIL[/red] - {e}")
            all_passed = False

        console.print("3. Testing dmm_query tool...")
        try:
            from dmm.mcp.tools.query import execute_query
            result = await execute_query("test query", budget=500)
            if result:
                console.print("   [green]PASS[/green] - Query tool works")
                if verbose:
                    preview = result[:100].replace("\n", " ")
                    console.print(f"      Preview: {preview}...")
            else:
                console.print("   [yellow]WARN[/yellow] - Query returned empty")
        except Exception as e:
            console.print(f"   [yellow]WARN[/yellow] - {e}")
            console.print("      (This may be expected if daemon is not running)")

        console.print("4. Testing baseline resource...")
        try:
            from dmm.mcp.resources.baseline import get_baseline
            result = await get_baseline()
            if result:
                console.print("   [green]PASS[/green] - Baseline resource works")
                if verbose:
                    preview = result[:100].replace("\n", " ")
                    console.print(f"      Preview: {preview}...")
            else:
                console.print("   [yellow]WARN[/yellow] - Baseline returned empty")
        except Exception as e:
            console.print(f"   [red]FAIL[/red] - {e}")
            all_passed = False

        console.print("5. Testing prompts...")
        try:
            from dmm.mcp.prompts.context_injection import generate_context_injection
            from dmm.mcp.prompts.memory_proposal import generate_memory_proposal
            
            ci_result = generate_context_injection("test task")
            mp_result = generate_memory_proposal("test conversation")
            
            if ci_result and mp_result:
                console.print("   [green]PASS[/green] - Prompts work")
            else:
                console.print("   [yellow]WARN[/yellow] - Prompts returned empty")
        except Exception as e:
            console.print(f"   [red]FAIL[/red] - {e}")
            all_passed = False

        return all_passed

    passed = asyncio.run(run_tests())

    console.print("")
    if passed:
        console.print("[green]All tests passed![/green]")
    else:
        console.print("[yellow]Some tests failed or had warnings.[/yellow]")
        console.print("Run 'dmm mcp test -v' for more details.")


def _find_dmm_executable(custom_path: Optional[str]) -> str:
    """Find the dmm executable path."""
    if custom_path:
        path = Path(custom_path)
        if path.exists():
            return str(path.resolve())
        console.print(f"[yellow]Warning: Custom path '{custom_path}' not found[/yellow]")

    dmm_system_path = Path.home() / ".dmm-system" / "bin" / "dmm"
    if dmm_system_path.exists():
        return str(dmm_system_path)

    try:
        result = subprocess.run(
            ["which", "dmm"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass

    return "dmm"


def _check_claude_cli_available() -> bool:
    """Check if Claude Code CLI is available."""
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _install_via_claude_cli(dmm_path: str, scope: str) -> bool:
    """Install MCP server using Claude CLI."""
    cmd = [
        "claude", "mcp", "add", "dmm",
        "--command", dmm_path,
        "--args", "mcp", "serve",
        "--scope", scope,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            console.print(f"[green]DMM MCP server installed (scope: {scope})[/green]")
            console.print("\nRestart Claude Code to activate.")
            return True
        else:
            console.print(f"[yellow]Claude CLI failed: {result.stderr}[/yellow]")
            console.print("Falling back to config file method...")
            return False

    except subprocess.TimeoutExpired:
        console.print("[yellow]Claude CLI timed out[/yellow]")
        return False
    except Exception as e:
        console.print(f"[yellow]Claude CLI error: {e}[/yellow]")
        return False


def _install_via_config_file(dmm_path: str, scope: str) -> bool:
    """Install MCP server by writing config file directly."""
    if scope == "user":
        config_path = Path.home() / ".config" / "claude" / "mcp.json"
    else:
        config_path = Path.cwd() / ".mcp.json"

    config_path.parent.mkdir(parents=True, exist_ok=True)

    existing_config: dict = {}
    if config_path.exists():
        try:
            existing_config = json.loads(config_path.read_text())
        except json.JSONDecodeError:
            console.print(f"[yellow]Warning: Existing config at {config_path} is invalid[/yellow]")

    if "mcpServers" not in existing_config:
        existing_config["mcpServers"] = {}

    existing_config["mcpServers"]["dmm"] = {
        "command": dmm_path,
        "args": ["mcp", "serve"],
    }

    try:
        config_path.write_text(json.dumps(existing_config, indent=2))
        console.print(f"[green]DMM MCP server configured in {config_path}[/green]")
        console.print("\nRestart Claude Code to activate.")
        return True
    except OSError as e:
        console.print(f"[red]Error writing config: {e}[/red]")
        return False


def _uninstall_via_claude_cli() -> bool:
    """Uninstall MCP server using Claude CLI."""
    cmd = ["claude", "mcp", "remove", "dmm"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            console.print("[green]DMM MCP server removed[/green]")
            return True
        else:
            console.print(f"[yellow]Claude CLI: {result.stderr or 'DMM not found'}[/yellow]")
            return False

    except Exception as e:
        console.print(f"[yellow]Claude CLI error: {e}[/yellow]")
        return False


def _uninstall_via_config_file(scope: str) -> bool:
    """Uninstall MCP server by editing config file."""
    if scope == "user":
        config_path = Path.home() / ".config" / "claude" / "mcp.json"
    else:
        config_path = Path.cwd() / ".mcp.json"

    if not config_path.exists():
        console.print(f"[yellow]Config file not found: {config_path}[/yellow]")
        return True

    try:
        config = json.loads(config_path.read_text())

        if "mcpServers" in config and "dmm" in config["mcpServers"]:
            del config["mcpServers"]["dmm"]
            config_path.write_text(json.dumps(config, indent=2))
            console.print(f"[green]DMM removed from {config_path}[/green]")
        else:
            console.print("[yellow]DMM was not configured[/yellow]")

        return True

    except Exception as e:
        console.print(f"[red]Error updating config: {e}[/red]")
        return False


def _show_status_via_cli() -> None:
    """Show MCP status using Claude CLI."""
    try:
        result = subprocess.run(
            ["claude", "mcp", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if "dmm" in result.stdout.lower():
            console.print("[green]DMM is configured in Claude Code[/green]\n")

            for line in result.stdout.split("\n"):
                if "dmm" in line.lower():
                    console.print(f"  {line}")
        else:
            console.print("[yellow]DMM is not configured in Claude Code[/yellow]")
            console.print("\nRun 'dmm mcp install' to configure.")

    except Exception as e:
        console.print(f"[yellow]Could not check via CLI: {e}[/yellow]")
        _show_status_via_config()


def _show_status_via_config() -> None:
    """Show MCP status by reading config files."""
    configs_found = []

    user_config = Path.home() / ".config" / "claude" / "mcp.json"
    if user_config.exists():
        try:
            config = json.loads(user_config.read_text())
            if "mcpServers" in config and "dmm" in config["mcpServers"]:
                configs_found.append(("User", user_config, config["mcpServers"]["dmm"]))
        except Exception:
            pass

    project_config = Path.cwd() / ".mcp.json"
    if project_config.exists():
        try:
            config = json.loads(project_config.read_text())
            if "mcpServers" in config and "dmm" in config["mcpServers"]:
                configs_found.append(("Project", project_config, config["mcpServers"]["dmm"]))
        except Exception:
            pass

    if configs_found:
        console.print("[green]DMM MCP configuration found:[/green]\n")
        for scope, path, config in configs_found:
            console.print(f"  [{scope}] {path}")
            console.print(f"    Command: {config.get('command', 'N/A')}")
            console.print(f"    Args: {' '.join(config.get('args', []))}")
            console.print("")
    else:
        console.print("[yellow]DMM is not configured as an MCP server[/yellow]")
        console.print("\nRun 'dmm mcp install' to configure.")


def _show_server_info() -> None:
    """Show MCP server information."""
    table = Table(title="MCP Server Details")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Server Name", "dmm")
    table.add_row("Version", "1.0.0")
    table.add_row("Transport", "stdio (default), sse")

    table.add_row("Tools", "dmm_query, dmm_remember, dmm_forget, dmm_status, dmm_conflicts")
    table.add_row("Resources", "memory://baseline, memory://recent, memory://conflicts")
    table.add_row("Prompts", "context_injection, memory_proposal")

    console.print(table)
