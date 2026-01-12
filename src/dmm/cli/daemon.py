"""CLI commands for daemon management."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from dmm.core.constants import DEFAULT_HOST, DEFAULT_PORT

console = Console()
err_console = Console(stderr=True)

daemon_app = typer.Typer(help="Daemon management commands")


@daemon_app.command("start")
def daemon_start(
    foreground: Annotated[
        bool, typer.Option("--foreground", "-f", help="Run in foreground")
    ] = False,
    host: Annotated[str, typer.Option("--host", help="Daemon host")] = DEFAULT_HOST,
    port: Annotated[int, typer.Option("--port", help="Daemon port")] = DEFAULT_PORT,
    pid_file: Annotated[
        Path, typer.Option("--pid-file", help="PID file location")
    ] = Path("/tmp/dmm.pid"),
) -> None:
    """Start the DMM daemon."""
    from dmm.daemon.lifecycle import DaemonConfig, DaemonLifecycle, check_daemon_running

    # Check if already running
    if check_daemon_running(host, port):
        console.print(f"[yellow]Daemon already running at http://{host}:{port}[/yellow]")
        raise typer.Exit(0)

    config = DaemonConfig(
        host=host,
        port=port,
        pid_file=pid_file,
    )
    lifecycle = DaemonLifecycle(config)

    if foreground:
        console.print(f"[green]Starting DMM daemon in foreground...[/green]")
        console.print(f"Listening on http://{host}:{port}")
        console.print("Press Ctrl+C to stop")

        try:
            # Write PID file
            import os
            lifecycle.write_pid_file(os.getpid())

            # Run server directly
            from dmm.daemon.server import run_server
            run_server(host=host, port=port)

        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down...[/yellow]")
        finally:
            # Cleanup PID file
            pid_file.unlink(missing_ok=True)

        raise typer.Exit(0)

    # Background mode
    try:
        result = lifecycle.start(foreground=False)
        if result.success:
            console.print(f"[green]DMM daemon started (PID: {result.pid})[/green]")
            console.print(f"Listening on {result.url}")
        else:
            err_console.print(f"[red]Failed to start daemon: {result.message}[/red]")
            raise typer.Exit(1)

    except Exception as e:
        err_console.print(f"[red]Error starting daemon: {e}[/red]")
        raise typer.Exit(1)


@daemon_app.command("stop")
def daemon_stop(
    pid_file: Annotated[
        Path, typer.Option("--pid-file", help="PID file location")
    ] = Path("/tmp/dmm.pid"),
    timeout: Annotated[
        float, typer.Option("--timeout", help="Shutdown timeout in seconds")
    ] = 5.0,
) -> None:
    """Stop the DMM daemon."""
    from dmm.daemon.lifecycle import DaemonConfig, DaemonLifecycle

    config = DaemonConfig(pid_file=pid_file)
    lifecycle = DaemonLifecycle(config)

    try:
        result = lifecycle.stop(timeout=timeout)
        if result.success:
            if result.was_running:
                console.print(f"[green]{result.message}[/green]")
            else:
                console.print(f"[yellow]{result.message}[/yellow]")
        else:
            err_console.print(f"[red]Failed to stop daemon: {result.message}[/red]")
            raise typer.Exit(1)

    except Exception as e:
        err_console.print(f"[red]Error stopping daemon: {e}[/red]")
        raise typer.Exit(1)


@daemon_app.command("status")
def daemon_status(
    host: Annotated[str, typer.Option("--host", help="Daemon host")] = DEFAULT_HOST,
    port: Annotated[int, typer.Option("--port", help="Daemon port")] = DEFAULT_PORT,
    pid_file: Annotated[
        Path, typer.Option("--pid-file", help="PID file location")
    ] = Path("/tmp/dmm.pid"),
    json_output: Annotated[
        bool, typer.Option("--json", help="Output as JSON")
    ] = False,
) -> None:
    """Check daemon status."""
    import json

    from dmm.daemon.lifecycle import DaemonConfig, DaemonLifecycle

    config = DaemonConfig(host=host, port=port, pid_file=pid_file)
    lifecycle = DaemonLifecycle(config)

    status = lifecycle.status()

    if json_output:
        console.print(json.dumps(status.to_dict(), indent=2))
        return

    if status.running:
        console.print(f"[green]Daemon running[/green]")
        console.print(f"  PID: {status.pid}")
        console.print(f"  URL: {status.url}")
        console.print(f"  Health: {status.health or 'unknown'}")
        if status.uptime_seconds:
            uptime_min = status.uptime_seconds / 60
            console.print(f"  Uptime: {uptime_min:.1f} minutes")
    else:
        console.print("[yellow]Daemon not running[/yellow]")


@daemon_app.command("restart")
def daemon_restart(
    host: Annotated[str, typer.Option("--host", help="Daemon host")] = DEFAULT_HOST,
    port: Annotated[int, typer.Option("--port", help="Daemon port")] = DEFAULT_PORT,
    pid_file: Annotated[
        Path, typer.Option("--pid-file", help="PID file location")
    ] = Path("/tmp/dmm.pid"),
) -> None:
    """Restart the DMM daemon."""
    from dmm.daemon.lifecycle import DaemonConfig, DaemonLifecycle

    config = DaemonConfig(host=host, port=port, pid_file=pid_file)
    lifecycle = DaemonLifecycle(config)

    # Stop if running
    console.print("[yellow]Stopping daemon...[/yellow]")
    stop_result = lifecycle.stop()
    if stop_result.was_running:
        console.print(f"[green]Stopped (PID: {lifecycle.read_pid_file() or 'unknown'})[/green]")

    # Start
    console.print("[yellow]Starting daemon...[/yellow]")
    try:
        start_result = lifecycle.start(foreground=False)
        if start_result.success:
            console.print(f"[green]DMM daemon restarted (PID: {start_result.pid})[/green]")
            console.print(f"Listening on {start_result.url}")
        else:
            err_console.print(f"[red]Failed to start: {start_result.message}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        err_console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
