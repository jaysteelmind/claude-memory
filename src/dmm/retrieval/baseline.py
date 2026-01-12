"""Baseline Pack management with caching."""

import json
from datetime import datetime
from pathlib import Path

from dmm.core.constants import (
    BASELINE_PRIORITY_FILES,
    DEFAULT_BASELINE_BUDGET,
    get_dmm_root,
)
from dmm.core.exceptions import BaselineError
from dmm.indexer.store import MemoryStore
from dmm.models.memory import IndexedMemory
from dmm.models.pack import BaselinePack, BaselineValidation, MemoryPackEntry


class BaselineManager:
    """Manages the baseline pack with caching."""

    def __init__(
        self,
        store: MemoryStore,
        base_path: Path | None = None,
        token_budget: int = DEFAULT_BASELINE_BUDGET,
    ) -> None:
        """
        Initialize baseline manager.

        Args:
            store: Memory store instance
            base_path: Base path for .dmm directory
            token_budget: Token budget for baseline (default: 800)
        """
        self._store = store
        self._base_path = base_path or Path.cwd()
        self._token_budget = token_budget
        self._cache: BaselinePack | None = None
        self._cache_path = get_dmm_root(self._base_path) / "packs" / "baseline_pack.json"

    @property
    def token_budget(self) -> int:
        """Get baseline token budget."""
        return self._token_budget

    def get_baseline_pack(self) -> BaselinePack:
        """
        Get the current baseline pack.

        Returns cached version if valid, regenerates if stale.
        """
        # Get current baseline memories
        baseline_memories = self._store.get_baseline_memories()
        current_hashes = {m.path: m.file_hash for m in baseline_memories}

        # Check cache validity
        if self._cache is not None and self._cache.is_valid(current_hashes):
            return self._cache

        # Try to load from disk cache
        disk_cache = self._load_cache()
        if disk_cache is not None and disk_cache.is_valid(current_hashes):
            self._cache = disk_cache
            return self._cache

        # Regenerate
        self._cache = self._build_baseline_pack(baseline_memories)
        self._save_cache(self._cache)

        return self._cache

    def invalidate_cache(self) -> None:
        """Force cache regeneration on next access."""
        self._cache = None
        if self._cache_path.exists():
            self._cache_path.unlink()

    def validate_baseline_budget(self) -> BaselineValidation:
        """
        Check if baseline fits within budget.

        Returns validation result with overflow details if over budget.
        """
        baseline_memories = self._store.get_baseline_memories()
        
        total_tokens = sum(m.token_count for m in baseline_memories)
        is_valid = total_tokens <= self._token_budget

        overflow_files: list[str] = []
        overflow_tokens = 0

        if not is_valid:
            # Sort by priority descending to identify least critical files
            sorted_memories = sorted(baseline_memories, key=lambda m: m.priority, reverse=True)
            
            running_total = 0
            for memory in sorted_memories:
                running_total += memory.token_count
                if running_total > self._token_budget:
                    overflow_files.append(memory.path)
                    overflow_tokens += memory.token_count

        return BaselineValidation(
            total_tokens=total_tokens,
            budget=self._token_budget,
            is_valid=is_valid,
            overflow_files=overflow_files,
            overflow_tokens=overflow_tokens,
        )

    def get_baseline_tokens(self) -> int:
        """Get total tokens in current baseline."""
        pack = self.get_baseline_pack()
        return pack.total_tokens

    def _build_baseline_pack(self, memories: list[IndexedMemory]) -> BaselinePack:
        """Build baseline pack from memories."""
        # Sort memories according to priority ordering
        sorted_memories = self._sort_baseline_memories(memories)

        entries: list[MemoryPackEntry] = []
        total_tokens = 0
        file_hashes: dict[str, str] = {}

        for memory in sorted_memories:
            # Check budget (warn but include anyway for baseline)
            entry = MemoryPackEntry(
                path=memory.path,
                title=memory.title,
                content=memory.body,
                token_count=memory.token_count,
                relevance_score=1.0,  # Baseline always has max relevance
                source="baseline",
            )
            entries.append(entry)
            total_tokens += memory.token_count
            file_hashes[memory.path] = memory.file_hash

        return BaselinePack(
            entries=entries,
            total_tokens=total_tokens,
            generated_at=datetime.now(),
            file_hashes=file_hashes,
        )

    def _sort_baseline_memories(self, memories: list[IndexedMemory]) -> list[IndexedMemory]:
        """
        Sort baseline memories according to priority ordering.

        Order:
        1. identity.md (if exists)
        2. hard_constraints.md (if exists)
        3. Remaining files alphabetically by filename
        """
        priority_files: dict[str, IndexedMemory] = {}
        other_files: list[IndexedMemory] = []

        for memory in memories:
            filename = memory.path.rsplit("/", 1)[-1]
            if filename in BASELINE_PRIORITY_FILES:
                priority_files[filename] = memory
            else:
                other_files.append(memory)

        # Build sorted list
        sorted_memories: list[IndexedMemory] = []

        # Add priority files in order
        for priority_file in BASELINE_PRIORITY_FILES:
            if priority_file in priority_files:
                sorted_memories.append(priority_files[priority_file])

        # Add remaining files alphabetically
        other_files.sort(key=lambda m: m.path.rsplit("/", 1)[-1])
        sorted_memories.extend(other_files)

        return sorted_memories

    def _load_cache(self) -> BaselinePack | None:
        """Load cached baseline pack from disk."""
        if not self._cache_path.exists():
            return None

        try:
            with open(self._cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            entries = [
                MemoryPackEntry(
                    path=e["path"],
                    title=e["title"],
                    content=e["content"],
                    token_count=e["token_count"],
                    relevance_score=e["relevance_score"],
                    source=e["source"],
                )
                for e in data["entries"]
            ]

            return BaselinePack(
                entries=entries,
                total_tokens=data["total_tokens"],
                generated_at=datetime.fromisoformat(data["generated_at"]),
                file_hashes=data["file_hashes"],
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    def _save_cache(self, pack: BaselinePack) -> None:
        """Save baseline pack to disk cache."""
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "entries": [
                {
                    "path": e.path,
                    "title": e.title,
                    "content": e.content,
                    "token_count": e.token_count,
                    "relevance_score": e.relevance_score,
                    "source": e.source,
                }
                for e in pack.entries
            ],
            "total_tokens": pack.total_tokens,
            "generated_at": pack.generated_at.isoformat(),
            "file_hashes": pack.file_hashes,
        }

        with open(self._cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
