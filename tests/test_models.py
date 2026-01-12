"""Tests for data models."""

from datetime import datetime

import pytest

from dmm.core.constants import Confidence, Scope, Status
from dmm.models.memory import DirectoryInfo, MemoryFile
from dmm.models.pack import BaselinePack, MemoryPack, MemoryPackEntry
from dmm.models.query import (
    HealthResponse,
    QueryRequest,
    QueryResponse,
    QueryStats,
    RetrievalResult,
    SearchFilters,
    StatusResponse,
)


class TestMemoryFile:
    """Tests for MemoryFile model."""

    def test_create_memory_file(self) -> None:
        """Should create memory file with required fields."""
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

        assert memory.id == "mem_001"
        assert memory.path == "project/test.md"
        assert memory.directory == "project"

    def test_directory_extraction(self) -> None:
        """Should extract directory from path."""
        memory = MemoryFile(
            id="mem_001",
            path="project/subdir/test.md",
            title="Test",
            body="Content",
            token_count=100,
            tags=[],
            scope=Scope.PROJECT,
            priority=0.5,
            confidence=Confidence.ACTIVE,
            status=Status.ACTIVE,
        )

        assert memory.directory == "project/subdir"

    def test_is_baseline(self) -> None:
        """Should identify baseline scope."""
        baseline = MemoryFile(
            id="mem_001",
            path="baseline/id.md",
            title="ID",
            body="Content",
            token_count=100,
            tags=[],
            scope=Scope.BASELINE,
            priority=1.0,
            confidence=Confidence.STABLE,
            status=Status.ACTIVE,
        )

        project = MemoryFile(
            id="mem_002",
            path="project/test.md",
            title="Test",
            body="Content",
            token_count=100,
            tags=[],
            scope=Scope.PROJECT,
            priority=0.5,
            confidence=Confidence.ACTIVE,
            status=Status.ACTIVE,
        )

        assert baseline.is_baseline is True
        assert project.is_baseline is False

    def test_is_active(self) -> None:
        """Should identify active status."""
        active = MemoryFile(
            id="mem_001",
            path="project/test.md",
            title="Test",
            body="Content",
            token_count=100,
            tags=[],
            scope=Scope.PROJECT,
            priority=0.5,
            confidence=Confidence.ACTIVE,
            status=Status.ACTIVE,
        )

        deprecated = MemoryFile(
            id="mem_002",
            path="project/old.md",
            title="Old",
            body="Content",
            token_count=100,
            tags=[],
            scope=Scope.PROJECT,
            priority=0.5,
            confidence=Confidence.DEPRECATED,
            status=Status.DEPRECATED,
        )

        assert active.is_active is True
        assert deprecated.is_active is False

    def test_is_expired(self) -> None:
        """Should identify expired memories."""
        from datetime import timedelta

        not_expired = MemoryFile(
            id="mem_001",
            path="ephemeral/test.md",
            title="Test",
            body="Content",
            token_count=100,
            tags=[],
            scope=Scope.EPHEMERAL,
            priority=0.5,
            confidence=Confidence.ACTIVE,
            status=Status.ACTIVE,
            expires=datetime.now() + timedelta(days=7),
        )

        expired = MemoryFile(
            id="mem_002",
            path="ephemeral/old.md",
            title="Old",
            body="Content",
            token_count=100,
            tags=[],
            scope=Scope.EPHEMERAL,
            priority=0.5,
            confidence=Confidence.ACTIVE,
            status=Status.ACTIVE,
            expires=datetime.now() - timedelta(days=1),
        )

        no_expiry = MemoryFile(
            id="mem_003",
            path="project/test.md",
            title="Test",
            body="Content",
            token_count=100,
            tags=[],
            scope=Scope.PROJECT,
            priority=0.5,
            confidence=Confidence.ACTIVE,
            status=Status.ACTIVE,
        )

        assert not_expired.is_expired is False
        assert expired.is_expired is True
        assert no_expiry.is_expired is False

    def test_to_dict(self) -> None:
        """Should convert to dictionary."""
        memory = MemoryFile(
            id="mem_001",
            path="project/test.md",
            title="Test",
            body="Content",
            token_count=100,
            tags=["a", "b"],
            scope=Scope.PROJECT,
            priority=0.5,
            confidence=Confidence.ACTIVE,
            status=Status.ACTIVE,
        )

        data = memory.to_dict()

        assert data["id"] == "mem_001"
        assert data["path"] == "project/test.md"
        assert data["scope"] == "project"
        assert data["tags"] == ["a", "b"]


class TestMemoryPackEntry:
    """Tests for MemoryPackEntry model."""

    def test_to_markdown(self) -> None:
        """Should render to markdown."""
        entry = MemoryPackEntry(
            path="project/test.md",
            title="Test Memory",
            content="This is the content.",
            token_count=50,
            relevance_score=0.85,
            source="retrieved",
        )

        md = entry.to_markdown()

        assert "project/test.md" in md
        assert "This is the content." in md

    def test_to_markdown_with_score(self) -> None:
        """Should include score when requested."""
        entry = MemoryPackEntry(
            path="project/test.md",
            title="Test",
            content="Content",
            token_count=50,
            relevance_score=0.85,
            source="retrieved",
        )

        md = entry.to_markdown(include_score=True)

        assert "0.85" in md or "85" in md


class TestMemoryPack:
    """Tests for MemoryPack model."""

    @pytest.fixture
    def sample_pack(self) -> MemoryPack:
        """Create a sample pack."""
        return MemoryPack(
            generated_at=datetime.now(),
            query="test query",
            baseline_tokens=200,
            retrieved_tokens=300,
            total_tokens=500,
            budget=2000,
            baseline_entries=[
                MemoryPackEntry(
                    path="baseline/id.md",
                    title="Identity",
                    content="Identity content",
                    token_count=200,
                    relevance_score=1.0,
                    source="baseline",
                )
            ],
            retrieved_entries=[
                MemoryPackEntry(
                    path="project/auth.md",
                    title="Auth",
                    content="Auth content",
                    token_count=300,
                    relevance_score=0.9,
                    source="retrieved",
                )
            ],
            included_paths=["baseline/id.md", "project/auth.md"],
            excluded_paths=["project/other.md"],
        )

    def test_remaining_budget(self, sample_pack: MemoryPack) -> None:
        """Should calculate remaining budget."""
        assert sample_pack.remaining_budget == 1500

    def test_baseline_count(self, sample_pack: MemoryPack) -> None:
        """Should count baseline entries."""
        assert sample_pack.baseline_count == 1

    def test_retrieved_count(self, sample_pack: MemoryPack) -> None:
        """Should count retrieved entries."""
        assert sample_pack.retrieved_count == 1

    def test_to_markdown(self, sample_pack: MemoryPack) -> None:
        """Should render to markdown."""
        md = sample_pack.to_markdown()

        assert "# DMM Memory Pack" in md
        assert "## Baseline (Always Included)" in md
        assert "Identity" in md
        assert "Auth" in md
        assert "## Pack Statistics" in md


class TestBaselinePack:
    """Tests for BaselinePack model."""

    def test_is_valid(self) -> None:
        """Should validate against file hashes."""
        pack = BaselinePack(
            entries=[],
            total_tokens=100,
            generated_at=datetime.now(),
            file_hashes={"a.md": "hash1", "b.md": "hash2"},
        )

        assert pack.is_valid({"a.md": "hash1", "b.md": "hash2"}) is True
        assert pack.is_valid({"a.md": "hash1", "b.md": "changed"}) is False
        assert pack.is_valid({"a.md": "hash1"}) is False

    def test_is_empty(self) -> None:
        """Should detect empty pack."""
        empty = BaselinePack(
            entries=[],
            total_tokens=0,
            generated_at=datetime.now(),
            file_hashes={},
        )

        not_empty = BaselinePack(
            entries=[
                MemoryPackEntry(
                    path="test.md",
                    title="Test",
                    content="Content",
                    token_count=100,
                    relevance_score=1.0,
                    source="baseline",
                )
            ],
            total_tokens=100,
            generated_at=datetime.now(),
            file_hashes={},
        )

        assert empty.is_empty is True
        assert not_empty.is_empty is False


class TestSearchFilters:
    """Tests for SearchFilters model."""

    def test_defaults(self) -> None:
        """Should have sensible defaults."""
        filters = SearchFilters()

        assert filters.scopes is None
        assert filters.exclude_deprecated is True
        assert filters.exclude_ephemeral is False
        assert filters.min_priority == 0.0

    def test_custom_values(self) -> None:
        """Should accept custom values."""
        filters = SearchFilters(
            scopes=[Scope.PROJECT, Scope.GLOBAL],
            exclude_deprecated=False,
            min_priority=0.5,
        )

        assert filters.scopes == [Scope.PROJECT, Scope.GLOBAL]
        assert filters.exclude_deprecated is False
        assert filters.min_priority == 0.5


class TestQueryRequest:
    """Tests for QueryRequest model."""

    def test_to_search_filters(self) -> None:
        """Should convert to search filters."""
        request = QueryRequest(
            query="test",
            budget=2000,
            exclude_ephemeral=True,
            include_deprecated=True,
        )

        filters = request.to_search_filters()

        assert filters.exclude_ephemeral is True
        assert filters.exclude_deprecated is False  # include_deprecated=True means don't exclude

    def test_to_dict(self) -> None:
        """Should convert to dictionary."""
        request = QueryRequest(
            query="test query",
            budget=1500,
        )

        data = request.to_dict()

        assert data["query"] == "test query"
        assert data["budget"] == 1500


class TestQueryResponse:
    """Tests for QueryResponse model."""

    def test_to_dict(self) -> None:
        """Should convert to dictionary."""
        pack = MemoryPack(
            generated_at=datetime.now(),
            query="test",
            baseline_tokens=100,
            retrieved_tokens=200,
            total_tokens=300,
            budget=2000,
            baseline_entries=[],
            retrieved_entries=[],
            included_paths=[],
            excluded_paths=[],
        )

        stats = QueryStats(
            query_time_ms=50.0,
            embedding_time_ms=10.0,
            retrieval_time_ms=30.0,
            assembly_time_ms=10.0,
            directories_searched=["project"],
            candidates_considered=5,
            baseline_files=1,
            retrieved_files=2,
            excluded_files=0,
        )

        response = QueryResponse(
            pack=pack,
            pack_markdown="# Pack",
            stats=stats,
            success=True,
        )

        data = response.to_dict()

        assert data["success"] is True
        assert "pack" in data
        assert "stats" in data


class TestDirectoryInfo:
    """Tests for DirectoryInfo model."""

    def test_create(self) -> None:
        """Should create directory info."""
        info = DirectoryInfo(
            path="project/auth",
            file_count=5,
            avg_priority=0.7,
            scopes=["project"],
        )

        assert info.path == "project/auth"
        assert info.file_count == 5
        assert info.avg_priority == 0.7


class TestHealthResponse:
    """Tests for HealthResponse model."""

    def test_to_dict(self) -> None:
        """Should convert to dictionary."""
        response = HealthResponse(
            status="healthy",
            uptime_seconds=3600.0,
            indexed_count=42,
            baseline_tokens=650,
            last_reindex=None,
            watcher_active=True,
            version="1.0.0",
        )

        data = response.to_dict()

        assert data["status"] == "healthy"
        assert data["uptime_seconds"] == 3600.0
        assert data["indexed_count"] == 42


class TestStatusResponse:
    """Tests for StatusResponse model."""

    def test_to_dict(self) -> None:
        """Should convert to dictionary."""
        response = StatusResponse(
            daemon_running=True,
            daemon_pid=12345,
            daemon_version="1.0.0",
            memory_root="/path/to/memory",
            indexed_memories=42,
            baseline_files=3,
            baseline_tokens=650,
            last_reindex=None,
            watcher_active=True,
        )

        data = response.to_dict()

        assert data["daemon_running"] is True
        assert data["daemon_pid"] == 12345
        assert data["indexed_memories"] == 42
