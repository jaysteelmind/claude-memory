"""
DMM Status Tool - Check system health and statistics.

This tool provides an overview of the DMM system state including
daemon status, memory counts, index health, and recent activity.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from dmm.core.config import get_config

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10.0


async def execute_status(verbose: bool = False) -> str:
    """
    Check DMM system health and statistics.

    Args:
        verbose: If True, include additional details

    Returns:
        Formatted system status as markdown
    """
    config = get_config()
    host = config.get("daemon", {}).get("host", "127.0.0.1")
    port = config.get("daemon", {}).get("port", 7437)

    status_data: dict[str, Any] = {
        "daemon": await _check_daemon_status(host, port),
        "memory": _check_memory_status(config),
        "index": _check_index_status(config),
    }

    if verbose:
        status_data["config"] = _get_config_summary(config)

    return _format_status_response(status_data, verbose)


async def _check_daemon_status(host: str, port: int) -> dict[str, Any]:
    """Check if the DMM daemon is running and responsive."""
    url = f"http://{host}:{port}/health"

    result: dict[str, Any] = {
        "running": False,
        "host": host,
        "port": port,
        "response_time_ms": None,
        "version": None,
        "uptime": None,
    }

    try:
        start_time = datetime.now(timezone.utc)
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(url)
            end_time = datetime.now(timezone.utc)

            response_time = (end_time - start_time).total_seconds() * 1000
            result["response_time_ms"] = round(response_time, 2)

            if response.status_code == 200:
                result["running"] = True
                data = response.json()
                result["version"] = data.get("version")
                result["uptime"] = data.get("uptime")
                result["indexed_count"] = data.get("indexed_count")
            else:
                result["error"] = f"HTTP {response.status_code}"

    except httpx.ConnectError:
        result["error"] = "Connection refused"
    except httpx.TimeoutException:
        result["error"] = "Connection timeout"
    except Exception as e:
        result["error"] = str(e)

    return result


def _check_memory_status(config: dict[str, Any]) -> dict[str, Any]:
    """Check memory file statistics."""
    memory_root = Path(config.get("memory_root", ".dmm/memory"))

    if not memory_root.is_absolute():
        project_root = Path(config.get("project_root", Path.cwd()))
        memory_root = project_root / memory_root

    result: dict[str, Any] = {
        "root": str(memory_root),
        "exists": memory_root.exists(),
        "scopes": {},
        "total_files": 0,
        "total_bytes": 0,
    }

    if not memory_root.exists():
        return result

    scopes = ["baseline", "global", "agent", "project", "ephemeral", "deprecated"]

    for scope in scopes:
        scope_dir = memory_root / scope
        if not scope_dir.exists():
            result["scopes"][scope] = {"count": 0, "bytes": 0}
            continue

        files = list(scope_dir.glob("*.md"))
        file_count = len(files)
        total_bytes = sum(f.stat().st_size for f in files if f.is_file())

        result["scopes"][scope] = {
            "count": file_count,
            "bytes": total_bytes,
        }
        result["total_files"] += file_count
        result["total_bytes"] += total_bytes

    return result


def _check_index_status(config: dict[str, Any]) -> dict[str, Any]:
    """Check index database status."""
    index_root = Path(config.get("index_root", ".dmm/index"))

    if not index_root.is_absolute():
        project_root = Path(config.get("project_root", Path.cwd()))
        index_root = project_root / index_root

    result: dict[str, Any] = {
        "root": str(index_root),
        "exists": index_root.exists(),
        "databases": {},
    }

    if not index_root.exists():
        return result

    db_files = [
        ("embeddings.db", "Vector embeddings"),
        ("stats.db", "Usage statistics"),
        ("conflicts.db", "Conflict records"),
        ("review_queue.db", "Review queue"),
        ("tasks.db", "Task state"),
        ("agentos.db", "AgentOS state"),
    ]

    for db_name, description in db_files:
        db_path = index_root / db_name
        if db_path.exists():
            stat = db_path.stat()
            result["databases"][db_name] = {
                "exists": True,
                "bytes": stat.st_size,
                "modified": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
                "description": description,
            }
        else:
            result["databases"][db_name] = {
                "exists": False,
                "description": description,
            }

    kuzu_dir = index_root / "knowledge.kuzu"
    if kuzu_dir.exists() and kuzu_dir.is_dir():
        kuzu_size = sum(f.stat().st_size for f in kuzu_dir.rglob("*") if f.is_file())
        result["databases"]["knowledge.kuzu"] = {
            "exists": True,
            "bytes": kuzu_size,
            "description": "Knowledge graph",
        }
    else:
        result["databases"]["knowledge.kuzu"] = {
            "exists": False,
            "description": "Knowledge graph",
        }

    return result


def _get_config_summary(config: dict[str, Any]) -> dict[str, Any]:
    """Get configuration summary for verbose output."""
    return {
        "project_root": str(config.get("project_root", ".")),
        "memory_root": str(config.get("memory_root", ".dmm/memory")),
        "index_root": str(config.get("index_root", ".dmm/index")),
        "daemon_host": config.get("daemon", {}).get("host", "127.0.0.1"),
        "daemon_port": config.get("daemon", {}).get("port", 7437),
        "baseline_budget": config.get("baseline_budget", 800),
        "default_query_budget": config.get("default_query_budget", 1500),
    }


def _format_status_response(status_data: dict[str, Any], verbose: bool) -> str:
    """Format status data as readable markdown."""
    lines: list[str] = []

    lines.append("## DMM System Status\n")

    daemon = status_data["daemon"]
    if daemon["running"]:
        lines.append("### Daemon: Running")
        lines.append(f"- **Address:** {daemon['host']}:{daemon['port']}")
        if daemon.get("response_time_ms"):
            lines.append(f"- **Response Time:** {daemon['response_time_ms']}ms")
        if daemon.get("version"):
            lines.append(f"- **Version:** {daemon['version']}")
        if daemon.get("uptime"):
            lines.append(f"- **Uptime:** {daemon['uptime']}")
        if daemon.get("indexed_count"):
            lines.append(f"- **Indexed Memories:** {daemon['indexed_count']}")
    else:
        lines.append("### Daemon: Not Running")
        lines.append(f"- **Address:** {daemon['host']}:{daemon['port']}")
        if daemon.get("error"):
            lines.append(f"- **Error:** {daemon['error']}")
        lines.append("\n*Run `dmm daemon start` to start the daemon.*")

    lines.append("")

    memory = status_data["memory"]
    lines.append("### Memory Files")
    if memory["exists"]:
        lines.append(f"- **Total Files:** {memory['total_files']}")
        lines.append(f"- **Total Size:** {_format_bytes(memory['total_bytes'])}")
        lines.append("\n**By Scope:**")
        for scope, data in memory["scopes"].items():
            if data["count"] > 0:
                lines.append(f"- {scope}: {data['count']} files ({_format_bytes(data['bytes'])})")
    else:
        lines.append(f"- Memory directory not found: {memory['root']}")
        lines.append("\n*Run `dmm init` to initialize the memory system.*")

    lines.append("")

    index = status_data["index"]
    lines.append("### Index Databases")
    if index["exists"]:
        for db_name, data in index["databases"].items():
            if data["exists"]:
                size_str = _format_bytes(data.get("bytes", 0))
                lines.append(f"- **{db_name}:** {size_str}")
            elif verbose:
                lines.append(f"- **{db_name}:** Not created")
    else:
        lines.append(f"- Index directory not found: {index['root']}")

    if verbose and "config" in status_data:
        lines.append("")
        lines.append("### Configuration")
        config = status_data["config"]
        for key, value in config.items():
            lines.append(f"- **{key}:** {value}")

    lines.append("")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines.append(f"*Status checked at {timestamp}*")

    return "\n".join(lines)


def _format_bytes(num_bytes: int) -> str:
    """Format byte count as human-readable string."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    if num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    return f"{num_bytes / (1024 * 1024 * 1024):.1f} GB"
