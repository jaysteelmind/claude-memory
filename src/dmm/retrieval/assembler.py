"""Context assembler for building Memory Packs."""

from datetime import datetime

from dmm.core.constants import DEFAULT_BASELINE_BUDGET, DEFAULT_TOTAL_BUDGET, Scope
from dmm.indexer.parser import TokenCounter
from dmm.models.pack import BaselinePack, MemoryPack, MemoryPackEntry
from dmm.models.query import RetrievalResult


class ContextAssembler:
    """Assembles Memory Packs from baseline and retrieved memories."""

    # Scope ordering for retrieved memories
    SCOPE_ORDER = [
        Scope.GLOBAL.value,
        Scope.AGENT.value,
        Scope.PROJECT.value,
        Scope.EPHEMERAL.value,
    ]

    def __init__(self, token_counter: TokenCounter | None = None) -> None:
        """
        Initialize the assembler.

        Args:
            token_counter: Token counter instance (optional)
        """
        self._token_counter = token_counter or TokenCounter()

    def assemble(
        self,
        query: str,
        baseline: BaselinePack,
        retrieved: RetrievalResult,
        budget: int = DEFAULT_TOTAL_BUDGET,
    ) -> MemoryPack:
        """
        Assemble the final Memory Pack.

        Order:
        1. Baseline entries (always included first)
        2. Retrieved entries (by scope: global -> agent -> project -> ephemeral)

        Args:
            query: Original query string
            baseline: Pre-compiled baseline pack
            retrieved: Retrieval result with candidate entries
            budget: Total token budget

        Returns:
            Assembled MemoryPack
        """
        # Sort retrieved entries by scope
        sorted_retrieved = self._sort_by_scope(retrieved.entries)

        # Calculate tokens
        baseline_tokens = baseline.total_tokens
        retrieved_tokens = retrieved.total_tokens
        total_tokens = baseline_tokens + retrieved_tokens

        # Build included paths list
        included_paths = [e.path for e in baseline.entries]
        included_paths.extend([e.path for e in sorted_retrieved])

        return MemoryPack(
            generated_at=datetime.now(),
            query=query,
            baseline_tokens=baseline_tokens,
            retrieved_tokens=retrieved_tokens,
            total_tokens=total_tokens,
            budget=budget,
            baseline_entries=list(baseline.entries),
            retrieved_entries=sorted_retrieved,
            included_paths=included_paths,
            excluded_paths=retrieved.excluded_for_budget,
        )

    def render_markdown(self, pack: MemoryPack, verbose: bool = False) -> str:
        """
        Render pack as markdown string.

        Args:
            pack: MemoryPack to render
            verbose: Include detailed statistics and scores

        Returns:
            Markdown formatted string
        """
        return pack.to_markdown(verbose=verbose)

    def _sort_by_scope(self, entries: list[MemoryPackEntry]) -> list[MemoryPackEntry]:
        """
        Sort entries by scope order.

        Order: global -> agent -> project -> ephemeral -> other
        """
        def scope_key(entry: MemoryPackEntry) -> tuple[int, float]:
            # Extract scope from path
            scope = entry.path.split("/")[0] if "/" in entry.path else "other"
            
            # Get order index (higher = later)
            try:
                order = self.SCOPE_ORDER.index(scope)
            except ValueError:
                order = len(self.SCOPE_ORDER)  # Unknown scopes go last
            
            # Secondary sort by relevance score (descending)
            return (order, -entry.relevance_score)

        return sorted(entries, key=scope_key)

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        return self._token_counter.count(text)

    def calculate_remaining_budget(
        self,
        total_budget: int,
        baseline_tokens: int,
        used_tokens: int,
    ) -> int:
        """Calculate remaining retrieval budget."""
        return max(0, total_budget - baseline_tokens - used_tokens)


class PackBuilder:
    """Builder pattern for constructing Memory Packs incrementally."""

    def __init__(
        self,
        query: str,
        budget: int = DEFAULT_TOTAL_BUDGET,
        baseline_budget: int = DEFAULT_BASELINE_BUDGET,
    ) -> None:
        """
        Initialize pack builder.

        Args:
            query: Query string
            budget: Total token budget
            baseline_budget: Baseline token budget
        """
        self._query = query
        self._budget = budget
        self._baseline_budget = baseline_budget
        self._baseline_entries: list[MemoryPackEntry] = []
        self._retrieved_entries: list[MemoryPackEntry] = []
        self._excluded_paths: list[str] = []
        self._baseline_tokens = 0
        self._retrieved_tokens = 0

    @property
    def remaining_budget(self) -> int:
        """Get remaining token budget for retrieval."""
        retrieval_budget = self._budget - self._baseline_budget
        return max(0, retrieval_budget - self._retrieved_tokens)

    @property
    def total_tokens(self) -> int:
        """Get total tokens used."""
        return self._baseline_tokens + self._retrieved_tokens

    def add_baseline(self, pack: BaselinePack) -> "PackBuilder":
        """Add baseline pack entries."""
        self._baseline_entries = list(pack.entries)
        self._baseline_tokens = pack.total_tokens
        return self

    def add_entry(self, entry: MemoryPackEntry) -> bool:
        """
        Add a retrieved entry if budget allows.

        Returns:
            True if added, False if excluded for budget
        """
        if entry.token_count <= self.remaining_budget:
            self._retrieved_entries.append(entry)
            self._retrieved_tokens += entry.token_count
            return True
        else:
            self._excluded_paths.append(entry.path)
            return False

    def add_entries(self, entries: list[MemoryPackEntry]) -> int:
        """
        Add multiple entries, respecting budget.

        Returns:
            Number of entries added
        """
        added = 0
        for entry in entries:
            if self.add_entry(entry):
                added += 1
        return added

    def exclude(self, path: str) -> "PackBuilder":
        """Mark a path as excluded."""
        self._excluded_paths.append(path)
        return self

    def build(self) -> MemoryPack:
        """Build the final MemoryPack."""
        included_paths = [e.path for e in self._baseline_entries]
        included_paths.extend([e.path for e in self._retrieved_entries])

        return MemoryPack(
            generated_at=datetime.now(),
            query=self._query,
            baseline_tokens=self._baseline_tokens,
            retrieved_tokens=self._retrieved_tokens,
            total_tokens=self.total_tokens,
            budget=self._budget,
            baseline_entries=self._baseline_entries,
            retrieved_entries=self._retrieved_entries,
            included_paths=included_paths,
            excluded_paths=self._excluded_paths,
        )
