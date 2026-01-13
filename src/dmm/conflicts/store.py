"""Conflict storage and persistence layer.

This module handles all database operations for conflict detection,
including CRUD operations, queries, and statistics.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator

from dmm.core.constants import get_conflicts_db_path
from dmm.core.exceptions import ConflictNotFoundError, ConflictStoreError
from dmm.models.conflict import (
    Conflict,
    ConflictMemory,
    ConflictStats,
    ConflictStatus,
    ConflictType,
    DetectionMethod,
    ResolutionAction,
    ResolutionRequest,
)


CONFLICTS_SCHEMA_SQL = """
-- Main conflicts table (extended from Phase 2)
CREATE TABLE IF NOT EXISTS conflicts (
    conflict_id TEXT PRIMARY KEY,
    
    -- Classification
    conflict_type TEXT NOT NULL CHECK (conflict_type IN (
        'contradictory', 'duplicate', 'supersession', 'scope_overlap', 'stale'
    )),
    detection_method TEXT NOT NULL CHECK (detection_method IN (
        'tag_overlap', 'semantic_similarity', 'supersession_chain', 
        'rule_extraction', 'manual', 'co_retrieval'
    )),
    confidence REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    
    -- Description
    description TEXT NOT NULL,
    evidence TEXT,
    
    -- Status
    status TEXT NOT NULL DEFAULT 'unresolved' CHECK (status IN (
        'unresolved', 'in_progress', 'resolved', 'dismissed'
    )),
    detected_at TEXT NOT NULL,
    
    -- Resolution
    resolved_at TEXT,
    resolution_action TEXT CHECK (resolution_action IN (
        'deprecate', 'merge', 'clarify', 'dismiss', 'defer'
    )),
    resolution_target TEXT,
    resolution_reason TEXT,
    resolved_by TEXT,
    
    -- Metadata
    scan_id TEXT,
    suppressed_until TEXT,
    
    -- Deduplication
    memory_pair_hash TEXT UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_conflicts_status ON conflicts(status);
CREATE INDEX IF NOT EXISTS idx_conflicts_type ON conflicts(conflict_type);
CREATE INDEX IF NOT EXISTS idx_conflicts_detected ON conflicts(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_conflicts_confidence ON conflicts(confidence DESC);
CREATE INDEX IF NOT EXISTS idx_conflicts_pair_hash ON conflicts(memory_pair_hash);

-- Memories involved in conflicts
CREATE TABLE IF NOT EXISTS conflict_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conflict_id TEXT NOT NULL REFERENCES conflicts(conflict_id) ON DELETE CASCADE,
    memory_id TEXT NOT NULL,
    path TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    scope TEXT,
    priority REAL,
    role TEXT NOT NULL CHECK (role IN ('primary', 'secondary', 'related')),
    key_claims_json TEXT DEFAULT '[]',
    last_modified TEXT,
    
    UNIQUE(conflict_id, memory_id)
);

CREATE INDEX IF NOT EXISTS idx_conflict_memories_conflict ON conflict_memories(conflict_id);
CREATE INDEX IF NOT EXISTS idx_conflict_memories_memory ON conflict_memories(memory_id);

-- Scan history
CREATE TABLE IF NOT EXISTS conflict_scans (
    scan_id TEXT PRIMARY KEY,
    scan_type TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    duration_ms INTEGER,
    
    -- Scope
    memories_scanned INTEGER,
    methods_used_json TEXT,
    
    -- Results
    conflicts_detected INTEGER DEFAULT 0,
    conflicts_new INTEGER DEFAULT 0,
    conflicts_existing INTEGER DEFAULT 0,
    
    -- By type/method
    by_type_json TEXT DEFAULT '{}',
    by_method_json TEXT DEFAULT '{}',
    
    -- Status
    status TEXT DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed')),
    errors_json TEXT DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_scans_started ON conflict_scans(started_at DESC);

-- Resolution audit log
CREATE TABLE IF NOT EXISTS resolution_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conflict_id TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    details_json TEXT,
    
    -- What changed
    memories_modified_json TEXT DEFAULT '[]',
    memories_deprecated_json TEXT DEFAULT '[]',
    memories_created_json TEXT DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_resolution_log_conflict ON resolution_log(conflict_id);

-- Conflict metadata
CREATE TABLE IF NOT EXISTS conflict_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

INIT_META_SQL = """
INSERT OR IGNORE INTO conflict_meta (key, value, updated_at) VALUES
    ('schema_version', '2', datetime('now')),
    ('total_scans', '0', datetime('now')),
    ('last_scan_at', '', datetime('now'));
"""


class ConflictStore:
    """Database storage for conflicts and scan history."""

    def __init__(self, base_path: Path | None = None) -> None:
        """Initialize the conflict store.
        
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
        """Create tables if they do not exist."""
        try:
            with self._get_connection() as conn:
                conn.executescript(CONFLICTS_SCHEMA_SQL)
                conn.executescript(INIT_META_SQL)
                conn.commit()
        except sqlite3.Error as e:
            raise ConflictStoreError(f"Failed to initialize conflict store: {e}", operation="initialize")

    def close(self) -> None:
        """Close the database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def create(self, conflict: Conflict) -> str:
        """Create a new conflict record.
        
        Args:
            conflict: The conflict to create.
            
        Returns:
            The conflict ID.
            
        Raises:
            ConflictStoreError: If creation fails.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO conflicts (
                        conflict_id, conflict_type, detection_method, confidence,
                        description, evidence, status, detected_at,
                        scan_id, memory_pair_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        conflict.conflict_id,
                        conflict.conflict_type.value,
                        conflict.detection_method.value,
                        conflict.confidence,
                        conflict.description,
                        conflict.evidence,
                        conflict.status.value,
                        conflict.detected_at.isoformat(),
                        conflict.scan_id,
                        conflict.memory_pair_hash,
                    ),
                )
                
                for memory in conflict.memories:
                    conn.execute(
                        """
                        INSERT INTO conflict_memories (
                            conflict_id, memory_id, path, title, summary,
                            scope, priority, role, key_claims_json, last_modified
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            conflict.conflict_id,
                            memory.memory_id,
                            memory.path,
                            memory.title,
                            memory.summary,
                            memory.scope,
                            memory.priority,
                            memory.role,
                            json.dumps(memory.key_claims),
                            memory.last_modified.isoformat() if memory.last_modified else None,
                        ),
                    )
                
                conn.commit()
                return conflict.conflict_id
                
        except sqlite3.IntegrityError as e:
            if "memory_pair_hash" in str(e):
                raise ConflictStoreError(
                    "Conflict already exists for this memory pair",
                    operation="create",
                )
            raise ConflictStoreError(f"Failed to create conflict: {e}", operation="create")
        except sqlite3.Error as e:
            raise ConflictStoreError(f"Failed to create conflict: {e}", operation="create")

    def get(self, conflict_id: str) -> Conflict | None:
        """Get a conflict by ID.
        
        Args:
            conflict_id: The conflict ID.
            
        Returns:
            The conflict or None if not found.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM conflicts WHERE conflict_id = ?",
                    (conflict_id,),
                )
                row = cursor.fetchone()
                
                if row is None:
                    return None
                
                return self._row_to_conflict(conn, row)
                
        except sqlite3.Error as e:
            raise ConflictStoreError(f"Failed to get conflict: {e}", operation="get")

    def get_by_memory_pair(self, pair: tuple[str, str]) -> Conflict | None:
        """Get conflict for a specific memory pair.
        
        Args:
            pair: Tuple of two memory IDs.
            
        Returns:
            The conflict or None if not found.
        """
        pair_hash = "|".join(sorted(pair))
        
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM conflicts WHERE memory_pair_hash = ?",
                    (pair_hash,),
                )
                row = cursor.fetchone()
                
                if row is None:
                    return None
                
                return self._row_to_conflict(conn, row)
                
        except sqlite3.Error as e:
            raise ConflictStoreError(f"Failed to get conflict by pair: {e}", operation="get_by_memory_pair")

    def get_by_memory(self, memory_id: str) -> list[Conflict]:
        """Get all conflicts involving a memory.
        
        Args:
            memory_id: The memory ID.
            
        Returns:
            List of conflicts involving the memory.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT c.* FROM conflicts c
                    JOIN conflict_memories cm ON c.conflict_id = cm.conflict_id
                    WHERE cm.memory_id = ?
                    ORDER BY c.detected_at DESC
                    """,
                    (memory_id,),
                )
                
                return [self._row_to_conflict(conn, row) for row in cursor.fetchall()]
                
        except sqlite3.Error as e:
            raise ConflictStoreError(f"Failed to get conflicts by memory: {e}", operation="get_by_memory")

    def get_unresolved(
        self,
        limit: int = 50,
        min_confidence: float = 0.0,
    ) -> list[Conflict]:
        """Get unresolved conflicts sorted by confidence.
        
        Args:
            limit: Maximum number of conflicts to return.
            min_confidence: Minimum confidence threshold.
            
        Returns:
            List of unresolved conflicts.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM conflicts
                    WHERE status = 'unresolved' AND confidence >= ?
                    ORDER BY confidence DESC, detected_at DESC
                    LIMIT ?
                    """,
                    (min_confidence, limit),
                )
                
                return [self._row_to_conflict(conn, row) for row in cursor.fetchall()]
                
        except sqlite3.Error as e:
            raise ConflictStoreError(f"Failed to get unresolved conflicts: {e}", operation="get_unresolved")

    def get_by_status(
        self,
        status: ConflictStatus,
        limit: int = 50,
    ) -> list[Conflict]:
        """Get conflicts by status.
        
        Args:
            status: The status to filter by.
            limit: Maximum number of conflicts to return.
            
        Returns:
            List of conflicts with the given status.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM conflicts
                    WHERE status = ?
                    ORDER BY detected_at DESC
                    LIMIT ?
                    """,
                    (status.value, limit),
                )
                
                return [self._row_to_conflict(conn, row) for row in cursor.fetchall()]
                
        except sqlite3.Error as e:
            raise ConflictStoreError(f"Failed to get conflicts by status: {e}", operation="get_by_status")

    def get_by_type(
        self,
        conflict_type: ConflictType,
        limit: int = 50,
    ) -> list[Conflict]:
        """Get conflicts by type.
        
        Args:
            conflict_type: The type to filter by.
            limit: Maximum number of conflicts to return.
            
        Returns:
            List of conflicts with the given type.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM conflicts
                    WHERE conflict_type = ?
                    ORDER BY detected_at DESC
                    LIMIT ?
                    """,
                    (conflict_type.value, limit),
                )
                
                return [self._row_to_conflict(conn, row) for row in cursor.fetchall()]
                
        except sqlite3.Error as e:
            raise ConflictStoreError(f"Failed to get conflicts by type: {e}", operation="get_by_type")

    def get_all(self, limit: int = 100) -> list[Conflict]:
        """Get all conflicts.
        
        Args:
            limit: Maximum number of conflicts to return.
            
        Returns:
            List of all conflicts.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM conflicts
                    ORDER BY detected_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                
                return [self._row_to_conflict(conn, row) for row in cursor.fetchall()]
                
        except sqlite3.Error as e:
            raise ConflictStoreError(f"Failed to get all conflicts: {e}", operation="get_all")

    def get_conflicts_among(self, memory_ids: list[str]) -> list[Conflict]:
        """Get conflicts among a set of memories.
        
        Args:
            memory_ids: List of memory IDs to check.
            
        Returns:
            List of conflicts between the given memories.
        """
        if len(memory_ids) < 2:
            return []
        
        try:
            with self._get_connection() as conn:
                placeholders = ",".join("?" * len(memory_ids))
                cursor = conn.execute(
                    f"""
                    SELECT DISTINCT c.* FROM conflicts c
                    JOIN conflict_memories cm1 ON c.conflict_id = cm1.conflict_id
                    JOIN conflict_memories cm2 ON c.conflict_id = cm2.conflict_id
                    WHERE cm1.memory_id IN ({placeholders})
                    AND cm2.memory_id IN ({placeholders})
                    AND cm1.memory_id != cm2.memory_id
                    AND c.status = 'unresolved'
                    ORDER BY c.confidence DESC
                    """,
                    memory_ids + memory_ids,
                )
                
                return [self._row_to_conflict(conn, row) for row in cursor.fetchall()]
                
        except sqlite3.Error as e:
            raise ConflictStoreError(f"Failed to get conflicts among memories: {e}", operation="get_conflicts_among")

    def update_status(
        self,
        conflict_id: str,
        status: ConflictStatus,
        resolution: ResolutionRequest | None = None,
    ) -> bool:
        """Update conflict status and optionally record resolution.
        
        Args:
            conflict_id: The conflict ID.
            status: The new status.
            resolution: Optional resolution details.
            
        Returns:
            True if updated, False if not found.
        """
        try:
            with self._get_connection() as conn:
                if resolution and status in (ConflictStatus.RESOLVED, ConflictStatus.DISMISSED):
                    cursor = conn.execute(
                        """
                        UPDATE conflicts SET
                            status = ?,
                            resolved_at = ?,
                            resolution_action = ?,
                            resolution_target = ?,
                            resolution_reason = ?,
                            resolved_by = ?
                        WHERE conflict_id = ?
                        """,
                        (
                            status.value,
                            datetime.utcnow().isoformat(),
                            resolution.action.value,
                            resolution.target_memory_id,
                            resolution.reason,
                            resolution.resolved_by,
                            conflict_id,
                        ),
                    )
                else:
                    cursor = conn.execute(
                        "UPDATE conflicts SET status = ? WHERE conflict_id = ?",
                        (status.value, conflict_id),
                    )
                
                conn.commit()
                return cursor.rowcount > 0
                
        except sqlite3.Error as e:
            raise ConflictStoreError(f"Failed to update conflict status: {e}", operation="update_status")

    def delete(self, conflict_id: str) -> bool:
        """Delete a conflict.
        
        Args:
            conflict_id: The conflict ID.
            
        Returns:
            True if deleted, False if not found.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM conflicts WHERE conflict_id = ?",
                    (conflict_id,),
                )
                conn.commit()
                return cursor.rowcount > 0
                
        except sqlite3.Error as e:
            raise ConflictStoreError(f"Failed to delete conflict: {e}", operation="delete")

    def exists_for_pair(self, pair: tuple[str, str]) -> bool:
        """Check if a conflict exists for a memory pair.
        
        Args:
            pair: Tuple of two memory IDs.
            
        Returns:
            True if conflict exists.
        """
        pair_hash = "|".join(sorted(pair))
        
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT 1 FROM conflicts WHERE memory_pair_hash = ? AND status != 'dismissed'",
                    (pair_hash,),
                )
                return cursor.fetchone() is not None
                
        except sqlite3.Error as e:
            raise ConflictStoreError(f"Failed to check conflict existence: {e}", operation="exists_for_pair")

    def get_stats(self) -> ConflictStats:
        """Get conflict statistics.
        
        Returns:
            Conflict statistics.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'unresolved' THEN 1 ELSE 0 END) as unresolved,
                        SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                        SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) as resolved,
                        SUM(CASE WHEN status = 'dismissed' THEN 1 ELSE 0 END) as dismissed,
                        AVG(confidence) as avg_confidence
                    FROM conflicts
                    """
                )
                row = cursor.fetchone()
                
                by_type_cursor = conn.execute(
                    "SELECT conflict_type, COUNT(*) as count FROM conflicts GROUP BY conflict_type"
                )
                by_type = {r["conflict_type"]: r["count"] for r in by_type_cursor.fetchall()}
                
                by_method_cursor = conn.execute(
                    "SELECT detection_method, COUNT(*) as count FROM conflicts GROUP BY detection_method"
                )
                by_method = {r["detection_method"]: r["count"] for r in by_method_cursor.fetchall()}
                
                oldest_cursor = conn.execute(
                    "SELECT MIN(detected_at) as oldest FROM conflicts WHERE status = 'unresolved'"
                )
                oldest_row = oldest_cursor.fetchone()
                oldest_unresolved = None
                if oldest_row and oldest_row["oldest"]:
                    oldest_unresolved = datetime.fromisoformat(oldest_row["oldest"])
                
                return ConflictStats(
                    total=row["total"] or 0,
                    unresolved=row["unresolved"] or 0,
                    in_progress=row["in_progress"] or 0,
                    resolved=row["resolved"] or 0,
                    dismissed=row["dismissed"] or 0,
                    by_type=by_type,
                    by_method=by_method,
                    avg_confidence=row["avg_confidence"] or 0.0,
                    oldest_unresolved=oldest_unresolved,
                )
                
        except sqlite3.Error as e:
            raise ConflictStoreError(f"Failed to get conflict stats: {e}", operation="get_stats")

    def log_resolution(
        self,
        conflict_id: str,
        action: str,
        actor: str,
        details: dict | None = None,
        memories_modified: list[str] | None = None,
        memories_deprecated: list[str] | None = None,
        memories_created: list[str] | None = None,
    ) -> None:
        """Log a resolution action.
        
        Args:
            conflict_id: The conflict ID.
            action: The action taken.
            actor: Who performed the action.
            details: Additional details.
            memories_modified: List of modified memory IDs.
            memories_deprecated: List of deprecated memory IDs.
            memories_created: List of created memory IDs.
        """
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO resolution_log (
                        conflict_id, action, actor, timestamp, details_json,
                        memories_modified_json, memories_deprecated_json, memories_created_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        conflict_id,
                        action,
                        actor,
                        datetime.utcnow().isoformat(),
                        json.dumps(details or {}),
                        json.dumps(memories_modified or []),
                        json.dumps(memories_deprecated or []),
                        json.dumps(memories_created or []),
                    ),
                )
                conn.commit()
                
        except sqlite3.Error as e:
            raise ConflictStoreError(f"Failed to log resolution: {e}", operation="log_resolution")

    def save_scan(
        self,
        scan_id: str,
        scan_type: str,
        started_at: datetime,
        completed_at: datetime | None = None,
        duration_ms: int | None = None,
        memories_scanned: int = 0,
        methods_used: list[str] | None = None,
        conflicts_detected: int = 0,
        conflicts_new: int = 0,
        conflicts_existing: int = 0,
        by_type: dict[str, int] | None = None,
        by_method: dict[str, int] | None = None,
        status: str = "running",
        errors: list[str] | None = None,
    ) -> None:
        """Save or update a scan record.
        
        Args:
            scan_id: The scan ID.
            scan_type: Type of scan.
            started_at: When the scan started.
            completed_at: When the scan completed.
            duration_ms: Duration in milliseconds.
            memories_scanned: Number of memories scanned.
            methods_used: Detection methods used.
            conflicts_detected: Total conflicts detected.
            conflicts_new: New conflicts detected.
            conflicts_existing: Existing conflicts found.
            by_type: Conflicts by type.
            by_method: Conflicts by detection method.
            status: Scan status.
            errors: List of errors.
        """
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO conflict_scans (
                        scan_id, scan_type, started_at, completed_at, duration_ms,
                        memories_scanned, methods_used_json, conflicts_detected,
                        conflicts_new, conflicts_existing, by_type_json,
                        by_method_json, status, errors_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        scan_id,
                        scan_type,
                        started_at.isoformat(),
                        completed_at.isoformat() if completed_at else None,
                        duration_ms,
                        memories_scanned,
                        json.dumps(methods_used or []),
                        conflicts_detected,
                        conflicts_new,
                        conflicts_existing,
                        json.dumps(by_type or {}),
                        json.dumps(by_method or {}),
                        status,
                        json.dumps(errors or []),
                    ),
                )
                conn.commit()
                
        except sqlite3.Error as e:
            raise ConflictStoreError(f"Failed to save scan: {e}", operation="save_scan")

    def get_scan_history(self, limit: int = 20) -> list[dict]:
        """Get recent scan history.
        
        Args:
            limit: Maximum number of scans to return.
            
        Returns:
            List of scan records.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM conflict_scans
                    ORDER BY started_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        "scan_id": row["scan_id"],
                        "scan_type": row["scan_type"],
                        "started_at": row["started_at"],
                        "completed_at": row["completed_at"],
                        "duration_ms": row["duration_ms"],
                        "memories_scanned": row["memories_scanned"],
                        "methods_used": json.loads(row["methods_used_json"] or "[]"),
                        "conflicts_detected": row["conflicts_detected"],
                        "conflicts_new": row["conflicts_new"],
                        "conflicts_existing": row["conflicts_existing"],
                        "by_type": json.loads(row["by_type_json"] or "{}"),
                        "by_method": json.loads(row["by_method_json"] or "{}"),
                        "status": row["status"],
                        "errors": json.loads(row["errors_json"] or "[]"),
                    })
                
                return results
                
        except sqlite3.Error as e:
            raise ConflictStoreError(f"Failed to get scan history: {e}", operation="get_scan_history")

    def _row_to_conflict(self, conn: sqlite3.Connection, row: sqlite3.Row) -> Conflict:
        """Convert a database row to a Conflict object."""
        memories_cursor = conn.execute(
            "SELECT * FROM conflict_memories WHERE conflict_id = ?",
            (row["conflict_id"],),
        )
        
        memories = []
        for mem_row in memories_cursor.fetchall():
            last_modified = None
            if mem_row["last_modified"]:
                last_modified = datetime.fromisoformat(mem_row["last_modified"])
            
            memories.append(ConflictMemory(
                memory_id=mem_row["memory_id"],
                path=mem_row["path"],
                title=mem_row["title"],
                summary=mem_row["summary"] or "",
                scope=mem_row["scope"] or "",
                priority=mem_row["priority"] or 0.0,
                role=mem_row["role"],
                key_claims=json.loads(mem_row["key_claims_json"] or "[]"),
                last_modified=last_modified,
            ))
        
        resolved_at = None
        if row["resolved_at"]:
            resolved_at = datetime.fromisoformat(row["resolved_at"])
        
        suppressed_until = None
        if row["suppressed_until"]:
            suppressed_until = datetime.fromisoformat(row["suppressed_until"])
        
        resolution_action = None
        if row["resolution_action"]:
            resolution_action = ResolutionAction(row["resolution_action"])
        
        return Conflict(
            conflict_id=row["conflict_id"],
            memories=memories,
            conflict_type=ConflictType(row["conflict_type"]),
            detection_method=DetectionMethod(row["detection_method"]),
            confidence=row["confidence"],
            description=row["description"],
            evidence=row["evidence"] or "",
            status=ConflictStatus(row["status"]),
            detected_at=datetime.fromisoformat(row["detected_at"]),
            resolved_at=resolved_at,
            resolution_action=resolution_action,
            resolution_target=row["resolution_target"],
            resolution_reason=row["resolution_reason"],
            resolved_by=row["resolved_by"],
            scan_id=row["scan_id"],
            suppressed_until=suppressed_until,
        )
