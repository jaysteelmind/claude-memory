"""
Unit tests for task data models.

Tests cover:
- Task creation and validation
- Status transitions
- Dependency management
- Serialization/deserialization
- TaskResult and TaskPlan models
"""

import pytest
from datetime import datetime, timedelta
from dmm.agentos.tasks import (
    Task,
    TaskStatus,
    TaskPriority,
    TaskType,
    DependencyType,
    TaskDependency,
    TaskRequirements,
    TaskConstraints,
    TaskExecution,
    TaskOutput,
    TaskError,
    TaskResult,
    TaskPlan,
    generate_task_id,
    validate_task_id,
    is_valid_transition,
)


class TestTaskIdGeneration:
    """Tests for task ID generation and validation."""
    
    def test_generate_task_id_format(self):
        """Test generated ID has correct format."""
        task_id = generate_task_id()
        assert task_id.startswith("task_")
        assert len(task_id) >= 13  # task_ + at least 8 hex chars
    
    def test_generate_task_id_uniqueness(self):
        """Test generated IDs are unique."""
        ids = [generate_task_id() for _ in range(100)]
        assert len(set(ids)) == 100
    
    def test_validate_task_id_valid(self):
        """Test validation of valid task IDs."""
        assert validate_task_id("task_abc12345")
        assert validate_task_id("task_0123456789abcdef")
        assert validate_task_id("task_ffffffff")
    
    def test_validate_task_id_invalid(self):
        """Test validation of invalid task IDs."""
        assert not validate_task_id("task_")
        assert not validate_task_id("task_ABC")  # uppercase
        assert not validate_task_id("task_12")  # too short
        assert not validate_task_id("invalid_abc12345")  # wrong prefix
        assert not validate_task_id("")


class TestTaskStatus:
    """Tests for TaskStatus enum."""
    
    def test_terminal_states(self):
        """Test terminal states identification."""
        terminal = TaskStatus.terminal_states()
        assert TaskStatus.COMPLETED in terminal
        assert TaskStatus.FAILED in terminal
        assert TaskStatus.CANCELLED in terminal
        assert TaskStatus.RUNNING not in terminal
    
    def test_active_states(self):
        """Test active states identification."""
        active = TaskStatus.active_states()
        assert TaskStatus.PENDING in active
        assert TaskStatus.RUNNING in active
        assert TaskStatus.BLOCKED in active
        assert TaskStatus.COMPLETED not in active
    
    def test_is_terminal(self):
        """Test is_terminal method."""
        assert TaskStatus.COMPLETED.is_terminal()
        assert TaskStatus.FAILED.is_terminal()
        assert not TaskStatus.RUNNING.is_terminal()
    
    def test_is_active(self):
        """Test is_active method."""
        assert TaskStatus.RUNNING.is_active()
        assert TaskStatus.PENDING.is_active()
        assert not TaskStatus.COMPLETED.is_active()


class TestStatusTransitions:
    """Tests for status transition validation."""
    
    def test_valid_transitions_from_pending(self):
        """Test valid transitions from PENDING."""
        assert is_valid_transition(TaskStatus.PENDING, TaskStatus.SCHEDULED)
        assert is_valid_transition(TaskStatus.PENDING, TaskStatus.RUNNING)
        assert is_valid_transition(TaskStatus.PENDING, TaskStatus.CANCELLED)
    
    def test_invalid_transitions_from_pending(self):
        """Test invalid transitions from PENDING."""
        assert not is_valid_transition(TaskStatus.PENDING, TaskStatus.COMPLETED)
        assert not is_valid_transition(TaskStatus.PENDING, TaskStatus.FAILED)
    
    def test_valid_transitions_from_running(self):
        """Test valid transitions from RUNNING."""
        assert is_valid_transition(TaskStatus.RUNNING, TaskStatus.COMPLETED)
        assert is_valid_transition(TaskStatus.RUNNING, TaskStatus.FAILED)
        assert is_valid_transition(TaskStatus.RUNNING, TaskStatus.PAUSED)
        assert is_valid_transition(TaskStatus.RUNNING, TaskStatus.CANCELLED)
    
    def test_no_transitions_from_completed(self):
        """Test no transitions from COMPLETED."""
        assert not is_valid_transition(TaskStatus.COMPLETED, TaskStatus.RUNNING)
        assert not is_valid_transition(TaskStatus.COMPLETED, TaskStatus.PENDING)
    
    def test_retry_transition_from_failed(self):
        """Test retry transition from FAILED."""
        assert is_valid_transition(TaskStatus.FAILED, TaskStatus.PENDING)


class TestTaskCreation:
    """Tests for Task creation."""
    
    def test_create_minimal_task(self):
        """Test creating task with minimal arguments."""
        task = Task(name="Test task")
        assert task.name == "Test task"
        assert task.id.startswith("task_")
        assert task.execution.status == TaskStatus.PENDING
        assert task.task_type == TaskType.SIMPLE
    
    def test_create_task_with_all_fields(self):
        """Test creating task with all fields."""
        task = Task(
            id="task_testid12345",
            name="Full task",
            description="A complete task",
            task_type=TaskType.COMPOSITE,
            priority=8,
            assigned_agent="agent_reviewer",
            tags=["test", "important"],
        )
        assert task.id == "task_testid12345"
        assert task.name == "Full task"
        assert task.priority == 8
        assert task.assigned_agent == "agent_reviewer"
        assert "test" in task.tags
    
    def test_task_default_timestamps(self):
        """Test task has default timestamps."""
        task = Task(name="Test")
        assert task.created_at is not None
        assert task.updated_at is not None
        assert isinstance(task.created_at, datetime)


class TestTaskValidation:
    """Tests for Task validation."""
    
    def test_validate_valid_task(self):
        """Test validation of valid task."""
        task = Task(name="Valid task")
        errors = task.validate()
        assert len(errors) == 0
    
    def test_validate_missing_name(self):
        """Test validation catches missing name."""
        task = Task(name="")
        errors = task.validate()
        assert any("name is required" in e for e in errors)
    
    def test_validate_name_too_long(self):
        """Test validation catches name too long."""
        task = Task(name="x" * 300)
        errors = task.validate()
        assert any("exceeds maximum length" in e for e in errors)
    
    def test_validate_invalid_priority(self):
        """Test validation catches invalid priority."""
        task = Task(name="Test", priority=15)
        errors = task.validate()
        assert any("priority must be between" in e for e in errors)
    
    def test_validate_circular_dependency(self):
        """Test validation catches self-dependency."""
        task = Task(name="Test")
        task.dependencies.append(TaskDependency(task_id=task.id))
        errors = task.validate()
        assert any("cannot depend on itself" in e for e in errors)


class TestTaskStatusManagement:
    """Tests for Task status management."""
    
    def test_set_status_valid_transition(self):
        """Test valid status transition."""
        task = Task(name="Test")
        assert task.set_status(TaskStatus.SCHEDULED)
        assert task.status == TaskStatus.SCHEDULED
    
    def test_set_status_invalid_transition(self):
        """Test invalid status transition."""
        task = Task(name="Test")
        assert not task.set_status(TaskStatus.COMPLETED)
        assert task.status == TaskStatus.PENDING
    
    def test_set_status_updates_timestamps(self):
        """Test status change updates timestamps."""
        task = Task(name="Test")
        original_updated = task.updated_at
        task.set_status(TaskStatus.RUNNING)
        assert task.updated_at >= original_updated
        assert task.execution.started_at is not None
    
    def test_set_status_to_terminal_sets_completed_at(self):
        """Test terminal status sets completed_at."""
        task = Task(name="Test")
        task.set_status(TaskStatus.RUNNING)
        task.set_status(TaskStatus.COMPLETED)
        assert task.execution.completed_at is not None
    
    def test_is_complete(self):
        """Test is_complete method."""
        task = Task(name="Test")
        assert not task.is_complete()
        task.set_status(TaskStatus.RUNNING)
        task.set_status(TaskStatus.COMPLETED)
        assert task.is_complete()
    
    def test_is_runnable(self):
        """Test is_runnable method."""
        task = Task(name="Test")
        assert task.is_runnable()
        task.blocked_by.append("other_task")
        assert not task.is_runnable()


class TestTaskDependencies:
    """Tests for Task dependency management."""
    
    def test_add_dependency(self):
        """Test adding dependency."""
        task = Task(name="Test")
        task.add_dependency("task_dep123456")
        assert len(task.dependencies) == 1
        assert task.dependencies[0].task_id == "task_dep123456"
        assert "task_dep123456" in task.blocked_by
    
    def test_add_dependency_with_type(self):
        """Test adding dependency with specific type."""
        task = Task(name="Test")
        task.add_dependency("task_dep123456", DependencyType.DATA, required=False)
        assert task.dependencies[0].dependency_type == DependencyType.DATA
        assert not task.dependencies[0].required
    
    def test_remove_dependency(self):
        """Test removing dependency."""
        task = Task(name="Test")
        task.add_dependency("task_dep123456")
        assert task.remove_dependency("task_dep123456")
        assert len(task.dependencies) == 0
        assert "task_dep123456" not in task.blocked_by
    
    def test_resolve_dependency(self):
        """Test resolving dependency."""
        task = Task(name="Test")
        task.add_dependency("task_dep123456")
        task.resolve_dependency("task_dep123456")
        assert "task_dep123456" not in task.blocked_by
    
    def test_get_required_dependencies(self):
        """Test getting required dependencies."""
        task = Task(name="Test")
        task.add_dependency("task_req1", required=True)
        task.add_dependency("task_opt1", required=False)
        required = task.get_required_dependencies()
        assert "task_req1" in required
        assert "task_opt1" not in required


class TestTaskSubtasks:
    """Tests for Task subtask management."""
    
    def test_add_subtask(self):
        """Test adding subtask."""
        task = Task(name="Parent")
        assert task.add_subtask("task_child123")
        assert "task_child123" in task.subtask_ids
        assert task.task_type == TaskType.COMPOSITE
    
    def test_add_subtask_max_depth(self):
        """Test adding subtask respects max depth."""
        task = Task(name="Parent", depth=10)
        assert not task.add_subtask("task_child123")
    
    def test_remove_subtask(self):
        """Test removing subtask."""
        task = Task(name="Parent")
        task.add_subtask("task_child123")
        assert task.remove_subtask("task_child123")
        assert "task_child123" not in task.subtask_ids
        assert task.task_type == TaskType.SIMPLE
    
    def test_has_subtasks(self):
        """Test has_subtasks method."""
        task = Task(name="Test")
        assert not task.has_subtasks()
        task.add_subtask("task_child123")
        assert task.has_subtasks()


class TestTaskExecution:
    """Tests for Task execution management."""
    
    def test_start_attempt(self):
        """Test starting execution attempt."""
        task = Task(name="Test")
        attempt = task.start_attempt()
        assert attempt == 1
        assert task.execution.attempt_count == 1
    
    def test_can_retry(self):
        """Test can_retry method."""
        task = Task(name="Test")
        task.constraints.max_attempts = 3
        assert task.can_retry()
        task.execution.attempt_count = 3
        assert not task.can_retry()
    
    def test_record_error(self):
        """Test recording error."""
        task = Task(name="Test")
        error = TaskError(
            error_type="ValueError",
            message="Something went wrong",
        )
        task.record_error(error)
        assert task.execution.last_error == "Something went wrong"
    
    def test_set_output(self):
        """Test setting output."""
        task = Task(name="Test")
        output = TaskOutput(data={"result": "success"})
        task.set_output(output)
        assert task.outputs is not None
        assert task.outputs.data["result"] == "success"


class TestTaskSerialization:
    """Tests for Task serialization."""
    
    def test_to_dict(self):
        """Test converting task to dictionary."""
        task = Task(
            name="Test task",
            description="A test",
            priority=7,
            tags=["test"],
        )
        data = task.to_dict()
        assert data["name"] == "Test task"
        assert data["description"] == "A test"
        assert data["priority"] == 7
        assert "test" in data["tags"]
    
    def test_from_dict(self):
        """Test creating task from dictionary."""
        data = {
            "id": "task_test1234567",
            "name": "From dict",
            "description": "Created from dict",
            "task_type": "simple",
            "priority": 6,
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }
        task = Task.from_dict(data)
        assert task.id == "task_test1234567"
        assert task.name == "From dict"
        assert task.priority == 6
    
    def test_round_trip_serialization(self):
        """Test serialization round trip."""
        original = Task(
            name="Original",
            description="Test round trip",
            priority=8,
            tags=["a", "b"],
        )
        original.add_dependency("task_dep123456")
        
        data = original.to_dict()
        restored = Task.from_dict(data)
        
        assert restored.name == original.name
        assert restored.priority == original.priority
        assert restored.tags == original.tags


class TestTaskResult:
    """Tests for TaskResult model."""
    
    def test_create_success_result(self):
        """Test creating success result."""
        result = TaskResult(
            task_id="task_test1234567",
            status=TaskStatus.COMPLETED,
            outputs=TaskOutput(data={"value": 42}),
            duration_seconds=1.5,
        )
        assert result.is_success()
        assert not result.is_failure()
        assert result.outputs.data["value"] == 42
    
    def test_create_failure_result(self):
        """Test creating failure result."""
        result = TaskResult(
            task_id="task_test1234567",
            status=TaskStatus.FAILED,
            error=TaskError(error_type="Error", message="Failed"),
        )
        assert result.is_failure()
        assert not result.is_success()
        assert result.error.message == "Failed"
    
    def test_result_to_dict(self):
        """Test result serialization."""
        result = TaskResult(
            task_id="task_test1234567",
            status=TaskStatus.COMPLETED,
            duration_seconds=2.0,
        )
        data = result.to_dict()
        assert data["task_id"] == "task_test1234567"
        assert data["status"] == "completed"
        assert data["duration_seconds"] == 2.0


class TestTaskPlan:
    """Tests for TaskPlan model."""
    
    def test_create_plan(self):
        """Test creating task plan."""
        root = Task(name="Root task")
        subtask1 = Task(name="Subtask 1", parent_id=root.id)
        subtask2 = Task(name="Subtask 2", parent_id=root.id)
        
        plan = TaskPlan(
            root_task=root,
            subtasks=[subtask1, subtask2],
            execution_order=[root.id, subtask1.id, subtask2.id],
        )
        
        assert plan.root_task == root
        assert len(plan.subtasks) == 2
    
    def test_get_all_tasks(self):
        """Test getting all tasks from plan."""
        root = Task(name="Root")
        subtask = Task(name="Subtask")
        plan = TaskPlan(root_task=root, subtasks=[subtask])
        
        all_tasks = plan.get_all_tasks()
        assert len(all_tasks) == 2
        assert root in all_tasks
        assert subtask in all_tasks
    
    def test_get_task_by_id(self):
        """Test getting task by ID from plan."""
        root = Task(name="Root")
        subtask = Task(name="Subtask")
        plan = TaskPlan(root_task=root, subtasks=[subtask])
        
        found = plan.get_task_by_id(subtask.id)
        assert found == subtask
        
        not_found = plan.get_task_by_id("nonexistent")
        assert not_found is None
    
    def test_plan_to_dict(self):
        """Test plan serialization."""
        root = Task(name="Root")
        plan = TaskPlan(
            root_task=root,
            execution_order=[root.id],
            estimated_duration_seconds=60.0,
        )
        
        data = plan.to_dict()
        assert data["root_task"]["name"] == "Root"
        assert data["estimated_duration_seconds"] == 60.0
