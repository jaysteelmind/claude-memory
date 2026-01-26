"""
Task store for persistence.

This module provides persistence for tasks using SQLite for indexing
and querying, with optional YAML file storage for human-readable
task definitions.
"""

import asyncio
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Optional

import yaml

from dmm.agentos.tasks.constants import (
    TaskStatus,
    DependencyType,
    TASKS_DB_NAME,
    TASKS_TABLE_NAME,
    TASK_DEPENDENCIES_TABLE_NAME,
    TASK_LOGS_TABLE_NAME,
    TASKS_DIR_NAME,
    ACTIVE_TASKS_DIR,
    PENDING_TASKS_DIR,
    COMPLETED_TASKS_DIR,
    FAILED_TASKS_DIR,
    TASK_INDEX_FILE,
    TASK_FILE_EXTENSION,
)
from dmm.agentos.tasks.models import (
    Task,
    TaskDependency,
    TaskResult,
    TaskOutput,
    TaskError,
)


# =============================================================================
# Database Schema
# =============================================================================

TASKS_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {TASKS_TABLE_NAME} (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    task_type TEXT NOT NULL,
    parent_id TEXT,
    depth INTEGER DEFAULT 0,
    assigned_agent TEXT,
    delegated_from TEXT,
    status TEXT NOT NULL,
    priority INTEGER DEFAULT 5,
    attempt_count INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    timeout_seconds REAL DEFAULT 300.0,
    inputs_json TEXT,
    outputs_json TEXT,
    requirements_json TEXT,
    constraints_json TEXT,
    execution_json TEXT,
    tags_json TEXT,
    metadata_json TEXT,
    scheduled_at TEXT,
    deadline TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    last_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON {TASKS_TABLE_NAME}(status);
CREATE INDEX IF NOT EXISTS idx_tasks_parent ON {TASKS_TABLE_NAME}(parent_id);
CREATE INDEX IF NOT EXISTS idx_tasks_agent ON {TASKS_TABLE_NAME}(assigned_agent);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON {TASKS_TABLE_NAME}(priority DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON {TASKS_TABLE_NAME}(created_at DESC);

CREATE TABLE IF NOT EXISTS {TASK_DEPENDENCIES_TABLE_NAME} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    depends_on_task_id TEXT NOT NULL,
    dependency_type TEXT NOT NULL,
    required INTEGER DEFAULT 1,
    output_mapping_json TEXT,
    resolved INTEGER DEFAULT 0,
    resolved_at TEXT,
    FOREIGN KEY (task_id) REFERENCES {TASKS_TABLE_NAME}(id) ON DELETE CASCADE,
    UNIQUE(task_id, depends_on_task_id)
);

CREATE INDEX IF NOT EXISTS idx_deps_task ON {TASK_DEPENDENCIES_TABLE_NAME}(task_id);
CREATE INDEX IF NOT EXISTS idx_deps_depends ON {TASK_DEPENDENCIES_TABLE_NAME}(depends_on_task_id);

CREATE TABLE IF NOT EXISTS {TASK_LOGS_TABLE_NAME} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    details_json TEXT,
    FOREIGN KEY (task_id) REFERENCES {TASKS_TABLE_NAME}(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_logs_task ON {TASK_LOGS_TABLE_NAME}(task_id);
CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON {TASK_LOGS_TABLE_NAME}(timestamp DESC);
"""


# =============================================================================
# Task Store Implementation
# =============================================================================

class TaskStore:
    """
    Persistent storage for tasks.
    
    Provides CRUD operations with SQLite backend and optional
    YAML file storage for human-readable task definitions.
    """
    
    def __init__(
        self,
        base_path: Path,
        use_file_storage: bool = True,
    ) -> None:
        """
        Initialize task store.
        
        Args:
            base_path: Base path for .dmm directory
            use_file_storage: Whether to also store tasks as YAML files
        """
        self._base_path = Path(base_path)
        self._use_file_storage = use_file_storage
        self._db_path = self._base_path / "index" / TASKS_DB_NAME
        self._tasks_dir = self._base_path / TASKS_DIR_NAME
        self._conn: Optional[sqlite3.Connection] = None
        self._initialized = False
    
    # -------------------------------------------------------------------------
    # Initialization
    # -------------------------------------------------------------------------
    
    def initialize(self) -> None:
        """Initialize the task store."""
        if self._initialized:
            return
        
        # Ensure directories exist
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        
        if self._use_file_storage:
            self._tasks_dir.mkdir(parents=True, exist_ok=True)
            (self._tasks_dir / ACTIVE_TASKS_DIR).mkdir(exist_ok=True)
            (self._tasks_dir / PENDING_TASKS_DIR).mkdir(exist_ok=True)
            (self._tasks_dir / COMPLETED_TASKS_DIR).mkdir(exist_ok=True)
            (self._tasks_dir / FAILED_TASKS_DIR).mkdir(exist_ok=True)
        
        # Initialize database
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(TASKS_SCHEMA)
        self._conn.commit()
        
        self._initialized = True
    
    def close(self) -> None:
        """Close the task store."""
        if self._conn:
            self._conn.close()
            self._conn = None
        self._initialized = False
    
    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """Context manager for database transactions."""
        if not self._conn:
            raise RuntimeError("TaskStore not initialized")
        
        cursor = self._conn.cursor()
        try:
            yield cursor
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cursor.close()
    
    def _ensure_initialized(self) -> None:
        """Ensure store is initialized."""
        if not self._initialized:
            self.initialize()
    
    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------
    
    def create(self, task: Task) -> str:
        """
        Create a new task.
        
        Args:
            task: Task to create
            
        Returns:
            Task ID
            
        Raises:
            ValueError: If task with same ID exists
        """
        self._ensure_initialized()
        
        # Validate task
        errors = task.validate()
        if errors:
            raise ValueError(f"Invalid task: {'; '.join(errors)}")
        
        with self._transaction() as cursor:
            # Check for existing task
            cursor.execute(
                f"SELECT id FROM {TASKS_TABLE_NAME} WHERE id = ?",
                (task.id,)
            )
            if cursor.fetchone():
                raise ValueError(f"Task with ID {task.id} already exists")
            
            # Insert task
            cursor.execute(
                f"""
                INSERT INTO {TASKS_TABLE_NAME} (
                    id, name, description, task_type, parent_id, depth,
                    assigned_agent, delegated_from, status, priority,
                    attempt_count, max_attempts, timeout_seconds,
                    inputs_json, outputs_json, requirements_json,
                    constraints_json, execution_json, tags_json, metadata_json,
                    scheduled_at, deadline, created_at, updated_at,
                    started_at, completed_at, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.name,
                    task.description,
                    task.task_type.value,
                    task.parent_id,
                    task.depth,
                    task.assigned_agent,
                    task.delegated_from,
                    task.execution.status.value,
                    task.priority,
                    task.execution.attempt_count,
                    task.constraints.max_attempts,
                    task.constraints.timeout_seconds,
                    json.dumps(task.inputs),
                    json.dumps(task.outputs.data if task.outputs else None),
                    json.dumps({
                        "skills": task.requirements.skills,
                        "tools": task.requirements.tools,
                        "memory_scopes": task.requirements.memory_scopes,
                        "memory_tags": task.requirements.memory_tags,
                        "min_context_tokens": task.requirements.min_context_tokens,
                        "max_context_tokens": task.requirements.max_context_tokens,
                    }),
                    json.dumps({
                        "timeout_seconds": task.constraints.timeout_seconds,
                        "max_attempts": task.constraints.max_attempts,
                        "retry_delay_seconds": task.constraints.retry_delay_seconds,
                        "retry_backoff_multiplier": task.constraints.retry_backoff_multiplier,
                        "allow_parallel": task.constraints.allow_parallel,
                        "require_approval": task.constraints.require_approval,
                        "allowed_tools": task.constraints.allowed_tools,
                        "denied_tools": task.constraints.denied_tools,
                    }),
                    json.dumps({
                        "status": task.execution.status.value,
                        "attempt_count": task.execution.attempt_count,
                        "started_at": task.execution.started_at.isoformat() if task.execution.started_at else None,
                        "completed_at": task.execution.completed_at.isoformat() if task.execution.completed_at else None,
                        "last_error": task.execution.last_error,
                        "execution_log": task.execution.execution_log,
                        "metrics": task.execution.metrics,
                    }),
                    json.dumps(task.tags),
                    json.dumps(task.metadata),
                    task.scheduled_at.isoformat() if task.scheduled_at else None,
                    task.deadline.isoformat() if task.deadline else None,
                    task.created_at.isoformat(),
                    task.updated_at.isoformat(),
                    task.execution.started_at.isoformat() if task.execution.started_at else None,
                    task.execution.completed_at.isoformat() if task.execution.completed_at else None,
                    task.execution.last_error,
                )
            )
            
            # Insert dependencies
            for dep in task.dependencies:
                cursor.execute(
                    f"""
                    INSERT INTO {TASK_DEPENDENCIES_TABLE_NAME} (
                        task_id, depends_on_task_id, dependency_type,
                        required, output_mapping_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        task.id,
                        dep.task_id,
                        dep.dependency_type.value,
                        1 if dep.required else 0,
                        json.dumps(dep.output_mapping) if dep.output_mapping else None,
                    )
                )
        
        # Write to file if enabled
        if self._use_file_storage:
            self._write_task_file(task)
        
        return task.id
    
    def get(self, task_id: str) -> Optional[Task]:
        """
        Get a task by ID.
        
        Args:
            task_id: Task ID
            
        Returns:
            Task or None if not found
        """
        self._ensure_initialized()
        
        with self._transaction() as cursor:
            cursor.execute(
                f"SELECT * FROM {TASKS_TABLE_NAME} WHERE id = ?",
                (task_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
            
            # Get dependencies
            cursor.execute(
                f"""
                SELECT depends_on_task_id, dependency_type, required, output_mapping_json
                FROM {TASK_DEPENDENCIES_TABLE_NAME}
                WHERE task_id = ?
                """,
                (task_id,)
            )
            deps_rows = cursor.fetchall()
            
            # Get subtask IDs
            cursor.execute(
                f"SELECT id FROM {TASKS_TABLE_NAME} WHERE parent_id = ?",
                (task_id,)
            )
            subtask_rows = cursor.fetchall()
            
            return self._row_to_task(row, deps_rows, subtask_rows)
    
    def update(self, task: Task) -> bool:
        """
        Update an existing task.
        
        Args:
            task: Task with updated data
            
        Returns:
            True if updated, False if not found
        """
        self._ensure_initialized()
        
        task.updated_at = datetime.utcnow()
        
        with self._transaction() as cursor:
            cursor.execute(
                f"""
                UPDATE {TASKS_TABLE_NAME} SET
                    name = ?, description = ?, task_type = ?, parent_id = ?,
                    depth = ?, assigned_agent = ?, delegated_from = ?,
                    status = ?, priority = ?, attempt_count = ?,
                    max_attempts = ?, timeout_seconds = ?,
                    inputs_json = ?, outputs_json = ?, requirements_json = ?,
                    constraints_json = ?, execution_json = ?, tags_json = ?,
                    metadata_json = ?, scheduled_at = ?, deadline = ?,
                    updated_at = ?, started_at = ?, completed_at = ?, last_error = ?
                WHERE id = ?
                """,
                (
                    task.name,
                    task.description,
                    task.task_type.value,
                    task.parent_id,
                    task.depth,
                    task.assigned_agent,
                    task.delegated_from,
                    task.execution.status.value,
                    task.priority,
                    task.execution.attempt_count,
                    task.constraints.max_attempts,
                    task.constraints.timeout_seconds,
                    json.dumps(task.inputs),
                    json.dumps(task.outputs.data if task.outputs else None),
                    json.dumps({
                        "skills": task.requirements.skills,
                        "tools": task.requirements.tools,
                        "memory_scopes": task.requirements.memory_scopes,
                        "memory_tags": task.requirements.memory_tags,
                        "min_context_tokens": task.requirements.min_context_tokens,
                        "max_context_tokens": task.requirements.max_context_tokens,
                    }),
                    json.dumps({
                        "timeout_seconds": task.constraints.timeout_seconds,
                        "max_attempts": task.constraints.max_attempts,
                        "retry_delay_seconds": task.constraints.retry_delay_seconds,
                        "retry_backoff_multiplier": task.constraints.retry_backoff_multiplier,
                        "allow_parallel": task.constraints.allow_parallel,
                        "require_approval": task.constraints.require_approval,
                        "allowed_tools": task.constraints.allowed_tools,
                        "denied_tools": task.constraints.denied_tools,
                    }),
                    json.dumps({
                        "status": task.execution.status.value,
                        "attempt_count": task.execution.attempt_count,
                        "started_at": task.execution.started_at.isoformat() if task.execution.started_at else None,
                        "completed_at": task.execution.completed_at.isoformat() if task.execution.completed_at else None,
                        "last_error": task.execution.last_error,
                        "execution_log": task.execution.execution_log,
                        "metrics": task.execution.metrics,
                    }),
                    json.dumps(task.tags),
                    json.dumps(task.metadata),
                    task.scheduled_at.isoformat() if task.scheduled_at else None,
                    task.deadline.isoformat() if task.deadline else None,
                    task.updated_at.isoformat(),
                    task.execution.started_at.isoformat() if task.execution.started_at else None,
                    task.execution.completed_at.isoformat() if task.execution.completed_at else None,
                    task.execution.last_error,
                    task.id,
                )
            )
            
            if cursor.rowcount == 0:
                return False
            
            # Update dependencies
            cursor.execute(
                f"DELETE FROM {TASK_DEPENDENCIES_TABLE_NAME} WHERE task_id = ?",
                (task.id,)
            )
            for dep in task.dependencies:
                cursor.execute(
                    f"""
                    INSERT INTO {TASK_DEPENDENCIES_TABLE_NAME} (
                        task_id, depends_on_task_id, dependency_type,
                        required, output_mapping_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        task.id,
                        dep.task_id,
                        dep.dependency_type.value,
                        1 if dep.required else 0,
                        json.dumps(dep.output_mapping) if dep.output_mapping else None,
                    )
                )
        
        # Update file if enabled
        if self._use_file_storage:
            self._write_task_file(task)
        
        return True
    
    def delete(self, task_id: str) -> bool:
        """
        Delete a task.
        
        Args:
            task_id: Task ID
            
        Returns:
            True if deleted, False if not found
        """
        self._ensure_initialized()
        
        with self._transaction() as cursor:
            # Get task for file deletion
            cursor.execute(
                f"SELECT status FROM {TASKS_TABLE_NAME} WHERE id = ?",
                (task_id,)
            )
            row = cursor.fetchone()
            if not row:
                return False
            
            status = row["status"]
            
            # Delete from database (cascade will handle dependencies and logs)
            cursor.execute(
                f"DELETE FROM {TASKS_TABLE_NAME} WHERE id = ?",
                (task_id,)
            )
        
        # Delete file if enabled
        if self._use_file_storage:
            self._delete_task_file(task_id, status)
        
        return True
    
    # -------------------------------------------------------------------------
    # Query Operations
    # -------------------------------------------------------------------------
    
    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        agent_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        """
        List tasks with optional filters.
        
        Args:
            status: Filter by status
            agent_id: Filter by assigned agent
            parent_id: Filter by parent task
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of tasks
        """
        self._ensure_initialized()
        
        conditions = []
        params: list[Any] = []
        
        if status is not None:
            conditions.append("status = ?")
            params.append(status.value)
        
        if agent_id is not None:
            conditions.append("assigned_agent = ?")
            params.append(agent_id)
        
        if parent_id is not None:
            conditions.append("parent_id = ?")
            params.append(parent_id)
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        with self._transaction() as cursor:
            cursor.execute(
                f"""
                SELECT * FROM {TASKS_TABLE_NAME}
                {where_clause}
                ORDER BY priority DESC, created_at DESC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset]
            )
            rows = cursor.fetchall()
            
            tasks = []
            for row in rows:
                # Get dependencies for each task
                cursor.execute(
                    f"""
                    SELECT depends_on_task_id, dependency_type, required, output_mapping_json
                    FROM {TASK_DEPENDENCIES_TABLE_NAME}
                    WHERE task_id = ?
                    """,
                    (row["id"],)
                )
                deps_rows = cursor.fetchall()
                
                # Get subtask IDs
                cursor.execute(
                    f"SELECT id FROM {TASKS_TABLE_NAME} WHERE parent_id = ?",
                    (row["id"],)
                )
                subtask_rows = cursor.fetchall()
                
                tasks.append(self._row_to_task(row, deps_rows, subtask_rows))
            
            return tasks
    
    def get_runnable_tasks(self, limit: int = 10) -> list[Task]:
        """
        Get tasks that are ready to run.
        
        Args:
            limit: Maximum number of results
            
        Returns:
            List of runnable tasks
        """
        self._ensure_initialized()
        
        with self._transaction() as cursor:
            # Get tasks with pending/scheduled status
            cursor.execute(
                f"""
                SELECT t.* FROM {TASKS_TABLE_NAME} t
                WHERE t.status IN ('pending', 'scheduled')
                AND NOT EXISTS (
                    SELECT 1 FROM {TASK_DEPENDENCIES_TABLE_NAME} d
                    JOIN {TASKS_TABLE_NAME} dt ON d.depends_on_task_id = dt.id
                    WHERE d.task_id = t.id
                    AND d.required = 1
                    AND dt.status NOT IN ('completed')
                )
                ORDER BY t.priority DESC, t.created_at ASC
                LIMIT ?
                """,
                (limit,)
            )
            rows = cursor.fetchall()
            
            tasks = []
            for row in rows:
                cursor.execute(
                    f"""
                    SELECT depends_on_task_id, dependency_type, required, output_mapping_json
                    FROM {TASK_DEPENDENCIES_TABLE_NAME}
                    WHERE task_id = ?
                    """,
                    (row["id"],)
                )
                deps_rows = cursor.fetchall()
                
                cursor.execute(
                    f"SELECT id FROM {TASKS_TABLE_NAME} WHERE parent_id = ?",
                    (row["id"],)
                )
                subtask_rows = cursor.fetchall()
                
                tasks.append(self._row_to_task(row, deps_rows, subtask_rows))
            
            return tasks
    
    def get_blocked_tasks(self) -> list[Task]:
        """Get all blocked tasks."""
        return self.list_tasks(status=TaskStatus.BLOCKED)
    
    def get_tasks_by_ids(self, task_ids: list[str]) -> list[Task]:
        """Get multiple tasks by IDs."""
        self._ensure_initialized()
        
        if not task_ids:
            return []
        
        placeholders = ",".join("?" * len(task_ids))
        
        with self._transaction() as cursor:
            cursor.execute(
                f"SELECT * FROM {TASKS_TABLE_NAME} WHERE id IN ({placeholders})",
                task_ids
            )
            rows = cursor.fetchall()
            
            tasks = []
            for row in rows:
                cursor.execute(
                    f"""
                    SELECT depends_on_task_id, dependency_type, required, output_mapping_json
                    FROM {TASK_DEPENDENCIES_TABLE_NAME}
                    WHERE task_id = ?
                    """,
                    (row["id"],)
                )
                deps_rows = cursor.fetchall()
                
                cursor.execute(
                    f"SELECT id FROM {TASKS_TABLE_NAME} WHERE parent_id = ?",
                    (row["id"],)
                )
                subtask_rows = cursor.fetchall()
                
                tasks.append(self._row_to_task(row, deps_rows, subtask_rows))
            
            return tasks
    
    def count_tasks(
        self,
        status: Optional[TaskStatus] = None,
        agent_id: Optional[str] = None,
    ) -> int:
        """Count tasks with optional filters."""
        self._ensure_initialized()
        
        conditions = []
        params: list[Any] = []
        
        if status is not None:
            conditions.append("status = ?")
            params.append(status.value)
        
        if agent_id is not None:
            conditions.append("assigned_agent = ?")
            params.append(agent_id)
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        with self._transaction() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) FROM {TASKS_TABLE_NAME} {where_clause}",
                params
            )
            return cursor.fetchone()[0]
    
    # -------------------------------------------------------------------------
    # Status Updates
    # -------------------------------------------------------------------------
    
    def update_status(
        self,
        task_id: str,
        new_status: TaskStatus,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Update task status.
        
        Args:
            task_id: Task ID
            new_status: New status
            error_message: Optional error message for failures
            
        Returns:
            True if updated
        """
        self._ensure_initialized()
        
        now = datetime.utcnow()
        
        with self._transaction() as cursor:
            # Get current task including execution_json
            cursor.execute(
                f"SELECT status, execution_json FROM {TASKS_TABLE_NAME} WHERE id = ?",
                (task_id,)
            )
            row = cursor.fetchone()
            if not row:
                return False
            
            # Parse and update execution_json
            execution_data = json.loads(row["execution_json"]) if row["execution_json"] else {}
            execution_data["status"] = new_status.value
            
            updates = ["status = ?", "updated_at = ?"]
            params: list[Any] = [new_status.value, now.isoformat()]
            
            if new_status == TaskStatus.RUNNING:
                updates.append("started_at = COALESCE(started_at, ?)")
                params.append(now.isoformat())
                if not execution_data.get("started_at"):
                    execution_data["started_at"] = now.isoformat()
            elif new_status.is_terminal():
                updates.append("completed_at = ?")
                params.append(now.isoformat())
                execution_data["completed_at"] = now.isoformat()
            
            if error_message:
                updates.append("last_error = ?")
                params.append(error_message)
                execution_data["last_error"] = error_message
            
            # Update execution_json
            updates.append("execution_json = ?")
            params.append(json.dumps(execution_data))
            
            params.append(task_id)
            
            cursor.execute(
                f"UPDATE {TASKS_TABLE_NAME} SET {', '.join(updates)} WHERE id = ?",
                params
            )
            
            return cursor.rowcount > 0
    
    def resolve_dependency(
        self,
        task_id: str,
        dependency_task_id: str,
    ) -> bool:
        """Mark a dependency as resolved."""
        self._ensure_initialized()
        
        with self._transaction() as cursor:
            cursor.execute(
                f"""
                UPDATE {TASK_DEPENDENCIES_TABLE_NAME}
                SET resolved = 1, resolved_at = ?
                WHERE task_id = ? AND depends_on_task_id = ?
                """,
                (datetime.utcnow().isoformat(), task_id, dependency_task_id)
            )
            return cursor.rowcount > 0
    
    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------
    
    def add_log_entry(
        self,
        task_id: str,
        message: str,
        level: str = "INFO",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Add a log entry for a task."""
        self._ensure_initialized()
        
        with self._transaction() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {TASK_LOGS_TABLE_NAME}
                (task_id, timestamp, level, message, details_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    datetime.utcnow().isoformat(),
                    level,
                    message,
                    json.dumps(details) if details else None,
                )
            )
    
    def get_task_logs(
        self,
        task_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get log entries for a task."""
        self._ensure_initialized()
        
        with self._transaction() as cursor:
            cursor.execute(
                f"""
                SELECT timestamp, level, message, details_json
                FROM {TASK_LOGS_TABLE_NAME}
                WHERE task_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (task_id, limit)
            )
            rows = cursor.fetchall()
            
            return [
                {
                    "timestamp": row["timestamp"],
                    "level": row["level"],
                    "message": row["message"],
                    "details": json.loads(row["details_json"]) if row["details_json"] else None,
                }
                for row in rows
            ]
    
    # -------------------------------------------------------------------------
    # File Operations
    # -------------------------------------------------------------------------
    
    def _get_task_dir(self, status: str) -> Path:
        """Get directory for task based on status."""
        if status in ("pending", "scheduled", "blocked"):
            return self._tasks_dir / PENDING_TASKS_DIR
        elif status in ("running", "paused"):
            return self._tasks_dir / ACTIVE_TASKS_DIR
        elif status == "completed":
            return self._tasks_dir / COMPLETED_TASKS_DIR
        else:
            return self._tasks_dir / FAILED_TASKS_DIR
    
    def _write_task_file(self, task: Task) -> None:
        """Write task to YAML file."""
        task_dir = self._get_task_dir(task.execution.status.value)
        file_path = task_dir / f"{task.id}{TASK_FILE_EXTENSION}"
        
        # Remove from other directories
        for dir_name in [PENDING_TASKS_DIR, ACTIVE_TASKS_DIR, COMPLETED_TASKS_DIR, FAILED_TASKS_DIR]:
            other_path = self._tasks_dir / dir_name / f"{task.id}{TASK_FILE_EXTENSION}"
            if other_path.exists() and other_path != file_path:
                other_path.unlink()
        
        # Write task data
        with open(file_path, "w") as f:
            yaml.dump(task.to_dict(), f, default_flow_style=False, sort_keys=False)
    
    def _delete_task_file(self, task_id: str, status: str) -> None:
        """Delete task file."""
        for dir_name in [PENDING_TASKS_DIR, ACTIVE_TASKS_DIR, COMPLETED_TASKS_DIR, FAILED_TASKS_DIR]:
            file_path = self._tasks_dir / dir_name / f"{task_id}{TASK_FILE_EXTENSION}"
            if file_path.exists():
                file_path.unlink()
    
    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------
    
    def _row_to_task(
        self,
        row: sqlite3.Row,
        deps_rows: list[sqlite3.Row],
        subtask_rows: list[sqlite3.Row],
    ) -> Task:
        """Convert database row to Task object."""
        # Parse JSON fields
        inputs = json.loads(row["inputs_json"]) if row["inputs_json"] else {}
        outputs_data = json.loads(row["outputs_json"]) if row["outputs_json"] else None
        requirements = json.loads(row["requirements_json"]) if row["requirements_json"] else {}
        constraints = json.loads(row["constraints_json"]) if row["constraints_json"] else {}
        execution_raw = json.loads(row["execution_json"]) if row["execution_json"] else {}
        tags = json.loads(row["tags_json"]) if row["tags_json"] else []
        metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        
        # Parse datetime fields in execution
        for dt_field in ["started_at", "completed_at"]:
            if execution_raw.get(dt_field) and isinstance(execution_raw[dt_field], str):
                execution_raw[dt_field] = datetime.fromisoformat(execution_raw[dt_field])
        execution = execution_raw
        
        # Parse dependencies
        dependencies = []
        blocked_by = []
        for dep_row in deps_rows:
            dep = TaskDependency(
                task_id=dep_row["depends_on_task_id"],
                dependency_type=DependencyType(dep_row["dependency_type"]),
                required=bool(dep_row["required"]),
                output_mapping=json.loads(dep_row["output_mapping_json"]) if dep_row["output_mapping_json"] else None,
            )
            dependencies.append(dep)
            if dep.required:
                blocked_by.append(dep.task_id)
        
        # Parse subtask IDs
        subtask_ids = [sr["id"] for sr in subtask_rows]
        
        # Parse datetime fields
        def parse_dt(value: Optional[str]) -> Optional[datetime]:
            if value:
                return datetime.fromisoformat(value)
            return None
        
        # Create outputs if present
        outputs = None
        if outputs_data:
            outputs = TaskOutput(data=outputs_data)
        
        return Task(
            id=row["id"],
            name=row["name"],
            description=row["description"] or "",
            task_type=row["task_type"],
            parent_id=row["parent_id"],
            subtask_ids=subtask_ids,
            depth=row["depth"],
            requirements=requirements,
            constraints=constraints,
            assigned_agent=row["assigned_agent"],
            delegated_from=row["delegated_from"],
            inputs=inputs,
            outputs=outputs,
            execution=execution,
            dependencies=dependencies,
            blocked_by=blocked_by,
            priority=row["priority"],
            scheduled_at=parse_dt(row["scheduled_at"]),
            deadline=parse_dt(row["deadline"]),
            created_at=parse_dt(row["created_at"]) or datetime.utcnow(),
            updated_at=parse_dt(row["updated_at"]) or datetime.utcnow(),
            tags=tags,
            metadata=metadata,
        )
    
    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------
    
    def get_stats(self) -> dict[str, Any]:
        """Get task store statistics."""
        self._ensure_initialized()
        
        with self._transaction() as cursor:
            # Total count
            cursor.execute(f"SELECT COUNT(*) FROM {TASKS_TABLE_NAME}")
            total = cursor.fetchone()[0]
            
            # Count by status
            cursor.execute(
                f"""
                SELECT status, COUNT(*) as count
                FROM {TASKS_TABLE_NAME}
                GROUP BY status
                """
            )
            by_status = {row["status"]: row["count"] for row in cursor.fetchall()}
            
            # Count by agent
            cursor.execute(
                f"""
                SELECT assigned_agent, COUNT(*) as count
                FROM {TASKS_TABLE_NAME}
                WHERE assigned_agent IS NOT NULL
                GROUP BY assigned_agent
                """
            )
            by_agent = {row["assigned_agent"]: row["count"] for row in cursor.fetchall()}
            
            return {
                "total": total,
                "by_status": by_status,
                "by_agent": by_agent,
            }
