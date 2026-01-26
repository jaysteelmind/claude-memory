"""Tests for TaskManagerAgent."""

import pytest

from examples.agents.task_manager_agent import (
    Task,
    TaskManagerAgent,
    TaskManagerConfig,
    TaskPriority,
    TaskStatus,
)


class TestTaskManagerAgent:
    """Tests for TaskManagerAgent."""

    def test_init_default_config(self) -> None:
        """Agent initializes with default config."""
        agent = TaskManagerAgent()
        assert agent.config.max_concurrent_tasks == 5
        assert agent.config.default_priority == TaskPriority.NORMAL

    def test_init_custom_config(self) -> None:
        """Agent initializes with custom config."""
        config = TaskManagerConfig(
            max_concurrent_tasks=10,
            default_priority=TaskPriority.HIGH,
        )
        agent = TaskManagerAgent(config=config)
        assert agent.config.max_concurrent_tasks == 10
        assert agent.config.default_priority == TaskPriority.HIGH

    def test_create_task(self) -> None:
        """Create task with basic parameters."""
        agent = TaskManagerAgent()
        
        task = agent.create_task(
            name="Test Task",
            description="A test task",
        )
        
        assert task.name == "Test Task"
        assert task.description == "A test task"
        assert task.status == TaskStatus.PENDING
        assert task.priority == TaskPriority.NORMAL
        assert task.task_id.startswith("task_")

    def test_create_task_with_priority(self) -> None:
        """Create task with specific priority."""
        agent = TaskManagerAgent()
        
        task = agent.create_task(
            name="Urgent Task",
            description="Must do now",
            priority=TaskPriority.CRITICAL,
        )
        
        assert task.priority == TaskPriority.CRITICAL

    def test_create_task_with_dependencies(self) -> None:
        """Create task with dependencies."""
        agent = TaskManagerAgent()
        
        task1 = agent.create_task(name="First", description="First task")
        task2 = agent.create_task(
            name="Second",
            description="Depends on first",
            dependencies=[task1.task_id],
        )
        
        assert task1.task_id in task2.dependencies

    def test_decompose_task(self) -> None:
        """Decompose task into subtasks."""
        agent = TaskManagerAgent()
        
        main_task = agent.create_task(
            name="Main Task",
            description="Review code",
        )
        
        subtasks = agent.decompose_task(
            main_task.task_id,
            subtask_definitions=[
                {"name": "Step 1", "description": "First step"},
                {"name": "Step 2", "description": "Second step"},
            ],
        )
        
        assert len(subtasks) == 2
        assert subtasks[0].parent_id == main_task.task_id
        assert subtasks[1].parent_id == main_task.task_id
        assert main_task.task_id == subtasks[0].parent_id

    def test_decompose_task_auto(self) -> None:
        """Decompose task with automatic decomposition."""
        agent = TaskManagerAgent()
        
        main_task = agent.create_task(
            name="Code Review",
            description="Review Python code for quality",
        )
        
        subtasks = agent.decompose_task(main_task.task_id)
        
        assert len(subtasks) > 0
        assert all(st.parent_id == main_task.task_id for st in subtasks)

    def test_decompose_nonexistent_task(self) -> None:
        """Decompose raises error for nonexistent task."""
        agent = TaskManagerAgent()
        
        with pytest.raises(KeyError):
            agent.decompose_task("nonexistent_task_id")

    def test_schedule_tasks(self) -> None:
        """Schedule pending tasks."""
        agent = TaskManagerAgent()
        
        task1 = agent.create_task(name="Task 1", description="First")
        task2 = agent.create_task(name="Task 2", description="Second")
        
        scheduled = agent.schedule_tasks()
        
        assert len(scheduled) == 2
        assert all(t.status == TaskStatus.SCHEDULED for t in scheduled)

    def test_schedule_respects_max_concurrent(self) -> None:
        """Scheduling respects max concurrent limit."""
        config = TaskManagerConfig(max_concurrent_tasks=2)
        agent = TaskManagerAgent(config=config)
        
        for i in range(5):
            task = agent.create_task(name=f"Task {i}", description=f"Task {i}")
            agent.start_task(task.task_id)
        
        new_task = agent.create_task(name="New Task", description="New")
        scheduled = agent.schedule_tasks()
        
        assert len(scheduled) == 0

    def test_start_task(self) -> None:
        """Start a pending task."""
        agent = TaskManagerAgent()
        
        task = agent.create_task(name="Task", description="Test")
        agent.start_task(task.task_id)
        
        assert task.status == TaskStatus.RUNNING
        assert task.started_at is not None

    def test_start_nonexistent_task(self) -> None:
        """Start raises error for nonexistent task."""
        agent = TaskManagerAgent()
        
        with pytest.raises(KeyError):
            agent.start_task("nonexistent_task_id")

    def test_complete_task(self) -> None:
        """Complete a running task."""
        agent = TaskManagerAgent()
        
        task = agent.create_task(name="Task", description="Test")
        agent.start_task(task.task_id)
        agent.complete_task(task.task_id, outputs={"result": "done"})
        
        assert task.status == TaskStatus.COMPLETED
        assert task.completed_at is not None
        assert task.progress == 1.0
        assert task.outputs["result"] == "done"

    def test_fail_task(self) -> None:
        """Fail a task."""
        agent = TaskManagerAgent()
        
        task = agent.create_task(name="Task", description="Test")
        agent.start_task(task.task_id)
        agent.fail_task(task.task_id, error="Something went wrong")
        
        assert task.status == TaskStatus.FAILED
        assert task.outputs["error"] == "Something went wrong"

    def test_update_progress(self) -> None:
        """Update task progress."""
        agent = TaskManagerAgent()
        
        task = agent.create_task(name="Task", description="Test")
        agent.start_task(task.task_id)
        agent.update_progress(task.task_id, 0.5)
        
        assert task.progress == 0.5

    def test_update_progress_clamps_values(self) -> None:
        """Progress is clamped to 0.0-1.0."""
        agent = TaskManagerAgent()
        
        task = agent.create_task(name="Task", description="Test")
        
        agent.update_progress(task.task_id, 1.5)
        assert task.progress == 1.0
        
        agent.update_progress(task.task_id, -0.5)
        assert task.progress == 0.0

    def test_delegate_task(self) -> None:
        """Delegate task to agent."""
        agent = TaskManagerAgent()
        
        task = agent.create_task(name="Task", description="Test")
        agent.delegate_task(task.task_id, "agent_123")
        
        assert task.assigned_agent == "agent_123"

    def test_get_task(self) -> None:
        """Get task by ID."""
        agent = TaskManagerAgent()
        
        task = agent.create_task(name="Task", description="Test")
        retrieved = agent.get_task(task.task_id)
        
        assert retrieved is task

    def test_get_task_not_found(self) -> None:
        """Get returns None for nonexistent task."""
        agent = TaskManagerAgent()
        
        result = agent.get_task("nonexistent")
        assert result is None

    def test_get_all_tasks(self) -> None:
        """Get all tasks."""
        agent = TaskManagerAgent()
        
        agent.create_task(name="Task 1", description="First")
        agent.create_task(name="Task 2", description="Second")
        
        tasks = agent.get_all_tasks()
        assert len(tasks) == 2

    def test_get_tasks_by_status(self) -> None:
        """Get tasks filtered by status."""
        agent = TaskManagerAgent()
        
        task1 = agent.create_task(name="Task 1", description="First")
        task2 = agent.create_task(name="Task 2", description="Second")
        agent.start_task(task1.task_id)
        
        running = agent.get_tasks_by_status(TaskStatus.RUNNING)
        pending = agent.get_tasks_by_status(TaskStatus.PENDING)
        
        assert len(running) == 1
        assert len(pending) == 1

    def test_get_execution_order(self) -> None:
        """Get execution order respects dependencies."""
        agent = TaskManagerAgent()
        
        task1 = agent.create_task(name="First", description="No deps")
        task2 = agent.create_task(
            name="Second",
            description="Depends on first",
            dependencies=[task1.task_id],
        )
        
        order = agent.get_execution_order()
        
        task1_idx = next(i for i, t in enumerate(order) if t.task_id == task1.task_id)
        task2_idx = next(i for i, t in enumerate(order) if t.task_id == task2.task_id)
        
        assert task1_idx < task2_idx

    def test_subscribe_to_events(self) -> None:
        """Subscribe to task events."""
        agent = TaskManagerAgent()
        events = []
        
        def callback(task: Task, event: str) -> None:
            events.append((task.task_id, event))
        
        agent.subscribe(callback)
        
        task = agent.create_task(name="Task", description="Test")
        agent.start_task(task.task_id)
        agent.complete_task(task.task_id)
        
        assert len(events) == 3
        assert events[0][1] == "created"
        assert events[1][1] == "started"
        assert events[2][1] == "completed"

    def test_get_status_report(self) -> None:
        """Generate status report."""
        agent = TaskManagerAgent()
        
        task1 = agent.create_task(name="Task 1", description="First")
        task2 = agent.create_task(name="Task 2", description="Second")
        agent.start_task(task1.task_id)
        agent.complete_task(task1.task_id)
        
        report = agent.get_status_report()
        
        assert "# Task Status Report" in report
        assert "Task 1" in report
        assert "Task 2" in report

    def test_parent_progress_updates(self) -> None:
        """Parent task progress updates from subtasks."""
        agent = TaskManagerAgent()
        
        main_task = agent.create_task(name="Main", description="Parent")
        subtasks = agent.decompose_task(
            main_task.task_id,
            subtask_definitions=[
                {"name": "Sub 1", "description": "First"},
                {"name": "Sub 2", "description": "Second"},
            ],
        )
        
        agent.start_task(subtasks[0].task_id)
        agent.complete_task(subtasks[0].task_id)
        
        assert main_task.progress == 0.5
        
        agent.start_task(subtasks[1].task_id)
        agent.complete_task(subtasks[1].task_id)
        
        assert main_task.progress == 1.0


class TestTask:
    """Tests for Task dataclass."""

    def test_to_dict(self) -> None:
        """Task converts to dictionary."""
        task = Task(
            task_id="task_123",
            name="Test Task",
            description="A test",
            priority=TaskPriority.HIGH,
        )
        
        data = task.to_dict()
        
        assert data["task_id"] == "task_123"
        assert data["name"] == "Test Task"
        assert data["priority"] == "high"
        assert data["status"] == "pending"
