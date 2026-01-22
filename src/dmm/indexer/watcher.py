"""File system watcher for memory directory changes."""

import asyncio
import threading
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Awaitable, Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers.polling import PollingObserver as Observer
import logging

logger = logging.getLogger(__name__)

from dmm.core.constants import MEMORY_FILE_EXTENSION
from dmm.core.exceptions import WatcherError

class ChangeType(str, Enum):
    """Type of file system change."""

    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"

@dataclass
class ChangeEvent:
    """Represents a file system change event."""

    type: ChangeType
    path: Path
    timestamp: datetime

    @property
    def is_memory_file(self) -> bool:
        """Check if this is a memory markdown file."""
        return self.path.suffix == MEMORY_FILE_EXTENSION

class DebouncedHandler(FileSystemEventHandler):
    """File system event handler with debouncing."""

    def __init__(
        self,
        callback: Callable[[ChangeEvent], None],
        debounce_ms: int = 100,
        ignore_patterns: list[str] | None = None,
    ) -> None:
        """
        Initialize handler.

        Args:
            callback: Sync callback for debounced events
            debounce_ms: Debounce window in milliseconds
            ignore_patterns: Glob patterns to ignore
        """
        super().__init__()
        self._callback = callback
        self._debounce_seconds = debounce_ms / 1000.0
        self._ignore_patterns = ignore_patterns or []
        self._pending: dict[str, tuple[ChangeEvent, threading.Timer]] = {}
        self._lock = threading.Lock()

    def _should_ignore(self, path: Path) -> bool:
        """Check if path should be ignored."""
        path_str = str(path)

        # Ignore non-markdown files
        if path.suffix != MEMORY_FILE_EXTENSION:
            return True

        # Ignore deprecated directory by default
        if "/deprecated/" in path_str or "\\deprecated\\" in path_str:
            return True

        # Check ignore patterns
        for pattern in self._ignore_patterns:
            if path.match(pattern):
                return True

        return False

    def _handle_event(self, event: FileSystemEvent, change_type: ChangeType) -> None:
        """Handle a file system event with debouncing."""
        if event.is_directory:
            return

        path = Path(event.src_path)

        if self._should_ignore(path):
            return

        change = ChangeEvent(
            type=change_type,
            path=path,
            timestamp=datetime.now(),
        )

        with self._lock:
            path_key = str(path)

            # Cancel any pending timer for this path
            if path_key in self._pending:
                _, timer = self._pending[path_key]
                timer.cancel()

            # Create new debounced callback
            def fire_callback() -> None:
                with self._lock:
                    if path_key in self._pending:
                        event_to_fire, _ = self._pending.pop(path_key)
                        self._callback(event_to_fire)

            timer = threading.Timer(self._debounce_seconds, fire_callback)
            self._pending[path_key] = (change, timer)
            timer.start()

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation."""
        self._handle_event(event, ChangeType.CREATED)

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification."""
        self._handle_event(event, ChangeType.MODIFIED)

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file deletion."""
        self._handle_event(event, ChangeType.DELETED)

    def cancel_pending(self) -> None:
        """Cancel all pending debounced events."""
        with self._lock:
            for _, timer in self._pending.values():
                timer.cancel()
            self._pending.clear()

class MemoryWatcher:
    """Watches memory directory for file changes."""

    def __init__(
        self,
        memory_root: Path,
        on_change: Callable[[ChangeEvent], Awaitable[None]],
        debounce_ms: int = 100,
        ignore_patterns: list[str] | None = None,
    ) -> None:
        """
        Initialize the file watcher.

        Args:
            memory_root: Path to .dmm/memory/
            on_change: Async callback for file changes
            debounce_ms: Debounce window for rapid changes
            ignore_patterns: Glob patterns to ignore
        """
        self._memory_root = memory_root
        self._on_change = on_change
        self._debounce_ms = debounce_ms
        self._ignore_patterns = ignore_patterns or []

        self._observer: Observer | None = None
        self._handler: DebouncedHandler | None = None
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def is_running(self) -> bool:
        """Check if watcher is running."""
        return self._running

    @property
    def memory_root(self) -> Path:
        """Get the watched memory root path."""
        return self._memory_root

    def _sync_callback(self, event: ChangeEvent) -> None:
        """Sync callback that schedules async callback."""
        if self._loop is not None and self._running:
            future = asyncio.run_coroutine_threadsafe(
                self._on_change(event),
                self._loop,
            )
        else:
            pass  # Loop not available or not running

    async def start(self) -> None:
        """Start watching for changes."""
        if self._running:
            return

        if not self._memory_root.exists():
            raise WatcherError(
                f"Memory root does not exist: {self._memory_root}",
                details={"path": str(self._memory_root)},
            )

        self._loop = asyncio.get_running_loop()

        self._handler = DebouncedHandler(
            callback=self._sync_callback,
            debounce_ms=self._debounce_ms,
            ignore_patterns=self._ignore_patterns,
        )

        self._observer = Observer(timeout=1.0)  # Poll every 1 second
        self._observer.schedule(
            self._handler,
            str(self._memory_root),
            recursive=True,
        )

        try:
            self._observer.start()
            self._running = True

        except Exception as e:
            raise WatcherError(
                f"Failed to start file watcher: {e}",
                details={"path": str(self._memory_root)},
            ) from e

    async def stop(self) -> None:
        """Stop watching and cleanup."""
        if not self._running:
            return

        self._running = False

        if self._handler:
            self._handler.cancel_pending()
            self._handler = None

        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None

        self._loop = None

    async def scan_existing(self) -> list[ChangeEvent]:
        """
        Scan for existing memory files.

        Returns list of ChangeEvents for all existing files.
        Used for initial indexing on startup.
        """
        events: list[ChangeEvent] = []

        if not self._memory_root.exists():
            return events

        for md_file in self._memory_root.rglob(f"*{MEMORY_FILE_EXTENSION}"):
            # Skip deprecated directory
            if "/deprecated/" in str(md_file) or "\\deprecated\\" in str(md_file):
                continue

            events.append(
                ChangeEvent(
                    type=ChangeType.CREATED,
                    path=md_file,
                    timestamp=datetime.now(),
                )
            )

        return events

    def get_stats(self) -> dict[str, int | bool | str]:
        """Get watcher statistics."""
        pending_count = 0
        if self._handler:
            with self._handler._lock:
                pending_count = len(self._handler._pending)

        return {
            "running": self._running,
            "memory_root": str(self._memory_root),
            "debounce_ms": self._debounce_ms,
            "pending_events": pending_count,
        }
