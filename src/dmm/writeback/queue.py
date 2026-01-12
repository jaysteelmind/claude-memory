"""Review queue with SQLite persistence for write proposals."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator

from dmm.core.constants import get_review_queue_db_path
from dmm.core.exceptions import QueueError
from dmm.models.proposal import (
    ProposalStatus,
    ProposalType,
    WriteProposal,
)


QUEUE_SCHEMA_SQL = """
-- Proposals table
CREATE TABLE IF NOT EXISTS proposals (
    proposal_id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('create', 'update', 'deprecate', 'promote')),
    target_path TEXT NOT NULL,
    reason TEXT NOT NULL,
    
    -- Content fields
    content TEXT,
    patch TEXT,
    new_scope TEXT,
    
    -- Metadata
    proposed_by TEXT NOT NULL DEFAULT 'agent',
    created_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'pending', 'in_review', 'approved', 'committed', 
        'rejected', 'modified', 'deferred', 'failed'
    )),
    
    -- For UPDATE operations
    memory_id TEXT,
    
    -- For DEPRECATE operations
    deprecation_reason TEXT,
    
    -- For PROMOTE operations
    source_scope TEXT,
    
    -- Review tracking
    reviewed_at TEXT,
    reviewer_notes TEXT,
    retry_count INTEGER DEFAULT 0,
    
    -- Commit tracking
    committed_at TEXT,
    commit_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
CREATE INDEX IF NOT EXISTS idx_proposals_created ON proposals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_proposals_target_path ON proposals(target_path);

-- Review log table
CREATE TABLE IF NOT EXISTS review_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id TEXT NOT NULL,
    action TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    notes TEXT,
    timestamp TEXT NOT NULL,
    
    FOREIGN KEY (proposal_id) REFERENCES proposals(proposal_id)
);

CREATE INDEX IF NOT EXISTS idx_review_log_proposal ON review_log(proposal_id);

-- System metadata
CREATE TABLE IF NOT EXISTS queue_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

INIT_QUEUE_META_SQL = """
INSERT OR IGNORE INTO queue_meta (key, value, updated_at) VALUES
    ('schema_version', '1', datetime('now')),
    ('total_proposals', '0', datetime('now')),
    ('total_approved', '0', datetime('now')),
    ('total_rejected', '0', datetime('now'));
"""


class ReviewQueue:
    """SQLite-backed queue for managing write proposals."""

    def __init__(self, base_path: Path | None = None) -> None:
        """Initialize the review queue.
        
        Args:
            base_path: Base path for the DMM directory. Defaults to cwd.
        """
        self._db_path = get_review_queue_db_path(base_path)
        self._connection: sqlite3.Connection | None = None

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection with proper setup."""
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
            try:
                conn.executescript(QUEUE_SCHEMA_SQL)
                conn.executescript(INIT_QUEUE_META_SQL)
                conn.commit()
            except sqlite3.Error as e:
                raise QueueError(
                    f"Failed to initialize review queue database: {e}",
                    operation="initialize",
                ) from e

    def close(self) -> None:
        """Close the database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def enqueue(self, proposal: WriteProposal) -> None:
        """Add a proposal to the queue.
        
        Args:
            proposal: The write proposal to enqueue.
            
        Raises:
            QueueError: If enqueue operation fails.
        """
        with self._get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO proposals (
                        proposal_id, type, target_path, reason,
                        content, patch, new_scope,
                        proposed_by, created_at, status,
                        memory_id, deprecation_reason, source_scope,
                        reviewed_at, reviewer_notes, retry_count,
                        committed_at, commit_error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        proposal.proposal_id,
                        proposal.type.value,
                        proposal.target_path,
                        proposal.reason,
                        proposal.content,
                        proposal.patch,
                        proposal.new_scope,
                        proposal.proposed_by,
                        proposal.created_at.isoformat(),
                        proposal.status.value,
                        proposal.memory_id,
                        proposal.deprecation_reason,
                        proposal.source_scope,
                        proposal.reviewed_at.isoformat() if proposal.reviewed_at else None,
                        proposal.reviewer_notes,
                        proposal.retry_count,
                        proposal.committed_at.isoformat() if proposal.committed_at else None,
                        proposal.commit_error,
                    ),
                )
                
                self._log_action(
                    conn,
                    proposal.proposal_id,
                    "enqueue",
                    None,
                    proposal.status.value,
                    f"Proposal enqueued: {proposal.reason}",
                )
                
                conn.commit()
                
            except sqlite3.IntegrityError as e:
                raise QueueError(
                    f"Proposal '{proposal.proposal_id}' already exists",
                    operation="enqueue",
                    details={"proposal_id": proposal.proposal_id},
                ) from e
            except sqlite3.Error as e:
                raise QueueError(
                    f"Failed to enqueue proposal: {e}",
                    operation="enqueue",
                ) from e

    def get(self, proposal_id: str) -> WriteProposal | None:
        """Get a proposal by ID.
        
        Args:
            proposal_id: The proposal ID to retrieve.
            
        Returns:
            The proposal if found, None otherwise.
        """
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    "SELECT * FROM proposals WHERE proposal_id = ?",
                    (proposal_id,),
                )
                row = cursor.fetchone()
                return self._row_to_proposal(row) if row else None
            except sqlite3.Error as e:
                raise QueueError(
                    f"Failed to get proposal '{proposal_id}': {e}",
                    operation="get",
                ) from e

    def get_by_path(self, target_path: str) -> list[WriteProposal]:
        """Get all proposals for a target path.
        
        Args:
            target_path: The target path to search for.
            
        Returns:
            List of proposals for the path.
        """
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    "SELECT * FROM proposals WHERE target_path = ? ORDER BY created_at DESC",
                    (target_path,),
                )
                return [self._row_to_proposal(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                raise QueueError(
                    f"Failed to get proposals for path '{target_path}': {e}",
                    operation="get_by_path",
                ) from e

    def get_pending(self, limit: int = 100) -> list[WriteProposal]:
        """Get pending proposals awaiting review.
        
        Args:
            limit: Maximum number of proposals to return.
            
        Returns:
            List of pending proposals, oldest first.
        """
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    """
                    SELECT * FROM proposals 
                    WHERE status = 'pending' 
                    ORDER BY created_at ASC 
                    LIMIT ?
                    """,
                    (limit,),
                )
                return [self._row_to_proposal(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                raise QueueError(
                    f"Failed to get pending proposals: {e}",
                    operation="get_pending",
                ) from e

    def get_by_status(
        self, 
        status: ProposalStatus, 
        limit: int = 100,
    ) -> list[WriteProposal]:
        """Get proposals by status.
        
        Args:
            status: The status to filter by.
            limit: Maximum number of proposals to return.
            
        Returns:
            List of proposals with the given status.
        """
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    """
                    SELECT * FROM proposals 
                    WHERE status = ? 
                    ORDER BY created_at DESC 
                    LIMIT ?
                    """,
                    (status.value, limit),
                )
                return [self._row_to_proposal(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                raise QueueError(
                    f"Failed to get proposals with status '{status.value}': {e}",
                    operation="get_by_status",
                ) from e

    def update_status(
        self,
        proposal_id: str,
        new_status: ProposalStatus,
        notes: str | None = None,
    ) -> bool:
        """Update the status of a proposal.
        
        Args:
            proposal_id: The proposal ID to update.
            new_status: The new status to set.
            notes: Optional notes about the status change.
            
        Returns:
            True if updated, False if proposal not found.
        """
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    "SELECT status FROM proposals WHERE proposal_id = ?",
                    (proposal_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return False
                
                old_status = row["status"]
                
                update_fields = ["status = ?", "reviewed_at = ?"]
                params: list = [new_status.value, datetime.now().isoformat()]
                
                if notes:
                    update_fields.append("reviewer_notes = ?")
                    params.append(notes)
                
                if new_status == ProposalStatus.COMMITTED:
                    update_fields.append("committed_at = ?")
                    params.append(datetime.now().isoformat())
                
                params.append(proposal_id)
                
                conn.execute(
                    f"UPDATE proposals SET {', '.join(update_fields)} WHERE proposal_id = ?",
                    params,
                )
                
                self._log_action(
                    conn,
                    proposal_id,
                    "status_change",
                    old_status,
                    new_status.value,
                    notes,
                )
                
                conn.commit()
                return True
                
            except sqlite3.Error as e:
                raise QueueError(
                    f"Failed to update proposal status: {e}",
                    operation="update_status",
                ) from e

    def update_proposal(self, proposal: WriteProposal) -> bool:
        """Update a proposal with new data.
        
        Args:
            proposal: The proposal with updated data.
            
        Returns:
            True if updated, False if proposal not found.
        """
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    """
                    UPDATE proposals SET
                        type = ?, target_path = ?, reason = ?,
                        content = ?, patch = ?, new_scope = ?,
                        status = ?, memory_id = ?,
                        deprecation_reason = ?, source_scope = ?,
                        reviewed_at = ?, reviewer_notes = ?,
                        retry_count = ?, committed_at = ?, commit_error = ?
                    WHERE proposal_id = ?
                    """,
                    (
                        proposal.type.value,
                        proposal.target_path,
                        proposal.reason,
                        proposal.content,
                        proposal.patch,
                        proposal.new_scope,
                        proposal.status.value,
                        proposal.memory_id,
                        proposal.deprecation_reason,
                        proposal.source_scope,
                        proposal.reviewed_at.isoformat() if proposal.reviewed_at else None,
                        proposal.reviewer_notes,
                        proposal.retry_count,
                        proposal.committed_at.isoformat() if proposal.committed_at else None,
                        proposal.commit_error,
                        proposal.proposal_id,
                    ),
                )
                conn.commit()
                return cursor.rowcount > 0
                
            except sqlite3.Error as e:
                raise QueueError(
                    f"Failed to update proposal: {e}",
                    operation="update_proposal",
                ) from e

    def increment_retry(self, proposal_id: str) -> int:
        """Increment the retry count for a proposal.
        
        Args:
            proposal_id: The proposal ID.
            
        Returns:
            The new retry count.
        """
        with self._get_connection() as conn:
            try:
                conn.execute(
                    "UPDATE proposals SET retry_count = retry_count + 1 WHERE proposal_id = ?",
                    (proposal_id,),
                )
                conn.commit()
                
                cursor = conn.execute(
                    "SELECT retry_count FROM proposals WHERE proposal_id = ?",
                    (proposal_id,),
                )
                row = cursor.fetchone()
                return row["retry_count"] if row else 0
                
            except sqlite3.Error as e:
                raise QueueError(
                    f"Failed to increment retry count: {e}",
                    operation="increment_retry",
                ) from e

    def set_commit_error(self, proposal_id: str, error: str) -> None:
        """Set the commit error for a failed proposal.
        
        Args:
            proposal_id: The proposal ID.
            error: The error message.
        """
        with self._get_connection() as conn:
            try:
                conn.execute(
                    """
                    UPDATE proposals 
                    SET status = 'failed', commit_error = ?
                    WHERE proposal_id = ?
                    """,
                    (error, proposal_id),
                )
                
                self._log_action(
                    conn,
                    proposal_id,
                    "commit_failed",
                    None,
                    "failed",
                    error,
                )
                
                conn.commit()
                
            except sqlite3.Error as e:
                raise QueueError(
                    f"Failed to set commit error: {e}",
                    operation="set_commit_error",
                ) from e

    def delete(self, proposal_id: str) -> bool:
        """Delete a proposal from the queue.
        
        Args:
            proposal_id: The proposal ID to delete.
            
        Returns:
            True if deleted, False if not found.
        """
        with self._get_connection() as conn:
            try:
                conn.execute(
                    "DELETE FROM review_log WHERE proposal_id = ?",
                    (proposal_id,),
                )
                cursor = conn.execute(
                    "DELETE FROM proposals WHERE proposal_id = ?",
                    (proposal_id,),
                )
                conn.commit()
                return cursor.rowcount > 0
                
            except sqlite3.Error as e:
                raise QueueError(
                    f"Failed to delete proposal: {e}",
                    operation="delete",
                ) from e

    def get_stats(self) -> dict:
        """Get queue statistics.
        
        Returns:
            Dictionary with queue statistics.
        """
        with self._get_connection() as conn:
            try:
                stats = {}
                
                cursor = conn.execute(
                    """
                    SELECT status, COUNT(*) as count 
                    FROM proposals 
                    GROUP BY status
                    """
                )
                stats["by_status"] = {row["status"]: row["count"] for row in cursor.fetchall()}
                
                cursor = conn.execute("SELECT COUNT(*) as total FROM proposals")
                stats["total"] = cursor.fetchone()["total"]
                
                cursor = conn.execute(
                    """
                    SELECT type, COUNT(*) as count 
                    FROM proposals 
                    GROUP BY type
                    """
                )
                stats["by_type"] = {row["type"]: row["count"] for row in cursor.fetchall()}
                
                return stats
                
            except sqlite3.Error as e:
                raise QueueError(
                    f"Failed to get queue stats: {e}",
                    operation="get_stats",
                ) from e

    def get_history(self, proposal_id: str) -> list[dict]:
        """Get the review history for a proposal.
        
        Args:
            proposal_id: The proposal ID.
            
        Returns:
            List of history entries.
        """
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    """
                    SELECT * FROM review_log 
                    WHERE proposal_id = ? 
                    ORDER BY timestamp ASC
                    """,
                    (proposal_id,),
                )
                return [dict(row) for row in cursor.fetchall()]
                
            except sqlite3.Error as e:
                raise QueueError(
                    f"Failed to get proposal history: {e}",
                    operation="get_history",
                ) from e

    def has_pending_for_path(self, target_path: str) -> bool:
        """Check if there are pending proposals for a path.
        
        Args:
            target_path: The target path to check.
            
        Returns:
            True if there are pending proposals.
        """
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    """
                    SELECT COUNT(*) as count FROM proposals 
                    WHERE target_path = ? AND status IN ('pending', 'in_review', 'approved')
                    """,
                    (target_path,),
                )
                return cursor.fetchone()["count"] > 0
                
            except sqlite3.Error as e:
                raise QueueError(
                    f"Failed to check pending for path: {e}",
                    operation="has_pending_for_path",
                ) from e

    def _log_action(
        self,
        conn: sqlite3.Connection,
        proposal_id: str,
        action: str,
        from_status: str | None,
        to_status: str | None,
        notes: str | None,
    ) -> None:
        """Log an action to the review log."""
        conn.execute(
            """
            INSERT INTO review_log (proposal_id, action, from_status, to_status, notes, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (proposal_id, action, from_status, to_status, notes, datetime.now().isoformat()),
        )

    def _row_to_proposal(self, row: sqlite3.Row) -> WriteProposal:
        """Convert a database row to a WriteProposal."""
        return WriteProposal(
            proposal_id=row["proposal_id"],
            type=ProposalType(row["type"]),
            target_path=row["target_path"],
            reason=row["reason"],
            content=row["content"],
            patch=row["patch"],
            new_scope=row["new_scope"],
            proposed_by=row["proposed_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
            status=ProposalStatus(row["status"]),
            memory_id=row["memory_id"],
            deprecation_reason=row["deprecation_reason"],
            source_scope=row["source_scope"],
            reviewed_at=datetime.fromisoformat(row["reviewed_at"]) if row["reviewed_at"] else None,
            reviewer_notes=row["reviewer_notes"],
            retry_count=row["retry_count"],
            committed_at=datetime.fromisoformat(row["committed_at"]) if row["committed_at"] else None,
            commit_error=row["commit_error"],
        )
