"""
DMM Conflicts Tool - Detect contradictory memories.

This tool queries the conflict detection system to find memories
that may contain contradictory or inconsistent information.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from dmm.core.config import get_config

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0


async def execute_conflicts(
    include_resolved: bool = False,
    min_severity: str = "low",
) -> str:
    """
    Check for conflicting memories that need resolution.

    Args:
        include_resolved: If True, include previously resolved conflicts
        min_severity: Minimum severity to include (low, medium, high, critical)

    Returns:
        List of detected conflicts with severity and suggested resolutions
    """
    severity_levels = ["low", "medium", "high", "critical"]
    if min_severity not in severity_levels:
        return f"Error: Invalid severity '{min_severity}'. Valid values: {', '.join(severity_levels)}"

    min_severity_idx = severity_levels.index(min_severity)

    config = get_config()
    host = config.get("daemon", {}).get("host", "127.0.0.1")
    port = config.get("daemon", {}).get("port", 7437)

    daemon_conflicts = await _fetch_daemon_conflicts(host, port)

    if daemon_conflicts is None:
        file_conflicts = _scan_file_conflicts(config)
        conflicts = file_conflicts
    else:
        conflicts = daemon_conflicts

    filtered_conflicts = []
    for conflict in conflicts:
        conflict_severity = conflict.get("severity", "low")
        if conflict_severity in severity_levels:
            conflict_severity_idx = severity_levels.index(conflict_severity)
            if conflict_severity_idx >= min_severity_idx:
                if include_resolved or conflict.get("status") != "resolved":
                    filtered_conflicts.append(conflict)

    return _format_conflicts_response(filtered_conflicts)


async def _fetch_daemon_conflicts(host: str, port: int) -> list[dict[str, Any]] | None:
    """Fetch conflicts from the daemon API."""
    url = f"http://{host}:{port}/conflicts"

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(url)

            if response.status_code == 200:
                data = response.json()
                return data.get("conflicts", [])
            else:
                logger.warning("Daemon conflicts endpoint returned %d", response.status_code)
                return None

    except httpx.ConnectError:
        logger.info("Daemon not running, falling back to file scan")
        return None
    except Exception as e:
        logger.warning("Failed to fetch conflicts from daemon: %s", e)
        return None


def _scan_file_conflicts(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Scan for conflicts by analyzing memory files directly."""
    memory_root = Path(config.get("memory_root", ".dmm/memory"))

    if not memory_root.is_absolute():
        project_root = Path(config.get("project_root", Path.cwd()))
        memory_root = project_root / memory_root

    if not memory_root.exists():
        return []

    memories = _load_all_memories(memory_root)

    if len(memories) < 2:
        return []

    conflicts: list[dict[str, Any]] = []

    conflicts.extend(_detect_tag_overlaps(memories))
    conflicts.extend(_detect_supersession_conflicts(memories))
    conflicts.extend(_detect_scope_conflicts(memories))

    seen_pairs: set[str] = set()
    unique_conflicts: list[dict[str, Any]] = []

    for conflict in conflicts:
        pair_key = _get_conflict_pair_key(conflict)
        if pair_key not in seen_pairs:
            seen_pairs.add(pair_key)
            unique_conflicts.append(conflict)

    unique_conflicts.sort(
        key=lambda c: ["low", "medium", "high", "critical"].index(c.get("severity", "low")),
        reverse=True,
    )

    return unique_conflicts


def _load_all_memories(memory_root: Path) -> list[dict[str, Any]]:
    """Load all active memories from the filesystem."""
    memories: list[dict[str, Any]] = []
    scopes = ["baseline", "global", "agent", "project", "ephemeral"]

    for scope in scopes:
        scope_dir = memory_root / scope
        if not scope_dir.exists():
            continue

        for md_file in scope_dir.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                metadata = _parse_frontmatter(content)

                if metadata.get("status") == "deprecated":
                    continue

                metadata["_file_path"] = str(md_file)
                metadata["_scope"] = scope
                metadata["_content"] = _strip_frontmatter(content)
                memories.append(metadata)

            except OSError as e:
                logger.warning("Failed to read %s: %s", md_file, e)
                continue

    return memories


def _parse_frontmatter(content: str) -> dict[str, Any]:
    """Parse YAML frontmatter from markdown content."""
    import re

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

    tags_match = re.search(r"tags:\s*\[([^\]]*)\]", frontmatter)
    if tags_match:
        tags_str = tags_match.group(1)
        tags = [t.strip().strip("'\"") for t in tags_str.split(",") if t.strip()]
        metadata["tags"] = tags

    scope_match = re.search(r"scope:\s*(\w+)", frontmatter)
    if scope_match:
        metadata["scope"] = scope_match.group(1).strip()

    status_match = re.search(r"status:\s*(\w+)", frontmatter)
    if status_match:
        metadata["status"] = status_match.group(1).strip()

    supersedes_match = re.search(r"supersedes:\s*\[([^\]]*)\]", frontmatter)
    if supersedes_match:
        supersedes_str = supersedes_match.group(1)
        supersedes = [s.strip().strip("'\"") for s in supersedes_str.split(",") if s.strip()]
        metadata["supersedes"] = supersedes

    priority_match = re.search(r"priority:\s*([\d.]+)", frontmatter)
    if priority_match:
        try:
            metadata["priority"] = float(priority_match.group(1))
        except ValueError:
            pass

    return metadata


def _strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter from content."""
    if not content.startswith("---"):
        return content

    parts = content.split("---", 2)
    if len(parts) >= 3:
        return parts[2].strip()

    return content


def _detect_tag_overlaps(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect conflicts based on high tag overlap with different content."""
    conflicts: list[dict[str, Any]] = []

    for i, mem_a in enumerate(memories):
        tags_a = set(mem_a.get("tags", []))
        if not tags_a:
            continue

        for mem_b in memories[i + 1:]:
            tags_b = set(mem_b.get("tags", []))
            if not tags_b:
                continue

            intersection = tags_a & tags_b
            union = tags_a | tags_b

            if not union:
                continue

            jaccard = len(intersection) / len(union)

            if jaccard >= 0.7:
                content_a = mem_a.get("_content", "")[:200]
                content_b = mem_b.get("_content", "")[:200]

                if content_a != content_b:
                    severity = "high" if jaccard >= 0.9 else "medium"
                    conflicts.append({
                        "type": "tag_overlap",
                        "severity": severity,
                        "memory_a": mem_a.get("id", "unknown"),
                        "memory_b": mem_b.get("id", "unknown"),
                        "overlap_score": round(jaccard, 3),
                        "shared_tags": list(intersection),
                        "description": (
                            f"Memories share {len(intersection)} tags "
                            f"({jaccard:.0%} overlap) but have different content"
                        ),
                        "suggestion": "Review and consolidate or differentiate these memories",
                        "status": "open",
                    })

    return conflicts


def _detect_supersession_conflicts(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect conflicts in supersession chains."""
    conflicts: list[dict[str, Any]] = []
    memory_by_id: dict[str, dict[str, Any]] = {m.get("id", ""): m for m in memories if m.get("id")}

    for memory in memories:
        supersedes = memory.get("supersedes", [])
        if not supersedes:
            continue

        for superseded_id in supersedes:
            if superseded_id in memory_by_id:
                old_memory = memory_by_id[superseded_id]
                if old_memory.get("status") != "deprecated":
                    conflicts.append({
                        "type": "supersession",
                        "severity": "high",
                        "memory_a": memory.get("id", "unknown"),
                        "memory_b": superseded_id,
                        "description": (
                            f"Memory {memory.get('id')} supersedes {superseded_id} "
                            f"but the old memory is still active"
                        ),
                        "suggestion": f"Deprecate memory {superseded_id}",
                        "status": "open",
                    })

    return conflicts


def _detect_scope_conflicts(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect conflicts where lower scope contradicts higher scope."""
    conflicts: list[dict[str, Any]] = []
    scope_priority = {"baseline": 0, "global": 1, "agent": 2, "project": 3, "ephemeral": 4}

    baseline_memories = [m for m in memories if m.get("_scope") == "baseline"]

    for baseline_mem in baseline_memories:
        baseline_tags = set(baseline_mem.get("tags", []))
        if not baseline_tags:
            continue

        for memory in memories:
            if memory.get("_scope") == "baseline":
                continue

            mem_tags = set(memory.get("tags", []))
            overlap = baseline_tags & mem_tags

            if len(overlap) >= 2:
                baseline_content = baseline_mem.get("_content", "").lower()
                mem_content = memory.get("_content", "").lower()

                contradiction_indicators = [
                    ("do not", "should"),
                    ("never", "always"),
                    ("forbidden", "allowed"),
                    ("disabled", "enabled"),
                    ("reject", "accept"),
                ]

                for neg, pos in contradiction_indicators:
                    if (neg in baseline_content and pos in mem_content) or \
                       (pos in baseline_content and neg in mem_content):
                        conflicts.append({
                            "type": "scope_contradiction",
                            "severity": "critical",
                            "memory_a": baseline_mem.get("id", "unknown"),
                            "memory_b": memory.get("id", "unknown"),
                            "description": (
                                f"Memory {memory.get('id')} in {memory.get('_scope')} scope "
                                f"may contradict baseline memory {baseline_mem.get('id')}"
                            ),
                            "suggestion": "Baseline memories are authoritative; review and align",
                            "status": "open",
                        })
                        break

    return conflicts


def _get_conflict_pair_key(conflict: dict[str, Any]) -> str:
    """Generate a unique key for a conflict pair."""
    mem_a = conflict.get("memory_a", "")
    mem_b = conflict.get("memory_b", "")
    conflict_type = conflict.get("type", "")
    return f"{min(mem_a, mem_b)}:{max(mem_a, mem_b)}:{conflict_type}"


def _format_conflicts_response(conflicts: list[dict[str, Any]]) -> str:
    """Format conflicts as readable markdown."""
    if not conflicts:
        return (
            "## No Conflicts Detected\n\n"
            "All memories appear to be consistent. No contradictions found."
        )

    lines: list[str] = []
    lines.append(f"## Memory Conflicts ({len(conflicts)} found)\n")

    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for conflict in conflicts:
        severity = conflict.get("severity", "low")
        severity_counts[severity] = severity_counts.get(severity, 0) + 1

    lines.append("**Summary:**")
    for severity in ["critical", "high", "medium", "low"]:
        count = severity_counts[severity]
        if count > 0:
            lines.append(f"- {severity.capitalize()}: {count}")
    lines.append("")

    for idx, conflict in enumerate(conflicts, 1):
        severity = conflict.get("severity", "low").upper()
        conflict_type = conflict.get("type", "unknown").replace("_", " ").title()

        lines.append(f"### {idx}. [{severity}] {conflict_type}")
        lines.append(f"**Memories:** `{conflict.get('memory_a')}` vs `{conflict.get('memory_b')}`")
        lines.append(f"**Issue:** {conflict.get('description', 'No description')}")
        lines.append(f"**Suggestion:** {conflict.get('suggestion', 'Review manually')}")

        if conflict.get("shared_tags"):
            lines.append(f"**Shared Tags:** {', '.join(conflict['shared_tags'])}")

        if conflict.get("overlap_score"):
            lines.append(f"**Overlap Score:** {conflict['overlap_score']:.1%}")

        lines.append("")

    lines.append("---")
    lines.append("*Use `dmm conflicts resolve <id>` to resolve conflicts.*")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines.append(f"*Scanned at {timestamp}*")

    return "\n".join(lines)
