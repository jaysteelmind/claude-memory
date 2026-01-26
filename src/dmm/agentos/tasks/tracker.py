"""
Task tracker for progress monitoring and status aggregation.

This module provides task tracking capabilities including:
- Real-time progress monitoring
- Status aggregation for composite tasks
- Event notification system
- Task hierarchy traversal
- Metrics collection
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional
from enum import Enum
from threading import Lock

from dmm.agentos.tasks.constants import (
    TaskStatus,
    TaskType,
)
from dmm.agentos.tasks.models import Task, TaskResult, TaskOutput, TaskError
from dmm.agentos.tasks.store import TaskStore


# =============================================================================
# Event Types
# =============================================================================

class TaskEventType(str, Enum):
    """Types of task events."""
    
    CREATED = "created"
    SCHEDULED = "scheduled"
    STARTED = "started"
    PROGRESS = "progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    UNBLOCKED = "unblocked"
    RETRY = "retry"
    SUBTASK_CREATED = "subtask_created"
    SUBTASK_COMPLETED = "subtask_completed"
    DEADLINE_WARNING = "deadline_warning"
    TIMEOUT_WARNING = "timeout_warning"


@dataclass
class TaskEvent:
    """An event related to a task."""
    
    event_type: TaskEventType
    task_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    data: dict[str, Any] = field(default_factory=dict)
    parent_task_id: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "event_type": self.event_type.value,
            "task_id": self.task_id,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "parent_task_id": self.parent_task_id,
        }


# =============================================================================
# Progress Tracking
# =============================================================================

@dataclass
class TaskProgress:
    """Progress information for a task."""
    
    task_id: str
    status: TaskStatus
    progress_percent: float = 0.0
    current_step: str = ""
    total_steps: int = 0
    completed_steps: int = 0
    started_at: Optional[datetime] = None
    estimated_completion: Optional[datetime] = None
    elapsed_seconds: float = 0.0
    remaining_seconds: Optional[float] = None
    subtask_progress: dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert progress to dictionary."""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "progress_percent": self.progress_percent,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "estimated_completion": self.estimated_completion.isoformat() if self.estimated_completion else None,
            "elapsed_seconds": self.elapsed_seconds,
            "remaining_seconds": self.remaining_seconds,
            "subtask_progress": self.subtask_progress,
        }


@dataclass
class TaskHierarchy:
    """Hierarchical view of a task and its subtasks."""
    
    task: Task
    children: list["TaskHierarchy"] = field(default_factory=list)
    depth: int = 0
    
    def flatten(self) -> list[Task]:
        """Flatten hierarchy to list of tasks."""
        result = [self.task]
        for child in self.children:
            result.extend(child.flatten())
        return result
    
    def to_dict(self) -> dict[str, Any]:
        """Convert hierarchy to dictionary."""
        return {
            "task": self.task.to_dict(),
            "children": [c.to_dict() for c in self.children],
            "depth": self.depth,
        }


@dataclass
class AggregateStatus:
    """Aggregated status for a composite task."""
    
    total_tasks: int = 0
    pending: int = 0
    scheduled: int = 0
    running: int = 0
    blocked: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    overall_progress: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_tasks": self.total_tasks,
            "pending": self.pending,
            "scheduled": self.scheduled,
            "running": self.running,
            "blocked": self.blocked,
            "completed": self.completed,
            "failed": self.failed,
            "cancelled": self.cancelled,
            "overall_progress": self.overall_progress,
        }


# =============================================================================
# Task Tracker Implementation
# =============================================================================

class TaskTracker:
    """
    Tracks task progress and provides monitoring capabilities.
    
    The tracker:
    1. Monitors task status changes
    2. Calculates progress for composite tasks
    3. Emits events for task lifecycle changes
    4. Provides hierarchical task views
    5. Collects metrics for analysis
    """
    
    def __init__(
        self,
        task_store: TaskStore,
    ) -> None:
        """
        Initialize task tracker.
        
        Args:
            task_store: Task persistence store
        """
        self._store = task_store
        
        # Event subscribers (using strong references - callers must unsubscribe)
        self._subscribers: list[Callable[[TaskEvent], None]] = []
        self._subscribers_lock = Lock()
        
        # Progress cache
        self._progress_cache: dict[str, TaskProgress] = {}
        self._progress_lock = Lock()
        
        # Metrics
        self._event_history: list[TaskEvent] = []
        self._max_history_size = 1000
    
    # -------------------------------------------------------------------------
    # Event System
    # -------------------------------------------------------------------------
    
    def subscribe(self, callback: Callable[[TaskEvent], None]) -> Callable[[], None]:
        """
        Subscribe to task events.
        
        Args:
            callback: Function to call when events occur
            
        Returns:
            Unsubscribe function
        """
        with self._subscribers_lock:
            self._subscribers.append(callback)
        
        def unsubscribe() -> None:
            with self._subscribers_lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)
        
        return unsubscribe
    
    def emit_event(self, event: TaskEvent) -> None:
        """
        Emit a task event to all subscribers.
        
        Args:
            event: Event to emit
        """
        # Store in history
        self._event_history.append(event)
        if len(self._event_history) > self._max_history_size:
            self._event_history = self._event_history[-self._max_history_size:]
        
        # Notify subscribers
        with self._subscribers_lock:
            for callback in self._subscribers:
                try:
                    callback(event)
                except Exception:
                    pass
    
    def get_event_history(
        self,
        task_id: Optional[str] = None,
        event_types: Optional[list[TaskEventType]] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[TaskEvent]:
        """
        Get event history with optional filters.
        
        Args:
            task_id: Filter by task ID
            event_types: Filter by event types
            since: Filter by timestamp
            limit: Maximum number of events
            
        Returns:
            List of matching events
        """
        events = self._event_history
        
        if task_id:
            events = [e for e in events if e.task_id == task_id]
        
        if event_types:
            events = [e for e in events if e.event_type in event_types]
        
        if since:
            events = [e for e in events if e.timestamp >= since]
        
        return events[-limit:]
    
    # -------------------------------------------------------------------------
    # Status Tracking
    # -------------------------------------------------------------------------
    
    def track_status_change(
        self,
        task_id: str,
        old_status: TaskStatus,
        new_status: TaskStatus,
        data: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Track a task status change.
        
        Args:
            task_id: Task ID
            old_status: Previous status
            new_status: New status
            data: Additional event data
        """
        event_data = data or {}
        event_data["old_status"] = old_status.value
        event_data["new_status"] = new_status.value
        
        # Determine event type
        event_type_map = {
            TaskStatus.SCHEDULED: TaskEventType.SCHEDULED,
            TaskStatus.RUNNING: TaskEventType.STARTED,
            TaskStatus.COMPLETED: TaskEventType.COMPLETED,
            TaskStatus.FAILED: TaskEventType.FAILED,
            TaskStatus.CANCELLED: TaskEventType.CANCELLED,
            TaskStatus.BLOCKED: TaskEventType.BLOCKED,
        }
        
        event_type = event_type_map.get(new_status, TaskEventType.PROGRESS)
        
        # Check for unblocked
        if old_status == TaskStatus.BLOCKED and new_status != TaskStatus.BLOCKED:
            event_type = TaskEventType.UNBLOCKED
        
        # Get parent task ID
        task = self._store.get(task_id)
        parent_id = task.parent_id if task else None
        
        event = TaskEvent(
            event_type=event_type,
            task_id=task_id,
            data=event_data,
            parent_task_id=parent_id,
        )
        
        self.emit_event(event)
        
        # Update parent task progress if this is a subtask
        if parent_id:
            self._update_parent_progress(parent_id)
    
    def track_progress(
        self,
        task_id: str,
        progress_percent: float,
        current_step: str = "",
        completed_steps: int = 0,
        total_steps: int = 0,
    ) -> None:
        """
        Track task progress.
        
        Args:
            task_id: Task ID
            progress_percent: Progress percentage (0-100)
            current_step: Current step description
            completed_steps: Number of completed steps
            total_steps: Total number of steps
        """
        task = self._store.get(task_id)
        if not task:
            return
        
        # Calculate elapsed and remaining time
        elapsed_seconds = 0.0
        remaining_seconds = None
        estimated_completion = None
        
        if task.execution.started_at:
            elapsed_seconds = (datetime.utcnow() - task.execution.started_at).total_seconds()
            
            if progress_percent > 0:
                total_estimated = elapsed_seconds / (progress_percent / 100)
                remaining_seconds = total_estimated - elapsed_seconds
                estimated_completion = datetime.utcnow() + timedelta(seconds=remaining_seconds)
        
        # Create progress object
        progress = TaskProgress(
            task_id=task_id,
            status=task.execution.status,
            progress_percent=progress_percent,
            current_step=current_step,
            total_steps=total_steps,
            completed_steps=completed_steps,
            started_at=task.execution.started_at,
            estimated_completion=estimated_completion,
            elapsed_seconds=elapsed_seconds,
            remaining_seconds=remaining_seconds,
        )
        
        # Cache progress
        with self._progress_lock:
            self._progress_cache[task_id] = progress
        
        # Emit progress event
        event = TaskEvent(
            event_type=TaskEventType.PROGRESS,
            task_id=task_id,
            data={
                "progress_percent": progress_percent,
                "current_step": current_step,
                "completed_steps": completed_steps,
                "total_steps": total_steps,
            },
            parent_task_id=task.parent_id,
        )
        self.emit_event(event)
    
    def _update_parent_progress(self, parent_id: str) -> None:
        """Update progress for a parent task based on subtasks."""
        parent = self._store.get(parent_id)
        if not parent or not parent.subtask_ids:
            return
        
        # Get subtask statuses
        subtasks = self._store.get_tasks_by_ids(parent.subtask_ids)
        if not subtasks:
            return
        
        completed = sum(1 for t in subtasks if t.execution.status == TaskStatus.COMPLETED)
        total = len(subtasks)
        
        progress_percent = (completed / total) * 100 if total > 0 else 0
        
        # Update progress cache
        with self._progress_lock:
            if parent_id in self._progress_cache:
                self._progress_cache[parent_id].progress_percent = progress_percent
                self._progress_cache[parent_id].subtask_progress = {
                    t.id: 100.0 if t.execution.status == TaskStatus.COMPLETED else 0.0
                    for t in subtasks
                }
    
    # -------------------------------------------------------------------------
    # Progress Retrieval
    # -------------------------------------------------------------------------
    
    def get_progress(self, task_id: str) -> Optional[TaskProgress]:
        """
        Get progress for a task.
        
        Args:
            task_id: Task ID
            
        Returns:
            TaskProgress or None
        """
        # Check cache first
        with self._progress_lock:
            if task_id in self._progress_cache:
                return self._progress_cache[task_id]
        
        # Calculate from task
        task = self._store.get(task_id)
        if not task:
            return None
        
        progress = self._calculate_progress(task)
        
        with self._progress_lock:
            self._progress_cache[task_id] = progress
        
        return progress
    
    def _calculate_progress(self, task: Task) -> TaskProgress:
        """Calculate progress for a task."""
        # For simple tasks, progress is based on status
        if task.task_type == TaskType.SIMPLE:
            status_progress = {
                TaskStatus.PENDING: 0.0,
                TaskStatus.SCHEDULED: 5.0,
                TaskStatus.RUNNING: 50.0,
                TaskStatus.BLOCKED: 25.0,
                TaskStatus.PAUSED: 50.0,
                TaskStatus.COMPLETED: 100.0,
                TaskStatus.FAILED: 0.0,
                TaskStatus.CANCELLED: 0.0,
            }
            progress_percent = status_progress.get(task.execution.status, 0.0)
        else:
            # For composite tasks, calculate from subtasks
            if task.subtask_ids:
                subtasks = self._store.get_tasks_by_ids(task.subtask_ids)
                completed = sum(1 for t in subtasks if t.execution.status == TaskStatus.COMPLETED)
                progress_percent = (completed / len(subtasks)) * 100 if subtasks else 0.0
            else:
                progress_percent = 0.0
        
        elapsed_seconds = 0.0
        if task.execution.started_at:
            elapsed_seconds = (datetime.utcnow() - task.execution.started_at).total_seconds()
        
        return TaskProgress(
            task_id=task.id,
            status=task.execution.status,
            progress_percent=progress_percent,
            started_at=task.execution.started_at,
            elapsed_seconds=elapsed_seconds,
        )
    
    # -------------------------------------------------------------------------
    # Status Aggregation
    # -------------------------------------------------------------------------
    
    def get_aggregate_status(self, task_id: str) -> AggregateStatus:
        """
        Get aggregated status for a task and its subtasks.
        
        Args:
            task_id: Task ID
            
        Returns:
            AggregateStatus
        """
        hierarchy = self.get_hierarchy(task_id)
        if not hierarchy:
            return AggregateStatus()
        
        all_tasks = hierarchy.flatten()
        
        status = AggregateStatus(total_tasks=len(all_tasks))
        
        for task in all_tasks:
            task_status = task.execution.status
            if task_status == TaskStatus.PENDING:
                status.pending += 1
            elif task_status == TaskStatus.SCHEDULED:
                status.scheduled += 1
            elif task_status == TaskStatus.RUNNING:
                status.running += 1
            elif task_status == TaskStatus.BLOCKED:
                status.blocked += 1
            elif task_status == TaskStatus.COMPLETED:
                status.completed += 1
            elif task_status == TaskStatus.FAILED:
                status.failed += 1
            elif task_status == TaskStatus.CANCELLED:
                status.cancelled += 1
        
        # Calculate overall progress
        if status.total_tasks > 0:
            status.overall_progress = (status.completed / status.total_tasks) * 100
        
        return status
    
    # -------------------------------------------------------------------------
    # Hierarchy Traversal
    # -------------------------------------------------------------------------
    
    def get_hierarchy(self, task_id: str, max_depth: int = 10) -> Optional[TaskHierarchy]:
        """
        Get task hierarchy starting from a task.
        
        Args:
            task_id: Root task ID
            max_depth: Maximum depth to traverse
            
        Returns:
            TaskHierarchy or None
        """
        task = self._store.get(task_id)
        if not task:
            return None
        
        return self._build_hierarchy(task, depth=0, max_depth=max_depth)
    
    def _build_hierarchy(
        self,
        task: Task,
        depth: int,
        max_depth: int,
    ) -> TaskHierarchy:
        """Recursively build task hierarchy."""
        hierarchy = TaskHierarchy(task=task, depth=depth)
        
        if depth >= max_depth or not task.subtask_ids:
            return hierarchy
        
        subtasks = self._store.get_tasks_by_ids(task.subtask_ids)
        for subtask in subtasks:
            child_hierarchy = self._build_hierarchy(subtask, depth + 1, max_depth)
            hierarchy.children.append(child_hierarchy)
        
        return hierarchy
    
    def get_root_task(self, task_id: str) -> Optional[Task]:
        """
        Get the root task for a given task.
        
        Args:
            task_id: Task ID
            
        Returns:
            Root task or None
        """
        task = self._store.get(task_id)
        if not task:
            return None
        
        while task.parent_id:
            parent = self._store.get(task.parent_id)
            if not parent:
                break
            task = parent
        
        return task
    
    def get_siblings(self, task_id: str) -> list[Task]:
        """
        Get sibling tasks (tasks with same parent).
        
        Args:
            task_id: Task ID
            
        Returns:
            List of sibling tasks
        """
        task = self._store.get(task_id)
        if not task or not task.parent_id:
            return []
        
        parent = self._store.get(task.parent_id)
        if not parent:
            return []
        
        siblings = self._store.get_tasks_by_ids(parent.subtask_ids)
        return [s for s in siblings if s.id != task_id]
    
    # -------------------------------------------------------------------------
    # Deadline and Timeout Monitoring
    # -------------------------------------------------------------------------
    
    def check_deadlines(self, warning_threshold_minutes: float = 30.0) -> list[Task]:
        """
        Check for tasks approaching deadlines.
        
        Args:
            warning_threshold_minutes: Minutes before deadline to warn
            
        Returns:
            List of tasks approaching deadline
        """
        now = datetime.utcnow()
        warning_threshold = timedelta(minutes=warning_threshold_minutes)
        
        approaching_deadline: list[Task] = []
        
        for status in [TaskStatus.PENDING, TaskStatus.SCHEDULED, TaskStatus.RUNNING]:
            tasks = self._store.list_tasks(status=status)
            for task in tasks:
                if task.deadline:
                    time_until_deadline = task.deadline - now
                    if timedelta(0) < time_until_deadline <= warning_threshold:
                        approaching_deadline.append(task)
                        
                        # Emit warning event
                        event = TaskEvent(
                            event_type=TaskEventType.DEADLINE_WARNING,
                            task_id=task.id,
                            data={
                                "deadline": task.deadline.isoformat(),
                                "minutes_remaining": time_until_deadline.total_seconds() / 60,
                            },
                        )
                        self.emit_event(event)
        
        return approaching_deadline
    
    def check_timeouts(self) -> list[Task]:
        """
        Check for tasks that have exceeded their timeout.
        
        Returns:
            List of timed-out tasks
        """
        timed_out: list[Task] = []
        now = datetime.utcnow()
        
        running_tasks = self._store.list_tasks(status=TaskStatus.RUNNING)
        for task in running_tasks:
            if task.execution.started_at:
                elapsed = (now - task.execution.started_at).total_seconds()
                if elapsed > task.constraints.timeout_seconds:
                    timed_out.append(task)
                    
                    # Emit warning event
                    event = TaskEvent(
                        event_type=TaskEventType.TIMEOUT_WARNING,
                        task_id=task.id,
                        data={
                            "timeout_seconds": task.constraints.timeout_seconds,
                            "elapsed_seconds": elapsed,
                        },
                    )
                    self.emit_event(event)
        
        return timed_out
    
    # -------------------------------------------------------------------------
    # Metrics
    # -------------------------------------------------------------------------
    
    def get_metrics(self) -> dict[str, Any]:
        """Get tracker metrics."""
        stats = self._store.get_stats()
        
        # Calculate event counts by type
        event_counts: dict[str, int] = {}
        for event in self._event_history:
            event_type = event.event_type.value
            event_counts[event_type] = event_counts.get(event_type, 0) + 1
        
        return {
            "task_counts": stats,
            "event_counts": event_counts,
            "total_events": len(self._event_history),
            "cached_progress_count": len(self._progress_cache),
            "subscriber_count": len(self._subscribers),
        }
    
    def clear_cache(self) -> None:
        """Clear the progress cache."""
        with self._progress_lock:
            self._progress_cache.clear()
    
    def clear_history(self) -> None:
        """Clear the event history."""
        self._event_history.clear()
