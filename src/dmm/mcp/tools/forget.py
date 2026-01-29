"""
DMM Forget Tool - Deprecate outdated or incorrect memories.

This tool marks memories as deprecated when they are no longer accurate,
relevant, or have been superseded by newer information.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from dmm.core.config import get_config

logger = logging.getLogger(__name__)

MEMORY_ID_PATTERN = re.compile(r"^mem_\d{4}_\d{2}_\d{2}_\d+.*$")
MIN_REASON_LENGTH = 10
MAX_REASON_LENGTH = 500


async def execute_forget(
    memory_id: str,
    reason: str,
    permanent: bool = False,
) -> str:
    """
    Deprecate a memory that is no longer accurate or relevant.

    Args:
        memory_id: The ID of the memory to deprecate (format: mem_YYYY_MM_DD_NNN)
        reason: Explanation for why this memory should be deprecated
        permanent: If True, move to deprecated folder; if False, just mark status

    Returns:
        Confirmation of deprecation or error message
    """
    validation_error = _validate_inputs(memory_id, reason)
    if validation_error:
        return validation_error

    memory_id = memory_id.strip()
    reason = reason.strip()

    config = get_config()
    memory_root = Path(config.get("memory_root", ".dmm/memory"))

    if not memory_root.is_absolute():
        project_root = Path(config.get("project_root", Path.cwd()))
        memory_root = project_root / memory_root

    memory_file = _find_memory_file(memory_root, memory_id)

    if not memory_file:
        similar = _find_similar_memories(memory_root, memory_id)
        if similar:
            similar_list = ", ".join(similar[:5])
            return (
                f"Error: Memory '{memory_id}' not found.\n\n"
                f"Similar memories found: {similar_list}"
            )
        return f"Error: Memory '{memory_id}' not found in any scope."

    try:
        content = memory_file.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Failed to read memory file %s: %s", memory_file, e)
        return f"Error: Could not read memory file: {e}"

    if _is_already_deprecated(content):
        return f"Memory '{memory_id}' is already deprecated."

    updated_content = _update_memory_status(content, reason)

    if permanent:
        deprecated_dir = memory_root / "deprecated"
        deprecated_dir.mkdir(parents=True, exist_ok=True)
        new_path = deprecated_dir / memory_file.name

        counter = 1
        base_name = memory_file.stem
        while new_path.exists():
            new_path = deprecated_dir / f"{base_name}_{counter:02d}.md"
            counter += 1

        try:
            new_path.write_text(updated_content, encoding="utf-8")
            memory_file.unlink()
            logger.info("Moved memory to deprecated: %s -> %s", memory_file, new_path)
            location_msg = f"Moved to: deprecated/{new_path.name}"
        except OSError as e:
            logger.error("Failed to move memory file: %s", e)
            return f"Error: Failed to move memory file: {e}"
    else:
        try:
            memory_file.write_text(updated_content, encoding="utf-8")
            logger.info("Marked memory as deprecated: %s", memory_file)
            location_msg = f"Location: {memory_file.parent.name}/{memory_file.name}"
        except OSError as e:
            logger.error("Failed to update memory file: %s", e)
            return f"Error: Failed to update memory file: {e}"

    await _trigger_reindex()

    return (
        f"Memory deprecated successfully.\n\n"
        f"**ID:** {memory_id}\n"
        f"**Reason:** {reason}\n"
        f"**{location_msg}**\n\n"
        f"This memory will no longer appear in query results."
    )


def _validate_inputs(memory_id: str, reason: str) -> str | None:
    """Validate inputs and return error message if invalid."""
    if not memory_id or not memory_id.strip():
        return "Error: Memory ID cannot be empty."

    memory_id = memory_id.strip()
    if not MEMORY_ID_PATTERN.match(memory_id):
        return (
            f"Error: Invalid memory ID format '{memory_id}'.\n"
            f"Expected format: mem_YYYY_MM_DD_NNN (e.g., mem_2026_01_15_042)"
        )

    if not reason or not reason.strip():
        return "Error: Reason cannot be empty. Please explain why this memory should be deprecated."

    reason = reason.strip()
    if len(reason) < MIN_REASON_LENGTH:
        return f"Error: Reason too short (minimum {MIN_REASON_LENGTH} characters)."

    if len(reason) > MAX_REASON_LENGTH:
        return f"Error: Reason too long (maximum {MAX_REASON_LENGTH} characters)."

    return None


def _find_memory_file(memory_root: Path, memory_id: str) -> Path | None:
    """Find the memory file by ID across all scopes."""
    if not memory_root.exists():
        return None

    scopes = ["baseline", "global", "agent", "project", "ephemeral"]

    for scope in scopes:
        scope_dir = memory_root / scope
        if not scope_dir.exists():
            continue

        for md_file in scope_dir.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                if f"id: {memory_id}" in content:
                    return md_file
            except OSError:
                continue

    return None


def _find_similar_memories(memory_root: Path, memory_id: str) -> list[str]:
    """Find memories with similar IDs for suggestions."""
    if not memory_root.exists():
        return []

    date_match = re.search(r"mem_(\d{4}_\d{2}_\d{2})", memory_id)
    if not date_match:
        return []

    date_prefix = date_match.group(1)
    similar: list[str] = []

    scopes = ["baseline", "global", "agent", "project", "ephemeral"]
    for scope in scopes:
        scope_dir = memory_root / scope
        if not scope_dir.exists():
            continue

        for md_file in scope_dir.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                id_match = re.search(r"id:\s*(mem_[^\n]+)", content)
                if id_match:
                    found_id = id_match.group(1).strip()
                    if date_prefix in found_id:
                        similar.append(found_id)
            except OSError:
                continue

    return similar


def _is_already_deprecated(content: str) -> bool:
    """Check if memory is already deprecated."""
    status_match = re.search(r"status:\s*(\w+)", content)
    if status_match:
        return status_match.group(1).lower() == "deprecated"

    confidence_match = re.search(r"confidence:\s*(\w+)", content)
    if confidence_match:
        return confidence_match.group(1).lower() == "deprecated"

    return False


def _update_memory_status(content: str, reason: str) -> str:
    """Update memory frontmatter to mark as deprecated."""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    content = re.sub(
        r"(status:\s*)\w+",
        r"\1deprecated",
        content,
        count=1,
    )

    content = re.sub(
        r"(confidence:\s*)\w+",
        r"\1deprecated",
        content,
        count=1,
    )

    content = re.sub(
        r"(last_used:\s*)[^\n]+",
        f"\\g<1>{date_str}",
        content,
        count=1,
    )

    deprecation_note = f"deprecated_at: {timestamp}\ndeprecation_reason: {reason}\n"

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            body = parts[2]
            frontmatter = frontmatter.rstrip() + "\n" + deprecation_note
            content = f"---{frontmatter}---{body}"

    return content


async def _trigger_reindex() -> None:
    """Trigger daemon reindex after deprecating a memory."""
    config = get_config()
    host = config.get("daemon", {}).get("host", "127.0.0.1")
    port = config.get("daemon", {}).get("port", 7437)
    url = f"http://{host}:{port}/reindex"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url)
            logger.debug("Triggered reindex after memory deprecation")
    except Exception as e:
        logger.debug("Could not trigger reindex (non-critical): %s", e)
