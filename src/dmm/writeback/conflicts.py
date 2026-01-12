"""Conflicts database schema preparation for Phase 3.

This module creates the conflicts database schema that Phase 3 will populate.
Phase 2 creates the schema but does not populate it.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from dmm.core.constants import get_dmm_root


CONFLICTS_DB_NAME = "conflicts.db"


def get_conflicts_db_path(base_path: Path | None = None) -> Path:
    """Get the path to the conflicts database.
    
    Args:
        base_path: Base path for the DMM directory. Defaults to cwd.
        
    Returns:
        Path to the conflicts database.
    """
    dmm_root = get_dmm_root(base_path)
    return dmm_root / "index" / CONFLICTS_DB_NAME


CONFLICTS_SCHEMA_SQL = """
-- Conflicts table (Phase 3 will populate)
CREATE TABLE IF NOT EXISTS conflicts (
    conflict_id TEXT PRIMARY KEY,
    detected_at TEXT NOT NULL,
    
    -- Involved memories (JSON array of {id, path, summary})
    memories_json TEXT NOT NULL,
    
    -- Conflict details
    type TEXT NOT NULL CHECK (type IN ('contradictory', 'duplicate', 'supersession', 'ambiguous')),
    confidence REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    description TEXT NOT NULL,
    
    -- Status
    status TEXT NOT NULL DEFAULT 'unresolved'
        CHECK (status IN ('unresolved', 'in_progress', 'resolved', 'dismissed')),
    
    -- Resolution
    resolved_at TEXT,
    resolution_action TEXT CHECK (resolution_action IN ('deprecate', 'merge', 'clarify', 'dismiss', 'split')),
    resolution_target TEXT,                    -- Memory ID affected
    resolution_reason TEXT,
    resolved_by TEXT                           -- 'agent', 'human', 'system'
);

CREATE INDEX IF NOT EXISTS idx_conflicts_status ON conflicts(status);
CREATE INDEX IF NOT EXISTS idx_conflicts_detected ON conflicts(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_conflicts_type ON conflicts(type);

-- Conflict-memory mapping (for queries)
CREATE TABLE IF NOT EXISTS conflict_memories (
    conflict_id TEXT NOT NULL REFERENCES conflicts(conflict_id) ON DELETE CASCADE,
    memory_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('primary', 'secondary', 'related')),
    PRIMARY KEY (conflict_id, memory_id)
);

CREATE INDEX IF NOT EXISTS idx_conflict_memories_memory ON conflict_memories(memory_id);

-- Conflict detection metadata
CREATE TABLE IF NOT EXISTS conflict_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

INIT_CONFLICT_META_SQL = """
INSERT OR IGNORE INTO conflict_meta (key, value, updated_at) VALUES
    ('schema_version', '1', datetime('now')),
    ('total_conflicts', '0', datetime('now')),
    ('last_scan', '', datetime('now'));
"""


class ConflictsDB:
    """Database for conflict tracking (Phase 3 preparation).
    
    Phase 2 creates the schema. Phase 3 will add:
    - ConflictDetector: Scans for conflicts
    - ConflictResolver: Resolves conflicts
    - Integration with ReviewerAgent
    """

    def __init__(self, base_path: Path | None = None) -> None:
        """Initialize the conflicts database.
        
        Args:
            base_path: Base path for the DMM directory.
        """
        self._db_path = get_conflicts_db_path(base_path)
        self._connection: sqlite3.Connection | None = None

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection."""
        if self._connection is None:
            self._connection = self._create_connection()
        yield self._connection

    def _create_connection(self) -> sqlite3.Connection:
        """Create and configure a database connection."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        
        return conn

    def initialize(self) -> None:
        """Create tables if they don't exist."""
        with self._get_connection() as conn:
            conn.executescript(CONFLICTS_SCHEMA_SQL)
            conn.executescript(INIT_CONFLICT_META_SQL)
            conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def get_stats(self) -> dict[str, int]:
        """Get conflict statistics.
        
        Returns:
            Dictionary with conflict counts by status.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT status, COUNT(*) as count
                FROM conflicts
                GROUP BY status
                """
            )
            
            stats = {
                "unresolved": 0,
                "in_progress": 0,
                "resolved": 0,
                "dismissed": 0,
                "total": 0,
            }
            
            for row in cursor.fetchall():
                stats[row["status"]] = row["count"]
                stats["total"] += row["count"]
            
            return stats

    # Phase 3 will add:
    # - add_conflict(memories, type, confidence, description)
    # - get_conflict(conflict_id)
    # - get_unresolved(limit)
    # - get_conflicts_for_memory(memory_id)
    # - resolve_conflict(conflict_id, action, target, reason, resolved_by)
    # - dismiss_conflict(conflict_id, reason)
    # - scan_for_conflicts(memory_id)  # Called after commits


def initialize_conflicts_db(base_path: Path | None = None) -> None:
    """Initialize the conflicts database schema.
    
    This should be called during dmm init to prepare for Phase 3.
    
    Args:
        base_path: Base path for the DMM directory.
    """
    db = ConflictsDB(base_path)
    db.initialize()
    db.close()
