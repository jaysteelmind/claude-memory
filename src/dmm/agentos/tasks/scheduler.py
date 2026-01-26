"""
Task scheduler for queue management and execution ordering.

This module provides task scheduling capabilities including:
- Priority-based task queuing
- Dependency-aware scheduling
- Parallel execution batching
- Resource-aware scheduling
- Deadline-based prioritization
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional
from threading import Lock
import heapq

from dmm.agentos.tasks.constants import (
    TaskStatus,
    TaskPriority,
    DependencyType,
    ExecutionMode,
    TASK_POLL_INTERVAL_SECONDS,
)
from dmm.agentos.tasks.models import Task, TaskPlan
from dmm.agentos.tasks.store import TaskStore


# =============================================================================
# Scheduler Configuration
# =============================================================================

@dataclass
class SchedulerConfig:
    """Configuration for task scheduler."""
    
    max_concurrent_tasks: int = 5
    max_queue_size: int = 1000
    default_priority: int = TaskPriority.NORMAL.value
    enable_deadline_boost: bool = True
    deadline_boost_hours: float = 1.0
    deadline_boost_priority: int = 2
    starvation_prevention_minutes: float = 30.0
    starvation_boost_priority: int = 1
    poll_interval_seconds: float = TASK_POLL_INTERVAL_SECONDS
    execution_mode: ExecutionMode = ExecutionMode.PARALLEL


@dataclass
class ScheduledTask:
    """A task entry in the scheduler queue."""
    
    task_id: str
    priority: int
    scheduled_at: datetime
    deadline: Optional[datetime] = None
    effective_priority: int = 0
    
    def __post_init__(self) -> None:
        self.effective_priority = self.priority
    
    def __lt__(self, other: "ScheduledTask") -> bool:
        """Compare for priority queue (higher priority = smaller value for heapq)."""
        # Negate priority so higher priority comes first in min-heap
        if self.effective_priority != other.effective_priority:
            return self.effective_priority > other.effective_priority
        # Earlier scheduled time wins ties
        return self.scheduled_at < other.scheduled_at
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ScheduledTask):
            return False
        return self.task_id == other.task_id


@dataclass
class SchedulerStats:
    """Statistics for the scheduler."""
    
    total_scheduled: int = 0
    total_completed: int = 0
    total_failed: int = 0
    total_cancelled: int = 0
    current_queue_size: int = 0
    current_running: int = 0
    average_wait_time_seconds: float = 0.0
    average_execution_time_seconds: float = 0.0


@dataclass
class BatchResult:
    """Result of getting a batch of tasks to execute."""
    
    tasks: list[Task]
    can_parallel: bool
    reason: str = ""


# =============================================================================
# Task Scheduler Implementation
# =============================================================================

class TaskScheduler:
    """
    Manages task scheduling and execution ordering.
    
    The scheduler:
    1. Maintains a priority queue of pending tasks
    2. Tracks task dependencies and blocks appropriately
    3. Provides batches of tasks ready for execution
    4. Handles deadline-based priority boosting
    5. Prevents task starvation
    """
    
    def __init__(
        self,
        task_store: TaskStore,
        config: Optional[SchedulerConfig] = None,
    ) -> None:
        """
        Initialize task scheduler.
        
        Args:
            task_store: Task persistence store
            config: Scheduler configuration
        """
        self._store = task_store
        self._config = config or SchedulerConfig()
        
        # Priority queue (min-heap, but we negate priorities)
        self._queue: list[ScheduledTask] = []
        self._queue_lock = Lock()
        
        # Track running tasks
        self._running_tasks: set[str] = set()
        self._running_lock = Lock()
        
        # Statistics
        self._stats = SchedulerStats()
        self._wait_times: list[float] = []
        self._execution_times: list[float] = []
        
        # Callbacks
        self._on_task_ready: Optional[Callable[[Task], None]] = None
        self._on_task_blocked: Optional[Callable[[Task, str], None]] = None
    
    # -------------------------------------------------------------------------
    # Queue Management
    # -------------------------------------------------------------------------
    
    def schedule(self, task: Task) -> bool:
        """
        Schedule a task for execution.
        
        Args:
            task: Task to schedule
            
        Returns:
            True if scheduled successfully
        """
        with self._queue_lock:
            # Check queue size limit
            if len(self._queue) >= self._config.max_queue_size:
                return False
            
            # Check if already scheduled
            if any(st.task_id == task.id for st in self._queue):
                return False
            
            # Create scheduled entry
            scheduled = ScheduledTask(
                task_id=task.id,
                priority=task.priority,
                scheduled_at=datetime.utcnow(),
                deadline=task.deadline,
            )
            
            # Calculate effective priority
            scheduled.effective_priority = self._calculate_effective_priority(scheduled)
            
            # Add to queue
            heapq.heappush(self._queue, scheduled)
            
            # Update task status
            task.set_status(TaskStatus.SCHEDULED)
            task.scheduled_at = scheduled.scheduled_at
            self._store.update(task)
            
            # Update stats
            self._stats.total_scheduled += 1
            self._stats.current_queue_size = len(self._queue)
            
            return True
    
    def schedule_plan(self, plan: TaskPlan) -> int:
        """
        Schedule all tasks in a plan.
        
        Args:
            plan: Task plan to schedule
            
        Returns:
            Number of tasks scheduled
        """
        scheduled_count = 0
        
        # Schedule in execution order
        all_tasks = plan.get_all_tasks()
        task_map = {t.id: t for t in all_tasks}
        
        for task_id in plan.execution_order:
            task = task_map.get(task_id)
            if task:
                # Store the task first
                try:
                    self._store.create(task)
                except ValueError:
                    # Task might already exist
                    self._store.update(task)
                
                if self.schedule(task):
                    scheduled_count += 1
        
        return scheduled_count
    
    def unschedule(self, task_id: str) -> bool:
        """
        Remove a task from the schedule.
        
        Args:
            task_id: Task ID to unschedule
            
        Returns:
            True if removed
        """
        with self._queue_lock:
            original_size = len(self._queue)
            self._queue = [st for st in self._queue if st.task_id != task_id]
            
            if len(self._queue) < original_size:
                heapq.heapify(self._queue)
                self._stats.current_queue_size = len(self._queue)
                return True
            
            return False
    
    def reschedule(self, task_id: str, new_priority: Optional[int] = None) -> bool:
        """
        Reschedule a task with optional new priority.
        
        Args:
            task_id: Task ID to reschedule
            new_priority: Optional new priority
            
        Returns:
            True if rescheduled
        """
        task = self._store.get(task_id)
        if not task:
            return False
        
        # Remove from queue if present
        self.unschedule(task_id)
        
        # Update priority if specified
        if new_priority is not None:
            task.priority = new_priority
            self._store.update(task)
        
        # Re-add to queue
        return self.schedule(task)
    
    # -------------------------------------------------------------------------
    # Task Retrieval
    # -------------------------------------------------------------------------
    
    def get_next_task(self) -> Optional[Task]:
        """
        Get the next task ready for execution.
        
        Returns:
            Next task or None if no tasks ready
        """
        batch = self.get_next_batch(max_tasks=1)
        if batch.tasks:
            return batch.tasks[0]
        return None
    
    def get_next_batch(self, max_tasks: Optional[int] = None) -> BatchResult:
        """
        Get a batch of tasks ready for parallel execution.
        
        Args:
            max_tasks: Maximum number of tasks to return
            
        Returns:
            BatchResult with tasks ready to execute
        """
        max_tasks = max_tasks or self._config.max_concurrent_tasks
        
        with self._queue_lock:
            # Check concurrent task limit
            with self._running_lock:
                available_slots = self._config.max_concurrent_tasks - len(self._running_tasks)
                if available_slots <= 0:
                    return BatchResult(
                        tasks=[],
                        can_parallel=False,
                        reason="Maximum concurrent tasks reached"
                    )
                max_tasks = min(max_tasks, available_slots)
            
            if not self._queue:
                return BatchResult(tasks=[], can_parallel=True, reason="Queue empty")
            
            # Recalculate effective priorities
            self._update_effective_priorities()
            
            # Get tasks that are ready (dependencies satisfied)
            ready_tasks: list[Task] = []
            checked_ids: set[str] = set()
            
            # We need to check all items since dependencies might block high-priority items
            for scheduled in sorted(self._queue):
                if len(ready_tasks) >= max_tasks:
                    break
                
                if scheduled.task_id in checked_ids:
                    continue
                checked_ids.add(scheduled.task_id)
                
                task = self._store.get(scheduled.task_id)
                if not task:
                    continue
                
                # Check if task can run
                if self._can_task_run(task):
                    ready_tasks.append(task)
            
            # Determine if parallel execution is possible
            can_parallel = (
                self._config.execution_mode == ExecutionMode.PARALLEL
                and len(ready_tasks) > 1
                and all(t.constraints.allow_parallel for t in ready_tasks)
            )
            
            return BatchResult(
                tasks=ready_tasks,
                can_parallel=can_parallel,
                reason="" if ready_tasks else "No tasks ready (dependencies not met)"
            )
    
    def _can_task_run(self, task: Task) -> bool:
        """Check if a task can run (dependencies satisfied)."""
        if task.execution.status not in (TaskStatus.PENDING, TaskStatus.SCHEDULED):
            return False
        
        # Check required dependencies
        for dep in task.dependencies:
            if not dep.required:
                continue
            
            dep_task = self._store.get(dep.task_id)
            if not dep_task:
                continue
            
            if dep.dependency_type == DependencyType.COMPLETION:
                if dep_task.execution.status != TaskStatus.COMPLETED:
                    return False
            elif dep.dependency_type == DependencyType.DATA:
                if dep_task.outputs is None:
                    return False
        
        return True
    
    # -------------------------------------------------------------------------
    # Task Lifecycle
    # -------------------------------------------------------------------------
    
    def mark_running(self, task_id: str) -> bool:
        """
        Mark a task as running.
        
        Args:
            task_id: Task ID
            
        Returns:
            True if marked successfully
        """
        task = self._store.get(task_id)
        if not task:
            return False
        
        # Remove from queue
        self.unschedule(task_id)
        
        # Add to running set
        with self._running_lock:
            self._running_tasks.add(task_id)
            self._stats.current_running = len(self._running_tasks)
        
        # Update task status
        task.set_status(TaskStatus.RUNNING)
        self._store.update(task)
        
        # Record wait time
        if task.scheduled_at:
            wait_time = (datetime.utcnow() - task.scheduled_at).total_seconds()
            self._wait_times.append(wait_time)
            self._update_average_wait_time()
        
        return True
    
    def mark_completed(self, task_id: str) -> bool:
        """
        Mark a task as completed.
        
        Args:
            task_id: Task ID
            
        Returns:
            True if marked successfully
        """
        task = self._store.get(task_id)
        if not task:
            return False
        
        # Remove from running set
        with self._running_lock:
            self._running_tasks.discard(task_id)
            self._stats.current_running = len(self._running_tasks)
        
        # Update task status
        task.set_status(TaskStatus.COMPLETED)
        self._store.update(task)
        
        # Update stats
        self._stats.total_completed += 1
        
        # Record execution time
        if task.execution.started_at:
            exec_time = (datetime.utcnow() - task.execution.started_at).total_seconds()
            self._execution_times.append(exec_time)
            self._update_average_execution_time()
        
        # Resolve dependencies for blocked tasks
        self._resolve_dependencies(task_id)
        
        return True
    
    def mark_failed(self, task_id: str, error_message: Optional[str] = None) -> bool:
        """
        Mark a task as failed.
        
        Args:
            task_id: Task ID
            error_message: Optional error message
            
        Returns:
            True if marked successfully
        """
        task = self._store.get(task_id)
        if not task:
            return False
        
        # Remove from running set
        with self._running_lock:
            self._running_tasks.discard(task_id)
            self._stats.current_running = len(self._running_tasks)
        
        # Record error
        if error_message:
            task.execution.last_error = error_message
        
        # Check if can retry
        if task.can_retry():
            # First transition to FAILED (valid from RUNNING)
            task.set_status(TaskStatus.FAILED)
            # Then transition to PENDING for retry (valid from FAILED)
            task.set_status(TaskStatus.PENDING)
            task.execution.add_log_entry(f"Retry scheduled after error: {error_message}")
            self._store.update(task)
            self.schedule(task)
            return True
        
        # Mark as failed (no retry)
        task.set_status(TaskStatus.FAILED)
        self._store.update(task)
        
        # Update stats
        self._stats.total_failed += 1
        
        return True
    
    def mark_cancelled(self, task_id: str) -> bool:
        """
        Mark a task as cancelled.
        
        Args:
            task_id: Task ID
            
        Returns:
            True if marked successfully
        """
        task = self._store.get(task_id)
        if not task:
            return False
        
        # Remove from queue and running set
        self.unschedule(task_id)
        with self._running_lock:
            self._running_tasks.discard(task_id)
            self._stats.current_running = len(self._running_tasks)
        
        # Update task status
        task.set_status(TaskStatus.CANCELLED)
        self._store.update(task)
        
        # Update stats
        self._stats.total_cancelled += 1
        
        return True
    
    def mark_blocked(self, task_id: str, blocked_by: str) -> bool:
        """
        Mark a task as blocked.
        
        Args:
            task_id: Task ID
            blocked_by: ID of blocking task
            
        Returns:
            True if marked successfully
        """
        task = self._store.get(task_id)
        if not task:
            return False
        
        # Update task
        if blocked_by not in task.blocked_by:
            task.blocked_by.append(blocked_by)
        task.set_status(TaskStatus.BLOCKED)
        self._store.update(task)
        
        # Notify callback
        if self._on_task_blocked:
            self._on_task_blocked(task, blocked_by)
        
        return True
    
    # -------------------------------------------------------------------------
    # Dependency Resolution
    # -------------------------------------------------------------------------
    
    def _resolve_dependencies(self, completed_task_id: str) -> None:
        """Resolve dependencies when a task completes."""
        # Find tasks that depend on the completed task
        blocked_tasks = self._store.list_tasks(status=TaskStatus.BLOCKED)
        
        for task in blocked_tasks:
            if completed_task_id in task.blocked_by:
                task.resolve_dependency(completed_task_id)
                self._store.update(task)
                
                # If no more blockers, unblock the task
                if not task.blocked_by:
                    task.set_status(TaskStatus.SCHEDULED)
                    self._store.update(task)
                    self.schedule(task)
        
        # Also check pending/scheduled tasks
        for status in [TaskStatus.PENDING, TaskStatus.SCHEDULED]:
            tasks = self._store.list_tasks(status=status)
            for task in tasks:
                if completed_task_id in task.blocked_by:
                    task.resolve_dependency(completed_task_id)
                    self._store.update(task)
    
    def check_dependencies(self, task_id: str) -> tuple[bool, list[str]]:
        """
        Check if task dependencies are satisfied.
        
        Args:
            task_id: Task ID
            
        Returns:
            Tuple of (all_satisfied, list of unsatisfied dependency IDs)
        """
        task = self._store.get(task_id)
        if not task:
            return False, []
        
        unsatisfied: list[str] = []
        
        for dep in task.dependencies:
            if not dep.required:
                continue
            
            dep_task = self._store.get(dep.task_id)
            if not dep_task:
                unsatisfied.append(dep.task_id)
                continue
            
            if dep.dependency_type == DependencyType.COMPLETION:
                if dep_task.execution.status != TaskStatus.COMPLETED:
                    unsatisfied.append(dep.task_id)
            elif dep.dependency_type == DependencyType.DATA:
                if dep_task.outputs is None:
                    unsatisfied.append(dep.task_id)
        
        return len(unsatisfied) == 0, unsatisfied
    
    # -------------------------------------------------------------------------
    # Priority Management
    # -------------------------------------------------------------------------
    
    def _calculate_effective_priority(self, scheduled: ScheduledTask) -> int:
        """Calculate effective priority with boosts."""
        priority = scheduled.priority
        
        # Deadline boost
        if self._config.enable_deadline_boost and scheduled.deadline:
            hours_until_deadline = (scheduled.deadline - datetime.utcnow()).total_seconds() / 3600
            if hours_until_deadline <= self._config.deadline_boost_hours:
                priority += self._config.deadline_boost_priority
        
        # Starvation prevention boost
        wait_minutes = (datetime.utcnow() - scheduled.scheduled_at).total_seconds() / 60
        if wait_minutes >= self._config.starvation_prevention_minutes:
            priority += self._config.starvation_boost_priority
        
        # Clamp to valid range
        return min(max(priority, 1), 10)
    
    def _update_effective_priorities(self) -> None:
        """Update effective priorities for all queued tasks."""
        for scheduled in self._queue:
            scheduled.effective_priority = self._calculate_effective_priority(scheduled)
        heapq.heapify(self._queue)
    
    def boost_priority(self, task_id: str, boost: int) -> bool:
        """
        Boost a task's priority.
        
        Args:
            task_id: Task ID
            boost: Priority boost amount
            
        Returns:
            True if boosted
        """
        task = self._store.get(task_id)
        if not task:
            return False
        
        new_priority = min(task.priority + boost, 10)
        return self.reschedule(task_id, new_priority)
    
    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------
    
    def _update_average_wait_time(self) -> None:
        """Update average wait time statistic."""
        if self._wait_times:
            # Keep only last 100 entries
            self._wait_times = self._wait_times[-100:]
            self._stats.average_wait_time_seconds = sum(self._wait_times) / len(self._wait_times)
    
    def _update_average_execution_time(self) -> None:
        """Update average execution time statistic."""
        if self._execution_times:
            # Keep only last 100 entries
            self._execution_times = self._execution_times[-100:]
            self._stats.average_execution_time_seconds = sum(self._execution_times) / len(self._execution_times)
    
    def get_stats(self) -> SchedulerStats:
        """Get scheduler statistics."""
        with self._queue_lock:
            self._stats.current_queue_size = len(self._queue)
        with self._running_lock:
            self._stats.current_running = len(self._running_tasks)
        return self._stats
    
    def get_queue_snapshot(self) -> list[dict[str, Any]]:
        """Get a snapshot of the current queue."""
        with self._queue_lock:
            return [
                {
                    "task_id": st.task_id,
                    "priority": st.priority,
                    "effective_priority": st.effective_priority,
                    "scheduled_at": st.scheduled_at.isoformat(),
                    "deadline": st.deadline.isoformat() if st.deadline else None,
                }
                for st in sorted(self._queue)
            ]
    
    def get_running_tasks(self) -> list[str]:
        """Get list of currently running task IDs."""
        with self._running_lock:
            return list(self._running_tasks)
    
    # -------------------------------------------------------------------------
    # Callbacks
    # -------------------------------------------------------------------------
    
    def set_on_task_ready(self, callback: Callable[[Task], None]) -> None:
        """Set callback for when a task becomes ready."""
        self._on_task_ready = callback
    
    def set_on_task_blocked(self, callback: Callable[[Task, str], None]) -> None:
        """Set callback for when a task is blocked."""
        self._on_task_blocked = callback
    
    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------
    
    def clear_queue(self) -> int:
        """
        Clear all tasks from the queue.
        
        Returns:
            Number of tasks cleared
        """
        with self._queue_lock:
            count = len(self._queue)
            self._queue.clear()
            self._stats.current_queue_size = 0
            return count
    
    def clear_completed(self, older_than_hours: float = 24.0) -> int:
        """
        Clear completed tasks older than specified hours.
        
        Args:
            older_than_hours: Age threshold in hours
            
        Returns:
            Number of tasks cleared
        """
        cutoff = datetime.utcnow() - timedelta(hours=older_than_hours)
        completed = self._store.list_tasks(status=TaskStatus.COMPLETED)
        
        cleared = 0
        for task in completed:
            if task.execution.completed_at and task.execution.completed_at < cutoff:
                self._store.delete(task.id)
                cleared += 1
        
        return cleared
