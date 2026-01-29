"""
DMM Recent Resource - Recently accessed or created memories.

This resource provides memories that were recently accessed or created,
useful for maintaining continuity across conversation turns.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from dmm.core.config import get_config

logger = logging.getLogger(__name__)

DEFAULT_RECENT_HOURS = 24
DEFAULT_MAX_RECENT = 10
RECENT_CACHE_TTL = 30.0

_recent_cache: dict[str, Any] = {
    "content": None,
    "timestamp": 0.0,
}


async def get_recent(
    hours: int = DEFAULT_RECENT_HOURS,
    max_count: int = DEFAULT_MAX_RECENT,
) -> str:
    """
    Get recently accessed or created memories.

    Args:
        hours: Number of hours to look back (default 24)
        max_count: Maximum number of memories to return (default 10)

    Returns:
        Formatted recent memories as markdown
    """
    import time

    current_time = time.time()

    if _is_cache_valid(current_time):
        logger.debug("Returning cached recent content")
        return _recent_cache["content"]

    config = get_config()
    memory_root = Path(config.get("memory_root", ".dmm/memory"))

    if not memory_root.is_absolute():
        project_root = Path(config.get("project_root", Path.cwd()))
        memory_root = project_root / memory_root

    if not memory_root.exists():
        return _format_no_recent_message()

    recent_memories = _find_recent_memories(memory_root, hours, max_count)

    if not recent_memories:
        return _format_no_recent_message()

    content = _format_recent_content(recent_memories, hours)

    _update_cache(content, current_time)

    return content


def _is_cache_valid(current_time: float) -> bool:
    """Check if the cached recent content is still valid."""
    if _recent_cache["content"] is None:
        return False

    if current_time - _recent_cache["timestamp"] > RECENT_CACHE_TTL:
        return False

    return True


def _update_cache(content: str, current_time: float) -> None:
    """Update the recent cache."""
    _recent_cache["content"] = content
    _recent_cache["timestamp"] = current_time


def _find_recent_memories(
    memory_root: Path,
    hours: int,
    max_count: int,
) -> list[dict[str, Any]]:
    """Find memories that were recently accessed or created."""
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    recent_memories: list[dict[str, Any]] = []

    scopes = ["baseline", "global", "agent", "project", "ephemeral"]

    for scope in scopes:
        scope_dir = memory_root / scope
        if not scope_dir.exists():
            continue

        for md_file in scope_dir.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                metadata = _parse_memory_metadata(content)

                if metadata.get("status") == "deprecated":
                    continue

                last_used = _parse_date(metadata.get("last_used"))
                created = _parse_date(metadata.get("created"))

                most_recent_date = last_used or created

                if most_recent_date is None:
                    file_mtime = datetime.fromtimestamp(
                        md_file.stat().st_mtime, tz=timezone.utc
                    )
                    most_recent_date = file_mtime

                if most_recent_date >= cutoff_time:
                    recent_memories.append({
                        "id": metadata.get("id", md_file.stem),
                        "scope": scope,
                        "priority": metadata.get("priority", 0.5),
                        "tags": metadata.get("tags", []),
                        "created": created,
                        "last_used": last_used,
                        "most_recent": most_recent_date,
                        "usage_count": metadata.get("usage_count", 0),
                        "content": _strip_frontmatter(content),
                        "file_name": md_file.name,
                    })

            except OSError as e:
                logger.warning("Failed to read file %s: %s", md_file, e)
                continue

    recent_memories.sort(key=lambda m: m["most_recent"], reverse=True)

    return recent_memories[:max_count]


def _parse_memory_metadata(content: str) -> dict[str, Any]:
    """Parse YAML frontmatter from memory content."""
    metadata: dict[str, Any] = {}

    if not content.startswith("---"):
        return metadata

    parts = content.split("---", 2)
    if len(parts) < 3:
        return metadata

    frontmatter = parts[1]

    id_match = re.search(r"id:\s*(.+)", frontmatter)
    if id_match:
        metadata["id"] = id_match.group(1).strip()

    priority_match = re.search(r"priority:\s*([\d.]+)", frontmatter)
    if priority_match:
        try:
            metadata["priority"] = float(priority_match.group(1))
        except ValueError:
            pass

    status_match = re.search(r"status:\s*(\w+)", frontmatter)
    if status_match:
        metadata["status"] = status_match.group(1).strip()

    tags_match = re.search(r"tags:\s*\[([^\]]*)\]", frontmatter)
    if tags_match:
        tags_str = tags_match.group(1)
        tags = [t.strip().strip("'\"") for t in tags_str.split(",") if t.strip()]
        metadata["tags"] = tags

    created_match = re.search(r"created:\s*(.+)", frontmatter)
    if created_match:
        metadata["created"] = created_match.group(1).strip()

    last_used_match = re.search(r"last_used:\s*(.+)", frontmatter)
    if last_used_match:
        metadata["last_used"] = last_used_match.group(1).strip()

    usage_count_match = re.search(r"usage_count:\s*(\d+)", frontmatter)
    if usage_count_match:
        try:
            metadata["usage_count"] = int(usage_count_match.group(1))
        except ValueError:
            pass

    scope_match = re.search(r"scope:\s*(\w+)", frontmatter)
    if scope_match:
        metadata["scope"] = scope_match.group(1).strip()

    return metadata


def _parse_date(date_str: str | None) -> datetime | None:
    """Parse a date string into a datetime object."""
    if not date_str:
        return None

    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    return None


def _strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter from content."""
    if not content.startswith("---"):
        return content.strip()

    parts = content.split("---", 2)
    if len(parts) >= 3:
        return parts[2].strip()

    return content.strip()


def _format_recent_content(memories: list[dict[str, Any]], hours: int) -> str:
    """Format recent memories as readable markdown."""
    lines: list[str] = []

    lines.append("# Recent Memories")
    lines.append("")
    lines.append(f"*Memories accessed or created in the last {hours} hours.*")
    lines.append("")
    lines.append("---")
    lines.append("")

    for memory in memories:
        memory_id = memory["id"]
        scope = memory["scope"]
        tags = memory.get("tags", [])

        most_recent = memory["most_recent"]
        if most_recent:
            time_ago = _format_time_ago(most_recent)
        else:
            time_ago = "unknown"

        lines.append(f"### {memory_id}")
        lines.append(f"*Scope: {scope} | Last activity: {time_ago}*")

        if tags:
            lines.append(f"*Tags: {', '.join(tags)}*")

        lines.append("")

        content = memory["content"]
        if len(content) > 300:
            content = content[:297] + "..."
        lines.append(content)

        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(f"*Showing {len(memories)} recent memories*")

    return "\n".join(lines)


def _format_time_ago(dt: datetime) -> str:
    """Format a datetime as a human-readable 'time ago' string."""
    now = datetime.now(timezone.utc)
    diff = now - dt

    seconds = diff.total_seconds()

    if seconds < 60:
        return "just now"
    if seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    if seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"

    days = int(seconds / 86400)
    return f"{days} day{'s' if days != 1 else ''} ago"


def _format_no_recent_message() -> str:
    """Format message when no recent memories exist."""
    return (
        "# Recent Memories\n\n"
        "*No recent memory activity found.*\n\n"
        "Recent memories appear here when you:\n"
        "- Create new memories with `dmm_remember`\n"
        "- Query memories with `dmm_query`\n"
        "- Update existing memories\n\n"
        "This resource helps maintain continuity across conversation turns.\n"
    )


def clear_recent_cache() -> None:
    """Clear the recent cache (useful for testing)."""
    global _recent_cache
    _recent_cache = {
        "content": None,
        "timestamp": 0.0,
    }
