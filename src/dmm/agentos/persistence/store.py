"""SQLite-based persistence store for AgentOS runtime state.

This module provides persistent storage for:
- Agent runtime state
- Inter-agent messages
- Self-modification audit log
- Session management
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator

from dmm.agentos.persistence.models import (
    AgentState,
    AgentStatus,
    MessageDirection,
    MessageRecord,
    ModificationLevel,
    ModificationRecord,
    ModificationStatus,
    SessionRecord,
)


class AgentOSStoreError(Exception):
    """Error in AgentOS store operations."""
    
    def __init__(
        self,
        message: str,
        operation: str | None = None,
        cause: Exception | None = None,
    ):
        self.operation = operation
        self.cause = cause
        super().__init__(message)


# Database schema
SCHEMA = """
-- Agent runtime state
CREATE TABLE IF NOT EXISTS agent_states (
    agent_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'idle',
    current_task_id TEXT,
    tokens_used INTEGER DEFAULT 0,
    api_calls_made INTEGER DEFAULT 0,
    last_active TEXT,
    error_message TEXT,
    context_data_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (agent_id, session_id)
);

CREATE INDEX IF NOT EXISTS idx_agent_states_session ON agent_states(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_states_status ON agent_states(status);

-- Message history
CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    sender_id TEXT NOT NULL,
    recipient_id TEXT NOT NULL,
    message_type TEXT NOT NULL,
    direction TEXT NOT NULL,
    content_json TEXT,
    correlation_id TEXT,
    timestamp TEXT NOT NULL,
    delivered_at TEXT,
    read_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient_id);
CREATE INDEX IF NOT EXISTS idx_messages_correlation ON messages(correlation_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp DESC);

-- Self-modification audit log
CREATE TABLE IF NOT EXISTS modifications (
    modification_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    level TEXT NOT NULL,
    status TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    description TEXT NOT NULL,
    diff_json TEXT,
    reason TEXT,
    requested_at TEXT NOT NULL,
    reviewed_at TEXT,
    reviewed_by TEXT,
    applied_at TEXT,
    rollback_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_modifications_session ON modifications(session_id);
CREATE INDEX IF NOT EXISTS idx_modifications_agent ON modifications(agent_id);
CREATE INDEX IF NOT EXISTS idx_modifications_status ON modifications(status);
CREATE INDEX IF NOT EXISTS idx_modifications_level ON modifications(level);

-- Sessions
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    primary_agent_id TEXT,
    active_agents_json TEXT,
    tasks_created INTEGER DEFAULT 0,
    tasks_completed INTEGER DEFAULT 0,
    messages_sent INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    metadata_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(ended_at) WHERE ended_at IS NULL;
"""


class AgentOSStore:
    """SQLite-based persistence store for AgentOS.
    
    Provides persistent storage for agent runtime state, messages,
    self-modification audit logs, and session management.
    
    Example:
        store = AgentOSStore(Path(".dmm/index/agentos.db"))
        store.initialize()
        
        # Save agent state
        state = AgentState(agent_id="agent_001", session_id="session_001")
        store.save_agent_state(state)
        
        # Get agent state
        state = store.get_agent_state("agent_001", "session_001")
    """
    
    def __init__(self, db_path: Path) -> None:
        """Initialize the store.
        
        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        self._connection: sqlite3.Connection | None = None
    
    def initialize(self) -> None:
        """Initialize database schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with self._get_connection() as conn:
            conn.executescript(SCHEMA)
            conn.commit()
    
    def close(self) -> None:
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
    
    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
            )
            self._connection.row_factory = sqlite3.Row
        
        try:
            yield self._connection
        except sqlite3.Error as e:
            self._connection.rollback()
            raise AgentOSStoreError(f"Database error: {e}", cause=e)
    
    # =========================================================================
    # Agent State Operations
    # =========================================================================
    
    def save_agent_state(self, state: AgentState) -> None:
        """Save or update agent state.
        
        Args:
            state: Agent state to save.
        """
        state.updated_at = datetime.now()
        
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO agent_states (
                        agent_id, session_id, status, current_task_id,
                        tokens_used, api_calls_made, last_active,
                        error_message, context_data_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        state.agent_id,
                        state.session_id,
                        state.status.value,
                        state.current_task_id,
                        state.tokens_used,
                        state.api_calls_made,
                        state.last_active.isoformat() if state.last_active else None,
                        state.error_message,
                        json.dumps(state.context_data),
                        state.created_at.isoformat(),
                        state.updated_at.isoformat(),
                    ),
                )
                conn.commit()
        except sqlite3.Error as e:
            raise AgentOSStoreError(
                f"Failed to save agent state: {e}",
                operation="save_agent_state",
                cause=e,
            )
    
    def get_agent_state(
        self,
        agent_id: str,
        session_id: str,
    ) -> AgentState | None:
        """Get agent state.
        
        Args:
            agent_id: Agent identifier.
            session_id: Session identifier.
            
        Returns:
            AgentState or None if not found.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM agent_states
                    WHERE agent_id = ? AND session_id = ?
                    """,
                    (agent_id, session_id),
                )
                row = cursor.fetchone()
                
                if row:
                    return self._row_to_agent_state(row)
                return None
        except sqlite3.Error as e:
            raise AgentOSStoreError(
                f"Failed to get agent state: {e}",
                operation="get_agent_state",
                cause=e,
            )
    
    def get_agent_states_for_session(
        self,
        session_id: str,
    ) -> list[AgentState]:
        """Get all agent states for a session.
        
        Args:
            session_id: Session identifier.
            
        Returns:
            List of agent states.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM agent_states WHERE session_id = ?",
                    (session_id,),
                )
                return [self._row_to_agent_state(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise AgentOSStoreError(
                f"Failed to get agent states: {e}",
                operation="get_agent_states_for_session",
                cause=e,
            )
    
    def update_agent_status(
        self,
        agent_id: str,
        session_id: str,
        status: AgentStatus,
        error_message: str | None = None,
    ) -> None:
        """Update agent status.
        
        Args:
            agent_id: Agent identifier.
            session_id: Session identifier.
            status: New status.
            error_message: Optional error message.
        """
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE agent_states
                    SET status = ?, error_message = ?, 
                        last_active = ?, updated_at = ?
                    WHERE agent_id = ? AND session_id = ?
                    """,
                    (
                        status.value,
                        error_message,
                        datetime.now().isoformat(),
                        datetime.now().isoformat(),
                        agent_id,
                        session_id,
                    ),
                )
                conn.commit()
        except sqlite3.Error as e:
            raise AgentOSStoreError(
                f"Failed to update agent status: {e}",
                operation="update_agent_status",
                cause=e,
            )
    
    def _row_to_agent_state(self, row: sqlite3.Row) -> AgentState:
        """Convert database row to AgentState."""
        return AgentState(
            agent_id=row["agent_id"],
            session_id=row["session_id"],
            status=AgentStatus(row["status"]),
            current_task_id=row["current_task_id"],
            tokens_used=row["tokens_used"],
            api_calls_made=row["api_calls_made"],
            last_active=datetime.fromisoformat(row["last_active"]) if row["last_active"] else None,
            error_message=row["error_message"],
            context_data=json.loads(row["context_data_json"]) if row["context_data_json"] else {},
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
    
    # =========================================================================
    # Message Operations
    # =========================================================================
    
    def save_message(self, message: MessageRecord) -> None:
        """Save a message record.
        
        Args:
            message: Message to save.
        """
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO messages (
                        message_id, session_id, sender_id, recipient_id,
                        message_type, direction, content_json, correlation_id,
                        timestamp, delivered_at, read_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message.message_id,
                        message.session_id,
                        message.sender_id,
                        message.recipient_id,
                        message.message_type,
                        message.direction.value,
                        json.dumps(message.content),
                        message.correlation_id,
                        message.timestamp.isoformat(),
                        message.delivered_at.isoformat() if message.delivered_at else None,
                        message.read_at.isoformat() if message.read_at else None,
                    ),
                )
                conn.commit()
        except sqlite3.Error as e:
            raise AgentOSStoreError(
                f"Failed to save message: {e}",
                operation="save_message",
                cause=e,
            )
    
    def get_messages_for_session(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list[MessageRecord]:
        """Get messages for a session.
        
        Args:
            session_id: Session identifier.
            limit: Maximum messages to return.
            
        Returns:
            List of messages, newest first.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM messages
                    WHERE session_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (session_id, limit),
                )
                return [self._row_to_message(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise AgentOSStoreError(
                f"Failed to get messages: {e}",
                operation="get_messages_for_session",
                cause=e,
            )
    
    def get_messages_for_agent(
        self,
        agent_id: str,
        session_id: str | None = None,
        direction: MessageDirection | None = None,
        limit: int = 100,
    ) -> list[MessageRecord]:
        """Get messages for an agent.
        
        Args:
            agent_id: Agent identifier.
            session_id: Optional session filter.
            direction: Optional direction filter.
            limit: Maximum messages to return.
            
        Returns:
            List of messages.
        """
        try:
            with self._get_connection() as conn:
                query = """
                    SELECT * FROM messages
                    WHERE (sender_id = ? OR recipient_id = ?)
                """
                params: list[Any] = [agent_id, agent_id]
                
                if session_id:
                    query += " AND session_id = ?"
                    params.append(session_id)
                
                if direction:
                    query += " AND direction = ?"
                    params.append(direction.value)
                
                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)
                
                cursor = conn.execute(query, params)
                return [self._row_to_message(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise AgentOSStoreError(
                f"Failed to get messages: {e}",
                operation="get_messages_for_agent",
                cause=e,
            )
    
    def mark_message_delivered(
        self,
        message_id: str,
        delivered_at: datetime | None = None,
    ) -> None:
        """Mark a message as delivered."""
        delivered_at = delivered_at or datetime.now()
        
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE messages SET delivered_at = ? WHERE message_id = ?",
                    (delivered_at.isoformat(), message_id),
                )
                conn.commit()
        except sqlite3.Error as e:
            raise AgentOSStoreError(
                f"Failed to mark message delivered: {e}",
                operation="mark_message_delivered",
                cause=e,
            )
    
    def mark_message_read(
        self,
        message_id: str,
        read_at: datetime | None = None,
    ) -> None:
        """Mark a message as read."""
        read_at = read_at or datetime.now()
        
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE messages SET read_at = ? WHERE message_id = ?",
                    (read_at.isoformat(), message_id),
                )
                conn.commit()
        except sqlite3.Error as e:
            raise AgentOSStoreError(
                f"Failed to mark message read: {e}",
                operation="mark_message_read",
                cause=e,
            )
    
    def _row_to_message(self, row: sqlite3.Row) -> MessageRecord:
        """Convert database row to MessageRecord."""
        return MessageRecord(
            message_id=row["message_id"],
            session_id=row["session_id"],
            sender_id=row["sender_id"],
            recipient_id=row["recipient_id"],
            message_type=row["message_type"],
            direction=MessageDirection(row["direction"]),
            content=json.loads(row["content_json"]) if row["content_json"] else {},
            correlation_id=row["correlation_id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            delivered_at=datetime.fromisoformat(row["delivered_at"]) if row["delivered_at"] else None,
            read_at=datetime.fromisoformat(row["read_at"]) if row["read_at"] else None,
        )
    
    # =========================================================================
    # Modification Operations
    # =========================================================================
    
    def save_modification(self, modification: ModificationRecord) -> None:
        """Save a modification record.
        
        Args:
            modification: Modification to save.
        """
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO modifications (
                        modification_id, session_id, agent_id, level, status,
                        target_type, target_id, description, diff_json, reason,
                        requested_at, reviewed_at, reviewed_by, applied_at, rollback_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        modification.modification_id,
                        modification.session_id,
                        modification.agent_id,
                        modification.level.value,
                        modification.status.value,
                        modification.target_type,
                        modification.target_id,
                        modification.description,
                        json.dumps(modification.diff),
                        modification.reason,
                        modification.requested_at.isoformat(),
                        modification.reviewed_at.isoformat() if modification.reviewed_at else None,
                        modification.reviewed_by,
                        modification.applied_at.isoformat() if modification.applied_at else None,
                        modification.rollback_at.isoformat() if modification.rollback_at else None,
                    ),
                )
                conn.commit()
        except sqlite3.Error as e:
            raise AgentOSStoreError(
                f"Failed to save modification: {e}",
                operation="save_modification",
                cause=e,
            )
    
    def get_modification(self, modification_id: str) -> ModificationRecord | None:
        """Get a modification record.
        
        Args:
            modification_id: Modification identifier.
            
        Returns:
            ModificationRecord or None if not found.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM modifications WHERE modification_id = ?",
                    (modification_id,),
                )
                row = cursor.fetchone()
                
                if row:
                    return self._row_to_modification(row)
                return None
        except sqlite3.Error as e:
            raise AgentOSStoreError(
                f"Failed to get modification: {e}",
                operation="get_modification",
                cause=e,
            )
    
    def get_pending_modifications(
        self,
        level: ModificationLevel | None = None,
    ) -> list[ModificationRecord]:
        """Get pending modification requests.
        
        Args:
            level: Optional filter by level.
            
        Returns:
            List of pending modifications.
        """
        try:
            with self._get_connection() as conn:
                if level:
                    cursor = conn.execute(
                        """
                        SELECT * FROM modifications
                        WHERE status = 'pending' AND level = ?
                        ORDER BY requested_at
                        """,
                        (level.value,),
                    )
                else:
                    cursor = conn.execute(
                        """
                        SELECT * FROM modifications
                        WHERE status = 'pending'
                        ORDER BY requested_at
                        """,
                    )
                return [self._row_to_modification(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise AgentOSStoreError(
                f"Failed to get pending modifications: {e}",
                operation="get_pending_modifications",
                cause=e,
            )
    
    def update_modification_status(
        self,
        modification_id: str,
        status: ModificationStatus,
        reviewed_by: str | None = None,
    ) -> None:
        """Update modification status.
        
        Args:
            modification_id: Modification identifier.
            status: New status.
            reviewed_by: Who reviewed (for approved/rejected).
        """
        now = datetime.now().isoformat()
        
        try:
            with self._get_connection() as conn:
                if status in (ModificationStatus.APPROVED, ModificationStatus.REJECTED):
                    conn.execute(
                        """
                        UPDATE modifications
                        SET status = ?, reviewed_at = ?, reviewed_by = ?
                        WHERE modification_id = ?
                        """,
                        (status.value, now, reviewed_by, modification_id),
                    )
                elif status == ModificationStatus.APPLIED:
                    conn.execute(
                        """
                        UPDATE modifications
                        SET status = ?, applied_at = ?
                        WHERE modification_id = ?
                        """,
                        (status.value, now, modification_id),
                    )
                elif status == ModificationStatus.ROLLED_BACK:
                    conn.execute(
                        """
                        UPDATE modifications
                        SET status = ?, rollback_at = ?
                        WHERE modification_id = ?
                        """,
                        (status.value, now, modification_id),
                    )
                else:
                    conn.execute(
                        "UPDATE modifications SET status = ? WHERE modification_id = ?",
                        (status.value, modification_id),
                    )
                conn.commit()
        except sqlite3.Error as e:
            raise AgentOSStoreError(
                f"Failed to update modification status: {e}",
                operation="update_modification_status",
                cause=e,
            )
    
    def _row_to_modification(self, row: sqlite3.Row) -> ModificationRecord:
        """Convert database row to ModificationRecord."""
        return ModificationRecord(
            modification_id=row["modification_id"],
            session_id=row["session_id"],
            agent_id=row["agent_id"],
            level=ModificationLevel(row["level"]),
            status=ModificationStatus(row["status"]),
            target_type=row["target_type"],
            target_id=row["target_id"],
            description=row["description"],
            diff=json.loads(row["diff_json"]) if row["diff_json"] else {},
            reason=row["reason"] or "",
            requested_at=datetime.fromisoformat(row["requested_at"]),
            reviewed_at=datetime.fromisoformat(row["reviewed_at"]) if row["reviewed_at"] else None,
            reviewed_by=row["reviewed_by"],
            applied_at=datetime.fromisoformat(row["applied_at"]) if row["applied_at"] else None,
            rollback_at=datetime.fromisoformat(row["rollback_at"]) if row["rollback_at"] else None,
        )
    
    # =========================================================================
    # Session Operations
    # =========================================================================
    
    def create_session(self, session: SessionRecord) -> None:
        """Create a new session.
        
        Args:
            session: Session to create.
        """
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO sessions (
                        session_id, started_at, ended_at, primary_agent_id,
                        active_agents_json, tasks_created, tasks_completed,
                        messages_sent, total_tokens, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session.session_id,
                        session.started_at.isoformat(),
                        session.ended_at.isoformat() if session.ended_at else None,
                        session.primary_agent_id,
                        json.dumps(session.active_agents),
                        session.tasks_created,
                        session.tasks_completed,
                        session.messages_sent,
                        session.total_tokens,
                        json.dumps(session.metadata),
                    ),
                )
                conn.commit()
        except sqlite3.Error as e:
            raise AgentOSStoreError(
                f"Failed to create session: {e}",
                operation="create_session",
                cause=e,
            )
    
    def get_session(self, session_id: str) -> SessionRecord | None:
        """Get a session.
        
        Args:
            session_id: Session identifier.
            
        Returns:
            SessionRecord or None if not found.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM sessions WHERE session_id = ?",
                    (session_id,),
                )
                row = cursor.fetchone()
                
                if row:
                    return self._row_to_session(row)
                return None
        except sqlite3.Error as e:
            raise AgentOSStoreError(
                f"Failed to get session: {e}",
                operation="get_session",
                cause=e,
            )
    
    def get_active_sessions(self) -> list[SessionRecord]:
        """Get all active sessions."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM sessions
                    WHERE ended_at IS NULL
                    ORDER BY started_at DESC
                    """,
                )
                return [self._row_to_session(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise AgentOSStoreError(
                f"Failed to get active sessions: {e}",
                operation="get_active_sessions",
                cause=e,
            )
    
    def end_session(
        self,
        session_id: str,
        ended_at: datetime | None = None,
    ) -> None:
        """End a session.
        
        Args:
            session_id: Session identifier.
            ended_at: End timestamp (defaults to now).
        """
        ended_at = ended_at or datetime.now()
        
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE sessions SET ended_at = ? WHERE session_id = ?",
                    (ended_at.isoformat(), session_id),
                )
                conn.commit()
        except sqlite3.Error as e:
            raise AgentOSStoreError(
                f"Failed to end session: {e}",
                operation="end_session",
                cause=e,
            )
    
    def update_session_stats(
        self,
        session_id: str,
        tasks_created: int | None = None,
        tasks_completed: int | None = None,
        messages_sent: int | None = None,
        total_tokens: int | None = None,
    ) -> None:
        """Update session statistics.
        
        Args:
            session_id: Session identifier.
            tasks_created: New tasks created count.
            tasks_completed: New tasks completed count.
            messages_sent: New messages sent count.
            total_tokens: New total tokens count.
        """
        updates = []
        params = []
        
        if tasks_created is not None:
            updates.append("tasks_created = ?")
            params.append(tasks_created)
        if tasks_completed is not None:
            updates.append("tasks_completed = ?")
            params.append(tasks_completed)
        if messages_sent is not None:
            updates.append("messages_sent = ?")
            params.append(messages_sent)
        if total_tokens is not None:
            updates.append("total_tokens = ?")
            params.append(total_tokens)
        
        if not updates:
            return
        
        params.append(session_id)
        
        try:
            with self._get_connection() as conn:
                conn.execute(
                    f"UPDATE sessions SET {', '.join(updates)} WHERE session_id = ?",
                    params,
                )
                conn.commit()
        except sqlite3.Error as e:
            raise AgentOSStoreError(
                f"Failed to update session stats: {e}",
                operation="update_session_stats",
                cause=e,
            )
    
    def _row_to_session(self, row: sqlite3.Row) -> SessionRecord:
        """Convert database row to SessionRecord."""
        return SessionRecord(
            session_id=row["session_id"],
            started_at=datetime.fromisoformat(row["started_at"]),
            ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
            primary_agent_id=row["primary_agent_id"],
            active_agents=json.loads(row["active_agents_json"]) if row["active_agents_json"] else [],
            tasks_created=row["tasks_created"],
            tasks_completed=row["tasks_completed"],
            messages_sent=row["messages_sent"],
            total_tokens=row["total_tokens"],
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
        )
    
    # =========================================================================
    # Utility Operations
    # =========================================================================
    
    def get_stats(self) -> dict[str, Any]:
        """Get store statistics.
        
        Returns:
            Dictionary of statistics.
        """
        try:
            with self._get_connection() as conn:
                stats = {}
                
                # Agent states
                cursor = conn.execute("SELECT COUNT(*) FROM agent_states")
                stats["agent_states"] = cursor.fetchone()[0]
                
                # Messages
                cursor = conn.execute("SELECT COUNT(*) FROM messages")
                stats["messages"] = cursor.fetchone()[0]
                
                # Modifications
                cursor = conn.execute("SELECT COUNT(*) FROM modifications")
                stats["modifications"] = cursor.fetchone()[0]
                
                # Pending modifications
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM modifications WHERE status = 'pending'"
                )
                stats["pending_modifications"] = cursor.fetchone()[0]
                
                # Sessions
                cursor = conn.execute("SELECT COUNT(*) FROM sessions")
                stats["sessions"] = cursor.fetchone()[0]
                
                # Active sessions
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM sessions WHERE ended_at IS NULL"
                )
                stats["active_sessions"] = cursor.fetchone()[0]
                
                return stats
        except sqlite3.Error as e:
            raise AgentOSStoreError(
                f"Failed to get stats: {e}",
                operation="get_stats",
                cause=e,
            )
    
    def cleanup_old_data(
        self,
        days: int = 30,
        keep_modifications: bool = True,
    ) -> dict[str, int]:
        """Clean up old data.
        
        Args:
            days: Delete data older than this many days.
            keep_modifications: Whether to keep modification records.
            
        Returns:
            Dictionary of deleted counts per table.
        """
        from datetime import timedelta
        
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        deleted = {}
        
        try:
            with self._get_connection() as conn:
                # Clean old messages
                cursor = conn.execute(
                    "DELETE FROM messages WHERE timestamp < ?",
                    (cutoff,),
                )
                deleted["messages"] = cursor.rowcount
                
                # Clean old agent states for ended sessions
                cursor = conn.execute(
                    """
                    DELETE FROM agent_states
                    WHERE session_id IN (
                        SELECT session_id FROM sessions
                        WHERE ended_at IS NOT NULL AND ended_at < ?
                    )
                    """,
                    (cutoff,),
                )
                deleted["agent_states"] = cursor.rowcount
                
                # Optionally clean old modifications
                if not keep_modifications:
                    cursor = conn.execute(
                        "DELETE FROM modifications WHERE requested_at < ?",
                        (cutoff,),
                    )
                    deleted["modifications"] = cursor.rowcount
                
                # Clean old sessions
                cursor = conn.execute(
                    "DELETE FROM sessions WHERE ended_at IS NOT NULL AND ended_at < ?",
                    (cutoff,),
                )
                deleted["sessions"] = cursor.rowcount
                
                conn.commit()
                return deleted
        except sqlite3.Error as e:
            raise AgentOSStoreError(
                f"Failed to cleanup old data: {e}",
                operation="cleanup_old_data",
                cause=e,
            )
