"""CLI commands for Claude Code integration verification.

This module provides commands to verify that the DMM system is properly
configured for Claude Code integration, checking for required files
and daemon status.
"""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from dmm.core.constants import get_dmm_root

console = Console()

claude_app = typer.Typer(
    name="claude",
    help="Claude Code integration commands",
    no_args_is_help=True,
)


def _check_daemon_running(host: str = "127.0.0.1", port: int = 7433) -> tuple[bool, int | None]:
    """Check if DMM daemon is running.
    
    Returns:
        Tuple of (is_running, pid or None)
    """
    import httpx
    
    pid_file = Path("/tmp/dmm.pid")
    pid = None
    
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
        except (ValueError, OSError):
            pass
    
    try:
        with httpx.Client(timeout=2.0) as client:
            response = client.get(f"http://{host}:{port}/health")
            if response.status_code == 200:
                return True, pid
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
        pass
    
    return False, pid


def _count_file_lines(file_path: Path) -> int:
    """Count lines in a file."""
    try:
        return len(file_path.read_text().splitlines())
    except OSError:
        return 0


def _check_boot_md_phase(boot_md_path: Path) -> str:
    """Determine BOOT.md phase status.
    
    Returns:
        'Phase 3' if updated, 'Phase 1' if outdated, 'unknown' otherwise
    """
    if not boot_md_path.exists():
        return "missing"
    
    try:
        content = boot_md_path.read_text()
        if "Phase 1 Limitations" in content or "Current Limitations (Phase 1)" in content:
            return "Phase 1 (outdated)"
        if "dmm conflicts" in content and "dmm write" in content:
            return "Phase 3"
        return "unknown"
    except OSError:
        return "error"


@claude_app.command("check")
def check_integration(
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show detailed output"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Check Claude Code integration status.
    
    Verifies that all required files exist and the daemon is accessible.
    Returns exit code 0 if integration is ready, 1 otherwise.
    """
    import json as json_module
    
    base_path = Path.cwd()
    dmm_root = get_dmm_root(base_path)
    
    results: list[dict[str, str]] = []
    all_pass = True
    
    # Check CLAUDE.md
    claude_md = base_path / "CLAUDE.md"
    if claude_md.exists():
        line_count = _count_file_lines(claude_md)
        results.append({
            "component": "CLAUDE.md",
            "status": "found",
            "details": f"{line_count} lines",
        })
    else:
        results.append({
            "component": "CLAUDE.md",
            "status": "missing",
            "details": "",
        })
        all_pass = False
    
    # Check BOOT.md
    boot_md = dmm_root / "BOOT.md"
    if boot_md.exists():
        phase = _check_boot_md_phase(boot_md)
        if phase == "Phase 1 (outdated)":
            results.append({
                "component": ".dmm/BOOT.md",
                "status": "outdated",
                "details": phase,
            })
            all_pass = False
        else:
            line_count = _count_file_lines(boot_md)
            results.append({
                "component": ".dmm/BOOT.md",
                "status": "found",
                "details": f"{phase}, {line_count} lines",
            })
    else:
        results.append({
            "component": ".dmm/BOOT.md",
            "status": "missing",
            "details": "",
        })
        all_pass = False
    
    # Check policy.md
    policy_md = dmm_root / "policy.md"
    if policy_md.exists():
        line_count = _count_file_lines(policy_md)
        results.append({
            "component": ".dmm/policy.md",
            "status": "found",
            "details": f"{line_count} lines",
        })
    else:
        results.append({
            "component": ".dmm/policy.md",
            "status": "missing",
            "details": "",
        })
        all_pass = False
    
    # Check daemon
    daemon_running, daemon_pid = _check_daemon_running()
    if daemon_running:
        pid_str = f"PID {daemon_pid}" if daemon_pid else ""
        results.append({
            "component": "Daemon",
            "status": "running",
            "details": pid_str,
        })
    else:
        results.append({
            "component": "Daemon",
            "status": "not running",
            "details": "",
        })
    
    # Check wrapper script
    wrapper = base_path / "bin" / "claude-code-dmm"
    if wrapper.exists():
        is_executable = wrapper.stat().st_mode & 0o111
        if is_executable:
            results.append({
                "component": "Wrapper script",
                "status": "found",
                "details": str(wrapper),
            })
        else:
            results.append({
                "component": "Wrapper script",
                "status": "not executable",
                "details": str(wrapper),
            })
    else:
        results.append({
            "component": "Wrapper script",
            "status": "not found",
            "details": "",
        })
    
    # Check memory directory
    memory_dir = dmm_root / "memory"
    if memory_dir.exists() and memory_dir.is_dir():
        memory_count = sum(1 for _ in memory_dir.rglob("*.md"))
        results.append({
            "component": ".dmm/memory/",
            "status": "found",
            "details": f"{memory_count} memory files",
        })
    else:
        results.append({
            "component": ".dmm/memory/",
            "status": "missing",
            "details": "",
        })
        all_pass = False
    
    # Output results
    if json_output:
        output = {
            "ready": all_pass,
            "components": results,
        }
        console.print(json_module.dumps(output, indent=2))
    else:
        console.print("[bold]Claude Code Integration Status[/bold]")
        console.print("=" * 40)
        
        table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
        table.add_column("Component", style="cyan", width=20)
        table.add_column("Status", width=15)
        table.add_column("Details", style="dim")
        
        for result in results:
            component = result["component"]
            status = result["status"]
            details = result["details"]
            
            if status in ("found", "running"):
                status_str = f"[green]{status}[/green]"
            elif status in ("missing", "outdated", "not running", "not executable", "not found"):
                status_str = f"[red]{status}[/red]"
            else:
                status_str = f"[yellow]{status}[/yellow]"
            
            table.add_row(f"{component}:", status_str, details)
        
        console.print(table)
        console.print()
        
        if all_pass:
            console.print("[bold green]Integration: READY[/bold green]")
        else:
            console.print("[bold red]Integration: INCOMPLETE[/bold red]")
            
            if verbose:
                console.print()
                console.print("[yellow]To fix:[/yellow]")
                for result in results:
                    if result["status"] in ("missing", "outdated", "not executable"):
                        component = result["component"]
                        if component == "CLAUDE.md":
                            console.print("  - Create CLAUDE.md in project root")
                        elif component == ".dmm/BOOT.md":
                            if result["status"] == "outdated":
                                console.print("  - Update .dmm/BOOT.md to Phase 3 content")
                            else:
                                console.print("  - Create .dmm/BOOT.md")
                        elif component == ".dmm/policy.md":
                            console.print("  - Create .dmm/policy.md")
                        elif component == ".dmm/memory/":
                            console.print("  - Create .dmm/memory/ directory")
                        elif component == "Wrapper script":
                            if result["status"] == "not executable":
                                console.print("  - Make wrapper script executable: chmod +x bin/claude-code-dmm")
                            else:
                                console.print("  - Create bin/claude-code-dmm wrapper script")
    
    if not all_pass:
        raise typer.Exit(1)
