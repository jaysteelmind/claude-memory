"""
DMM Conflicts Resource - Currently detected memory conflicts.

This resource provides a list of detected conflicts between memories,
enabling proactive conflict awareness and resolution prompting.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from dmm.mcp.tools.conflicts import execute_conflicts

logger = logging.getLogger(__name__)

CONFLICTS_CACHE_TTL = 120.0

_conflicts_cache: dict[str, Any] = {
    "content": None,
    "timestamp": 0.0,
    "conflict_count": 0,
}


async def get_conflicts() -> str:
    """
    Get currently detected memory conflicts.

    Returns:
        Formatted conflict list as markdown
    """
    import time

    current_time = time.time()

    if _is_cache_valid(current_time):
        logger.debug("Returning cached conflicts content")
        return _conflicts_cache["content"]

    conflicts_result = await execute_conflicts(
        include_resolved=False,
        min_severity="low",
    )

    content = _enhance_conflicts_output(conflicts_result)

    _update_cache(content, current_time, conflicts_result)

    return content


def _is_cache_valid(current_time: float) -> bool:
    """Check if the cached conflicts content is still valid."""
    if _conflicts_cache["content"] is None:
        return False

    if current_time - _conflicts_cache["timestamp"] > CONFLICTS_CACHE_TTL:
        return False

    return True


def _update_cache(content: str, current_time: float, raw_result: str) -> None:
    """Update the conflicts cache."""
    conflict_count = 0
    if "found)" in raw_result:
        try:
            count_part = raw_result.split("(")[1].split(" found)")[0]
            conflict_count = int(count_part)
        except (IndexError, ValueError):
            pass

    _conflicts_cache["content"] = content
    _conflicts_cache["timestamp"] = current_time
    _conflicts_cache["conflict_count"] = conflict_count


def _enhance_conflicts_output(conflicts_result: str) -> str:
    """Enhance the conflicts output with resource-specific context."""
    lines: list[str] = []

    if "No Conflicts Detected" in conflicts_result:
        lines.append("# Memory Conflicts Status")
        lines.append("")
        lines.append("**Status: Clear**")
        lines.append("")
        lines.append("No conflicts detected between memories. All stored information appears consistent.")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("*Conflicts are checked automatically when:*")
        lines.append("- New memories are created")
        lines.append("- Memories are updated")
        lines.append("- Periodic background scans run")
        lines.append("")
        lines.append("*If you suspect inconsistent information, use `dmm_conflicts()` for a fresh scan.*")
    else:
        lines.append("# Memory Conflicts Status")
        lines.append("")
        lines.append("**Status: Conflicts Detected**")
        lines.append("")
        lines.append("The following conflicts require attention:")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        result_lines = conflicts_result.split("\n")
        skip_header = True
        for line in result_lines:
            if skip_header and line.startswith("## Memory Conflicts"):
                skip_header = False
                continue
            if not skip_header:
                lines.append(line)

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("**Recommended Actions:**")
        lines.append("")
        lines.append("1. **Critical/High severity**: Address immediately before continuing work")
        lines.append("2. **Medium severity**: Review and resolve when convenient")
        lines.append("3. **Low severity**: Note for future cleanup")
        lines.append("")
        lines.append("*To resolve conflicts:*")
        lines.append("- Use `dmm_forget(memory_id, reason)` to deprecate outdated memories")
        lines.append("- Use `dmm_remember()` to create a corrected, consolidated memory")
        lines.append("- Report critical conflicts to the user for guidance")

    lines.append("")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines.append(f"*Last checked: {timestamp}*")

    return "\n".join(lines)


def get_conflict_count() -> int:
    """
    Get the current conflict count from cache.

    Returns:
        Number of conflicts detected in last scan, or -1 if not cached
    """
    if _conflicts_cache["content"] is None:
        return -1
    return _conflicts_cache["conflict_count"]


def has_critical_conflicts() -> bool:
    """
    Check if there are critical conflicts in the cache.

    Returns:
        True if critical conflicts were detected in last scan
    """
    if _conflicts_cache["content"] is None:
        return False
    return "[CRITICAL]" in _conflicts_cache["content"]


def clear_conflicts_cache() -> None:
    """Clear the conflicts cache (useful for testing)."""
    global _conflicts_cache
    _conflicts_cache = {
        "content": None,
        "timestamp": 0.0,
        "conflict_count": 0,
    }
