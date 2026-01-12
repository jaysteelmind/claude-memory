"""Memory Pack data models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class MemoryPackEntry:
    """A single memory included in a pack."""

    path: str
    title: str
    content: str
    token_count: int
    relevance_score: float
    source: Literal["baseline", "retrieved"]

    def to_markdown(self, include_score: bool = False) -> str:
        """Render entry as markdown section."""
        if include_score:
            header = f"### [{self.path}] (relevance: {self.relevance_score:.2f})"
        else:
            if self.source == "baseline":
                header = f"### [{self.path}] (relevance: baseline)"
            else:
                header = f"### [{self.path}]"
        return f"{header}\n\n{self.content}"


@dataclass
class MemoryPack:
    """The compiled memory pack returned to the agent."""

    # Metadata
    generated_at: datetime
    query: str

    # Token accounting
    baseline_tokens: int
    retrieved_tokens: int
    total_tokens: int
    budget: int

    # Entries (ordered)
    baseline_entries: list[MemoryPackEntry] = field(default_factory=list)
    retrieved_entries: list[MemoryPackEntry] = field(default_factory=list)

    # For traceability
    included_paths: list[str] = field(default_factory=list)
    excluded_paths: list[str] = field(default_factory=list)

    @property
    def remaining_budget(self) -> int:
        """Calculate remaining token budget."""
        return self.budget - self.total_tokens

    @property
    def baseline_count(self) -> int:
        """Number of baseline entries."""
        return len(self.baseline_entries)

    @property
    def retrieved_count(self) -> int:
        """Number of retrieved entries."""
        return len(self.retrieved_entries)

    @property
    def total_count(self) -> int:
        """Total number of entries."""
        return self.baseline_count + self.retrieved_count

    def to_markdown(self, verbose: bool = False) -> str:
        """Render pack as markdown string."""
        lines: list[str] = []

        # Header
        lines.append("# DMM Memory Pack")
        lines.append(f"Generated: {self.generated_at.isoformat()}")
        lines.append(f'Task: "{self.query}"')
        lines.append(
            f"Baseline tokens: {self.baseline_tokens} | "
            f"Retrieved tokens: {self.retrieved_tokens} | "
            f"Total: {self.total_tokens}"
        )
        lines.append("")
        lines.append("---")
        lines.append("")

        # Baseline section
        if self.baseline_entries:
            lines.append("## Baseline (Always Included)")
            lines.append("")
            for entry in self.baseline_entries:
                lines.append(entry.to_markdown(include_score=False))
                lines.append("")
            lines.append("---")
            lines.append("")

        # Retrieved section - group by scope
        if self.retrieved_entries:
            lines.append("## Retrieved Context")
            lines.append("")

            # Group entries by directory prefix (scope)
            scope_groups: dict[str, list[MemoryPackEntry]] = {}
            for entry in self.retrieved_entries:
                # Extract scope from path (first directory component)
                scope = entry.path.split("/")[0] if "/" in entry.path else "other"
                if scope not in scope_groups:
                    scope_groups[scope] = []
                scope_groups[scope].append(entry)

            # Output in order: global, agent, project, ephemeral, other
            scope_order = ["global", "agent", "project", "ephemeral", "other"]
            for scope in scope_order:
                if scope in scope_groups:
                    lines.append(f"### {scope.capitalize()}")
                    lines.append("")
                    for entry in scope_groups[scope]:
                        # Use h4 for entries within scope
                        entry_md = entry.to_markdown(include_score=verbose)
                        # Adjust header level
                        entry_md = entry_md.replace("### [", "#### [", 1)
                        lines.append(entry_md)
                        lines.append("")

            lines.append("---")
            lines.append("")

        # Statistics section
        lines.append("## Pack Statistics")
        lines.append(f"- Baseline: {self.baseline_count} files, {self.baseline_tokens} tokens")
        lines.append(f"- Retrieved: {self.retrieved_count} files, {self.retrieved_tokens} tokens")
        lines.append(f"- Budget: {self.budget} tokens")
        lines.append(f"- Remaining: {self.remaining_budget} tokens")
        if self.excluded_paths:
            lines.append(f"- Excluded: {len(self.excluded_paths)} files (budget exceeded)")

        if verbose and self.excluded_paths:
            lines.append("")
            lines.append("### Excluded Files")
            for path in self.excluded_paths:
                lines.append(f"- {path}")

        return "\n".join(lines)


@dataclass
class BaselinePack:
    """Pre-compiled baseline pack for fast inclusion."""

    entries: list[MemoryPackEntry]
    total_tokens: int
    generated_at: datetime
    file_hashes: dict[str, str] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        """Check if baseline pack is empty."""
        return len(self.entries) == 0

    def is_valid(self, current_hashes: dict[str, str]) -> bool:
        """Check if cached baseline is still valid."""
        return self.file_hashes == current_hashes


@dataclass
class BaselineValidation:
    """Result of baseline budget validation."""

    total_tokens: int
    budget: int
    is_valid: bool
    overflow_files: list[str] = field(default_factory=list)
    overflow_tokens: int = 0

    @property
    def message(self) -> str:
        """Generate validation message."""
        if self.is_valid:
            return f"Baseline valid: {self.total_tokens}/{self.budget} tokens"
        return (
            f"Baseline exceeds budget: {self.total_tokens}/{self.budget} tokens "
            f"(overflow: {self.overflow_tokens} tokens in {len(self.overflow_files)} files)"
        )
