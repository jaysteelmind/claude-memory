"""
DMM Baseline Resource - Always-loaded critical context.

This resource provides baseline memories that should inform every interaction:
project identity, hard constraints, and foundational principles.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from dmm.core.config import get_config

logger = logging.getLogger(__name__)

BASELINE_CACHE_TTL = 60.0
_baseline_cache: dict[str, Any] = {
    "content": None,
    "timestamp": 0.0,
    "file_mtimes": {},
}


async def get_baseline() -> str:
    """
    Get all baseline memories formatted for context injection.

    Returns:
        Concatenated baseline memories as markdown, sorted by priority
    """
    import time

    current_time = time.time()
    
    config = get_config()
    memory_root = Path(config.get("memory_root", ".dmm/memory"))

    if not memory_root.is_absolute():
        project_root = Path(config.get("project_root", Path.cwd()))
        memory_root = project_root / memory_root

    baseline_dir = memory_root / "baseline"

    if not baseline_dir.exists():
        return _format_no_baseline_message()

    if _is_cache_valid(baseline_dir, current_time):
        logger.debug("Returning cached baseline content")
        return _baseline_cache["content"]

    memories = _load_baseline_memories(baseline_dir)

    if not memories:
        return _format_no_baseline_message()

    content = _format_baseline_content(memories)

    _update_cache(baseline_dir, content, current_time)

    return content


def _is_cache_valid(baseline_dir: Path, current_time: float) -> bool:
    """Check if the cached baseline content is still valid."""
    if _baseline_cache["content"] is None:
        return False

    if current_time - _baseline_cache["timestamp"] > BASELINE_CACHE_TTL:
        return False

    current_mtimes = {}
    for md_file in baseline_dir.glob("*.md"):
        try:
            current_mtimes[str(md_file)] = md_file.stat().st_mtime
        except OSError:
            continue

    if current_mtimes != _baseline_cache["file_mtimes"]:
        return False

    return True


def _update_cache(baseline_dir: Path, content: str, current_time: float) -> None:
    """Update the baseline cache."""
    file_mtimes = {}
    for md_file in baseline_dir.glob("*.md"):
        try:
            file_mtimes[str(md_file)] = md_file.stat().st_mtime
        except OSError:
            continue

    _baseline_cache["content"] = content
    _baseline_cache["timestamp"] = current_time
    _baseline_cache["file_mtimes"] = file_mtimes


def _load_baseline_memories(baseline_dir: Path) -> list[dict[str, Any]]:
    """Load and parse all baseline memory files."""
    memories: list[dict[str, Any]] = []

    for md_file in baseline_dir.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            metadata = _parse_memory_metadata(content)

            if metadata.get("status") == "deprecated":
                continue

            memories.append({
                "id": metadata.get("id", md_file.stem),
                "priority": metadata.get("priority", 0.5),
                "tags": metadata.get("tags", []),
                "content": _strip_frontmatter(content),
                "file_name": md_file.name,
            })

        except OSError as e:
            logger.warning("Failed to read baseline file %s: %s", md_file, e)
            continue

    memories.sort(key=lambda m: m["priority"], reverse=True)

    return memories


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
            metadata["priority"] = 0.5

    status_match = re.search(r"status:\s*(\w+)", frontmatter)
    if status_match:
        metadata["status"] = status_match.group(1).strip()

    tags_match = re.search(r"tags:\s*\[([^\]]*)\]", frontmatter)
    if tags_match:
        tags_str = tags_match.group(1)
        tags = [t.strip().strip("'\"") for t in tags_str.split(",") if t.strip()]
        metadata["tags"] = tags

    return metadata


def _strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter from content."""
    if not content.startswith("---"):
        return content.strip()

    parts = content.split("---", 2)
    if len(parts) >= 3:
        return parts[2].strip()

    return content.strip()


def _format_baseline_content(memories: list[dict[str, Any]]) -> str:
    """Format baseline memories as readable markdown."""
    lines: list[str] = []

    lines.append("# Baseline Context")
    lines.append("")
    lines.append("*Critical constraints and principles that apply to ALL tasks.*")
    lines.append("*These are non-negotiable and take precedence over other memories.*")
    lines.append("")
    lines.append("---")
    lines.append("")

    total_tokens = 0
    max_tokens = 800

    for memory in memories:
        content = memory["content"]
        memory_tokens = len(content.split())

        if total_tokens + memory_tokens > max_tokens and total_tokens > 0:
            remaining = len(memories) - memories.index(memory)
            lines.append(f"\n*({remaining} additional baseline memories truncated)*")
            break

        lines.append(content)
        lines.append("")
        lines.append("---")
        lines.append("")

        total_tokens += memory_tokens

    lines.append(f"*Baseline: {len(memories)} memories, ~{total_tokens} tokens*")

    return "\n".join(lines)


def _format_no_baseline_message() -> str:
    """Format message when no baseline memories exist."""
    return (
        "# Baseline Context\n\n"
        "*No baseline memories configured.*\n\n"
        "Baseline memories contain critical constraints and principles that apply to all tasks.\n"
        "Create baseline memories in `.dmm/memory/baseline/` to establish foundational context.\n\n"
        "Example baseline memories:\n"
        "- Project identity and purpose\n"
        "- Hard constraints (e.g., 'No background jobs')\n"
        "- Coding standards and conventions\n"
        "- Security requirements\n"
    )


def clear_baseline_cache() -> None:
    """Clear the baseline cache (useful for testing)."""
    global _baseline_cache
    _baseline_cache = {
        "content": None,
        "timestamp": 0.0,
        "file_mtimes": {},
    }
