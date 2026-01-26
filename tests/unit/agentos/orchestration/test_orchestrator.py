"""
Unit tests for task orchestrator.

Tests cover:
- Task execution
- Callback invocation
- Error handling integration
- State management
- Metrics collection
"""

import pytest
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Optional

from dmm.agentos.orchestration import (
    TaskOrchestrator,
    OrchestratorConfig,
    OrchestratorMode,
    OrchestratorCallbacks,
    TaskExecutionResult,
    ExecutionStatus,
)


# =============================================================================
# Mock Classes
# =============================================================================

@dataclass
class MockRequirements:
    """Mock task requirements."""
    skills: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    memory_scopes: list[str] = field(default_factory=list)
    memory_tags: list[str] = field(default_factory=list)


@dataclass
class MockTask:
    """Mock task for testing."""
    id: str = "task_test123"
    name: str = "Test Task"
    description: str = "A test task"
    inputs: dict[str, Any] = field(default_factory=dict)
    requirements: MockRequirements = field(default_factory=MockRequirements)
    assigned_agent: Optional[str] = None


class MockSkill:
    """Mock skill for testing."""
    
    def __init__(self, skill_id: str, output: Any = "skill_output", should_fail: bool = False):
        self.id = skill_id
        self.name = f"Skill {skill_id}"
        self.output = output
        self.should_fail = should_fail
        self.execute_count = 0
    
    def execute(self, context, **kwargs):
        self.execute_count += 1
        if self.should_fail:
            raise ValueError(f"Skill {self.id} failed")
        return self.output


class MockTool:
    """Mock tool for testing."""
    
    def __init__(self, tool_id: str, output: Any = "tool_output"):
        self.id = tool_id
        self.name = f"Tool {tool_id}"
        self.output = output
    
    def run(self, **kwargs):
        return self.output


class MockSkillLoader:
    """Mock skill loader."""
    
    def __init__(self, skills: Optional[dict[str, MockSkill]] = None):
        self.skills = skills or {}
    
    def get(self, skill_id: str) -> Optional[MockSkill]:
        return self.skills.get(skill_id)


class MockToolLoader:
    """Mock tool loader."""
    
    def __init__(self, tools: Optional[dict[str, MockTool]] = None):
        self.tools = tools or {}
    
    def get(self, tool_id: str) -> Optional[MockTool]:
        return self.tools.get(tool_id)


# =============================================================================
# Tests
# =============================================================================

class TestOrchestratorConfig:
    """Tests for OrchestratorConfig."""
    
    def test_default_config(self):
        """Test default configuration."""
        config = OrchestratorConfig()
        
        assert config.mode == OrchestratorMode.SYNCHRONOUS
        assert config.max_concurrent_tasks == 5
        assert config.enable_error_recovery is True
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = OrchestratorConfig(
            mode=OrchestratorMode.PARALLEL,
            max_concurrent_tasks=10,
            stop_on_first_error=True,
        )
        
        assert config.mode == OrchestratorMode.PARALLEL
        assert config.max_concurrent_tasks == 10
        assert config.stop_on_first_error is True


class TestTaskOrchestrator:
    """Tests for TaskOrchestrator."""
    
    @pytest.fixture
    def orchestrator(self):
        """Create basic orchestrator."""
        return TaskOrchestrator()
    
    @pytest.fixture
    def orchestrator_with_skills(self):
        """Create orchestrator with mock skills."""
        skills = {
            "skill_1": MockSkill("skill_1", output="result_1"),
            "skill_2": MockSkill("skill_2", output="result_2"),
        }
        tools = {
            "tool_1": MockTool("tool_1", output="tool_result"),
        }
        
        return TaskOrchestrator(
            skill_loader=MockSkillLoader(skills),
            tool_loader=MockToolLoader(tools),
        )
    
    def test_create_orchestrator(self):
        """Test creating orchestrator."""
        orchestrator = TaskOrchestrator()
        assert orchestrator is not None
    
    def test_execute_simple_task(self, orchestrator):
        """Test executing simple task without skills."""
        task = MockTask(
            id="task_simple",
            name="Simple Task",
            requirements=MockRequirements(),
        )
        
        result = orchestrator.execute_task(task)
        
        assert result.task_id == "task_simple"
        assert result.success
        assert result.status == ExecutionStatus.SUCCESS
    
    def test_execute_task_with_skills(self, orchestrator_with_skills):
        """Test executing task with skills."""
        task = MockTask(
            id="task_with_skills",
            name="Task with Skills",
            requirements=MockRequirements(skills=["skill_1", "skill_2"]),
        )
        
        result = orchestrator_with_skills.execute_task(task)
        
        assert result.task_id == "task_with_skills"
        assert len(result.skill_results) == 2
    
    def test_execute_task_missing_skill(self, orchestrator):
        """Test executing task with missing skill."""
        task = MockTask(
            requirements=MockRequirements(skills=["nonexistent_skill"]),
        )
        
        result = orchestrator.execute_task(task)
        
        # Should succeed but with warning about missing skill
        assert result.success
        assert len(result.warnings) > 0
    
    def test_execute_task_failing_skill(self):
        """Test executing task with failing skill."""
        skills = {
            "failing_skill": MockSkill("failing_skill", should_fail=True),
        }
        orchestrator = TaskOrchestrator(
            skill_loader=MockSkillLoader(skills),
            config=OrchestratorConfig(enable_error_recovery=False),
        )
        
        task = MockTask(
            requirements=MockRequirements(skills=["failing_skill"]),
        )
        
        result = orchestrator.execute_task(task)
        
        assert not result.success
        assert result.status == ExecutionStatus.FAILED
    
    def test_execute_task_with_dependency_outputs(self, orchestrator):
        """Test executing task with dependency outputs."""
        task = MockTask()
        dependency_outputs = {
            "prev_task": {"data": "from_previous"},
        }
        
        result = orchestrator.execute_task(task, dependency_outputs=dependency_outputs)
        
        assert result.success
    
    def test_state_tracking(self, orchestrator):
        """Test orchestrator state tracking."""
        task = MockTask()
        
        orchestrator.execute_task(task)
        
        state = orchestrator.get_state()
        
        assert state.tasks_executed == 1
        assert state.tasks_succeeded == 1
        assert state.tasks_failed == 0
        assert not state.is_running
    
    def test_state_tracking_failure(self):
        """Test state tracking on failure."""
        skills = {"fail": MockSkill("fail", should_fail=True)}
        orchestrator = TaskOrchestrator(
            skill_loader=MockSkillLoader(skills),
            config=OrchestratorConfig(enable_error_recovery=False),
        )
        
        task = MockTask(requirements=MockRequirements(skills=["fail"]))
        orchestrator.execute_task(task)
        
        state = orchestrator.get_state()
        
        assert state.tasks_failed == 1


class TestOrchestratorCallbacks:
    """Tests for orchestrator callbacks."""
    
    def test_on_task_start_callback(self):
        """Test task start callback."""
        started_tasks = []
        
        callbacks = OrchestratorCallbacks(
            on_task_start=lambda task_id, ctx: started_tasks.append(task_id),
        )
        orchestrator = TaskOrchestrator(callbacks=callbacks)
        
        task = MockTask(id="callback_test")
        orchestrator.execute_task(task)
        
        assert "callback_test" in started_tasks
    
    def test_on_task_complete_callback(self):
        """Test task complete callback."""
        completed_results = []
        
        callbacks = OrchestratorCallbacks(
            on_task_complete=lambda task_id, result: completed_results.append(result),
        )
        orchestrator = TaskOrchestrator(callbacks=callbacks)
        
        task = MockTask()
        orchestrator.execute_task(task)
        
        assert len(completed_results) == 1
        assert completed_results[0].success
    
    def test_on_skill_callbacks(self):
        """Test skill start/complete callbacks."""
        skill_events = []
        
        callbacks = OrchestratorCallbacks(
            on_skill_start=lambda t, s: skill_events.append(("start", s)),
            on_skill_complete=lambda t, s, r: skill_events.append(("complete", s)),
        )
        
        skills = {"skill_1": MockSkill("skill_1")}
        orchestrator = TaskOrchestrator(
            skill_loader=MockSkillLoader(skills),
            callbacks=callbacks,
        )
        
        task = MockTask(requirements=MockRequirements(skills=["skill_1"]))
        orchestrator.execute_task(task)
        
        assert ("start", "skill_1") in skill_events
        assert ("complete", "skill_1") in skill_events
    
    def test_on_progress_callback(self):
        """Test progress callback."""
        progress_updates = []
        
        callbacks = OrchestratorCallbacks(
            on_progress=lambda t, p, m: progress_updates.append((t, p, m)),
        )
        
        skills = {"s1": MockSkill("s1"), "s2": MockSkill("s2")}
        orchestrator = TaskOrchestrator(
            skill_loader=MockSkillLoader(skills),
            callbacks=callbacks,
        )
        
        task = MockTask(requirements=MockRequirements(skills=["s1", "s2"]))
        orchestrator.execute_task(task)
        
        assert len(progress_updates) == 2


class TestBatchExecution:
    """Tests for batch task execution."""
    
    def test_execute_tasks_sequential(self):
        """Test sequential batch execution."""
        orchestrator = TaskOrchestrator()
        
        tasks = [
            MockTask(id="task_1"),
            MockTask(id="task_2"),
            MockTask(id="task_3"),
        ]
        
        results = orchestrator.execute_tasks(tasks, parallel=False)
        
        assert len(results) == 3
        assert all(r.success for r in results)
    
    def test_execute_tasks_stop_on_error(self):
        """Test batch stops on first error."""
        skills = {"fail": MockSkill("fail", should_fail=True)}
        orchestrator = TaskOrchestrator(
            skill_loader=MockSkillLoader(skills),
            config=OrchestratorConfig(
                stop_on_first_error=True,
                enable_error_recovery=False,
            ),
        )
        
        tasks = [
            MockTask(id="task_1"),
            MockTask(id="task_fail", requirements=MockRequirements(skills=["fail"])),
            MockTask(id="task_3"),
        ]
        
        results = orchestrator.execute_tasks(tasks, parallel=False)
        
        # Should stop after failure
        assert len(results) == 2
        assert results[0].success
        assert not results[1].success


class TestMetricsAndCleanup:
    """Tests for metrics and cleanup."""
    
    def test_get_executor_metrics(self):
        """Test getting executor metrics."""
        skills = {"s1": MockSkill("s1")}
        orchestrator = TaskOrchestrator(skill_loader=MockSkillLoader(skills))
        
        task = MockTask(requirements=MockRequirements(skills=["s1"]))
        orchestrator.execute_task(task)
        
        metrics = orchestrator.get_executor_metrics()
        
        assert "total_executions" in metrics
        assert metrics["total_executions"] >= 1
    
    def test_get_error_summary(self):
        """Test getting error summary."""
        orchestrator = TaskOrchestrator()
        
        summary = orchestrator.get_error_summary()
        
        assert "total_errors" in summary
        assert summary["total_errors"] == 0
    
    def test_reset_metrics(self):
        """Test resetting metrics."""
        orchestrator = TaskOrchestrator()
        
        task = MockTask()
        orchestrator.execute_task(task)
        
        orchestrator.reset_metrics()
        
        state = orchestrator.get_state()
        assert state.tasks_executed == 0
    
    def test_shutdown(self):
        """Test orchestrator shutdown."""
        orchestrator = TaskOrchestrator()
        
        # Should not raise
        orchestrator.shutdown(wait=True)


class TestTaskExecutionResult:
    """Tests for TaskExecutionResult."""
    
    def test_create_success_result(self):
        """Test creating success result."""
        result = TaskExecutionResult(
            task_id="task_123",
            success=True,
            status=ExecutionStatus.SUCCESS,
            outputs={"key": "value"},
            duration_seconds=1.5,
        )
        
        assert result.success
        assert result.outputs["key"] == "value"
    
    def test_create_failure_result(self):
        """Test creating failure result."""
        result = TaskExecutionResult(
            task_id="task_123",
            success=False,
            status=ExecutionStatus.FAILED,
            errors=[{"message": "Something failed"}],
        )
        
        assert not result.success
        assert len(result.errors) == 1
    
    def test_result_to_dict(self):
        """Test result serialization."""
        result = TaskExecutionResult(
            task_id="task_123",
            success=True,
            status=ExecutionStatus.SUCCESS,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        
        data = result.to_dict()
        
        assert data["task_id"] == "task_123"
        assert data["success"] is True
        assert data["status"] == "success"
        assert data["started_at"] is not None
