"""Main indexer that orchestrates parsing, embedding, and storage."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from dmm.core.config import DMMConfig
from dmm.core.constants import get_embeddings_db_path, get_memory_root
from dmm.core.exceptions import EmbeddingError, ParseError, StoreError
from dmm.indexer.embedder import MemoryEmbedder
from dmm.indexer.parser import MemoryParser, TokenCounter, ValidationWarning
from dmm.indexer.store import MemoryStore
from dmm.indexer.watcher import ChangeEvent, ChangeType, MemoryWatcher
from dmm.models.memory import MemoryFile


class IndexResult:
    """Result of an indexing operation."""

    def __init__(self) -> None:
        self.indexed: int = 0
        self.deleted: int = 0
        self.skipped: int = 0
        self.errors: list[dict[str, str]] = []
        self.warnings: list[ValidationWarning] = []
        self.start_time: datetime = datetime.now()
        self.end_time: datetime | None = None

    @property
    def duration_ms(self) -> float:
        """Get duration in milliseconds."""
        if self.end_time is None:
            return 0.0
        delta = self.end_time - self.start_time
        return delta.total_seconds() * 1000

    def add_error(self, path: str, error: str) -> None:
        """Add an error to the result."""
        self.errors.append({"path": path, "error": error})

    def finish(self) -> None:
        """Mark indexing as complete."""
        self.end_time = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "indexed": self.indexed,
            "deleted": self.deleted,
            "skipped": self.skipped,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "duration_ms": round(self.duration_ms, 2),
            "error_details": self.errors,
        }


class Indexer:
    """Orchestrates memory file indexing."""

    def __init__(
        self,
        config: DMMConfig,
        base_path: Path | None = None,
    ) -> None:
        """
        Initialize the indexer.

        Args:
            config: DMM configuration
            base_path: Base path for .dmm directory (defaults to cwd)
        """
        self._config = config
        self._base_path = base_path or Path.cwd()

        # Initialize components
        self._token_counter = TokenCounter()
        self._parser = MemoryParser(
            token_counter=self._token_counter,
            min_tokens=config.validation.min_tokens,
            max_tokens=config.validation.max_tokens,
        )
        self._embedder = MemoryEmbedder(
            model_name=config.indexer.embedding_model,
        )
        self._store = MemoryStore(
            db_path=get_embeddings_db_path(self._base_path),
        )

        # Watcher (initialized on start)
        self._watcher: MemoryWatcher | None = None
        self._watcher_task: asyncio.Task[None] | None = None

        # State
        self._initialized = False
        self._last_reindex: datetime | None = None

    @property
    def is_initialized(self) -> bool:
        """Check if indexer is initialized."""
        return self._initialized

    @property
    def is_watching(self) -> bool:
        """Check if file watcher is active."""
        return self._watcher is not None and self._watcher.is_running

    @property
    def last_reindex(self) -> datetime | None:
        """Get timestamp of last full reindex."""
        return self._last_reindex

    @property
    def store(self) -> MemoryStore:
        """Get the memory store."""
        return self._store

    @property
    def embedder(self) -> MemoryEmbedder:
        """Get the embedder."""
        return self._embedder

    async def initialize(self) -> None:
        """Initialize the indexer and database."""
        if self._initialized:
            return

        # Ensure directories exist
        memory_root = get_memory_root(self._base_path)
        memory_root.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._store.initialize()

        self._initialized = True

    async def start(self, watch: bool = True) -> IndexResult:
        """
        Start the indexer.

        Args:
            watch: Whether to start file watcher

        Returns:
            Result of initial indexing
        """
        await self.initialize()

        # Perform initial full index
        result = await self.reindex_all()

        # Start file watcher if requested
        if watch:
            await self._start_watcher()

        return result

    async def stop(self) -> None:
        """Stop the indexer and cleanup."""
        if self._watcher:
            await self._watcher.stop()
            self._watcher = None

        self._store.close()
        self._embedder.unload_model()
        self._initialized = False

    async def reindex_all(self) -> IndexResult:
        """Perform a full reindex of all memory files."""
        result = IndexResult()
        memory_root = get_memory_root(self._base_path)

        if not memory_root.exists():
            result.finish()
            return result

        # Collect all memory files
        memory_files: list[Path] = []
        for md_file in memory_root.rglob("*.md"):
            # Skip deprecated
            path_str = str(md_file)
            if "/deprecated/" in path_str or "\\deprecated\\" in path_str:
                continue
            memory_files.append(md_file)

        # Parse all files first
        parsed_memories: list[tuple[MemoryFile, str]] = []
        for file_path in memory_files:
            parse_result = self._parser.parse(file_path)

            if parse_result.error:
                result.add_error(str(file_path), str(parse_result.error))
                continue

            if parse_result.memory:
                file_hash = self._parser.compute_file_hash(file_path)
                parsed_memories.append((parse_result.memory, file_hash))
                result.warnings.extend(parse_result.warnings)

        # Batch embed for efficiency
        if parsed_memories:
            try:
                memories = [m for m, _ in parsed_memories]
                embeddings = self._embedder.embed_batch(memories)

                # Store each memory
                for (memory, file_hash), embedding in zip(parsed_memories, embeddings):
                    try:
                        self._store.upsert_memory(
                            memory=memory,
                            composite_embedding=embedding.composite_embedding,
                            directory_embedding=embedding.directory_embedding,
                            file_hash=file_hash,
                        )
                        result.indexed += 1
                    except StoreError as e:
                        result.add_error(memory.path, str(e))

            except EmbeddingError as e:
                result.add_error("batch_embedding", str(e))

        # Update metadata
        self._last_reindex = datetime.now()
        self._store.set_system_meta(
            "last_full_reindex",
            self._last_reindex.isoformat(),
        )

        result.finish()
        return result

    async def index_file(self, path: Path) -> tuple[bool, str | None]:
        """
        Index a single memory file.

        Returns:
            Tuple of (success, error_message)
        """
        # Check if file needs reindexing
        relative_path = self._get_relative_path(path)
        current_hash = self._parser.compute_file_hash(path)
        stored_hash = self._store.get_file_hash(relative_path)

        if stored_hash == current_hash:
            # File unchanged, skip
            return True, None

        # Parse file
        parse_result = self._parser.parse(path)

        if parse_result.error:
            return False, str(parse_result.error)

        if not parse_result.memory:
            return False, "Failed to parse memory file"

        # Generate embedding
        try:
            embedding = self._embedder.embed_memory(parse_result.memory)
        except EmbeddingError as e:
            return False, str(e)

        # Store
        try:
            self._store.upsert_memory(
                memory=parse_result.memory,
                composite_embedding=embedding.composite_embedding,
                directory_embedding=embedding.directory_embedding,
                file_hash=current_hash,
            )
        except StoreError as e:
            return False, str(e)

        return True, None

    async def delete_file(self, path: Path) -> bool:
        """
        Remove a memory file from the index.

        Returns:
            True if deleted, False if not found
        """
        relative_path = self._get_relative_path(path)
        return self._store.delete_memory_by_path(relative_path)

    async def _start_watcher(self) -> None:
        """Start the file watcher."""
        memory_root = get_memory_root(self._base_path)

        self._watcher = MemoryWatcher(
            memory_root=memory_root,
            on_change=self._handle_change,
            debounce_ms=self._config.indexer.debounce_ms,
        )

        await self._watcher.start()

    async def _handle_change(self, event: ChangeEvent) -> None:
        """Handle a file change event from the watcher."""
        if not event.is_memory_file:
            return

        if event.type == ChangeType.DELETED:
            await self.delete_file(event.path)
        else:
            # Created or modified
            if event.path.exists():
                await self.index_file(event.path)

    def _get_relative_path(self, path: Path) -> str:
        """Get path relative to memory root."""
        memory_root = get_memory_root(self._base_path)
        try:
            return str(path.relative_to(memory_root))
        except ValueError:
            # Path is not relative to memory root
            return path.name

    def get_stats(self) -> dict[str, Any]:
        """Get indexer statistics."""
        return {
            "initialized": self._initialized,
            "watching": self.is_watching,
            "memory_count": self._store.get_memory_count() if self._initialized else 0,
            "last_reindex": self._last_reindex.isoformat() if self._last_reindex else None,
            "embedder": self._embedder.get_model_info(),
            "watcher": self._watcher.get_stats() if self._watcher else None,
        }
