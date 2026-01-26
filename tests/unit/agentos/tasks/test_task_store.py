"""
Unit tests for task store.

Tests cover:
- Store initialization
- CRUD operations
- Query operations
- Status updates
- Dependency resolution
- Logging
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

from dmm.agentos.tasks import (
    Task,
    TaskStore,
    TaskStatus,
    TaskType,
    DependencyType,
    TaskDependency,
    TaskOutput,
)


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def task_store(temp_dir):
    """Create initialized task store."""
    store = TaskStore(temp_dir, use_file_storage=True)
    store.initialize()
    yield store
    store.close()


@pytest.fixture
def sample_task():
    """Create sample task for testing."""
    return Task(
        name="Sample task",
        description="A sample task for testing",
        priority=5,
        tags=["test", "sample"],
    )


class TestTaskStoreInitialization:
    """Tests for task store initialization."""
    
    def test_initialize_creates_directories(self, temp_dir):
        """Test initialization creates required directories."""
        store = TaskStore(temp_dir, use_file_storage=True)
        store.initialize()
        
        assert (temp_dir / "index").exists()
        assert (temp_dir / "tasks").exists()
        assert (temp_dir / "tasks" / "active").exists()
        assert (temp_dir / "tasks" / "pending").exists()
        assert (temp_dir / "tasks" / "completed").exists()
        assert (temp_dir / "tasks" / "failed").exists()
        
        store.close()
    
    def test_initialize_creates_database(self, temp_dir):
        """Test initialization creates database."""
        store = TaskStore(temp_dir)
        store.initialize()
        
        assert (temp_dir / "index" / "tasks.db").exists()
        
        store.close()
    
    def test_double_initialize_safe(self, task_store):
        """Test calling initialize twice is safe."""
        task_store.initialize()  # Should not raise


class TestTaskStoreCRUD:
    """Tests for CRUD operations."""
    
    def test_create_task(self, task_store, sample_task):
        """Test creating a task."""
        task_id = task_store.create(sample_task)
        
        assert task_id == sample_task.id
        
        retrieved = task_store.get(task_id)
        assert retrieved is not None
        assert retrieved.name == sample_task.name
    
    def test_create_duplicate_raises(self, task_store, sample_task):
        """Test creating duplicate task raises error."""
        task_store.create(sample_task)
        
        with pytest.raises(ValueError, match="already exists"):
            task_store.create(sample_task)
    
    def test_create_invalid_task_raises(self, task_store):
        """Test creating invalid task raises error."""
        invalid_task = Task(name="")  # Empty name
        
        with pytest.raises(ValueError, match="Invalid task"):
            task_store.create(invalid_task)
    
    def test_get_existing_task(self, task_store, sample_task):
        """Test getting existing task."""
        task_store.create(sample_task)
        
        retrieved = task_store.get(sample_task.id)
        
        assert retrieved is not None
        assert retrieved.id == sample_task.id
        assert retrieved.name == sample_task.name
        assert retrieved.description == sample_task.description
    
    def test_get_nonexistent_task(self, task_store):
        """Test getting nonexistent task returns None."""
        result = task_store.get("task_nonexistent1")
        assert result is None
    
    def test_update_task(self, task_store, sample_task):
        """Test updating a task."""
        task_store.create(sample_task)
        
        sample_task.name = "Updated name"
        sample_task.priority = 8
        
        assert task_store.update(sample_task)
        
        retrieved = task_store.get(sample_task.id)
        assert retrieved.name == "Updated name"
        assert retrieved.priority == 8
    
    def test_update_nonexistent_returns_false(self, task_store, sample_task):
        """Test updating nonexistent task returns False."""
        result = task_store.update(sample_task)
        assert result is False
    
    def test_delete_task(self, task_store, sample_task):
        """Test deleting a task."""
        task_store.create(sample_task)
        
        assert task_store.delete(sample_task.id)
        assert task_store.get(sample_task.id) is None
    
    def test_delete_nonexistent_returns_false(self, task_store):
        """Test deleting nonexistent task returns False."""
        result = task_store.delete("task_nonexistent1")
        assert result is False


class TestTaskStoreQueries:
    """Tests for query operations."""
    
    def test_list_tasks_empty(self, task_store):
        """Test listing tasks when empty."""
        tasks = task_store.list_tasks()
        assert len(tasks) == 0
    
    def test_list_tasks_all(self, task_store):
        """Test listing all tasks."""
        for i in range(5):
            task = Task(name=f"Task {i}")
            task_store.create(task)
        
        tasks = task_store.list_tasks()
        assert len(tasks) == 5
    
    def test_list_tasks_by_status(self, task_store):
        """Test listing tasks by status."""
        task1 = Task(name="Pending task")
        task2 = Task(name="Running task")
        
        task_store.create(task1)
        task_store.create(task2)
        
        task2.set_status(TaskStatus.RUNNING)
        task_store.update(task2)
        
        pending = task_store.list_tasks(status=TaskStatus.PENDING)
        running = task_store.list_tasks(status=TaskStatus.RUNNING)
        
        assert len(pending) == 1
        assert len(running) == 1
    
    def test_list_tasks_by_agent(self, task_store):
        """Test listing tasks by agent."""
        task1 = Task(name="Task 1", assigned_agent="agent_a")
        task2 = Task(name="Task 2", assigned_agent="agent_b")
        task3 = Task(name="Task 3", assigned_agent="agent_a")
        
        task_store.create(task1)
        task_store.create(task2)
        task_store.create(task3)
        
        agent_a_tasks = task_store.list_tasks(agent_id="agent_a")
        assert len(agent_a_tasks) == 2
    
    def test_list_tasks_with_pagination(self, task_store):
        """Test listing tasks with pagination."""
        for i in range(10):
            task = Task(name=f"Task {i}")
            task_store.create(task)
        
        page1 = task_store.list_tasks(limit=3, offset=0)
        page2 = task_store.list_tasks(limit=3, offset=3)
        
        assert len(page1) == 3
        assert len(page2) == 3
        assert page1[0].id != page2[0].id
    
    def test_get_runnable_tasks(self, task_store):
        """Test getting runnable tasks."""
        task1 = Task(name="Runnable")
        task2 = Task(name="Blocked")
        task2.blocked_by.append("task_blocker123")
        
        task_store.create(task1)
        task_store.create(task2)
        
        runnable = task_store.get_runnable_tasks()
        
        assert len(runnable) >= 1
        assert any(t.id == task1.id for t in runnable)
    
    def test_get_tasks_by_ids(self, task_store):
        """Test getting multiple tasks by IDs."""
        task1 = Task(name="Task 1")
        task2 = Task(name="Task 2")
        task3 = Task(name="Task 3")
        
        task_store.create(task1)
        task_store.create(task2)
        task_store.create(task3)
        
        tasks = task_store.get_tasks_by_ids([task1.id, task3.id])
        
        assert len(tasks) == 2
        ids = [t.id for t in tasks]
        assert task1.id in ids
        assert task3.id in ids
    
    def test_count_tasks(self, task_store):
        """Test counting tasks."""
        for i in range(5):
            task = Task(name=f"Task {i}")
            task_store.create(task)
        
        count = task_store.count_tasks()
        assert count == 5
    
    def test_count_tasks_by_status(self, task_store):
        """Test counting tasks by status."""
        task1 = Task(name="Task 1")
        task2 = Task(name="Task 2")
        
        task_store.create(task1)
        task_store.create(task2)
        
        task2.set_status(TaskStatus.RUNNING)
        task_store.update(task2)
        
        pending_count = task_store.count_tasks(status=TaskStatus.PENDING)
        running_count = task_store.count_tasks(status=TaskStatus.RUNNING)
        
        assert pending_count == 1
        assert running_count == 1


class TestTaskStoreStatusUpdates:
    """Tests for status update operations."""
    
    def test_update_status(self, task_store, sample_task):
        """Test updating task status."""
        task_store.create(sample_task)
        
        assert task_store.update_status(sample_task.id, TaskStatus.RUNNING)
        
        retrieved = task_store.get(sample_task.id)
        assert retrieved.execution.status == TaskStatus.RUNNING
    
    def test_update_status_sets_started_at(self, task_store, sample_task):
        """Test updating to RUNNING sets started_at."""
        task_store.create(sample_task)
        
        task_store.update_status(sample_task.id, TaskStatus.RUNNING)
        
        retrieved = task_store.get(sample_task.id)
        assert retrieved.execution.started_at is not None
    
    def test_update_status_with_error(self, task_store, sample_task):
        """Test updating status with error message."""
        task_store.create(sample_task)
        sample_task.set_status(TaskStatus.RUNNING)
        task_store.update(sample_task)
        
        task_store.update_status(
            sample_task.id,
            TaskStatus.FAILED,
            error_message="Test error"
        )
        
        retrieved = task_store.get(sample_task.id)
        assert retrieved.execution.last_error == "Test error"


class TestTaskStoreDependencies:
    """Tests for dependency operations."""
    
    def test_create_task_with_dependencies(self, task_store):
        """Test creating task with dependencies."""
        dep_task = Task(name="Dependency")
        task_store.create(dep_task)
        
        main_task = Task(name="Main")
        main_task.add_dependency(dep_task.id)
        task_store.create(main_task)
        
        retrieved = task_store.get(main_task.id)
        assert len(retrieved.dependencies) == 1
        assert retrieved.dependencies[0].task_id == dep_task.id
    
    def test_resolve_dependency(self, task_store):
        """Test resolving dependency."""
        dep_task = Task(name="Dependency")
        task_store.create(dep_task)
        
        main_task = Task(name="Main")
        main_task.add_dependency(dep_task.id)
        task_store.create(main_task)
        
        assert task_store.resolve_dependency(main_task.id, dep_task.id)


class TestTaskStoreLogging:
    """Tests for logging operations."""
    
    def test_add_log_entry(self, task_store, sample_task):
        """Test adding log entry."""
        task_store.create(sample_task)
        
        task_store.add_log_entry(
            sample_task.id,
            "Test log message",
            level="INFO",
            details={"key": "value"}
        )
        
        logs = task_store.get_task_logs(sample_task.id)
        assert len(logs) == 1
        assert logs[0]["message"] == "Test log message"
        assert logs[0]["level"] == "INFO"
    
    def test_get_task_logs_limit(self, task_store, sample_task):
        """Test getting logs with limit."""
        task_store.create(sample_task)
        
        for i in range(10):
            task_store.add_log_entry(sample_task.id, f"Log {i}")
        
        logs = task_store.get_task_logs(sample_task.id, limit=5)
        assert len(logs) == 5


class TestTaskStoreStatistics:
    """Tests for statistics."""
    
    def test_get_stats_empty(self, task_store):
        """Test getting stats when empty."""
        stats = task_store.get_stats()
        assert stats["total"] == 0
    
    def test_get_stats_with_tasks(self, task_store):
        """Test getting stats with tasks."""
        task1 = Task(name="Task 1", assigned_agent="agent_a")
        task2 = Task(name="Task 2", assigned_agent="agent_a")
        task3 = Task(name="Task 3", assigned_agent="agent_b")
        
        task_store.create(task1)
        task_store.create(task2)
        task_store.create(task3)
        
        stats = task_store.get_stats()
        
        assert stats["total"] == 3
        assert stats["by_status"]["pending"] == 3
        assert stats["by_agent"]["agent_a"] == 2
        assert stats["by_agent"]["agent_b"] == 1
