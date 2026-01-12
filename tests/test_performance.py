"""Performance benchmark tests for DMM."""

import asyncio
import tempfile
import time
from pathlib import Path

import pytest

from dmm.core.config import DMMConfig
from dmm.core.constants import Confidence, Scope, Status
from dmm.indexer.embedder import MemoryEmbedder
from dmm.indexer.indexer import Indexer
from dmm.indexer.parser import MemoryParser, TokenCounter
from dmm.indexer.store import MemoryStore
from dmm.models.memory import MemoryFile
from dmm.retrieval.baseline import BaselineManager
from dmm.retrieval.router import RetrievalConfig, RetrievalRouter


def create_memory_content(memory_id: str, title: str, tags: list[str]) -> str:
    """Create memory file content."""
    tags_str = ", ".join(tags)
    padding = "Additional context for testing. " * 20
    return f"""---
id: {memory_id}
tags: [{tags_str}]
scope: project
priority: 0.5
confidence: active
status: active
created: 2025-01-15
---

# {title}

This is test content for {title}. {padding}
"""


def create_test_embedding(dimension: int = 384, seed: float = 0.5) -> list[float]:
    """Create a test embedding vector."""
    import math
    return [math.sin(i * seed) for i in range(dimension)]


class TestPerformanceBenchmarks:
    """Performance benchmark tests."""

    @pytest.fixture
    def temp_dmm(self, tmp_path: Path):
        """Create a temporary DMM structure."""
        dmm = tmp_path / ".dmm"
        (dmm / "index").mkdir(parents=True)
        (dmm / "memory" / "baseline").mkdir(parents=True)
        (dmm / "memory" / "project").mkdir(parents=True)
        (dmm / "memory" / "global").mkdir(parents=True)
        (dmm / "packs").mkdir(parents=True)
        return dmm

    def test_parser_performance(self, temp_dmm: Path) -> None:
        """Parser should process a file in < 50ms."""
        memory_root = temp_dmm / "memory"
        
        # Create test file
        content = create_memory_content("mem_001", "Test Memory", ["test", "benchmark"])
        test_file = memory_root / "project" / "test.md"
        test_file.write_text(content)

        parser = MemoryParser(TokenCounter())

        # Warm up
        parser.parse(test_file)

        # Benchmark
        iterations = 10
        start = time.perf_counter()
        for _ in range(iterations):
            parser.parse(test_file)
        elapsed = (time.perf_counter() - start) / iterations * 1000

        print(f"\nParser: {elapsed:.2f}ms per file")
        assert elapsed < 50, f"Parser too slow: {elapsed:.2f}ms (target: <50ms)"

    def test_embedding_performance(self) -> None:
        """Embedding generation should complete in < 100ms per memory."""
        embedder = MemoryEmbedder(device="cpu")

        memory = MemoryFile(
            id="mem_001",
            path="project/test.md",
            title="Test Memory",
            body="This is test content for benchmarking embedding performance.",
            token_count=100,
            tags=["test", "benchmark"],
            scope=Scope.PROJECT,
            priority=0.5,
            confidence=Confidence.ACTIVE,
            status=Status.ACTIVE,
        )

        # Warm up (model loading)
        embedder.embed_memory(memory)

        # Benchmark
        iterations = 5
        start = time.perf_counter()
        for _ in range(iterations):
            embedder.embed_memory(memory)
        elapsed = (time.perf_counter() - start) / iterations * 1000

        print(f"\nEmbedding: {elapsed:.2f}ms per memory")
        assert elapsed < 100, f"Embedding too slow: {elapsed:.2f}ms (target: <100ms)"

    def test_store_upsert_performance(self, temp_dmm: Path) -> None:
        """Store upsert should complete in < 10ms."""
        db_path = temp_dmm / "index" / "embeddings.db"
        store = MemoryStore(db_path)
        store.initialize()

        memory = MemoryFile(
            id="mem_001",
            path="project/test.md",
            title="Test Memory",
            body="Test content",
            token_count=100,
            tags=["test"],
            scope=Scope.PROJECT,
            priority=0.5,
            confidence=Confidence.ACTIVE,
            status=Status.ACTIVE,
        )
        embedding = create_test_embedding()

        # Warm up
        store.upsert_memory(memory, embedding, embedding, "hash1")

        # Benchmark
        iterations = 20
        start = time.perf_counter()
        for i in range(iterations):
            memory_copy = MemoryFile(
                id=f"mem_{i:03d}",
                path=f"project/test_{i}.md",
                title=f"Test Memory {i}",
                body="Test content",
                token_count=100,
                tags=["test"],
                scope=Scope.PROJECT,
                priority=0.5,
                confidence=Confidence.ACTIVE,
                status=Status.ACTIVE,
            )
            store.upsert_memory(memory_copy, embedding, embedding, f"hash_{i}")
        elapsed = (time.perf_counter() - start) / iterations * 1000

        store.close()

        print(f"\nStore upsert: {elapsed:.2f}ms per operation")
        assert elapsed < 10, f"Store upsert too slow: {elapsed:.2f}ms (target: <10ms)"

    def test_store_search_performance(self, temp_dmm: Path) -> None:
        """Store search should complete in < 50ms for 100 memories."""
        db_path = temp_dmm / "index" / "embeddings.db"
        store = MemoryStore(db_path)
        store.initialize()

        # Populate with 100 memories
        for i in range(100):
            memory = MemoryFile(
                id=f"mem_{i:03d}",
                path=f"project/test_{i}.md",
                title=f"Test Memory {i}",
                body=f"Test content for memory {i}",
                token_count=100,
                tags=["test", f"tag_{i % 10}"],
                scope=Scope.PROJECT,
                priority=0.5 + (i % 5) * 0.1,
                confidence=Confidence.ACTIVE,
                status=Status.ACTIVE,
            )
            embedding = create_test_embedding(seed=i * 0.01)
            store.upsert_memory(memory, embedding, embedding, f"hash_{i}")

        query_embedding = create_test_embedding(seed=0.5)

        from dmm.models.query import SearchFilters
        filters = SearchFilters()

        # Benchmark
        iterations = 10
        start = time.perf_counter()
        for _ in range(iterations):
            store.search_by_content(query_embedding, None, filters, limit=20)
        elapsed = (time.perf_counter() - start) / iterations * 1000

        store.close()

        print(f"\nStore search (100 memories): {elapsed:.2f}ms")
        assert elapsed < 50, f"Store search too slow: {elapsed:.2f}ms (target: <50ms)"

    @pytest.mark.asyncio
    async def test_full_query_performance(self, temp_dmm: Path) -> None:
        """Full query pipeline should complete in < 200ms."""
        memory_root = temp_dmm / "memory"

        # Create test memories
        for i in range(20):
            scope = "baseline" if i < 2 else "project"
            content = create_memory_content(
                f"mem_{i:03d}",
                f"Memory {i}",
                ["test", f"tag_{i % 5}"]
            )
            content = content.replace("scope: project", f"scope: {scope}")
            if scope == "baseline":
                content = content.replace("priority: 0.5", "priority: 1.0")
            
            file_path = memory_root / scope / f"mem_{i}.md"
            file_path.write_text(content)

        # Initialize components
        config = DMMConfig()
        indexer = Indexer(config=config, base_path=temp_dmm.parent)
        await indexer.start(watch=False)

        baseline_manager = BaselineManager(
            store=indexer.store,
            base_path=temp_dmm.parent,
        )
        router = RetrievalRouter(
            store=indexer.store,
            embedder=indexer.embedder,
            config=RetrievalConfig(),
        )

        # Warm up
        baseline_manager.get_baseline_pack()
        router.retrieve("test query", budget=1000)

        # Benchmark
        iterations = 5
        start = time.perf_counter()
        for _ in range(iterations):
            baseline = baseline_manager.get_baseline_pack()
            result = router.retrieve("find relevant information", budget=1000)
        elapsed = (time.perf_counter() - start) / iterations * 1000

        await indexer.stop()

        print(f"\nFull query pipeline: {elapsed:.2f}ms")
        assert elapsed < 200, f"Query too slow: {elapsed:.2f}ms (target: <200ms)"

    @pytest.mark.asyncio
    async def test_indexing_performance(self, temp_dmm: Path) -> None:
        """Indexing a single file should complete in < 500ms."""
        memory_root = temp_dmm / "memory"

        # Create test file
        content = create_memory_content("mem_001", "Test Memory", ["test"])
        test_file = memory_root / "project" / "test.md"
        test_file.write_text(content)

        config = DMMConfig()
        indexer = Indexer(config=config, base_path=temp_dmm.parent)
        await indexer.initialize()

        # Warm up (loads model)
        await indexer.index_file(test_file)

        # Create new file
        content2 = create_memory_content("mem_002", "Test Memory 2", ["test2"])
        test_file2 = memory_root / "project" / "test2.md"
        test_file2.write_text(content2)

        # Benchmark
        iterations = 3
        start = time.perf_counter()
        for i in range(iterations):
            content_i = create_memory_content(f"mem_{i+10}", f"Memory {i+10}", ["bench"])
            file_i = memory_root / "project" / f"bench_{i}.md"
            file_i.write_text(content_i)
            await indexer.index_file(file_i)
        elapsed = (time.perf_counter() - start) / iterations * 1000

        await indexer.stop()

        print(f"\nSingle file indexing: {elapsed:.2f}ms")
        assert elapsed < 500, f"Indexing too slow: {elapsed:.2f}ms (target: <500ms)"
