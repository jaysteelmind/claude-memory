"""
Task data models.

This module defines the core data structures for the DMM task system,
including Task, Subtask, TaskResult, and supporting types.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
import hashlib
import re
import secrets

from dmm.agentos.tasks.constants import (
    TaskStatus,
    TaskPriority,
    TaskType,
    DependencyType,
    ExecutionMode,
    TASK_ID_PREFIX,
    TASK_ID_SEPARATOR,
    DEFAULT_PRIORITY,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_SUBTASK_DEPTH,
    MAX_TASK_NAME_LENGTH,
    MAX_TASK_DESCRIPTION_LENGTH,
    TASK_ID_PATTERN,
    is_valid_transition,
)


# =============================================================================
# ID Generation
# =============================================================================

def generate_task_id() -> str:
    """Generate a unique task ID."""
    random_part = secrets.token_hex(8)
    return f"{TASK_ID_PREFIX}{TASK_ID_SEPARATOR}{random_part}"


def validate_task_id(task_id: str) -> bool:
    """Validate a task ID format."""
    return bool(re.match(TASK_ID_PATTERN, task_id))


# =============================================================================
# Supporting Data Classes
# =============================================================================

@dataclass
class TaskDependency:
    """Represents a dependency between tasks."""
    
    task_id: str
    dependency_type: DependencyType = DependencyType.COMPLETION
    required: bool = True
    output_mapping: Optional[dict[str, str]] = None
    
    def __post_init__(self) -> None:
        if isinstance(self.dependency_type, str):
            self.dependency_type = DependencyType(self.dependency_type)


@dataclass
class TaskRequirements:
    """Requirements for executing a task."""
    
    skills: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    memory_scopes: list[str] = field(default_factory=list)
    memory_tags: list[str] = field(default_factory=list)
    min_context_tokens: int = 0
    max_context_tokens: int = 8000


@dataclass
class TaskConstraints:
    """Constraints on task execution."""
    
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    retry_delay_seconds: float = 5.0
    retry_backoff_multiplier: float = 2.0
    allow_parallel: bool = True
    require_approval: bool = False
    allowed_tools: Optional[list[str]] = None
    denied_tools: Optional[list[str]] = None


@dataclass
class TaskExecution:
    """Execution state and metadata for a task."""
    
    status: TaskStatus = TaskStatus.PENDING
    attempt_count: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_error: Optional[str] = None
    execution_log: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = TaskStatus(self.status)
    
    def add_log_entry(self, message: str) -> None:
        """Add an entry to the execution log."""
        timestamp = datetime.utcnow().isoformat()
        self.execution_log.append(f"[{timestamp}] {message}")
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate execution duration if available."""
        if self.started_at is None:
            return None
        end_time = self.completed_at or datetime.utcnow()
        return (end_time - self.started_at).total_seconds()


@dataclass
class TaskOutput:
    """Output from a completed task."""
    
    data: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    memories_created: list[str] = field(default_factory=list)
    memories_updated: list[str] = field(default_factory=list)
    messages_sent: list[str] = field(default_factory=list)


@dataclass
class TaskError:
    """Error information for a failed task."""
    
    error_type: str
    message: str
    details: Optional[dict[str, Any]] = None
    traceback: Optional[str] = None
    recoverable: bool = True
    timestamp: datetime = field(default_factory=datetime.utcnow)


# =============================================================================
# Main Task Model
# =============================================================================

@dataclass
class Task:
    """
    A unit of work in the Agent OS.
    
    Tasks can be simple (single execution) or composite (containing subtasks).
    They track execution state, dependencies, and produce outputs.
    """
    
    # Identity
    id: str = field(default_factory=generate_task_id)
    name: str = ""
    description: str = ""
    task_type: TaskType = TaskType.SIMPLE
    
    # Hierarchy
    parent_id: Optional[str] = None
    subtask_ids: list[str] = field(default_factory=list)
    depth: int = 0
    
    # Requirements
    requirements: TaskRequirements = field(default_factory=TaskRequirements)
    
    # Constraints
    constraints: TaskConstraints = field(default_factory=TaskConstraints)
    
    # Assignment
    assigned_agent: Optional[str] = None
    delegated_from: Optional[str] = None
    
    # Inputs/Outputs
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: Optional[TaskOutput] = None
    
    # Execution
    execution: TaskExecution = field(default_factory=TaskExecution)
    
    # Dependencies
    dependencies: list[TaskDependency] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    
    # Priority and scheduling
    priority: int = DEFAULT_PRIORITY
    scheduled_at: Optional[datetime] = None
    deadline: Optional[datetime] = None
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Metadata
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate and normalize task data."""
        if isinstance(self.task_type, str):
            self.task_type = TaskType(self.task_type)
        if isinstance(self.execution, dict):
            self.execution = TaskExecution(**self.execution)
        if isinstance(self.requirements, dict):
            self.requirements = TaskRequirements(**self.requirements)
        if isinstance(self.constraints, dict):
            self.constraints = TaskConstraints(**self.constraints)
        if self.outputs is not None and isinstance(self.outputs, dict):
            self.outputs = TaskOutput(**self.outputs)
        
        # Normalize dependencies
        normalized_deps = []
        for dep in self.dependencies:
            if isinstance(dep, dict):
                normalized_deps.append(TaskDependency(**dep))
            elif isinstance(dep, str):
                normalized_deps.append(TaskDependency(task_id=dep))
            else:
                normalized_deps.append(dep)
        self.dependencies = normalized_deps
    
    # -------------------------------------------------------------------------
    # Status Management
    # -------------------------------------------------------------------------
    
    @property
    def status(self) -> TaskStatus:
        """Get current task status."""
        return self.execution.status
    
    def set_status(self, new_status: TaskStatus) -> bool:
        """
        Set task status with validation.
        
        Returns True if transition was valid and applied.
        """
        if not is_valid_transition(self.execution.status, new_status):
            return False
        
        old_status = self.execution.status
        self.execution.status = new_status
        self.updated_at = datetime.utcnow()
        self.execution.add_log_entry(f"Status: {old_status.value} -> {new_status.value}")
        
        if new_status == TaskStatus.RUNNING and self.execution.started_at is None:
            self.execution.started_at = datetime.utcnow()
        elif new_status.is_terminal():
            self.execution.completed_at = datetime.utcnow()
        
        return True
    
    def is_complete(self) -> bool:
        """Check if task is in a terminal state."""
        return self.execution.status.is_terminal()
    
    def is_successful(self) -> bool:
        """Check if task completed successfully."""
        return self.execution.status == TaskStatus.COMPLETED
    
    def is_runnable(self) -> bool:
        """Check if task can be executed."""
        return (
            self.execution.status in (TaskStatus.PENDING, TaskStatus.SCHEDULED)
            and len(self.blocked_by) == 0
        )
    
    # -------------------------------------------------------------------------
    # Dependency Management
    # -------------------------------------------------------------------------
    
    def add_dependency(
        self,
        task_id: str,
        dependency_type: DependencyType = DependencyType.COMPLETION,
        required: bool = True,
    ) -> None:
        """Add a dependency to this task."""
        dep = TaskDependency(
            task_id=task_id,
            dependency_type=dependency_type,
            required=required,
        )
        self.dependencies.append(dep)
        if task_id not in self.blocked_by:
            self.blocked_by.append(task_id)
    
    def remove_dependency(self, task_id: str) -> bool:
        """Remove a dependency from this task."""
        original_count = len(self.dependencies)
        self.dependencies = [d for d in self.dependencies if d.task_id != task_id]
        if task_id in self.blocked_by:
            self.blocked_by.remove(task_id)
        return len(self.dependencies) < original_count
    
    def resolve_dependency(self, task_id: str) -> None:
        """Mark a dependency as resolved."""
        if task_id in self.blocked_by:
            self.blocked_by.remove(task_id)
            self.execution.add_log_entry(f"Dependency resolved: {task_id}")
    
    def get_required_dependencies(self) -> list[str]:
        """Get IDs of required dependencies."""
        return [d.task_id for d in self.dependencies if d.required]
    
    # -------------------------------------------------------------------------
    # Subtask Management
    # -------------------------------------------------------------------------
    
    def add_subtask(self, subtask_id: str) -> bool:
        """Add a subtask to this task."""
        if self.depth >= MAX_SUBTASK_DEPTH:
            return False
        if subtask_id not in self.subtask_ids:
            self.subtask_ids.append(subtask_id)
            self.task_type = TaskType.COMPOSITE
        return True
    
    def remove_subtask(self, subtask_id: str) -> bool:
        """Remove a subtask from this task."""
        if subtask_id in self.subtask_ids:
            self.subtask_ids.remove(subtask_id)
            if len(self.subtask_ids) == 0:
                self.task_type = TaskType.SIMPLE
            return True
        return False
    
    def has_subtasks(self) -> bool:
        """Check if this task has subtasks."""
        return len(self.subtask_ids) > 0
    
    # -------------------------------------------------------------------------
    # Execution Management
    # -------------------------------------------------------------------------
    
    def start_attempt(self) -> int:
        """Start a new execution attempt."""
        self.execution.attempt_count += 1
        self.execution.add_log_entry(f"Starting attempt {self.execution.attempt_count}")
        return self.execution.attempt_count
    
    def can_retry(self) -> bool:
        """Check if task can be retried."""
        return self.execution.attempt_count < self.constraints.max_attempts
    
    def record_error(self, error: TaskError) -> None:
        """Record an error for this task."""
        self.execution.last_error = error.message
        self.execution.add_log_entry(f"Error: {error.error_type}: {error.message}")
    
    def set_output(self, output: TaskOutput) -> None:
        """Set the task output."""
        self.outputs = output
        self.execution.add_log_entry("Output recorded")
    
    # -------------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------------
    
    def to_dict(self) -> dict[str, Any]:
        """Convert task to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "task_type": self.task_type.value,
            "parent_id": self.parent_id,
            "subtask_ids": self.subtask_ids,
            "depth": self.depth,
            "requirements": {
                "skills": self.requirements.skills,
                "tools": self.requirements.tools,
                "memory_scopes": self.requirements.memory_scopes,
                "memory_tags": self.requirements.memory_tags,
                "min_context_tokens": self.requirements.min_context_tokens,
                "max_context_tokens": self.requirements.max_context_tokens,
            },
            "constraints": {
                "timeout_seconds": self.constraints.timeout_seconds,
                "max_attempts": self.constraints.max_attempts,
                "retry_delay_seconds": self.constraints.retry_delay_seconds,
                "retry_backoff_multiplier": self.constraints.retry_backoff_multiplier,
                "allow_parallel": self.constraints.allow_parallel,
                "require_approval": self.constraints.require_approval,
                "allowed_tools": self.constraints.allowed_tools,
                "denied_tools": self.constraints.denied_tools,
            },
            "assigned_agent": self.assigned_agent,
            "delegated_from": self.delegated_from,
            "inputs": self.inputs,
            "outputs": self.outputs.data if self.outputs else None,
            "execution": {
                "status": self.execution.status.value,
                "attempt_count": self.execution.attempt_count,
                "started_at": self.execution.started_at.isoformat() if self.execution.started_at else None,
                "completed_at": self.execution.completed_at.isoformat() if self.execution.completed_at else None,
                "last_error": self.execution.last_error,
                "execution_log": self.execution.execution_log,
                "metrics": self.execution.metrics,
            },
            "dependencies": [
                {
                    "task_id": d.task_id,
                    "dependency_type": d.dependency_type.value,
                    "required": d.required,
                    "output_mapping": d.output_mapping,
                }
                for d in self.dependencies
            ],
            "blocked_by": self.blocked_by,
            "blocks": self.blocks,
            "priority": self.priority,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "tags": self.tags,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        """Create task from dictionary."""
        # Parse datetime fields
        for dt_field in ["created_at", "updated_at", "scheduled_at", "deadline"]:
            if data.get(dt_field) and isinstance(data[dt_field], str):
                data[dt_field] = datetime.fromisoformat(data[dt_field])
        
        # Parse execution datetime fields
        if "execution" in data and isinstance(data["execution"], dict):
            exec_data = data["execution"]
            for dt_field in ["started_at", "completed_at"]:
                if exec_data.get(dt_field) and isinstance(exec_data[dt_field], str):
                    exec_data[dt_field] = datetime.fromisoformat(exec_data[dt_field])
        
        return cls(**data)
    
    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------
    
    def validate(self) -> list[str]:
        """
        Validate task data.
        
        Returns a list of validation errors (empty if valid).
        """
        errors = []
        
        if not validate_task_id(self.id):
            errors.append(f"Invalid task ID format: {self.id}")
        
        if not self.name:
            errors.append("Task name is required")
        elif len(self.name) > MAX_TASK_NAME_LENGTH:
            errors.append(f"Task name exceeds maximum length of {MAX_TASK_NAME_LENGTH}")
        
        if len(self.description) > MAX_TASK_DESCRIPTION_LENGTH:
            errors.append(f"Task description exceeds maximum length of {MAX_TASK_DESCRIPTION_LENGTH}")
        
        if self.depth > MAX_SUBTASK_DEPTH:
            errors.append(f"Task depth exceeds maximum of {MAX_SUBTASK_DEPTH}")
        
        if self.priority < 1 or self.priority > 10:
            errors.append("Task priority must be between 1 and 10")
        
        if self.constraints.timeout_seconds <= 0:
            errors.append("Task timeout must be positive")
        
        if self.constraints.max_attempts < 1:
            errors.append("Task max_attempts must be at least 1")
        
        # Check for circular dependencies
        if self.id in [d.task_id for d in self.dependencies]:
            errors.append("Task cannot depend on itself")
        
        return errors
    
    def __hash__(self) -> int:
        """Hash based on task ID."""
        return hash(self.id)
    
    def __eq__(self, other: object) -> bool:
        """Equality based on task ID."""
        if not isinstance(other, Task):
            return False
        return self.id == other.id


# =============================================================================
# Task Result Model
# =============================================================================

@dataclass
class TaskResult:
    """Result of task execution."""
    
    task_id: str
    status: TaskStatus
    outputs: Optional[TaskOutput] = None
    error: Optional[TaskError] = None
    duration_seconds: float = 0.0
    attempt_count: int = 1
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = TaskStatus(self.status)
        if isinstance(self.outputs, dict):
            self.outputs = TaskOutput(**self.outputs)
        if isinstance(self.error, dict):
            self.error = TaskError(**self.error)
    
    def is_success(self) -> bool:
        """Check if result indicates success."""
        return self.status == TaskStatus.COMPLETED
    
    def is_failure(self) -> bool:
        """Check if result indicates failure."""
        return self.status == TaskStatus.FAILED
    
    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "outputs": {
                "data": self.outputs.data,
                "artifacts": self.outputs.artifacts,
                "memories_created": self.outputs.memories_created,
                "memories_updated": self.outputs.memories_updated,
                "messages_sent": self.outputs.messages_sent,
            } if self.outputs else None,
            "error": {
                "error_type": self.error.error_type,
                "message": self.error.message,
                "details": self.error.details,
                "recoverable": self.error.recoverable,
            } if self.error else None,
            "duration_seconds": self.duration_seconds,
            "attempt_count": self.attempt_count,
            "timestamp": self.timestamp.isoformat(),
        }


# =============================================================================
# Task Plan Model
# =============================================================================

@dataclass
class TaskPlan:
    """A plan for executing a task, possibly with subtasks."""
    
    root_task: Task
    subtasks: list[Task] = field(default_factory=list)
    execution_order: list[str] = field(default_factory=list)
    parallel_groups: list[list[str]] = field(default_factory=list)
    estimated_duration_seconds: float = 0.0
    estimated_tokens: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def get_all_tasks(self) -> list[Task]:
        """Get all tasks in the plan."""
        return [self.root_task] + self.subtasks
    
    def get_task_by_id(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        if self.root_task.id == task_id:
            return self.root_task
        for task in self.subtasks:
            if task.id == task_id:
                return task
        return None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert plan to dictionary."""
        return {
            "root_task": self.root_task.to_dict(),
            "subtasks": [t.to_dict() for t in self.subtasks],
            "execution_order": self.execution_order,
            "parallel_groups": self.parallel_groups,
            "estimated_duration_seconds": self.estimated_duration_seconds,
            "estimated_tokens": self.estimated_tokens,
            "created_at": self.created_at.isoformat(),
        }
