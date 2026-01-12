"""Integration tests for the complete DMM system."""

import asyncio
from datetime import datetime
from pathlib import Path

import pytest

from dmm.core.config import DMMConfig
from dmm.core.constants import Confidence, Scope, Status
from dmm.indexer.indexer import Indexer
from dmm.models.memory import MemoryFile
from dmm.retrieval.assembler import ContextAssembler
from dmm.retrieval.baseline import BaselineManager
from dmm.retrieval.router import RetrievalConfig, RetrievalRouter


def create_memory_file(
    memory_root: Path,
    scope: str,
    filename: str,
    memory_id: str,
    title: str,
    content: str,
    tags: list[str] | None = None,
    priority: float = 0.5,
) -> Path:
    """Create a memory file on disk."""
    tags = tags or ["test"]
    tags_str = ", ".join(tags)

    # Pad content to meet minimum token requirements
    padded_content = content + "\n\n" + ("Additional context. " * 50)

    file_content = f"""---
id: {memory_id}
tags: [{tags_str}]
scope: {scope}
priority: {priority}
confidence: active
status: active
created: 2025-01-15
---

# {title}

{padded_content}
"""
    file_path = memory_root / scope / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(file_content)
    return file_path


class TestFullPipeline:
    """Integration tests for the complete retrieval pipeline."""

    @pytest.fixture
    def populated_memory(self, memory_root: Path) -> Path:
        """Create a populated memory directory."""
        # Create baseline memories
        create_memory_file(
            memory_root, "baseline", "identity.md",
            "mem_base_001", "Agent Identity",
            "You are a test agent for the DMM system.",
            tags=["identity", "core"],
            priority=1.0,
        )
        create_memory_file(
            memory_root, "baseline", "hard_constraints.md",
            "mem_base_002", "Hard Constraints",
            "Never delete production data without backup.",
            tags=["constraints", "safety"],
            priority=1.0,
        )

        # Create project memories
        create_memory_file(
            memory_root, "project", "architecture.md",
            "mem_proj_001", "System Architecture",
            "The system uses a microservices architecture with event sourcing.",
            tags=["architecture", "design"],
            priority=0.8,
        )
        create_memory_file(
            memory_root, "project", "api_conventions.md",
            "mem_proj_002", "API Conventions",
            "All APIs must use REST with JSON payloads and proper error codes.",
            tags=["api", "conventions"],
            priority=0.7,
        )

        # Create global memories
        create_memory_file(
            memory_root, "global", "coding_style.md",
            "mem_glob_001", "Coding Style",
            "Use consistent naming conventions and document all public APIs.",
            tags=["style", "documentation"],
            priority=0.6,
        )

        return memory_root

    @pytest.mark.asyncio
    async def test_full_indexing_pipeline(
        self, dmm_root: Path, populated_memory: Path
    ) -> None:
        """Test indexing all memory files."""
        config = DMMConfig()
        indexer = Indexer(config=config, base_path=dmm_root.parent)

        result = await indexer.start(watch=False)

        assert result.indexed == 5
        assert len(result.errors) == 0
        assert indexer.store.get_memory_count() == 5

        await indexer.stop()

    @pytest.mark.asyncio
    async def test_baseline_always_included(
        self, dmm_root: Path, populated_memory: Path
    ) -> None:
        """Test that baseline is always included in retrieval."""
        config = DMMConfig()
        indexer = Indexer(config=config, base_path=dmm_root.parent)
        await indexer.start(watch=False)

        baseline_manager = BaselineManager(
            store=indexer.store,
            base_path=dmm_root.parent,
        )
        router = RetrievalRouter(
            store=indexer.store,
            embedder=indexer.embedder,
            config=RetrievalConfig(),
        )
        assembler = ContextAssembler()

        # Query for something unrelated to baseline
        baseline_pack = baseline_manager.get_baseline_pack()
        retrieval_result = router.retrieve(
            query="API design patterns",
            budget=1000,
        )
        pack = assembler.assemble(
            query="API design patterns",
            baseline=baseline_pack,
            retrieved=retrieval_result,
            budget=2000,
        )

        # Baseline should be included
        assert len(pack.baseline_entries) == 2
        baseline_paths = [e.path for e in pack.baseline_entries]
        assert "baseline/identity.md" in baseline_paths
        assert "baseline/hard_constraints.md" in baseline_paths

        await indexer.stop()

    @pytest.mark.asyncio
    async def test_relevant_memories_retrieved(
        self, dmm_root: Path, populated_memory: Path
    ) -> None:
        """Test that semantically relevant memories are retrieved."""
        config = DMMConfig()
        indexer = Indexer(config=config, base_path=dmm_root.parent)
        await indexer.start(watch=False)

        baseline_manager = BaselineManager(
            store=indexer.store,
            base_path=dmm_root.parent,
        )
        router = RetrievalRouter(
            store=indexer.store,
            embedder=indexer.embedder,
            config=RetrievalConfig(),
        )

        # Query for API-related content
        baseline_pack = baseline_manager.get_baseline_pack()
        retrieval_result = router.retrieve(
            query="How should I design REST APIs?",
            budget=2000,
        )

        # Should retrieve API-related memories
        retrieved_paths = [e.path for e in retrieval_result.entries]
        assert len(retrieved_paths) > 0

        await indexer.stop()

    @pytest.mark.asyncio
    async def test_token_budget_respected(
        self, dmm_root: Path, populated_memory: Path
    ) -> None:
        """Test that token budget is respected."""
        config = DMMConfig()
        indexer = Indexer(config=config, base_path=dmm_root.parent)
        await indexer.start(watch=False)

        baseline_manager = BaselineManager(
            store=indexer.store,
            base_path=dmm_root.parent,
        )
        router = RetrievalRouter(
            store=indexer.store,
            embedder=indexer.embedder,
            config=RetrievalConfig(),
        )
        assembler = ContextAssembler()

        baseline_pack = baseline_manager.get_baseline_pack()
        retrieval_result = router.retrieve(
            query="system design",
            budget=500,  # Small budget
        )
        pack = assembler.assemble(
            query="system design",
            baseline=baseline_pack,
            retrieved=retrieval_result,
            budget=baseline_pack.total_tokens + 500,
        )

        # Total should not exceed budget
        assert pack.total_tokens <= pack.budget

        await indexer.stop()

    @pytest.mark.asyncio
    async def test_memory_pack_markdown_output(
        self, dmm_root: Path, populated_memory: Path
    ) -> None:
        """Test that memory pack renders to valid markdown."""
        config = DMMConfig()
        indexer = Indexer(config=config, base_path=dmm_root.parent)
        await indexer.start(watch=False)

        baseline_manager = BaselineManager(
            store=indexer.store,
            base_path=dmm_root.parent,
        )
        router = RetrievalRouter(
            store=indexer.store,
            embedder=indexer.embedder,
            config=RetrievalConfig(),
        )
        assembler = ContextAssembler()

        baseline_pack = baseline_manager.get_baseline_pack()
        retrieval_result = router.retrieve(
            query="architecture design",
            budget=1500,
        )
        pack = assembler.assemble(
            query="architecture design",
            baseline=baseline_pack,
            retrieved=retrieval_result,
            budget=2000,
        )

        markdown = assembler.render_markdown(pack)

        # Check markdown structure
        assert "# DMM Memory Pack" in markdown
        assert "## Baseline (Always Included)" in markdown
        assert "## Pack Statistics" in markdown
        assert "baseline/identity.md" in markdown

        await indexer.stop()

    @pytest.mark.asyncio
    async def test_incremental_indexing(
        self, dmm_root: Path, populated_memory: Path
    ) -> None:
        """Test that new files are indexed correctly."""
        config = DMMConfig()
        indexer = Indexer(config=config, base_path=dmm_root.parent)
        await indexer.start(watch=False)

        initial_count = indexer.store.get_memory_count()

        # Add new memory file
        create_memory_file(
            populated_memory, "project", "new_feature.md",
            "mem_proj_new", "New Feature",
            "This is a new feature added after initial indexing.",
            tags=["feature", "new"],
        )

        # Reindex
        await indexer.reindex_all()

        new_count = indexer.store.get_memory_count()
        assert new_count == initial_count + 1

        await indexer.stop()
