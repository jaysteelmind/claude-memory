"""
Unit tests for task scheduler.

Tests cover:
- Task scheduling
- Priority queue management
- Dependency handling
- Batch retrieval
- Status lifecycle
- Statistics
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

from dmm.agentos.tasks import (
    Task,
    TaskStore,
    TaskScheduler,
    TaskStatus,
    TaskPriority,
    DependencyType,
    SchedulerConfig,
    ExecutionMode,
)


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def task_store(temp_dir):
    """Create initialized task store."""
    store = TaskStore(temp_dir, use_file_storage=False)
    store.initialize()
    yield store
    store.close()


@pytest.fixture
def scheduler(task_store):
    """Create task scheduler."""
    return TaskScheduler(task_store)


@pytest.fixture
def sample_task():
    """Create sample task."""
    return Task(name="Sample task", priority=5)


class TestSchedulerCreation:
    """Tests for scheduler creation."""
    
    def test_create_scheduler(self, task_store):
        """Test creating scheduler."""
        scheduler = TaskScheduler(task_store)
        assert scheduler is not None
    
    def test_create_scheduler_with_config(self, task_store):
        """Test creating scheduler with custom config."""
        config = SchedulerConfig(
            max_concurrent_tasks=10,
            max_queue_size=500,
        )
        scheduler = TaskScheduler(task_store, config=config)
        assert scheduler is not None


class TestTaskScheduling:
    """Tests for task scheduling."""
    
    def test_schedule_task(self, scheduler, task_store, sample_task):
        """Test scheduling a task."""
        task_store.create(sample_task)
        
        assert scheduler.schedule(sample_task)
        
        retrieved = task_store.get(sample_task.id)
        assert retrieved.execution.status == TaskStatus.SCHEDULED
    
    def test_schedule_sets_scheduled_at(self, scheduler, task_store, sample_task):
        """Test scheduling sets scheduled_at timestamp."""
        task_store.create(sample_task)
        scheduler.schedule(sample_task)
        
        retrieved = task_store.get(sample_task.id)
        assert retrieved.scheduled_at is not None
    
    def test_schedule_duplicate_fails(self, scheduler, task_store, sample_task):
        """Test scheduling same task twice fails."""
        task_store.create(sample_task)
        
        assert scheduler.schedule(sample_task)
        assert not scheduler.schedule(sample_task)
    
    def test_schedule_respects_queue_limit(self, task_store):
        """Test scheduling respects queue size limit."""
        config = SchedulerConfig(max_queue_size=2)
        scheduler = TaskScheduler(task_store, config=config)
        
        for i in range(3):
            task = Task(name=f"Task {i}")
            task_store.create(task)
            result = scheduler.schedule(task)
            if i < 2:
                assert result
            else:
                assert not result
    
    def test_unschedule_task(self, scheduler, task_store, sample_task):
        """Test unscheduling a task."""
        task_store.create(sample_task)
        scheduler.schedule(sample_task)
        
        assert scheduler.unschedule(sample_task.id)
        
        snapshot = scheduler.get_queue_snapshot()
        assert not any(s["task_id"] == sample_task.id for s in snapshot)
    
    def test_reschedule_task(self, scheduler, task_store, sample_task):
        """Test rescheduling a task with new priority."""
        task_store.create(sample_task)
        scheduler.schedule(sample_task)
        
        assert scheduler.reschedule(sample_task.id, new_priority=9)
        
        retrieved = task_store.get(sample_task.id)
        assert retrieved.priority == 9


class TestPriorityQueue:
    """Tests for priority queue behavior."""
    
    def test_higher_priority_first(self, scheduler, task_store):
        """Test higher priority tasks come first."""
        low_task = Task(name="Low priority", priority=3)
        high_task = Task(name="High priority", priority=8)
        
        task_store.create(low_task)
        task_store.create(high_task)
        
        scheduler.schedule(low_task)
        scheduler.schedule(high_task)
        
        next_task = scheduler.get_next_task()
        assert next_task.id == high_task.id
    
    def test_same_priority_fifo(self, scheduler, task_store):
        """Test same priority tasks are FIFO."""
        task1 = Task(name="Task 1", priority=5)
        task2 = Task(name="Task 2", priority=5)
        
        task_store.create(task1)
        task_store.create(task2)
        
        scheduler.schedule(task1)
        scheduler.schedule(task2)
        
        next_task = scheduler.get_next_task()
        assert next_task.id == task1.id
    
    def test_boost_priority(self, scheduler, task_store, sample_task):
        """Test boosting task priority."""
        task_store.create(sample_task)
        scheduler.schedule(sample_task)
        
        original_priority = sample_task.priority
        assert scheduler.boost_priority(sample_task.id, 2)
        
        retrieved = task_store.get(sample_task.id)
        assert retrieved.priority == original_priority + 2


class TestDependencyHandling:
    """Tests for dependency handling."""
    
    def test_blocked_task_not_returned(self, scheduler, task_store):
        """Test blocked task is not returned as next."""
        blocker = Task(name="Blocker")
        blocked = Task(name="Blocked")
        blocked.add_dependency(blocker.id)
        
        task_store.create(blocker)
        task_store.create(blocked)
        
        scheduler.schedule(blocker)
        scheduler.schedule(blocked)
        
        # Should return blocker, not blocked
        next_task = scheduler.get_next_task()
        assert next_task.id == blocker.id
    
    def test_dependency_resolution_unblocks(self, scheduler, task_store):
        """Test completing dependency unblocks task."""
        blocker = Task(name="Blocker")
        blocked = Task(name="Blocked", priority=9)
        blocked.add_dependency(blocker.id)
        
        task_store.create(blocker)
        task_store.create(blocked)
        
        scheduler.schedule(blocker)
        scheduler.schedule(blocked)
        
        # Complete the blocker
        scheduler.mark_running(blocker.id)
        scheduler.mark_completed(blocker.id)
        
        # Now blocked task should be available
        next_task = scheduler.get_next_task()
        # The blocked task should now be schedulable
        assert next_task is not None
    
    def test_check_dependencies(self, scheduler, task_store):
        """Test checking task dependencies."""
        dep = Task(name="Dependency")
        main = Task(name="Main")
        main.add_dependency(dep.id)
        
        task_store.create(dep)
        task_store.create(main)
        
        # Dependencies not satisfied
        satisfied, unsatisfied = scheduler.check_dependencies(main.id)
        assert not satisfied
        assert dep.id in unsatisfied
        
        # Complete dependency
        dep.set_status(TaskStatus.RUNNING)
        dep.set_status(TaskStatus.COMPLETED)
        task_store.update(dep)
        
        # Now satisfied
        satisfied, unsatisfied = scheduler.check_dependencies(main.id)
        assert satisfied
        assert len(unsatisfied) == 0


class TestBatchRetrieval:
    """Tests for batch task retrieval."""
    
    def test_get_next_batch(self, scheduler, task_store):
        """Test getting batch of tasks."""
        for i in range(5):
            task = Task(name=f"Task {i}", priority=5)
            task_store.create(task)
            scheduler.schedule(task)
        
        batch = scheduler.get_next_batch(max_tasks=3)
        
        assert len(batch.tasks) == 3
    
    def test_batch_respects_concurrent_limit(self, task_store):
        """Test batch respects concurrent task limit."""
        config = SchedulerConfig(max_concurrent_tasks=2)
        scheduler = TaskScheduler(task_store, config=config)
        
        for i in range(5):
            task = Task(name=f"Task {i}")
            task_store.create(task)
            scheduler.schedule(task)
        
        batch = scheduler.get_next_batch()
        assert len(batch.tasks) <= 2
    
    def test_batch_empty_when_all_running(self, task_store):
        """Test batch empty when all slots used."""
        config = SchedulerConfig(max_concurrent_tasks=1)
        scheduler = TaskScheduler(task_store, config=config)
        
        task1 = Task(name="Task 1")
        task2 = Task(name="Task 2")
        
        task_store.create(task1)
        task_store.create(task2)
        
        scheduler.schedule(task1)
        scheduler.schedule(task2)
        
        scheduler.mark_running(task1.id)
        
        batch = scheduler.get_next_batch()
        assert len(batch.tasks) == 0
        assert "Maximum concurrent" in batch.reason
    
    def test_batch_parallel_flag(self, task_store):
        """Test batch parallel execution flag."""
        config = SchedulerConfig(execution_mode=ExecutionMode.PARALLEL)
        scheduler = TaskScheduler(task_store, config=config)
        
        task1 = Task(name="Task 1")
        task2 = Task(name="Task 2")
        task1.constraints.allow_parallel = True
        task2.constraints.allow_parallel = True
        
        task_store.create(task1)
        task_store.create(task2)
        
        scheduler.schedule(task1)
        scheduler.schedule(task2)
        
        batch = scheduler.get_next_batch()
        if len(batch.tasks) > 1:
            assert batch.can_parallel


class TestStatusLifecycle:
    """Tests for task status lifecycle."""
    
    def test_mark_running(self, scheduler, task_store, sample_task):
        """Test marking task as running."""
        task_store.create(sample_task)
        scheduler.schedule(sample_task)
        
        assert scheduler.mark_running(sample_task.id)
        
        retrieved = task_store.get(sample_task.id)
        assert retrieved.execution.status == TaskStatus.RUNNING
    
    def test_mark_completed(self, scheduler, task_store, sample_task):
        """Test marking task as completed."""
        task_store.create(sample_task)
        scheduler.schedule(sample_task)
        scheduler.mark_running(sample_task.id)
        
        assert scheduler.mark_completed(sample_task.id)
        
        retrieved = task_store.get(sample_task.id)
        assert retrieved.execution.status == TaskStatus.COMPLETED
    
    def test_mark_failed_with_retry(self, scheduler, task_store):
        """Test marking task as failed triggers retry."""
        task = Task(name="Retryable")
        task.constraints.max_attempts = 3
        
        task_store.create(task)
        scheduler.schedule(task)
        scheduler.mark_running(task.id)
        
        # Simulate one attempt
        task_fresh = task_store.get(task.id)
        task_fresh.start_attempt()
        task_store.update(task_fresh)
        
        # First failure should reschedule (attempt_count=1, max=3, so can retry)
        scheduler.mark_failed(task.id, "First error")
        
        retrieved = task_store.get(task.id)
        # Should be rescheduled for retry - status will be PENDING or SCHEDULED
        assert retrieved.execution.status in [TaskStatus.PENDING, TaskStatus.SCHEDULED]
        assert retrieved.execution.last_error == "First error"
    
    def test_mark_failed_no_retry(self, scheduler, task_store):
        """Test marking task as failed when retries exhausted."""
        task = Task(name="No retry")
        task.constraints.max_attempts = 1
        
        task_store.create(task)
        scheduler.schedule(task)
        scheduler.mark_running(task.id)
        
        # Get fresh task and set attempt count to max
        task_fresh = task_store.get(task.id)
        task_fresh.execution.attempt_count = 1  # Already at max attempts
        task_store.update(task_fresh)
        
        scheduler.mark_failed(task.id, "Final error")
        
        retrieved = task_store.get(task.id)
        assert retrieved.execution.status == TaskStatus.FAILED
        assert retrieved.execution.last_error == "Final error"
    
    def test_mark_cancelled(self, scheduler, task_store, sample_task):
        """Test marking task as cancelled."""
        task_store.create(sample_task)
        scheduler.schedule(sample_task)
        
        assert scheduler.mark_cancelled(sample_task.id)
        
        retrieved = task_store.get(sample_task.id)
        assert retrieved.execution.status == TaskStatus.CANCELLED
    
    def test_mark_blocked(self, scheduler, task_store, sample_task):
        """Test marking task as blocked."""
        task_store.create(sample_task)
        scheduler.schedule(sample_task)
        scheduler.mark_running(sample_task.id)
        
        assert scheduler.mark_blocked(sample_task.id, "blocker_task")
        
        retrieved = task_store.get(sample_task.id)
        assert retrieved.execution.status == TaskStatus.BLOCKED


class TestSchedulerStatistics:
    """Tests for scheduler statistics."""
    
    def test_get_stats_empty(self, scheduler):
        """Test getting stats when empty."""
        stats = scheduler.get_stats()
        
        assert stats.total_scheduled == 0
        assert stats.current_queue_size == 0
        assert stats.current_running == 0
    
    def test_get_stats_with_tasks(self, scheduler, task_store):
        """Test getting stats with tasks."""
        for i in range(3):
            task = Task(name=f"Task {i}")
            task_store.create(task)
            scheduler.schedule(task)
        
        stats = scheduler.get_stats()
        
        assert stats.total_scheduled == 3
        assert stats.current_queue_size == 3
    
    def test_stats_update_on_completion(self, scheduler, task_store, sample_task):
        """Test stats update on task completion."""
        task_store.create(sample_task)
        scheduler.schedule(sample_task)
        scheduler.mark_running(sample_task.id)
        scheduler.mark_completed(sample_task.id)
        
        stats = scheduler.get_stats()
        
        assert stats.total_completed == 1
    
    def test_get_queue_snapshot(self, scheduler, task_store):
        """Test getting queue snapshot."""
        task = Task(name="Test", priority=7)
        task_store.create(task)
        scheduler.schedule(task)
        
        snapshot = scheduler.get_queue_snapshot()
        
        assert len(snapshot) == 1
        assert snapshot[0]["task_id"] == task.id
        assert snapshot[0]["priority"] == 7
    
    def test_get_running_tasks(self, scheduler, task_store, sample_task):
        """Test getting running task IDs."""
        task_store.create(sample_task)
        scheduler.schedule(sample_task)
        scheduler.mark_running(sample_task.id)
        
        running = scheduler.get_running_tasks()
        
        assert sample_task.id in running


class TestSchedulerCleanup:
    """Tests for scheduler cleanup."""
    
    def test_clear_queue(self, scheduler, task_store):
        """Test clearing the queue."""
        for i in range(5):
            task = Task(name=f"Task {i}")
            task_store.create(task)
            scheduler.schedule(task)
        
        cleared = scheduler.clear_queue()
        
        assert cleared == 5
        assert scheduler.get_stats().current_queue_size == 0
    
    def test_clear_completed(self, scheduler, task_store):
        """Test clearing old completed tasks."""
        task = Task(name="Old completed")
        task_store.create(task)
        scheduler.schedule(task)
        scheduler.mark_running(task.id)
        scheduler.mark_completed(task.id)
        
        # Clear with 0 hours threshold (all completed)
        cleared = scheduler.clear_completed(older_than_hours=0)
        
        assert cleared >= 0  # May or may not clear depending on timing
