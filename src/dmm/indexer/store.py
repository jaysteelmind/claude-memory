"""SQLite-VSS storage layer for memory embeddings."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator

import numpy as np

from dmm.core.constants import EMBEDDING_DIMENSION
from dmm.core.exceptions import StoreError
from dmm.models.memory import DirectoryInfo, IndexedMemory, MemoryFile
from dmm.models.query import SearchFilters

# SQL Schema
SCHEMA_SQL = """
-- Main memories table
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    directory TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    
    -- Metadata
    scope TEXT NOT NULL CHECK (scope IN ('baseline', 'global', 'agent', 'project', 'ephemeral')),
    priority REAL NOT NULL CHECK (priority >= 0.0 AND priority <= 1.0),
    confidence TEXT NOT NULL CHECK (confidence IN ('experimental', 'active', 'stable', 'deprecated')),
    status TEXT NOT NULL CHECK (status IN ('active', 'deprecated')),
    tags_json TEXT NOT NULL DEFAULT '[]',
    token_count INTEGER NOT NULL,
    
    -- Lifecycle (Phase 2 will populate)
    created_at TEXT,
    last_used_at TEXT,
    usage_count INTEGER DEFAULT 0,
    expires_at TEXT,
    
    -- Relations
    supersedes_json TEXT DEFAULT '[]',
    related_json TEXT DEFAULT '[]',
    
    -- Indexing
    file_hash TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    
    -- Embeddings stored as BLOBs
    composite_embedding BLOB NOT NULL,
    directory_embedding BLOB NOT NULL,
    
    -- Indexes
    CONSTRAINT valid_token_count CHECK (token_count >= 0 AND token_count <= 2000)
);

CREATE INDEX IF NOT EXISTS idx_memories_directory ON memories(directory);
CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope);
CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status);
CREATE INDEX IF NOT EXISTS idx_memories_priority ON memories(priority DESC);
CREATE INDEX IF NOT EXISTS idx_memories_confidence ON memories(confidence);

-- Directory summaries (for stage-1 routing)
CREATE TABLE IF NOT EXISTS directories (
    path TEXT PRIMARY KEY,
    description TEXT,
    file_count INTEGER DEFAULT 0,
    avg_priority REAL DEFAULT 0.5,
    scopes_json TEXT DEFAULT '[]',
    last_updated TEXT NOT NULL
);

-- System metadata
CREATE TABLE IF NOT EXISTS system_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

INIT_METADATA_SQL = """
INSERT OR IGNORE INTO system_meta (key, value, updated_at) VALUES
    ('schema_version', '1', datetime('now')),
    ('last_full_reindex', '', datetime('now')),
    ('embedding_model', 'all-MiniLM-L6-v2', datetime('now'));
"""


def _serialize_embedding(embedding: list[float]) -> bytes:
    """Serialize embedding to bytes for storage."""
    return np.array(embedding, dtype=np.float32).tobytes()


def _deserialize_embedding(data: bytes) -> list[float]:
    """Deserialize embedding from bytes."""
    return np.frombuffer(data, dtype=np.float32).tolist()


def _cosine_similarity(a: bytes, b: bytes) -> float:
    """Compute cosine similarity between two serialized embeddings."""
    arr_a = np.frombuffer(a, dtype=np.float32)
    arr_b = np.frombuffer(b, dtype=np.float32)
    
    # Vectors should already be normalized, but ensure safety
    norm_a = np.linalg.norm(arr_a)
    norm_b = np.linalg.norm(arr_b)
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    similarity = float(np.dot(arr_a, arr_b) / (norm_a * norm_b))
    return max(0.0, min(1.0, similarity))


class MemoryStore:
    """SQLite storage layer for memory embeddings and metadata."""

    def __init__(self, db_path: Path) -> None:
        """Initialize store with database path."""
        self._db_path = db_path
        self._connection: sqlite3.Connection | None = None

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection with proper setup."""
        if self._connection is None:
            self._connection = self._create_connection()
        yield self._connection

    def _create_connection(self) -> sqlite3.Connection:
        """Create and configure a database connection."""
        # Ensure parent directory exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        
        # Enable foreign keys and WAL mode for better concurrency
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        
        return conn

    def initialize(self) -> None:
        """Create tables if they don't exist."""
        with self._get_connection() as conn:
            try:
                conn.executescript(SCHEMA_SQL)
                conn.executescript(INIT_METADATA_SQL)
                conn.commit()
            except sqlite3.Error as e:
                raise StoreError(
                    f"Failed to initialize database: {e}",
                    operation="initialize",
                ) from e

    def close(self) -> None:
        """Close the database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def upsert_memory(
        self,
        memory: MemoryFile,
        composite_embedding: list[float],
        directory_embedding: list[float],
        file_hash: str,
    ) -> None:
        """Insert or update a memory with its embedding."""
        with self._get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO memories (
                        id, path, directory, title, body,
                        scope, priority, confidence, status, tags_json, token_count,
                        created_at, last_used_at, usage_count, expires_at,
                        supersedes_json, related_json,
                        file_hash, indexed_at,
                        composite_embedding, directory_embedding
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        path = excluded.path,
                        directory = excluded.directory,
                        title = excluded.title,
                        body = excluded.body,
                        scope = excluded.scope,
                        priority = excluded.priority,
                        confidence = excluded.confidence,
                        status = excluded.status,
                        tags_json = excluded.tags_json,
                        token_count = excluded.token_count,
                        created_at = excluded.created_at,
                        expires_at = excluded.expires_at,
                        supersedes_json = excluded.supersedes_json,
                        related_json = excluded.related_json,
                        file_hash = excluded.file_hash,
                        indexed_at = excluded.indexed_at,
                        composite_embedding = excluded.composite_embedding,
                        directory_embedding = excluded.directory_embedding
                    """,
                    (
                        memory.id,
                        memory.path,
                        memory.directory,
                        memory.title,
                        memory.body,
                        memory.scope.value,
                        memory.priority,
                        memory.confidence.value,
                        memory.status.value,
                        json.dumps(memory.tags),
                        memory.token_count,
                        memory.created.isoformat() if memory.created else None,
                        memory.last_used.isoformat() if memory.last_used else None,
                        memory.usage_count,
                        memory.expires.isoformat() if memory.expires else None,
                        json.dumps(memory.supersedes),
                        json.dumps(memory.related),
                        file_hash,
                        datetime.now().isoformat(),
                        _serialize_embedding(composite_embedding),
                        _serialize_embedding(directory_embedding),
                    ),
                )
                conn.commit()
                
                # Update directory stats
                self._update_directory_stats(conn, memory.directory)
                
            except sqlite3.Error as e:
                raise StoreError(
                    f"Failed to upsert memory '{memory.id}': {e}",
                    operation="upsert",
                    details={"memory_id": memory.id},
                ) from e

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory by ID. Returns True if deleted."""
        with self._get_connection() as conn:
            try:
                # Get directory before delete for stats update
                cursor = conn.execute(
                    "SELECT directory FROM memories WHERE id = ?",
                    (memory_id,),
                )
                row = cursor.fetchone()
                directory = row["directory"] if row else None
                
                cursor = conn.execute(
                    "DELETE FROM memories WHERE id = ?",
                    (memory_id,),
                )
                conn.commit()
                
                if directory:
                    self._update_directory_stats(conn, directory)
                
                return cursor.rowcount > 0
            except sqlite3.Error as e:
                raise StoreError(
                    f"Failed to delete memory '{memory_id}': {e}",
                    operation="delete",
                    details={"memory_id": memory_id},
                ) from e

    def delete_memory_by_path(self, path: str) -> bool:
        """Delete a memory by file path. Returns True if deleted."""
        with self._get_connection() as conn:
            try:
                # Get info before delete
                cursor = conn.execute(
                    "SELECT id, directory FROM memories WHERE path = ?",
                    (path,),
                )
                row = cursor.fetchone()
                if not row:
                    return False
                
                directory = row["directory"]
                
                cursor = conn.execute(
                    "DELETE FROM memories WHERE path = ?",
                    (path,),
                )
                conn.commit()
                
                self._update_directory_stats(conn, directory)
                
                return cursor.rowcount > 0
            except sqlite3.Error as e:
                raise StoreError(
                    f"Failed to delete memory at '{path}': {e}",
                    operation="delete",
                    details={"path": path},
                ) from e

    def get_memory(self, memory_id: str) -> IndexedMemory | None:
        """Retrieve a memory by ID."""
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    "SELECT * FROM memories WHERE id = ?",
                    (memory_id,),
                )
                row = cursor.fetchone()
                return self._row_to_indexed_memory(row) if row else None
            except sqlite3.Error as e:
                raise StoreError(
                    f"Failed to get memory '{memory_id}': {e}",
                    operation="get",
                    details={"memory_id": memory_id},
                ) from e

    def get_memory_by_path(self, path: str) -> IndexedMemory | None:
        """Retrieve a memory by file path."""
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    "SELECT * FROM memories WHERE path = ?",
                    (path,),
                )
                row = cursor.fetchone()
                return self._row_to_indexed_memory(row) if row else None
            except sqlite3.Error as e:
                raise StoreError(
                    f"Failed to get memory at '{path}': {e}",
                    operation="get",
                    details={"path": path},
                ) from e

    def get_file_hash(self, path: str) -> str | None:
        """Get the stored file hash for a path."""
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    "SELECT file_hash FROM memories WHERE path = ?",
                    (path,),
                )
                row = cursor.fetchone()
                return row["file_hash"] if row else None
            except sqlite3.Error as e:
                raise StoreError(
                    f"Failed to get file hash for '{path}': {e}",
                    operation="get_hash",
                ) from e

    def get_all_memories(self) -> list[IndexedMemory]:
        """Get all memories."""
        with self._get_connection() as conn:
            try:
                cursor = conn.execute("SELECT * FROM memories")
                return [self._row_to_indexed_memory(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                raise StoreError(
                    f"Failed to get all memories: {e}",
                    operation="get_all",
                ) from e

    def get_baseline_memories(self) -> list[IndexedMemory]:
        """Get all memories with scope='baseline'."""
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    "SELECT * FROM memories WHERE scope = 'baseline' AND status = 'active' ORDER BY path",
                )
                return [self._row_to_indexed_memory(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                raise StoreError(
                    f"Failed to get baseline memories: {e}",
                    operation="get_baseline",
                ) from e

    def get_memory_count(self) -> int:
        """Get total number of indexed memories."""
        with self._get_connection() as conn:
            try:
                cursor = conn.execute("SELECT COUNT(*) as count FROM memories")
                row = cursor.fetchone()
                return row["count"] if row else 0
            except sqlite3.Error as e:
                raise StoreError(
                    f"Failed to get memory count: {e}",
                    operation="count",
                ) from e

    def search_by_directory(
        self,
        query_embedding: list[float],
        limit: int = 5,
    ) -> list[tuple[str, float]]:
        """
        Stage 1: Find most relevant directories.
        
        Returns list of (directory_path, similarity_score).
        """
        query_bytes = _serialize_embedding(query_embedding)
        
        with self._get_connection() as conn:
            try:
                # Get unique directories with their average embeddings
                cursor = conn.execute(
                    """
                    SELECT DISTINCT directory, directory_embedding
                    FROM memories
                    WHERE status = 'active' AND scope != 'baseline'
                    """
                )
                
                results: list[tuple[str, float]] = []
                for row in cursor.fetchall():
                    similarity = _cosine_similarity(query_bytes, row["directory_embedding"])
                    results.append((row["directory"], similarity))
                
                # Sort by similarity descending and limit
                results.sort(key=lambda x: x[1], reverse=True)
                return results[:limit]
                
            except sqlite3.Error as e:
                raise StoreError(
                    f"Failed to search directories: {e}",
                    operation="search_directories",
                ) from e

    def search_by_content(
        self,
        query_embedding: list[float],
        directories: list[str] | None,
        filters: SearchFilters,
        limit: int = 20,
    ) -> list[tuple[IndexedMemory, float]]:
        """
        Stage 2: Find relevant memories within directories.
        
        Returns list of (memory, similarity_score).
        """
        query_bytes = _serialize_embedding(query_embedding)
        
        with self._get_connection() as conn:
            try:
                # Build query with filters
                conditions = ["scope != 'baseline'"]  # Baseline handled separately
                params: list[Any] = []
                
                if directories:
                    placeholders = ",".join("?" * len(directories))
                    conditions.append(f"directory IN ({placeholders})")
                    params.extend(directories)
                
                if filters.exclude_deprecated:
                    conditions.append("status != 'deprecated'")
                
                if filters.exclude_ephemeral:
                    conditions.append("scope != 'ephemeral'")
                
                if filters.scopes:
                    scope_placeholders = ",".join("?" * len(filters.scopes))
                    conditions.append(f"scope IN ({scope_placeholders})")
                    params.extend([s.value for s in filters.scopes])
                
                if filters.min_priority > 0:
                    conditions.append("priority >= ?")
                    params.append(filters.min_priority)
                
                if filters.max_token_count:
                    conditions.append("token_count <= ?")
                    params.append(filters.max_token_count)
                
                where_clause = " AND ".join(conditions)
                
                cursor = conn.execute(
                    f"SELECT * FROM memories WHERE {where_clause}",
                    params,
                )
                
                results: list[tuple[IndexedMemory, float]] = []
                for row in cursor.fetchall():
                    memory = self._row_to_indexed_memory(row)
                    similarity = _cosine_similarity(query_bytes, row["composite_embedding"])
                    results.append((memory, similarity))
                
                # Sort by similarity descending and limit
                results.sort(key=lambda x: x[1], reverse=True)
                return results[:limit]
                
            except sqlite3.Error as e:
                raise StoreError(
                    f"Failed to search content: {e}",
                    operation="search_content",
                ) from e

    def get_all_directories(self) -> list[DirectoryInfo]:
        """Get directory listing with stats."""
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    """
                    SELECT 
                        directory,
                        COUNT(*) as file_count,
                        AVG(priority) as avg_priority,
                        GROUP_CONCAT(DISTINCT scope) as scopes
                    FROM memories
                    WHERE status = 'active'
                    GROUP BY directory
                    ORDER BY directory
                    """
                )
                
                results: list[DirectoryInfo] = []
                for row in cursor.fetchall():
                    scopes = row["scopes"].split(",") if row["scopes"] else []
                    results.append(
                        DirectoryInfo(
                            path=row["directory"],
                            file_count=row["file_count"],
                            avg_priority=row["avg_priority"] or 0.5,
                            scopes=scopes,
                        )
                    )
                return results
                
            except sqlite3.Error as e:
                raise StoreError(
                    f"Failed to get directories: {e}",
                    operation="get_directories",
                ) from e

    def get_system_meta(self, key: str) -> str | None:
        """Get a system metadata value."""
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    "SELECT value FROM system_meta WHERE key = ?",
                    (key,),
                )
                row = cursor.fetchone()
                return row["value"] if row else None
            except sqlite3.Error as e:
                raise StoreError(
                    f"Failed to get system meta '{key}': {e}",
                    operation="get_meta",
                ) from e

    def set_system_meta(self, key: str, value: str) -> None:
        """Set a system metadata value."""
        with self._get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO system_meta (key, value, updated_at)
                    VALUES (?, ?, datetime('now'))
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (key, value),
                )
                conn.commit()
            except sqlite3.Error as e:
                raise StoreError(
                    f"Failed to set system meta '{key}': {e}",
                    operation="set_meta",
                ) from e

    def clear_all(self) -> None:
        """Clear all memories (for testing/reset)."""
        with self._get_connection() as conn:
            try:
                conn.execute("DELETE FROM memories")
                conn.execute("DELETE FROM directories")
                conn.commit()
            except sqlite3.Error as e:
                raise StoreError(
                    f"Failed to clear database: {e}",
                    operation="clear",
                ) from e

    def _update_directory_stats(self, conn: sqlite3.Connection, directory: str) -> None:
        """Update directory statistics after memory changes."""
        try:
            # Get current stats for directory
            cursor = conn.execute(
                """
                SELECT 
                    COUNT(*) as file_count,
                    AVG(priority) as avg_priority,
                    GROUP_CONCAT(DISTINCT scope) as scopes
                FROM memories
                WHERE directory = ? AND status = 'active'
                """,
                (directory,),
            )
            row = cursor.fetchone()
            
            if row["file_count"] > 0:
                conn.execute(
                    """
                    INSERT INTO directories (path, file_count, avg_priority, scopes_json, last_updated)
                    VALUES (?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(path) DO UPDATE SET
                        file_count = excluded.file_count,
                        avg_priority = excluded.avg_priority,
                        scopes_json = excluded.scopes_json,
                        last_updated = excluded.last_updated
                    """,
                    (
                        directory,
                        row["file_count"],
                        row["avg_priority"] or 0.5,
                        json.dumps(row["scopes"].split(",") if row["scopes"] else []),
                    ),
                )
            else:
                # No more files in directory, remove it
                conn.execute("DELETE FROM directories WHERE path = ?", (directory,))
            
            conn.commit()
        except sqlite3.Error:
            # Non-critical, don't raise
            pass

    def _row_to_indexed_memory(self, row: sqlite3.Row) -> IndexedMemory:
        """Convert database row to IndexedMemory."""
        return IndexedMemory(
            id=row["id"],
            path=row["path"],
            directory=row["directory"],
            title=row["title"],
            body=row["body"],
            composite_embedding=_deserialize_embedding(row["composite_embedding"]),
            directory_embedding=_deserialize_embedding(row["directory_embedding"]),
            scope=row["scope"],
            priority=row["priority"],
            confidence=row["confidence"],
            status=row["status"],
            tags=json.loads(row["tags_json"]),
            token_count=row["token_count"],
            file_hash=row["file_hash"],
            indexed_at=datetime.fromisoformat(row["indexed_at"]),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            last_used_at=datetime.fromisoformat(row["last_used_at"]) if row["last_used_at"] else None,
            usage_count=row["usage_count"],
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            supersedes=json.loads(row["supersedes_json"]),
            related=json.loads(row["related_json"]),
        )
