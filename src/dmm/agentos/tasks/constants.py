"""
Task system constants and enumerations.

This module defines all constants, enums, and configuration values
for the DMM task system.
"""

from enum import Enum
from typing import Final


# =============================================================================
# Task Status Enumeration
# =============================================================================

class TaskStatus(str, Enum):
    """Status of a task in the system."""
    
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    BLOCKED = "blocked"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    
    @classmethod
    def terminal_states(cls) -> tuple["TaskStatus", ...]:
        """Return states that indicate task completion."""
        return (cls.COMPLETED, cls.FAILED, cls.CANCELLED)
    
    @classmethod
    def active_states(cls) -> tuple["TaskStatus", ...]:
        """Return states that indicate task is active."""
        return (cls.PENDING, cls.SCHEDULED, cls.RUNNING, cls.BLOCKED, cls.PAUSED)
    
    def is_terminal(self) -> bool:
        """Check if this status is a terminal state."""
        return self in self.terminal_states()
    
    def is_active(self) -> bool:
        """Check if this status is an active state."""
        return self in self.active_states()


class TaskPriority(int, Enum):
    """Priority levels for tasks."""
    
    LOWEST = 1
    LOW = 3
    NORMAL = 5
    HIGH = 7
    HIGHEST = 9
    CRITICAL = 10
    
    @classmethod
    def from_int(cls, value: int) -> "TaskPriority":
        """Convert integer to nearest priority level."""
        if value <= 1:
            return cls.LOWEST
        elif value <= 3:
            return cls.LOW
        elif value <= 5:
            return cls.NORMAL
        elif value <= 7:
            return cls.HIGH
        elif value <= 9:
            return cls.HIGHEST
        else:
            return cls.CRITICAL


class TaskType(str, Enum):
    """Type of task."""
    
    SIMPLE = "simple"
    COMPOSITE = "composite"
    DELEGATED = "delegated"
    SCHEDULED = "scheduled"


class DependencyType(str, Enum):
    """Type of dependency between tasks."""
    
    COMPLETION = "completion"
    DATA = "data"
    RESOURCE = "resource"
    TEMPORAL = "temporal"


class ExecutionMode(str, Enum):
    """How the task should be executed."""
    
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"


# =============================================================================
# Task Configuration Constants
# =============================================================================

# ID Generation
TASK_ID_PREFIX: Final[str] = "task"
TASK_ID_SEPARATOR: Final[str] = "_"

# Default Values
DEFAULT_PRIORITY: Final[int] = TaskPriority.NORMAL.value
DEFAULT_MAX_ATTEMPTS: Final[int] = 3
DEFAULT_TIMEOUT_SECONDS: Final[float] = 300.0
DEFAULT_RETRY_DELAY_SECONDS: Final[float] = 5.0
DEFAULT_RETRY_BACKOFF_MULTIPLIER: Final[float] = 2.0

# Limits
MAX_SUBTASK_DEPTH: Final[int] = 10
MAX_SUBTASKS_PER_TASK: Final[int] = 50
MAX_DEPENDENCIES_PER_TASK: Final[int] = 20
MAX_TASK_NAME_LENGTH: Final[int] = 256
MAX_TASK_DESCRIPTION_LENGTH: Final[int] = 4096
MAX_EXECUTION_LOG_ENTRIES: Final[int] = 1000

# Timing
TASK_POLL_INTERVAL_SECONDS: Final[float] = 0.5
TASK_STALE_THRESHOLD_SECONDS: Final[float] = 3600.0
TASK_CLEANUP_AGE_DAYS: Final[int] = 30

# Database
TASKS_DB_NAME: Final[str] = "tasks.db"
TASKS_TABLE_NAME: Final[str] = "tasks"
TASK_DEPENDENCIES_TABLE_NAME: Final[str] = "task_dependencies"
TASK_LOGS_TABLE_NAME: Final[str] = "task_logs"

# File System
TASKS_DIR_NAME: Final[str] = "tasks"
ACTIVE_TASKS_DIR: Final[str] = "active"
PENDING_TASKS_DIR: Final[str] = "pending"
COMPLETED_TASKS_DIR: Final[str] = "completed"
FAILED_TASKS_DIR: Final[str] = "failed"
TASK_INDEX_FILE: Final[str] = "_index.yaml"
TASK_FILE_EXTENSION: Final[str] = ".yaml"

# Validation Patterns
TASK_ID_PATTERN: Final[str] = r"^task_[a-z0-9]{8,32}$"


# =============================================================================
# Status Transition Rules
# =============================================================================

VALID_STATUS_TRANSITIONS: Final[dict[TaskStatus, tuple[TaskStatus, ...]]] = {
    TaskStatus.PENDING: (
        TaskStatus.SCHEDULED,
        TaskStatus.RUNNING,
        TaskStatus.CANCELLED,
    ),
    TaskStatus.SCHEDULED: (
        TaskStatus.RUNNING,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
    ),
    TaskStatus.RUNNING: (
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.PAUSED,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
    ),
    TaskStatus.BLOCKED: (
        TaskStatus.SCHEDULED,
        TaskStatus.RUNNING,
        TaskStatus.CANCELLED,
    ),
    TaskStatus.PAUSED: (
        TaskStatus.RUNNING,
        TaskStatus.CANCELLED,
    ),
    TaskStatus.COMPLETED: (),
    TaskStatus.FAILED: (
        TaskStatus.PENDING,
    ),
    TaskStatus.CANCELLED: (),
}


def is_valid_transition(from_status: TaskStatus, to_status: TaskStatus) -> bool:
    """Check if a status transition is valid."""
    return to_status in VALID_STATUS_TRANSITIONS.get(from_status, ())
