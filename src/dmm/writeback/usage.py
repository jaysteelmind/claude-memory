"""Usage tracking for memory retrievals."""

import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator

from dmm.core.constants import get_usage_db_path
from dmm.core.exceptions import UsageTrackingError
from dmm.models.usage import (
    MemoryHealthReport,
    MemoryUsageRecord,
    QueryLogEntry,
    UsageStats,
)


USAGE_SCHEMA_SQL = """
-- Query log table
CREATE TABLE IF NOT EXISTS query_log (
    query_id TEXT PRIMARY KEY,
    query_text TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    
    -- Query parameters
    budget INTEGER NOT NULL,
    baseline_budget INTEGER NOT NULL,
    scope_filter TEXT,
    
    -- Results
    baseline_files_returned INTEGER DEFAULT 0,
    retrieved_files_returned INTEGER DEFAULT 0,
    total_tokens_used INTEGER DEFAULT 0,
    
    -- Performance
    query_time_ms REAL DEFAULT 0.0,
    embedding_time_ms REAL DEFAULT 0.0,
    retrieval_time_ms REAL DEFAULT 0.0,
    assembly_time_ms REAL DEFAULT 0.0,
    
    -- Retrieved memory IDs (JSON array)
    retrieved_memory_ids_json TEXT DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_query_log_timestamp ON query_log(timestamp DESC);

-- Memory usage table
CREATE TABLE IF NOT EXISTS memory_usage (
    memory_id TEXT PRIMARY KEY,
    memory_path TEXT NOT NULL,
    
    -- Counts
    total_retrievals INTEGER DEFAULT 0,
    baseline_retrievals INTEGER DEFAULT 0,
    query_retrievals INTEGER DEFAULT 0,
    
    -- Timestamps
    first_used TEXT,
    last_used TEXT,
    
    -- Co-occurrence (JSON object: memory_id -> count)
    co_occurred_with_json TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_memory_usage_retrievals ON memory_usage(total_retrievals DESC);
CREATE INDEX IF NOT EXISTS idx_memory_usage_last_used ON memory_usage(last_used DESC);

-- Usage metadata
CREATE TABLE IF NOT EXISTS usage_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

INIT_USAGE_META_SQL = """
INSERT OR IGNORE INTO usage_meta (key, value, updated_at) VALUES
    ('schema_version', '1', datetime('now')),
    ('total_queries', '0', datetime('now'));
"""


def generate_query_id() -> str:
    """Generate a unique query ID."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    random_suffix = secrets.token_hex(4)
    return f"qry_{timestamp}_{random_suffix}"


class UsageTracker:
    """Tracks memory retrieval usage for analytics and optimization."""

    def __init__(self, base_path: Path | None = None) -> None:
        """Initialize the usage tracker.
        
        Args:
            base_path: Base path for the DMM directory. Defaults to cwd.
        """
        self._db_path = get_usage_db_path(base_path)
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
                conn.executescript(USAGE_SCHEMA_SQL)
                conn.executescript(INIT_USAGE_META_SQL)
                conn.commit()
            except sqlite3.Error as e:
                raise UsageTrackingError(
                    f"Failed to initialize usage database: {e}",
                    details={"operation": "initialize"},
                ) from e

    def close(self) -> None:
        """Close the database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def log_query(
        self,
        query_text: str,
        budget: int,
        baseline_budget: int,
        baseline_files: int,
        retrieved_files: int,
        total_tokens: int,
        retrieved_memory_ids: list[str],
        scope_filter: str | None = None,
        query_time_ms: float = 0.0,
        embedding_time_ms: float = 0.0,
        retrieval_time_ms: float = 0.0,
        assembly_time_ms: float = 0.0,
    ) -> str:
        """Log a query operation.
        
        Args:
            query_text: The query text.
            budget: Total token budget.
            baseline_budget: Baseline token budget.
            baseline_files: Number of baseline files returned.
            retrieved_files: Number of retrieved files returned.
            total_tokens: Total tokens used.
            retrieved_memory_ids: List of memory IDs that were retrieved.
            scope_filter: Optional scope filter used.
            query_time_ms: Total query time in milliseconds.
            embedding_time_ms: Embedding time in milliseconds.
            retrieval_time_ms: Retrieval time in milliseconds.
            assembly_time_ms: Assembly time in milliseconds.
            
        Returns:
            The generated query ID.
        """
        query_id = generate_query_id()
        timestamp = datetime.now()

        with self._get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO query_log (
                        query_id, query_text, timestamp,
                        budget, baseline_budget, scope_filter,
                        baseline_files_returned, retrieved_files_returned, total_tokens_used,
                        query_time_ms, embedding_time_ms, retrieval_time_ms, assembly_time_ms,
                        retrieved_memory_ids_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        query_id,
                        query_text,
                        timestamp.isoformat(),
                        budget,
                        baseline_budget,
                        scope_filter,
                        baseline_files,
                        retrieved_files,
                        total_tokens,
                        query_time_ms,
                        embedding_time_ms,
                        retrieval_time_ms,
                        assembly_time_ms,
                        json.dumps(retrieved_memory_ids),
                    ),
                )
                conn.commit()

                self._update_memory_usage(conn, retrieved_memory_ids, timestamp, is_baseline=False)

                return query_id

            except sqlite3.Error as e:
                raise UsageTrackingError(
                    f"Failed to log query: {e}",
                    details={"operation": "log_query"},
                ) from e

    def log_baseline_retrieval(
        self,
        memory_ids: list[str],
        memory_paths: dict[str, str],
    ) -> None:
        """Log baseline memory retrievals.
        
        Args:
            memory_ids: List of baseline memory IDs retrieved.
            memory_paths: Mapping of memory ID to path.
        """
        timestamp = datetime.now()

        with self._get_connection() as conn:
            try:
                for memory_id in memory_ids:
                    path = memory_paths.get(memory_id, "")
                    
                    conn.execute(
                        """
                        INSERT INTO memory_usage (
                            memory_id, memory_path, total_retrievals, baseline_retrievals,
                            first_used, last_used
                        ) VALUES (?, ?, 1, 1, ?, ?)
                        ON CONFLICT(memory_id) DO UPDATE SET
                            total_retrievals = total_retrievals + 1,
                            baseline_retrievals = baseline_retrievals + 1,
                            last_used = excluded.last_used
                        """,
                        (memory_id, path, timestamp.isoformat(), timestamp.isoformat()),
                    )

                conn.commit()

            except sqlite3.Error as e:
                raise UsageTrackingError(
                    f"Failed to log baseline retrieval: {e}",
                    details={"operation": "log_baseline_retrieval"},
                ) from e

    def _update_memory_usage(
        self,
        conn: sqlite3.Connection,
        memory_ids: list[str],
        timestamp: datetime,
        is_baseline: bool = False,
    ) -> None:
        """Update memory usage records.
        
        Args:
            conn: Database connection.
            memory_ids: List of memory IDs retrieved.
            timestamp: Timestamp of retrieval.
            is_baseline: Whether these are baseline retrievals.
        """
        for memory_id in memory_ids:
            if is_baseline:
                conn.execute(
                    """
                    INSERT INTO memory_usage (
                        memory_id, memory_path, total_retrievals, baseline_retrievals,
                        first_used, last_used
                    ) VALUES (?, '', 1, 1, ?, ?)
                    ON CONFLICT(memory_id) DO UPDATE SET
                        total_retrievals = total_retrievals + 1,
                        baseline_retrievals = baseline_retrievals + 1,
                        last_used = excluded.last_used
                    """,
                    (memory_id, timestamp.isoformat(), timestamp.isoformat()),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO memory_usage (
                        memory_id, memory_path, total_retrievals, query_retrievals,
                        first_used, last_used
                    ) VALUES (?, '', 1, 1, ?, ?)
                    ON CONFLICT(memory_id) DO UPDATE SET
                        total_retrievals = total_retrievals + 1,
                        query_retrievals = query_retrievals + 1,
                        last_used = excluded.last_used
                    """,
                    (memory_id, timestamp.isoformat(), timestamp.isoformat()),
                )

        if len(memory_ids) > 1:
            self._update_co_occurrence(conn, memory_ids)

        conn.commit()

    def _update_co_occurrence(
        self,
        conn: sqlite3.Connection,
        memory_ids: list[str],
    ) -> None:
        """Update co-occurrence counts for memories retrieved together.
        
        Args:
            conn: Database connection.
            memory_ids: List of memory IDs that appeared together.
        """
        for i, memory_id in enumerate(memory_ids):
            cursor = conn.execute(
                "SELECT co_occurred_with_json FROM memory_usage WHERE memory_id = ?",
                (memory_id,),
            )
            row = cursor.fetchone()
            
            if row:
                co_occurred = json.loads(row["co_occurred_with_json"])
            else:
                co_occurred = {}

            for j, other_id in enumerate(memory_ids):
                if i != j:
                    co_occurred[other_id] = co_occurred.get(other_id, 0) + 1

            conn.execute(
                """
                UPDATE memory_usage 
                SET co_occurred_with_json = ?
                WHERE memory_id = ?
                """,
                (json.dumps(co_occurred), memory_id),
            )

    def get_memory_usage(self, memory_id: str) -> MemoryUsageRecord | None:
        """Get usage record for a specific memory.
        
        Args:
            memory_id: The memory ID.
            
        Returns:
            MemoryUsageRecord if found, None otherwise.
        """
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    "SELECT * FROM memory_usage WHERE memory_id = ?",
                    (memory_id,),
                )
                row = cursor.fetchone()
                
                if not row:
                    return None

                return MemoryUsageRecord(
                    memory_id=row["memory_id"],
                    memory_path=row["memory_path"],
                    total_retrievals=row["total_retrievals"],
                    baseline_retrievals=row["baseline_retrievals"],
                    query_retrievals=row["query_retrievals"],
                    first_used=datetime.fromisoformat(row["first_used"]) if row["first_used"] else None,
                    last_used=datetime.fromisoformat(row["last_used"]) if row["last_used"] else None,
                    co_occurred_with=json.loads(row["co_occurred_with_json"]),
                )

            except sqlite3.Error as e:
                raise UsageTrackingError(
                    f"Failed to get memory usage: {e}",
                    details={"operation": "get_memory_usage"},
                ) from e

    def get_most_retrieved(self, limit: int = 10) -> list[MemoryUsageRecord]:
        """Get the most frequently retrieved memories.
        
        Args:
            limit: Maximum number of results.
            
        Returns:
            List of MemoryUsageRecord sorted by retrieval count.
        """
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    """
                    SELECT * FROM memory_usage 
                    ORDER BY total_retrievals DESC 
                    LIMIT ?
                    """,
                    (limit,),
                )
                
                return [self._row_to_usage_record(row) for row in cursor.fetchall()]

            except sqlite3.Error as e:
                raise UsageTrackingError(
                    f"Failed to get most retrieved: {e}",
                    details={"operation": "get_most_retrieved"},
                ) from e

    def get_least_retrieved(self, limit: int = 10) -> list[MemoryUsageRecord]:
        """Get the least frequently retrieved memories.
        
        Args:
            limit: Maximum number of results.
            
        Returns:
            List of MemoryUsageRecord sorted by retrieval count ascending.
        """
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    """
                    SELECT * FROM memory_usage 
                    WHERE total_retrievals > 0
                    ORDER BY total_retrievals ASC 
                    LIMIT ?
                    """,
                    (limit,),
                )
                
                return [self._row_to_usage_record(row) for row in cursor.fetchall()]

            except sqlite3.Error as e:
                raise UsageTrackingError(
                    f"Failed to get least retrieved: {e}",
                    details={"operation": "get_least_retrieved"},
                ) from e

    def get_stale_memories(
        self,
        days_threshold: int = 30,
        limit: int = 50,
    ) -> list[MemoryUsageRecord]:
        """Get memories that haven't been retrieved recently.
        
        Args:
            days_threshold: Number of days to consider stale.
            limit: Maximum number of results.
            
        Returns:
            List of stale MemoryUsageRecord.
        """
        cutoff = (datetime.now() - timedelta(days=days_threshold)).isoformat()

        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    """
                    SELECT * FROM memory_usage 
                    WHERE last_used < ? OR last_used IS NULL
                    ORDER BY last_used ASC NULLS FIRST
                    LIMIT ?
                    """,
                    (cutoff, limit),
                )
                
                return [self._row_to_usage_record(row) for row in cursor.fetchall()]

            except sqlite3.Error as e:
                raise UsageTrackingError(
                    f"Failed to get stale memories: {e}",
                    details={"operation": "get_stale_memories"},
                ) from e

    def get_stats(
        self,
        days: int = 30,
    ) -> UsageStats:
        """Get aggregated usage statistics.
        
        Args:
            days: Number of days to include in statistics.
            
        Returns:
            UsageStats with aggregated data.
        """
        period_end = datetime.now()
        period_start = period_end - timedelta(days=days)

        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    """
                    SELECT 
                        COUNT(*) as total_queries,
                        AVG(query_time_ms) as avg_query_time_ms,
                        AVG(total_tokens_used) as avg_tokens,
                        SUM(retrieved_files_returned) as total_retrieved
                    FROM query_log
                    WHERE timestamp >= ?
                    """,
                    (period_start.isoformat(),),
                )
                row = cursor.fetchone()

                cursor = conn.execute(
                    "SELECT COUNT(DISTINCT memory_id) as unique_memories FROM memory_usage"
                )
                unique_row = cursor.fetchone()

                cursor = conn.execute(
                    """
                    SELECT memory_id, total_retrievals 
                    FROM memory_usage 
                    ORDER BY total_retrievals DESC 
                    LIMIT 10
                    """
                )
                most_retrieved = [(r["memory_id"], r["total_retrievals"]) for r in cursor.fetchall()]

                cursor = conn.execute(
                    """
                    SELECT memory_id, total_retrievals 
                    FROM memory_usage 
                    WHERE total_retrievals > 0
                    ORDER BY total_retrievals ASC 
                    LIMIT 10
                    """
                )
                least_retrieved = [(r["memory_id"], r["total_retrievals"]) for r in cursor.fetchall()]

                return UsageStats(
                    period_start=period_start,
                    period_end=period_end,
                    total_queries=row["total_queries"] or 0,
                    avg_query_time_ms=row["avg_query_time_ms"] or 0.0,
                    avg_tokens_per_query=row["avg_tokens"] or 0.0,
                    total_memories_retrieved=row["total_retrieved"] or 0,
                    unique_memories_retrieved=unique_row["unique_memories"] or 0,
                    most_retrieved=most_retrieved,
                    least_retrieved=least_retrieved,
                )

            except sqlite3.Error as e:
                raise UsageTrackingError(
                    f"Failed to get usage stats: {e}",
                    details={"operation": "get_stats"},
                ) from e

    def generate_health_report(
        self,
        stale_threshold_days: int = 30,
        hot_threshold_retrievals: int = 10,
    ) -> MemoryHealthReport:
        """Generate a health report for memory usage patterns.
        
        Args:
            stale_threshold_days: Days without retrieval to consider stale.
            hot_threshold_retrievals: Retrieval count to consider hot.
            
        Returns:
            MemoryHealthReport with analysis.
        """
        stale_memories = self.get_stale_memories(stale_threshold_days)
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM memory_usage 
                WHERE total_retrievals >= ?
                ORDER BY total_retrievals DESC
                """,
                (hot_threshold_retrievals,),
            )
            hot_records = [self._row_to_usage_record(row) for row in cursor.fetchall()]

        return MemoryHealthReport(
            generated_at=datetime.now(),
            stale_memories=[m.to_dict() for m in stale_memories],
            stale_threshold_days=stale_threshold_days,
            hot_memories=[m.to_dict() for m in hot_records],
            hot_threshold_retrievals=hot_threshold_retrievals,
            promotion_candidates=[],
            deprecation_candidates=[m.to_dict() for m in stale_memories[:10]],
        )

    def _row_to_usage_record(self, row: sqlite3.Row) -> MemoryUsageRecord:
        """Convert database row to MemoryUsageRecord."""
        return MemoryUsageRecord(
            memory_id=row["memory_id"],
            memory_path=row["memory_path"],
            total_retrievals=row["total_retrievals"],
            baseline_retrievals=row["baseline_retrievals"],
            query_retrievals=row["query_retrievals"],
            first_used=datetime.fromisoformat(row["first_used"]) if row["first_used"] else None,
            last_used=datetime.fromisoformat(row["last_used"]) if row["last_used"] else None,
            co_occurred_with=json.loads(row["co_occurred_with_json"]),
        )

    def clear_old_logs(self, days: int = 90) -> int:
        """Clear query logs older than specified days.
        
        Args:
            days: Age threshold in days.
            
        Returns:
            Number of logs deleted.
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    "DELETE FROM query_log WHERE timestamp < ?",
                    (cutoff,),
                )
                conn.commit()
                return cursor.rowcount

            except sqlite3.Error as e:
                raise UsageTrackingError(
                    f"Failed to clear old logs: {e}",
                    details={"operation": "clear_old_logs"},
                ) from e
