"""
Unit tests for task tracker.

Tests cover:
- Event system
- Progress tracking
- Status aggregation
- Hierarchy traversal
- Deadline monitoring
- Metrics collection
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from dmm.agentos.tasks import (
    Task,
    TaskStore,
    TaskTracker,
    TaskStatus,
    TaskType,
    TaskEventType,
    TaskProgress,
    TaskHierarchy,
    AggregateStatus,
    TaskEvent,
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
def tracker(task_store):
    """Create task tracker."""
    return TaskTracker(task_store)


@pytest.fixture
def sample_task():
    """Create sample task."""
    return Task(name="Sample task", priority=5)


class TestEventSystem:
    """Tests for event subscription and emission."""
    
    def test_subscribe_to_events(self, tracker):
        """Test subscribing to events."""
        events_received = []
        
        def handler(event):
            events_received.append(event)
        
        unsubscribe = tracker.subscribe(handler)
        
        # Emit an event
        event = TaskEvent(
            event_type=TaskEventType.CREATED,
            task_id="task_test1234567",
        )
        tracker.emit_event(event)
        
        assert len(events_received) == 1
        assert events_received[0].task_id == "task_test1234567"
        
        # Cleanup
        unsubscribe()
    
    def test_unsubscribe(self, tracker):
        """Test unsubscribing from events."""
        events_received = []
        
        def handler(event):
            events_received.append(event)
        
        unsubscribe = tracker.subscribe(handler)
        unsubscribe()
        
        # Emit an event
        event = TaskEvent(
            event_type=TaskEventType.CREATED,
            task_id="task_test1234567",
        )
        tracker.emit_event(event)
        
        assert len(events_received) == 0
    
    def test_multiple_subscribers(self, tracker):
        """Test multiple subscribers receive events."""
        events1 = []
        events2 = []
        
        def handler1(event):
            events1.append(event)
        
        def handler2(event):
            events2.append(event)
        
        unsub1 = tracker.subscribe(handler1)
        unsub2 = tracker.subscribe(handler2)
        
        event = TaskEvent(
            event_type=TaskEventType.STARTED,
            task_id="task_test1234567",
        )
        tracker.emit_event(event)
        
        assert len(events1) == 1
        assert len(events2) == 1
        
        unsub1()
        unsub2()
    
    def test_event_history(self, tracker):
        """Test event history is recorded."""
        for i in range(5):
            event = TaskEvent(
                event_type=TaskEventType.PROGRESS,
                task_id=f"task_test{i}",
            )
            tracker.emit_event(event)
        
        history = tracker.get_event_history()
        
        assert len(history) == 5
    
    def test_event_history_filter_by_task(self, tracker):
        """Test filtering event history by task ID."""
        tracker.emit_event(TaskEvent(TaskEventType.STARTED, "task_a"))
        tracker.emit_event(TaskEvent(TaskEventType.PROGRESS, "task_b"))
        tracker.emit_event(TaskEvent(TaskEventType.COMPLETED, "task_a"))
        
        history = tracker.get_event_history(task_id="task_a")
        
        assert len(history) == 2
        assert all(e.task_id == "task_a" for e in history)
    
    def test_event_history_filter_by_type(self, tracker):
        """Test filtering event history by event type."""
        tracker.emit_event(TaskEvent(TaskEventType.STARTED, "task_a"))
        tracker.emit_event(TaskEvent(TaskEventType.PROGRESS, "task_a"))
        tracker.emit_event(TaskEvent(TaskEventType.COMPLETED, "task_a"))
        
        history = tracker.get_event_history(
            event_types=[TaskEventType.STARTED, TaskEventType.COMPLETED]
        )
        
        assert len(history) == 2
    
    def test_event_history_limit(self, tracker):
        """Test event history respects limit."""
        for i in range(10):
            tracker.emit_event(TaskEvent(TaskEventType.PROGRESS, f"task_{i}"))
        
        history = tracker.get_event_history(limit=5)
        
        assert len(history) == 5


class TestStatusTracking:
    """Tests for status change tracking."""
    
    def test_track_status_change(self, tracker, task_store, sample_task):
        """Test tracking status change."""
        task_store.create(sample_task)
        
        events_received = []
        tracker.subscribe(lambda e: events_received.append(e))
        
        tracker.track_status_change(
            sample_task.id,
            TaskStatus.PENDING,
            TaskStatus.RUNNING,
        )
        
        assert len(events_received) == 1
        assert events_received[0].event_type == TaskEventType.STARTED
    
    def test_track_completion(self, tracker, task_store, sample_task):
        """Test tracking task completion."""
        task_store.create(sample_task)
        
        events_received = []
        tracker.subscribe(lambda e: events_received.append(e))
        
        tracker.track_status_change(
            sample_task.id,
            TaskStatus.RUNNING,
            TaskStatus.COMPLETED,
        )
        
        assert events_received[0].event_type == TaskEventType.COMPLETED
    
    def test_track_failure(self, tracker, task_store, sample_task):
        """Test tracking task failure."""
        task_store.create(sample_task)
        
        events_received = []
        tracker.subscribe(lambda e: events_received.append(e))
        
        tracker.track_status_change(
            sample_task.id,
            TaskStatus.RUNNING,
            TaskStatus.FAILED,
            data={"error": "Test error"},
        )
        
        assert events_received[0].event_type == TaskEventType.FAILED
        assert events_received[0].data["error"] == "Test error"
    
    def test_track_unblocked(self, tracker, task_store, sample_task):
        """Test tracking task unblocked."""
        task_store.create(sample_task)
        
        events_received = []
        tracker.subscribe(lambda e: events_received.append(e))
        
        tracker.track_status_change(
            sample_task.id,
            TaskStatus.BLOCKED,
            TaskStatus.SCHEDULED,
        )
        
        assert events_received[0].event_type == TaskEventType.UNBLOCKED


class TestProgressTracking:
    """Tests for progress tracking."""
    
    def test_track_progress(self, tracker, task_store, sample_task):
        """Test tracking task progress."""
        sample_task.set_status(TaskStatus.RUNNING)
        task_store.create(sample_task)
        
        tracker.track_progress(
            sample_task.id,
            progress_percent=50.0,
            current_step="Processing files",
            completed_steps=5,
            total_steps=10,
        )
        
        progress = tracker.get_progress(sample_task.id)
        
        assert progress is not None
        assert progress.progress_percent == 50.0
        assert progress.current_step == "Processing files"
        assert progress.completed_steps == 5
        assert progress.total_steps == 10
    
    def test_progress_emits_event(self, tracker, task_store, sample_task):
        """Test progress tracking emits event."""
        sample_task.set_status(TaskStatus.RUNNING)
        task_store.create(sample_task)
        
        events_received = []
        tracker.subscribe(lambda e: events_received.append(e))
        
        tracker.track_progress(sample_task.id, progress_percent=25.0)
        
        assert len(events_received) == 1
        assert events_received[0].event_type == TaskEventType.PROGRESS
        assert events_received[0].data["progress_percent"] == 25.0
    
    def test_get_progress_calculates_for_simple_task(self, tracker, task_store):
        """Test progress calculation for simple task."""
        task = Task(name="Simple task")
        task_store.create(task)
        
        progress = tracker.get_progress(task.id)
        
        assert progress is not None
        assert progress.status == TaskStatus.PENDING
        assert progress.progress_percent == 0.0
    
    def test_get_progress_for_running_task(self, tracker, task_store):
        """Test progress for running task."""
        task = Task(name="Running task")
        task.set_status(TaskStatus.RUNNING)
        task_store.create(task)
        
        progress = tracker.get_progress(task.id)
        
        assert progress.status == TaskStatus.RUNNING
        assert progress.progress_percent == 50.0  # Default for running
    
    def test_get_progress_for_completed_task(self, tracker, task_store):
        """Test progress for completed task."""
        task = Task(name="Completed task")
        task.set_status(TaskStatus.RUNNING)
        task.set_status(TaskStatus.COMPLETED)
        task_store.create(task)
        
        progress = tracker.get_progress(task.id)
        
        assert progress.status == TaskStatus.COMPLETED
        assert progress.progress_percent == 100.0
    
    def test_progress_elapsed_time(self, tracker, task_store):
        """Test progress includes elapsed time."""
        task = Task(name="Timed task")
        task.set_status(TaskStatus.RUNNING)
        task_store.create(task)
        
        progress = tracker.get_progress(task.id)
        
        assert progress.elapsed_seconds >= 0


class TestStatusAggregation:
    """Tests for status aggregation."""
    
    def test_aggregate_status_simple(self, tracker, task_store):
        """Test aggregate status for simple task."""
        task = Task(name="Simple")
        task_store.create(task)
        
        status = tracker.get_aggregate_status(task.id)
        
        assert status.total_tasks == 1
        assert status.pending == 1
    
    def test_aggregate_status_with_subtasks(self, tracker, task_store):
        """Test aggregate status with subtasks."""
        parent = Task(name="Parent", task_type=TaskType.COMPOSITE)
        child1 = Task(name="Child 1", parent_id=parent.id)
        child2 = Task(name="Child 2", parent_id=parent.id)
        
        child1.set_status(TaskStatus.RUNNING)
        child1.set_status(TaskStatus.COMPLETED)
        
        parent.subtask_ids = [child1.id, child2.id]
        
        task_store.create(parent)
        task_store.create(child1)
        task_store.create(child2)
        
        status = tracker.get_aggregate_status(parent.id)
        
        assert status.total_tasks == 3
        assert status.completed == 1
        assert status.pending == 2  # parent + child2
    
    def test_aggregate_overall_progress(self, tracker, task_store):
        """Test aggregate overall progress calculation."""
        parent = Task(name="Parent", task_type=TaskType.COMPOSITE)
        child1 = Task(name="Child 1", parent_id=parent.id)
        child2 = Task(name="Child 2", parent_id=parent.id)
        
        child1.set_status(TaskStatus.RUNNING)
        child1.set_status(TaskStatus.COMPLETED)
        
        parent.subtask_ids = [child1.id, child2.id]
        
        task_store.create(parent)
        task_store.create(child1)
        task_store.create(child2)
        
        status = tracker.get_aggregate_status(parent.id)
        
        # 1 out of 3 completed
        assert status.overall_progress == pytest.approx(33.33, rel=0.1)


class TestHierarchyTraversal:
    """Tests for task hierarchy traversal."""
    
    def test_get_hierarchy_simple(self, tracker, task_store):
        """Test getting hierarchy for simple task."""
        task = Task(name="Simple")
        task_store.create(task)
        
        hierarchy = tracker.get_hierarchy(task.id)
        
        assert hierarchy is not None
        assert hierarchy.task.id == task.id
        assert len(hierarchy.children) == 0
    
    def test_get_hierarchy_with_children(self, tracker, task_store):
        """Test getting hierarchy with children."""
        parent = Task(name="Parent", task_type=TaskType.COMPOSITE)
        child1 = Task(name="Child 1", parent_id=parent.id)
        child2 = Task(name="Child 2", parent_id=parent.id)
        
        parent.subtask_ids = [child1.id, child2.id]
        
        task_store.create(parent)
        task_store.create(child1)
        task_store.create(child2)
        
        hierarchy = tracker.get_hierarchy(parent.id)
        
        assert hierarchy.task.id == parent.id
        assert len(hierarchy.children) == 2
    
    def test_hierarchy_flatten(self, tracker, task_store):
        """Test flattening hierarchy."""
        parent = Task(name="Parent", task_type=TaskType.COMPOSITE)
        child = Task(name="Child", parent_id=parent.id)
        parent.subtask_ids = [child.id]
        
        task_store.create(parent)
        task_store.create(child)
        
        hierarchy = tracker.get_hierarchy(parent.id)
        all_tasks = hierarchy.flatten()
        
        assert len(all_tasks) == 2
    
    def test_hierarchy_max_depth(self, tracker, task_store):
        """Test hierarchy respects max depth."""
        root = Task(name="Root", task_type=TaskType.COMPOSITE)
        level1 = Task(name="Level 1", parent_id=root.id, task_type=TaskType.COMPOSITE)
        level2 = Task(name="Level 2", parent_id=level1.id)
        
        root.subtask_ids = [level1.id]
        level1.subtask_ids = [level2.id]
        
        task_store.create(root)
        task_store.create(level1)
        task_store.create(level2)
        
        hierarchy = tracker.get_hierarchy(root.id, max_depth=1)
        
        assert hierarchy.depth == 0
        assert len(hierarchy.children) == 1
        assert len(hierarchy.children[0].children) == 0  # Depth limited
    
    def test_get_root_task(self, tracker, task_store):
        """Test getting root task."""
        root = Task(name="Root", task_type=TaskType.COMPOSITE)
        child = Task(name="Child", parent_id=root.id)
        root.subtask_ids = [child.id]
        
        task_store.create(root)
        task_store.create(child)
        
        found_root = tracker.get_root_task(child.id)
        
        assert found_root.id == root.id
    
    def test_get_siblings(self, tracker, task_store):
        """Test getting sibling tasks."""
        parent = Task(name="Parent", task_type=TaskType.COMPOSITE)
        child1 = Task(name="Child 1", parent_id=parent.id)
        child2 = Task(name="Child 2", parent_id=parent.id)
        child3 = Task(name="Child 3", parent_id=parent.id)
        
        parent.subtask_ids = [child1.id, child2.id, child3.id]
        
        task_store.create(parent)
        task_store.create(child1)
        task_store.create(child2)
        task_store.create(child3)
        
        siblings = tracker.get_siblings(child1.id)
        
        assert len(siblings) == 2
        sibling_ids = [s.id for s in siblings]
        assert child2.id in sibling_ids
        assert child3.id in sibling_ids
        assert child1.id not in sibling_ids


class TestDeadlineMonitoring:
    """Tests for deadline monitoring."""
    
    def test_check_deadlines(self, tracker, task_store):
        """Test checking tasks approaching deadline."""
        task = Task(name="Urgent task")
        task.deadline = datetime.utcnow() + timedelta(minutes=15)
        task_store.create(task)
        
        approaching = tracker.check_deadlines(warning_threshold_minutes=30.0)
        
        assert len(approaching) == 1
        assert approaching[0].id == task.id
    
    def test_check_deadlines_emits_warning(self, tracker, task_store):
        """Test deadline check emits warning event."""
        task = Task(name="Urgent task")
        task.deadline = datetime.utcnow() + timedelta(minutes=15)
        task_store.create(task)
        
        events_received = []
        tracker.subscribe(lambda e: events_received.append(e))
        
        tracker.check_deadlines(warning_threshold_minutes=30.0)
        
        assert any(e.event_type == TaskEventType.DEADLINE_WARNING for e in events_received)
    
    def test_check_deadlines_ignores_far_deadlines(self, tracker, task_store):
        """Test deadline check ignores far deadlines."""
        task = Task(name="Future task")
        task.deadline = datetime.utcnow() + timedelta(hours=24)
        task_store.create(task)
        
        approaching = tracker.check_deadlines(warning_threshold_minutes=30.0)
        
        assert len(approaching) == 0


class TestTimeoutMonitoring:
    """Tests for timeout monitoring."""
    
    def test_check_timeouts(self, tracker, task_store):
        """Test checking timed out tasks."""
        task = Task(name="Slow task")
        task.constraints.timeout_seconds = 1.0
        task.set_status(TaskStatus.RUNNING)
        task.execution.started_at = datetime.utcnow() - timedelta(seconds=10)
        task_store.create(task)
        
        timed_out = tracker.check_timeouts()
        
        assert len(timed_out) == 1
        assert timed_out[0].id == task.id
    
    def test_check_timeouts_emits_warning(self, tracker, task_store):
        """Test timeout check emits warning event."""
        task = Task(name="Slow task")
        task.constraints.timeout_seconds = 1.0
        task.set_status(TaskStatus.RUNNING)
        task.execution.started_at = datetime.utcnow() - timedelta(seconds=10)
        task_store.create(task)
        
        events_received = []
        tracker.subscribe(lambda e: events_received.append(e))
        
        tracker.check_timeouts()
        
        assert any(e.event_type == TaskEventType.TIMEOUT_WARNING for e in events_received)
    
    def test_check_timeouts_ignores_healthy_tasks(self, tracker, task_store):
        """Test timeout check ignores healthy tasks."""
        task = Task(name="Fast task")
        task.constraints.timeout_seconds = 3600.0
        task.set_status(TaskStatus.RUNNING)
        task.execution.started_at = datetime.utcnow()
        task_store.create(task)
        
        timed_out = tracker.check_timeouts()
        
        assert len(timed_out) == 0


class TestMetrics:
    """Tests for metrics collection."""
    
    def test_get_metrics(self, tracker, task_store):
        """Test getting tracker metrics."""
        task = Task(name="Test")
        task_store.create(task)
        
        tracker.emit_event(TaskEvent(TaskEventType.CREATED, task.id))
        tracker.emit_event(TaskEvent(TaskEventType.STARTED, task.id))
        
        metrics = tracker.get_metrics()
        
        assert "task_counts" in metrics
        assert "event_counts" in metrics
        assert metrics["total_events"] == 2
    
    def test_clear_cache(self, tracker, task_store, sample_task):
        """Test clearing progress cache."""
        task_store.create(sample_task)
        tracker.get_progress(sample_task.id)  # Populate cache
        
        tracker.clear_cache()
        
        metrics = tracker.get_metrics()
        assert metrics["cached_progress_count"] == 0
    
    def test_clear_history(self, tracker):
        """Test clearing event history."""
        tracker.emit_event(TaskEvent(TaskEventType.CREATED, "task_1"))
        tracker.emit_event(TaskEvent(TaskEventType.STARTED, "task_1"))
        
        tracker.clear_history()
        
        history = tracker.get_event_history()
        assert len(history) == 0


class TestTaskEventModel:
    """Tests for TaskEvent model."""
    
    def test_create_event(self):
        """Test creating task event."""
        event = TaskEvent(
            event_type=TaskEventType.COMPLETED,
            task_id="task_test1234567",
            data={"duration": 10.5},
        )
        
        assert event.event_type == TaskEventType.COMPLETED
        assert event.task_id == "task_test1234567"
        assert event.data["duration"] == 10.5
        assert event.timestamp is not None
    
    def test_event_to_dict(self):
        """Test event serialization."""
        event = TaskEvent(
            event_type=TaskEventType.FAILED,
            task_id="task_test1234567",
            data={"error": "Test"},
            parent_task_id="task_parent123",
        )
        
        data = event.to_dict()
        
        assert data["event_type"] == "failed"
        assert data["task_id"] == "task_test1234567"
        assert data["parent_task_id"] == "task_parent123"


class TestTaskProgressModel:
    """Tests for TaskProgress model."""
    
    def test_create_progress(self):
        """Test creating task progress."""
        progress = TaskProgress(
            task_id="task_test1234567",
            status=TaskStatus.RUNNING,
            progress_percent=75.0,
            current_step="Finalizing",
        )
        
        assert progress.progress_percent == 75.0
        assert progress.current_step == "Finalizing"
    
    def test_progress_to_dict(self):
        """Test progress serialization."""
        progress = TaskProgress(
            task_id="task_test1234567",
            status=TaskStatus.RUNNING,
            progress_percent=50.0,
            elapsed_seconds=30.0,
        )
        
        data = progress.to_dict()
        
        assert data["task_id"] == "task_test1234567"
        assert data["status"] == "running"
        assert data["progress_percent"] == 50.0
        assert data["elapsed_seconds"] == 30.0


class TestAggregateStatusModel:
    """Tests for AggregateStatus model."""
    
    def test_create_aggregate_status(self):
        """Test creating aggregate status."""
        status = AggregateStatus(
            total_tasks=10,
            completed=5,
            running=2,
            pending=3,
        )
        
        assert status.total_tasks == 10
        assert status.completed == 5
    
    def test_aggregate_status_to_dict(self):
        """Test aggregate status serialization."""
        status = AggregateStatus(
            total_tasks=5,
            completed=2,
            overall_progress=40.0,
        )
        
        data = status.to_dict()
        
        assert data["total_tasks"] == 5
        assert data["completed"] == 2
        assert data["overall_progress"] == 40.0
