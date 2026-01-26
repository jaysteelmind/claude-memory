"""Memory Curator Agent - Manages and organizes the DMM memory system.

This agent demonstrates:
- Memory querying and search
- Conflict detection and analysis
- Memory health monitoring
- Usage pattern analysis
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class MemoryHealthStatus(str, Enum):
    """Memory system health status."""
    
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


@dataclass
class MemoryStats:
    """Statistics about the memory system."""
    
    total_memories: int
    by_scope: dict[str, int]
    by_status: dict[str, int]
    total_tokens: int
    avg_tokens_per_memory: float
    conflicts_unresolved: int
    stale_memories: int
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_memories": self.total_memories,
            "by_scope": self.by_scope,
            "by_status": self.by_status,
            "total_tokens": self.total_tokens,
            "avg_tokens_per_memory": self.avg_tokens_per_memory,
            "conflicts_unresolved": self.conflicts_unresolved,
            "stale_memories": self.stale_memories,
        }


@dataclass
class ConflictInfo:
    """Information about a detected conflict."""
    
    conflict_id: str
    memory_ids: tuple[str, str]
    conflict_type: str
    confidence: float
    description: str
    suggested_action: str


@dataclass
class MemoryCuratorConfig:
    """Configuration for MemoryCuratorAgent."""
    
    stale_threshold_days: int = 30
    conflict_confidence_threshold: float = 0.7
    max_baseline_tokens: int = 800
    enable_auto_cleanup: bool = False


class MemoryCuratorAgent:
    """Agent that manages and curates the DMM memory system.
    
    This agent provides:
    - Memory search and retrieval
    - Conflict detection and analysis
    - Memory health monitoring
    - Usage pattern tracking
    - Cleanup recommendations
    
    Example:
        agent = MemoryCuratorAgent(memory_dir=Path(".dmm/memory"))
        health = agent.check_health()
        conflicts = agent.find_conflicts()
    """
    
    def __init__(
        self,
        memory_dir: Path | None = None,
        config: MemoryCuratorConfig | None = None,
    ) -> None:
        """Initialize the agent.
        
        Args:
            memory_dir: Path to memory directory.
            config: Optional configuration.
        """
        self.memory_dir = memory_dir or Path(".dmm/memory")
        self.config = config or MemoryCuratorConfig()
        self._memory_cache: dict[str, dict[str, Any]] = {}
        self._last_scan: datetime | None = None
    
    def scan_memories(self, force: bool = False) -> int:
        """Scan and cache all memories.
        
        Args:
            force: Force rescan even if recently scanned.
            
        Returns:
            Number of memories found.
        """
        if not force and self._last_scan:
            elapsed = (datetime.now(timezone.utc) - self._last_scan).total_seconds()
            if elapsed < 60:
                return len(self._memory_cache)
        
        self._memory_cache.clear()
        
        if not self.memory_dir.exists():
            return 0
        
        for md_file in self.memory_dir.rglob("*.md"):
            if "deprecated" in str(md_file):
                continue
            
            try:
                memory_data = self._parse_memory_file(md_file)
                if memory_data:
                    self._memory_cache[memory_data["id"]] = memory_data
            except Exception:
                continue
        
        self._last_scan = datetime.now(timezone.utc)
        return len(self._memory_cache)
    
    def _parse_memory_file(self, file_path: Path) -> dict[str, Any] | None:
        """Parse a memory markdown file."""
        content = file_path.read_text()
        
        if not content.startswith("---"):
            return None
        
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None
        
        frontmatter = parts[1].strip()
        body = parts[2].strip()
        
        metadata: dict[str, Any] = {}
        for line in frontmatter.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                
                if value.startswith("[") and value.endswith("]"):
                    value = [v.strip().strip("'\"") for v in value[1:-1].split(",") if v.strip()]
                elif value.isdigit():
                    value = int(value)
                elif value.replace(".", "").isdigit():
                    value = float(value)
                
                metadata[key] = value
        
        if "id" not in metadata:
            return None
        
        relative_path = file_path.relative_to(self.memory_dir) if self.memory_dir in file_path.parents else file_path
        scope = relative_path.parts[0] if relative_path.parts else "unknown"
        
        title = ""
        for line in body.split("\n"):
            if line.startswith("# "):
                title = line[2:].strip()
                break
        
        word_count = len(body.split())
        token_estimate = int(word_count * 1.3)
        
        return {
            "id": metadata["id"],
            "path": str(file_path),
            "relative_path": str(relative_path),
            "scope": scope,
            "title": title,
            "tags": metadata.get("tags", []),
            "priority": metadata.get("priority", 0.5),
            "confidence": metadata.get("confidence", "active"),
            "status": metadata.get("status", "active"),
            "created": metadata.get("created"),
            "last_used": metadata.get("last_used"),
            "token_count": token_estimate,
            "body_preview": body[:200],
        }
    
    def get_stats(self) -> MemoryStats:
        """Get memory system statistics.
        
        Returns:
            MemoryStats with current statistics.
        """
        self.scan_memories()
        
        by_scope: dict[str, int] = {}
        by_status: dict[str, int] = {}
        total_tokens = 0
        stale_count = 0
        
        now = datetime.now(timezone.utc)
        
        for memory in self._memory_cache.values():
            scope = memory.get("scope", "unknown")
            by_scope[scope] = by_scope.get(scope, 0) + 1
            
            status = memory.get("status", "active")
            by_status[status] = by_status.get(status, 0) + 1
            
            total_tokens += memory.get("token_count", 0)
            
            last_used = memory.get("last_used")
            if last_used:
                try:
                    if isinstance(last_used, str):
                        last_used_dt = datetime.fromisoformat(last_used)
                        if last_used_dt.tzinfo is None:
                            last_used_dt = last_used_dt.replace(tzinfo=timezone.utc)
                        days_since = (now - last_used_dt).days
                        if days_since > self.config.stale_threshold_days:
                            stale_count += 1
                except (ValueError, TypeError):
                    pass
        
        total = len(self._memory_cache)
        avg_tokens = total_tokens / total if total > 0 else 0
        
        return MemoryStats(
            total_memories=total,
            by_scope=by_scope,
            by_status=by_status,
            total_tokens=total_tokens,
            avg_tokens_per_memory=avg_tokens,
            conflicts_unresolved=0,
            stale_memories=stale_count,
        )
    
    def check_health(self) -> tuple[MemoryHealthStatus, list[str]]:
        """Check memory system health.
        
        Returns:
            Tuple of (status, list of issues).
        """
        self.scan_memories()
        stats = self.get_stats()
        
        issues = []
        
        baseline_tokens = sum(
            m.get("token_count", 0)
            for m in self._memory_cache.values()
            if m.get("scope") == "baseline"
        )
        
        if baseline_tokens > self.config.max_baseline_tokens:
            issues.append(
                f"Baseline exceeds token limit: {baseline_tokens} > {self.config.max_baseline_tokens}"
            )
        
        if stats.stale_memories > 10:
            issues.append(f"High number of stale memories: {stats.stale_memories}")
        
        if stats.conflicts_unresolved > 5:
            issues.append(f"Unresolved conflicts: {stats.conflicts_unresolved}")
        
        deprecated_count = stats.by_status.get("deprecated", 0)
        if deprecated_count > stats.total_memories * 0.2:
            issues.append(f"High deprecated ratio: {deprecated_count}/{stats.total_memories}")
        
        if not issues:
            return MemoryHealthStatus.HEALTHY, []
        elif len(issues) <= 2:
            return MemoryHealthStatus.DEGRADED, issues
        else:
            return MemoryHealthStatus.CRITICAL, issues
    
    def search_memories(
        self,
        query: str | None = None,
        scope: str | None = None,
        tags: list[str] | None = None,
        min_priority: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Search memories with filters.
        
        Args:
            query: Text to search for in title/body.
            scope: Filter by scope.
            tags: Filter by tags (any match).
            min_priority: Minimum priority threshold.
            
        Returns:
            List of matching memories.
        """
        self.scan_memories()
        
        results = []
        query_lower = query.lower() if query else None
        
        for memory in self._memory_cache.values():
            if scope and memory.get("scope") != scope:
                continue
            
            if memory.get("priority", 0) < min_priority:
                continue
            
            if tags:
                memory_tags = memory.get("tags", [])
                if not any(t in memory_tags for t in tags):
                    continue
            
            if query_lower:
                title = memory.get("title", "").lower()
                body = memory.get("body_preview", "").lower()
                if query_lower not in title and query_lower not in body:
                    continue
            
            results.append(memory)
        
        results.sort(key=lambda m: m.get("priority", 0), reverse=True)
        return results
    
    def find_potential_conflicts(self) -> list[ConflictInfo]:
        """Find potential conflicts between memories.
        
        Uses tag overlap analysis to identify conflicts.
        
        Returns:
            List of potential conflicts.
        """
        self.scan_memories()
        
        conflicts = []
        memories = list(self._memory_cache.values())
        
        for i, m1 in enumerate(memories):
            for m2 in memories[i + 1:]:
                if m1.get("scope") != m2.get("scope"):
                    continue
                
                tags1 = set(m1.get("tags", []))
                tags2 = set(m2.get("tags", []))
                
                if not tags1 or not tags2:
                    continue
                
                overlap = tags1 & tags2
                union = tags1 | tags2
                
                if not union:
                    continue
                
                jaccard = len(overlap) / len(union)
                
                if jaccard >= self.config.conflict_confidence_threshold:
                    body1 = m1.get("body_preview", "").lower()
                    body2 = m2.get("body_preview", "").lower()
                    
                    contradiction_pairs = [
                        ("always", "never"),
                        ("must", "must not"),
                        ("enable", "disable"),
                        ("allow", "prohibit"),
                    ]
                    
                    has_contradiction = False
                    for word1, word2 in contradiction_pairs:
                        if (word1 in body1 and word2 in body2) or (word2 in body1 and word1 in body2):
                            has_contradiction = True
                            break
                    
                    if has_contradiction or jaccard >= 0.8:
                        conflicts.append(ConflictInfo(
                            conflict_id=f"conflict_{m1['id']}_{m2['id']}",
                            memory_ids=(m1["id"], m2["id"]),
                            conflict_type="potential_contradiction" if has_contradiction else "high_overlap",
                            confidence=jaccard,
                            description=f"High tag overlap ({jaccard:.0%}) between memories",
                            suggested_action="Review and merge or clarify scope",
                        ))
        
        return conflicts
    
    def get_stale_memories(self) -> list[dict[str, Any]]:
        """Get memories that haven't been used recently.
        
        Returns:
            List of stale memories.
        """
        self.scan_memories()
        
        stale = []
        now = datetime.now(timezone.utc)
        
        for memory in self._memory_cache.values():
            last_used = memory.get("last_used")
            if not last_used:
                stale.append(memory)
                continue
            
            try:
                if isinstance(last_used, str):
                    last_used_dt = datetime.fromisoformat(last_used)
                    if last_used_dt.tzinfo is None:
                        last_used_dt = last_used_dt.replace(tzinfo=timezone.utc)
                    days_since = (now - last_used_dt).days
                    if days_since > self.config.stale_threshold_days:
                        memory["days_since_used"] = days_since
                        stale.append(memory)
            except (ValueError, TypeError):
                stale.append(memory)
        
        return stale
    
    def suggest_consolidation(self) -> list[dict[str, Any]]:
        """Suggest memories that could be consolidated.
        
        Returns:
            List of consolidation suggestions.
        """
        self.scan_memories()
        
        suggestions = []
        
        tag_groups: dict[str, list[dict[str, Any]]] = {}
        for memory in self._memory_cache.values():
            for tag in memory.get("tags", []):
                if tag not in tag_groups:
                    tag_groups[tag] = []
                tag_groups[tag].append(memory)
        
        for tag, memories in tag_groups.items():
            if len(memories) >= 3:
                same_scope = {}
                for m in memories:
                    scope = m.get("scope", "unknown")
                    if scope not in same_scope:
                        same_scope[scope] = []
                    same_scope[scope].append(m)
                
                for scope, scope_memories in same_scope.items():
                    if len(scope_memories) >= 3:
                        suggestions.append({
                            "type": "consolidate",
                            "tag": tag,
                            "scope": scope,
                            "memory_count": len(scope_memories),
                            "memory_ids": [m["id"] for m in scope_memories],
                            "reason": f"Multiple memories ({len(scope_memories)}) share tag '{tag}' in scope '{scope}'",
                        })
        
        return suggestions
    
    def generate_health_report(self) -> str:
        """Generate a health report for the memory system.
        
        Returns:
            Formatted health report.
        """
        stats = self.get_stats()
        health_status, issues = self.check_health()
        conflicts = self.find_potential_conflicts()
        stale = self.get_stale_memories()
        
        lines = [
            "# Memory System Health Report",
            "",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            "",
            f"## Overall Status: {health_status.value.upper()}",
            "",
            "## Statistics",
            "",
            f"- Total memories: {stats.total_memories}",
            f"- Total tokens: {stats.total_tokens}",
            f"- Average tokens per memory: {stats.avg_tokens_per_memory:.0f}",
            "",
            "### By Scope",
            "",
        ]
        
        for scope, count in sorted(stats.by_scope.items()):
            lines.append(f"- {scope}: {count}")
        
        lines.extend(["", "### By Status", ""])
        
        for status, count in sorted(stats.by_status.items()):
            lines.append(f"- {status}: {count}")
        
        if issues:
            lines.extend(["", "## Issues", ""])
            for issue in issues:
                lines.append(f"- {issue}")
        
        if conflicts:
            lines.extend(["", "## Potential Conflicts", ""])
            for conflict in conflicts[:5]:
                lines.append(
                    f"- {conflict.conflict_type}: {conflict.memory_ids} "
                    f"(confidence: {conflict.confidence:.0%})"
                )
        
        if stale:
            lines.extend(["", f"## Stale Memories ({len(stale)} total)", ""])
            for memory in stale[:5]:
                lines.append(f"- {memory['id']}: {memory.get('title', 'Untitled')}")
        
        return "\n".join(lines)
