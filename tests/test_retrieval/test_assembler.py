"""Tests for the context assembler."""

from datetime import datetime

import pytest

from dmm.models.pack import BaselinePack, MemoryPackEntry
from dmm.models.query import RetrievalResult
from dmm.retrieval.assembler import ContextAssembler, PackBuilder


def create_entry(
    path: str,
    title: str,
    token_count: int = 100,
    relevance: float = 0.8,
    source: str = "retrieved",
) -> MemoryPackEntry:
    """Create a test entry."""
    return MemoryPackEntry(
        path=path,
        title=title,
        content=f"Content for {title}",
        token_count=token_count,
        relevance_score=relevance,
        source=source,
    )


class TestContextAssembler:
    """Tests for ContextAssembler."""

    @pytest.fixture
    def assembler(self) -> ContextAssembler:
        """Create assembler instance."""
        return ContextAssembler()

    @pytest.fixture
    def baseline_pack(self) -> BaselinePack:
        """Create a baseline pack."""
        return BaselinePack(
            entries=[
                create_entry("baseline/identity.md", "Identity", 150, source="baseline"),
                create_entry("baseline/constraints.md", "Constraints", 100, source="baseline"),
            ],
            total_tokens=250,
            generated_at=datetime.now(),
            file_hashes={"baseline/identity.md": "hash1", "baseline/constraints.md": "hash2"},
        )

    @pytest.fixture
    def retrieval_result(self) -> RetrievalResult:
        """Create a retrieval result."""
        return RetrievalResult(
            entries=[
                create_entry("project/auth.md", "Auth", 100, 0.9),
                create_entry("global/style.md", "Style", 80, 0.7),
            ],
            total_tokens=180,
            directories_searched=["project", "global"],
            candidates_considered=10,
            excluded_for_budget=["project/other.md"],
        )

    def test_assemble_basic(
        self,
        assembler: ContextAssembler,
        baseline_pack: BaselinePack,
        retrieval_result: RetrievalResult,
    ) -> None:
        """Should assemble pack with baseline and retrieved."""
        pack = assembler.assemble(
            query="test query",
            baseline=baseline_pack,
            retrieved=retrieval_result,
            budget=2000,
        )

        assert pack.query == "test query"
        assert pack.baseline_tokens == 250
        assert pack.retrieved_tokens == 180
        assert pack.total_tokens == 430
        assert len(pack.baseline_entries) == 2
        assert len(pack.retrieved_entries) == 2

    def test_assemble_includes_all_paths(
        self,
        assembler: ContextAssembler,
        baseline_pack: BaselinePack,
        retrieval_result: RetrievalResult,
    ) -> None:
        """Should include all paths in included_paths."""
        pack = assembler.assemble(
            query="test",
            baseline=baseline_pack,
            retrieved=retrieval_result,
            budget=2000,
        )

        assert "baseline/identity.md" in pack.included_paths
        assert "baseline/constraints.md" in pack.included_paths
        assert "project/auth.md" in pack.included_paths
        assert "global/style.md" in pack.included_paths

    def test_assemble_preserves_excluded(
        self,
        assembler: ContextAssembler,
        baseline_pack: BaselinePack,
        retrieval_result: RetrievalResult,
    ) -> None:
        """Should preserve excluded paths from retrieval."""
        pack = assembler.assemble(
            query="test",
            baseline=baseline_pack,
            retrieved=retrieval_result,
            budget=2000,
        )

        assert "project/other.md" in pack.excluded_paths

    def test_render_markdown(
        self,
        assembler: ContextAssembler,
        baseline_pack: BaselinePack,
        retrieval_result: RetrievalResult,
    ) -> None:
        """Should render valid markdown."""
        pack = assembler.assemble(
            query="test query",
            baseline=baseline_pack,
            retrieved=retrieval_result,
            budget=2000,
        )

        markdown = assembler.render_markdown(pack)

        assert "# DMM Memory Pack" in markdown
        assert "## Baseline (Always Included)" in markdown
        assert "baseline/identity.md" in markdown
        assert "## Pack Statistics" in markdown

    def test_render_markdown_verbose(
        self,
        assembler: ContextAssembler,
        baseline_pack: BaselinePack,
        retrieval_result: RetrievalResult,
    ) -> None:
        """Should include scores in verbose mode."""
        pack = assembler.assemble(
            query="test query",
            baseline=baseline_pack,
            retrieved=retrieval_result,
            budget=2000,
        )

        markdown = assembler.render_markdown(pack, verbose=True)

        # Verbose should include relevance scores
        assert "relevance" in markdown.lower() or "score" in markdown.lower() or "0." in markdown

    def test_sort_by_scope(self, assembler: ContextAssembler) -> None:
        """Should sort entries by scope order."""
        entries = [
            create_entry("ephemeral/temp.md", "Temp"),
            create_entry("global/style.md", "Style"),
            create_entry("project/auth.md", "Auth"),
            create_entry("agent/behavior.md", "Behavior"),
        ]

        sorted_entries = assembler._sort_by_scope(entries)
        paths = [e.path for e in sorted_entries]

        # Order should be: global, agent, project, ephemeral
        assert paths.index("global/style.md") < paths.index("agent/behavior.md")
        assert paths.index("agent/behavior.md") < paths.index("project/auth.md")
        assert paths.index("project/auth.md") < paths.index("ephemeral/temp.md")

    def test_estimate_tokens(self, assembler: ContextAssembler) -> None:
        """Should estimate token count."""
        count = assembler.estimate_tokens("Hello, world!")
        assert count > 0
        assert count < 10

    def test_calculate_remaining_budget(self, assembler: ContextAssembler) -> None:
        """Should calculate remaining budget correctly."""
        remaining = assembler.calculate_remaining_budget(
            total_budget=2000,
            baseline_tokens=800,
            used_tokens=500,
        )
        assert remaining == 700

    def test_calculate_remaining_budget_overflow(self, assembler: ContextAssembler) -> None:
        """Should return 0 for overflow."""
        remaining = assembler.calculate_remaining_budget(
            total_budget=1000,
            baseline_tokens=800,
            used_tokens=500,
        )
        assert remaining == 0


class TestPackBuilder:
    """Tests for PackBuilder."""

    def test_builder_basic(self) -> None:
        """Should build a pack."""
        builder = PackBuilder(query="test", budget=2000, baseline_budget=800)

        baseline = BaselinePack(
            entries=[create_entry("baseline/id.md", "ID", 200, source="baseline")],
            total_tokens=200,
            generated_at=datetime.now(),
            file_hashes={},
        )

        builder.add_baseline(baseline)
        builder.add_entry(create_entry("project/auth.md", "Auth", 100))

        pack = builder.build()

        assert pack.query == "test"
        assert pack.baseline_tokens == 200
        assert pack.retrieved_tokens == 100
        assert len(pack.baseline_entries) == 1
        assert len(pack.retrieved_entries) == 1

    def test_builder_respects_budget(self) -> None:
        """Should respect budget when adding entries."""
        builder = PackBuilder(query="test", budget=1000, baseline_budget=800)

        # Remaining budget is 200
        added1 = builder.add_entry(create_entry("project/a.md", "A", 100))
        added2 = builder.add_entry(create_entry("project/b.md", "B", 100))
        added3 = builder.add_entry(create_entry("project/c.md", "C", 100))

        assert added1 is True
        assert added2 is True
        assert added3 is False  # Would exceed budget

    def test_builder_remaining_budget(self) -> None:
        """Should track remaining budget."""
        builder = PackBuilder(query="test", budget=1000, baseline_budget=800)

        assert builder.remaining_budget == 200

        builder.add_entry(create_entry("project/a.md", "A", 50))
        assert builder.remaining_budget == 150

    def test_builder_total_tokens(self) -> None:
        """Should track total tokens."""
        builder = PackBuilder(query="test", budget=2000, baseline_budget=800)

        baseline = BaselinePack(
            entries=[create_entry("baseline/id.md", "ID", 300, source="baseline")],
            total_tokens=300,
            generated_at=datetime.now(),
            file_hashes={},
        )

        builder.add_baseline(baseline)
        builder.add_entry(create_entry("project/a.md", "A", 100))

        assert builder.total_tokens == 400

    def test_builder_add_entries(self) -> None:
        """Should add multiple entries."""
        builder = PackBuilder(query="test", budget=2000, baseline_budget=800)

        entries = [
            create_entry("project/a.md", "A", 100),
            create_entry("project/b.md", "B", 100),
            create_entry("project/c.md", "C", 100),
        ]

        added = builder.add_entries(entries)
        assert added == 3

    def test_builder_exclude(self) -> None:
        """Should track excluded paths."""
        builder = PackBuilder(query="test", budget=2000, baseline_budget=800)
        builder.exclude("project/excluded.md")

        pack = builder.build()
        assert "project/excluded.md" in pack.excluded_paths

    def test_builder_chaining(self) -> None:
        """Should support method chaining."""
        baseline = BaselinePack(
            entries=[],
            total_tokens=0,
            generated_at=datetime.now(),
            file_hashes={},
        )

        pack = (
            PackBuilder(query="test", budget=2000)
            .add_baseline(baseline)
            .exclude("project/x.md")
            .build()
        )

        assert pack is not None
        assert "project/x.md" in pack.excluded_paths
