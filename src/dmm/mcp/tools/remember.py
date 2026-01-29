"""
DMM Remember Tool - Create new memories from learned information.

This tool creates new memory files when the AI learns important information
during a conversation, such as project decisions, patterns, or constraints.
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

VALID_SCOPES = ("baseline", "global", "agent", "project", "ephemeral")
VALID_CONFIDENCE = ("experimental", "active", "stable")
MIN_CONTENT_LENGTH = 20
MAX_CONTENT_LENGTH = 4000
MIN_PRIORITY = 0.0
MAX_PRIORITY = 1.0
DEFAULT_PRIORITY = 0.6

KEYWORD_TAG_MAP: dict[str, list[str]] = {
    "api": ["api", "endpoint", "rest", "graphql", "http", "request", "response"],
    "database": ["database", "sql", "query", "schema", "table", "index", "migration"],
    "authentication": ["auth", "login", "password", "token", "jwt", "oauth", "session"],
    "testing": ["test", "spec", "unittest", "pytest", "mock", "fixture", "coverage"],
    "configuration": ["config", "setting", "environment", "env", "variable", "parameter"],
    "deployment": ["deploy", "docker", "kubernetes", "k8s", "ci", "cd", "pipeline"],
    "security": ["security", "vulnerability", "encryption", "ssl", "tls", "certificate"],
    "performance": ["performance", "optimization", "cache", "latency", "throughput", "memory"],
    "architecture": ["architecture", "design", "pattern", "structure", "module", "component"],
    "error_handling": ["error", "exception", "handling", "retry", "fallback", "recovery"],
    "logging": ["log", "logging", "trace", "debug", "monitor", "observability"],
    "validation": ["validation", "validate", "constraint", "rule", "check", "verify"],
}


async def execute_remember(
    content: str,
    scope: str = "project",
    tags: list[str] | None = None,
    priority: float = DEFAULT_PRIORITY,
    confidence: str = "active",
) -> str:
    """
    Create a new memory from content.

    Args:
        content: The information to remember (will be formatted as markdown)
        scope: Memory scope - baseline, global, agent, project, or ephemeral
        tags: Optional list of tags for categorization (auto-generated if not provided)
        priority: Importance from 0.0 to 1.0 (default 0.6)
        confidence: Confidence level - experimental, active, or stable

    Returns:
        Confirmation message with memory ID and details
    """
    validation_error = _validate_inputs(content, scope, priority, confidence)
    if validation_error:
        return validation_error

    content = content.strip()
    title = _extract_title(content)
    
    if not tags:
        tags = _extract_tags(content, title)
    else:
        tags = [_sanitize_tag(t) for t in tags if t and t.strip()]
        tags = tags[:10]

    if not tags:
        tags = ["note"]

    memory_id = _generate_memory_id()
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    frontmatter = _build_frontmatter(
        memory_id=memory_id,
        tags=tags,
        scope=scope,
        priority=priority,
        confidence=confidence,
        date_str=date_str,
    )

    if not content.lstrip().startswith("#"):
        full_content = f"{frontmatter}\n\n# {title}\n\n{content}"
    else:
        full_content = f"{frontmatter}\n\n{content}"

    config = get_config()
    memory_root = Path(config.get("memory_root", ".dmm/memory"))
    
    if not memory_root.is_absolute():
        project_root = Path(config.get("project_root", Path.cwd()))
        memory_root = project_root / memory_root

    scope_dir = memory_root / scope
    scope_dir.mkdir(parents=True, exist_ok=True)

    filename = _generate_filename(title)
    file_path = scope_dir / filename

    counter = 1
    base_filename = filename[:-3]
    while file_path.exists():
        filename = f"{base_filename}_{counter:02d}.md"
        file_path = scope_dir / filename
        counter += 1
        if counter > 99:
            return "Error: Too many memories with similar names. Please use a more specific title."

    try:
        file_path.write_text(full_content, encoding="utf-8")
        logger.info("Created memory file: %s", file_path)
    except OSError as e:
        logger.error("Failed to write memory file: %s", e)
        return f"Error: Failed to create memory file: {e}"

    await _trigger_reindex()

    token_estimate = len(content.split()) + len(title.split())

    return (
        f"Memory created successfully.\n\n"
        f"**ID:** {memory_id}\n"
        f"**Title:** {title}\n"
        f"**Scope:** {scope}\n"
        f"**Tags:** {', '.join(tags)}\n"
        f"**Priority:** {priority}\n"
        f"**File:** {file_path.name}\n"
        f"**Tokens:** ~{token_estimate}\n\n"
        f"The memory is now indexed and will be retrieved when relevant."
    )


def _validate_inputs(
    content: str,
    scope: str,
    priority: float,
    confidence: str,
) -> str | None:
    """Validate all inputs and return error message if invalid."""
    if not content or not content.strip():
        return "Error: Content cannot be empty."

    content_length = len(content.strip())
    if content_length < MIN_CONTENT_LENGTH:
        return f"Error: Content too short (minimum {MIN_CONTENT_LENGTH} characters)."

    if content_length > MAX_CONTENT_LENGTH:
        return f"Error: Content too long (maximum {MAX_CONTENT_LENGTH} characters)."

    if scope not in VALID_SCOPES:
        return f"Error: Invalid scope '{scope}'. Valid scopes: {', '.join(VALID_SCOPES)}"

    if not isinstance(priority, (int, float)):
        return "Error: Priority must be a number between 0.0 and 1.0."

    if not MIN_PRIORITY <= priority <= MAX_PRIORITY:
        return f"Error: Priority must be between {MIN_PRIORITY} and {MAX_PRIORITY}."

    if confidence not in VALID_CONFIDENCE:
        return f"Error: Invalid confidence '{confidence}'. Valid values: {', '.join(VALID_CONFIDENCE)}"

    return None


def _generate_memory_id() -> str:
    """Generate a unique memory ID based on timestamp."""
    now = datetime.now(timezone.utc)
    date_part = now.strftime("%Y_%m_%d")
    time_part = now.strftime("%H%M%S")
    microseconds = now.strftime("%f")[:3]
    return f"mem_{date_part}_{time_part}_{microseconds}"


def _extract_title(content: str) -> str:
    """Extract or generate a title from the content."""
    lines = content.strip().split("\n")

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            if title:
                return title[:80]
        if stripped.startswith("## "):
            title = stripped[3:].strip()
            if title:
                return title[:80]

    first_line = lines[0].strip() if lines else ""
    first_line = re.sub(r"^[#*_\->\s]+", "", first_line)

    if len(first_line) <= 60 and first_line:
        return first_line

    if first_line:
        words = first_line.split()
        title_words = []
        char_count = 0
        for word in words:
            if char_count + len(word) + 1 > 57:
                break
            title_words.append(word)
            char_count += len(word) + 1
        if title_words:
            return " ".join(title_words) + "..."

    return f"Memory {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"


def _extract_tags(content: str, title: str) -> list[str]:
    """Extract relevant tags from content using keyword analysis."""
    text = f"{title} {content}".lower()
    
    found_tags: list[str] = []
    
    for tag, keywords in KEYWORD_TAG_MAP.items():
        for keyword in keywords:
            if re.search(rf"\b{re.escape(keyword)}\b", text):
                found_tags.append(tag)
                break

    if not found_tags:
        found_tags = ["note"]

    return found_tags[:5]


def _sanitize_tag(tag: str) -> str:
    """Sanitize a tag string."""
    tag = tag.lower().strip()
    tag = re.sub(r"[^\w\-]", "_", tag)
    tag = re.sub(r"_+", "_", tag)
    tag = tag.strip("_")
    return tag[:30] if tag else "note"


def _generate_filename(title: str) -> str:
    """Generate a valid filename from a title."""
    filename = title.lower()
    filename = re.sub(r"[^\w\s\-]", "", filename)
    filename = re.sub(r"[\s\-]+", "_", filename)
    filename = re.sub(r"_+", "_", filename)
    filename = filename.strip("_")

    if len(filename) > 50:
        filename = filename[:50].rstrip("_")

    if not filename:
        filename = f"memory_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    return f"{filename}.md"


def _build_frontmatter(
    memory_id: str,
    tags: list[str],
    scope: str,
    priority: float,
    confidence: str,
    date_str: str,
) -> str:
    """Build YAML frontmatter for the memory file."""
    tags_formatted = ", ".join(tags)
    return f"""---
id: {memory_id}
tags: [{tags_formatted}]
scope: {scope}
priority: {priority}
confidence: {confidence}
status: active
created: {date_str}
last_used: {date_str}
usage_count: 0
source: mcp_auto
---"""


async def _trigger_reindex() -> None:
    """Trigger daemon reindex after creating a memory."""
    config = get_config()
    host = config.get("daemon", {}).get("host", "127.0.0.1")
    port = config.get("daemon", {}).get("port", 7437)
    url = f"http://{host}:{port}/reindex"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url)
            logger.debug("Triggered reindex after memory creation")
    except Exception as e:
        logger.debug("Could not trigger reindex (non-critical): %s", e)
