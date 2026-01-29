"""
DMM Query Tool - Retrieve relevant memories for a task.

This tool queries the DMM daemon for memories semantically relevant to
the given task or topic, returning formatted markdown for context injection.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx

from dmm.core.config import get_config

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
DEFAULT_BUDGET = 1500


async def execute_query(
    query: str,
    budget: int = DEFAULT_BUDGET,
    include_graph: bool = True,
    scope: str | None = None,
) -> str:
    """
    Execute a memory query against the DMM daemon.

    Args:
        query: Natural language description of the task or topic
        budget: Maximum tokens to return (default 1500)
        include_graph: Whether to expand results via knowledge graph
        scope: Optional scope filter (baseline, global, agent, project, ephemeral)

    Returns:
        Formatted memories as markdown, ready for context injection
    """
    if not query or not query.strip():
        return "Error: Query cannot be empty."

    config = get_config()
    host = config.get("daemon", {}).get("host", "127.0.0.1")
    port = config.get("daemon", {}).get("port", 7437)
    url = f"http://{host}:{port}/query"

    request_payload: dict[str, Any] = {
        "query": query.strip(),
        "budget": max(100, min(budget, 10000)),
        "include_graph": include_graph,
        "format": "markdown",
    }

    if scope:
        valid_scopes = ["baseline", "global", "agent", "project", "ephemeral"]
        if scope in valid_scopes:
            request_payload["scope"] = scope
        else:
            return f"Error: Invalid scope '{scope}'. Valid scopes: {', '.join(valid_scopes)}"

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(url, json=request_payload)

            if response.status_code == 503:
                return await _query_with_daemon_start(query, budget, include_graph, scope)

            if response.status_code != 200:
                logger.error("Query failed with status %d: %s", response.status_code, response.text)
                return f"Error querying memories: HTTP {response.status_code}"

            data = response.json()
            return _format_query_response(data, query)

    except httpx.ConnectError:
        logger.info("Daemon not running, attempting to start")
        return await _query_with_daemon_start(query, budget, include_graph, scope)
    except httpx.TimeoutException:
        logger.error("Query timed out after %s seconds", DEFAULT_TIMEOUT)
        return "Error: Query timed out. The daemon may be overloaded."
    except Exception as e:
        logger.exception("Unexpected error during query")
        return f"Error querying memories: {str(e)}"


async def _query_with_daemon_start(
    query: str,
    budget: int,
    include_graph: bool,
    scope: str | None,
) -> str:
    """Attempt to start the daemon and retry the query."""
    from dmm.cli.utils.daemon_manager import DaemonManager

    manager = DaemonManager()

    if not manager.is_running():
        logger.info("Starting DMM daemon")
        started = manager.start(wait=True, timeout=10.0)
        if not started:
            return (
                "DMM daemon is not running and could not be started automatically. "
                "Run 'dmm daemon start' manually."
            )
        await asyncio.sleep(0.5)

    return await execute_query(query, budget, include_graph, scope)


def _format_query_response(data: dict[str, Any], original_query: str) -> str:
    """Format the daemon response as readable markdown."""
    memories = data.get("memories", [])
    pack = data.get("pack", {})
    relationships = data.get("relationships", [])

    if not memories and not pack.get("entries"):
        return f"No relevant memories found for: '{original_query}'"

    output_lines: list[str] = []

    entries = pack.get("entries", []) if pack else memories
    entry_count = len(entries)

    output_lines.append(f"## Relevant Memories ({entry_count} found)\n")

    for entry in entries:
        if isinstance(entry, dict):
            memory_id = entry.get("id", entry.get("memory_id", "unknown"))
            title = entry.get("title", _extract_title_from_content(entry.get("content", "")))
            scope = entry.get("scope", "unknown")
            score = entry.get("score", entry.get("relevance", 0.0))
            content = entry.get("content", "")

            output_lines.append(f"### {title}")
            output_lines.append(f"*Scope: {scope} | Relevance: {score:.2f} | ID: {memory_id}*\n")

            clean_content = _strip_frontmatter(content)
            if clean_content:
                output_lines.append(clean_content)
            output_lines.append("\n---\n")

    if relationships:
        output_lines.append("\n## Related Knowledge\n")
        seen_relations: set[str] = set()
        for rel in relationships[:10]:
            source = rel.get("source", "?")
            rel_type = rel.get("type", rel.get("relation", "relates_to"))
            target = rel.get("target", "?")
            rel_key = f"{source}-{rel_type}-{target}"
            if rel_key not in seen_relations:
                seen_relations.add(rel_key)
                output_lines.append(f"- {source} **{rel_type}** {target}")

    token_count = pack.get("total_tokens", 0)
    if token_count:
        output_lines.append(f"\n*Total tokens: {token_count}*")

    return "\n".join(output_lines)


def _extract_title_from_content(content: str) -> str:
    """Extract title from markdown content."""
    if not content:
        return "Untitled"

    lines = content.strip().split("\n")
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
        if stripped.startswith("## "):
            return stripped[3:].strip()

    first_line = lines[0].strip() if lines else ""
    if len(first_line) <= 60:
        return first_line or "Untitled"
    return first_line[:57] + "..."


def _strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter from markdown content."""
    if not content:
        return ""

    content = content.strip()
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()

    return content
