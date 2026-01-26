"""
Unit tests for skill executor.

Tests cover:
- Skill execution
- Tool execution
- Timeout handling
- Metrics collection
- Batch execution
"""

import pytest
import time
from datetime import datetime

from dmm.agentos.orchestration import (
    SkillExecutor,
    ExecutorConfig,
    ExecutionResult,
    ExecutionStatus,
    ExecutionContext,
    ContextConfig,
)


@pytest.fixture
def executor():
    """Create skill executor."""
    return SkillExecutor(config=ExecutorConfig(
        default_timeout_seconds=5.0,
        max_retries=2,
    ))


@pytest.fixture
def context():
    """Create execution context."""
    return ExecutionContext(
        task_id="task_test123",
        task_name="Test Task",
        task_description="A test task",
    )


class MockSkill:
    """Mock skill for testing."""
    
    def __init__(self, output="success", should_fail=False, delay=0):
        self.id = "mock_skill"
        self.name = "Mock Skill"
        self.output = output
        self.should_fail = should_fail
        self.delay = delay
        self.execute_count = 0
    
    def execute(self, context, **kwargs):
        self.execute_count += 1
        if self.delay > 0:
            time.sleep(self.delay)
        if self.should_fail:
            raise ValueError("Mock skill failed")
        return self.output


class MockTool:
    """Mock tool for testing."""
    
    def __init__(self, output="tool_result", should_fail=False):
        self.id = "mock_tool"
        self.name = "Mock Tool"
        self.output = output
        self.should_fail = should_fail
    
    def run(self, **kwargs):
        if self.should_fail:
            raise RuntimeError("Mock tool failed")
        return self.output


class TestExecutionResult:
    """Tests for ExecutionResult."""
    
    def test_create_success_result(self):
        """Test creating success result."""
        result = ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            output={"data": "test"},
            duration_seconds=1.5,
        )
        
        assert result.is_success()
        assert not result.is_failure()
        assert result.output["data"] == "test"
    
    def test_create_failed_result(self):
        """Test creating failed result."""
        result = ExecutionResult(
            status=ExecutionStatus.FAILED,
            error="Something went wrong",
            error_type="ValueError",
        )
        
        assert not result.is_success()
        assert result.is_failure()
        assert result.error == "Something went wrong"
    
    def test_result_to_dict(self):
        """Test result serialization."""
        result = ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            output="test",
            duration_seconds=2.0,
            started_at=datetime.utcnow(),
        )
        
        data = result.to_dict()
        
        assert data["status"] == "success"
        assert data["output"] == "test"
        assert data["duration_seconds"] == 2.0


class TestSkillExecution:
    """Tests for skill execution."""
    
    def test_execute_skill_success(self, executor, context):
        """Test successful skill execution."""
        skill = MockSkill(output="skill_output")
        
        result = executor.execute_skill(skill, context)
        
        assert result.is_success()
        assert result.output == "skill_output"
        assert skill.execute_count == 1
    
    def test_execute_skill_failure(self, executor, context):
        """Test failed skill execution."""
        skill = MockSkill(should_fail=True)
        
        result = executor.execute_skill(skill, context)
        
        assert result.is_failure()
        assert result.status == ExecutionStatus.FAILED
        assert "Mock skill failed" in result.error
    
    def test_execute_skill_timeout(self, context):
        """Test skill execution timeout."""
        executor = SkillExecutor(config=ExecutorConfig(
            default_timeout_seconds=0.1,
        ))
        skill = MockSkill(delay=1.0)
        
        result = executor.execute_skill(skill, context)
        
        assert result.status == ExecutionStatus.TIMEOUT
        assert "timed out" in result.error.lower()
    
    def test_execute_skill_records_in_context(self, executor, context):
        """Test skill execution records output in context."""
        skill = MockSkill(output="recorded_output")
        
        executor.execute_skill(skill, context)
        
        assert len(context.state.skill_outputs) == 1
        assert context.state.skill_outputs[0]["skill_id"] == "mock_skill"
    
    def test_execute_callable_as_skill(self, executor, context):
        """Test executing callable as skill."""
        def callable_skill(ctx, **kwargs):
            return "callable_result"
        
        result = executor.execute_skill(callable_skill, context)
        
        assert result.is_success()
        assert result.output == "callable_result"


class TestToolExecution:
    """Tests for tool execution."""
    
    def test_execute_tool_success(self, executor, context):
        """Test successful tool execution."""
        tool = MockTool(output="tool_output")
        
        result = executor.execute_tool(tool, context, param1="value1")
        
        assert result.is_success()
        assert result.output == "tool_output"
    
    def test_execute_tool_failure(self, executor, context):
        """Test failed tool execution."""
        tool = MockTool(should_fail=True)
        
        result = executor.execute_tool(tool, context)
        
        assert result.is_failure()
        assert "Mock tool failed" in result.error
    
    def test_execute_tool_records_in_context(self, executor, context):
        """Test tool execution records in context."""
        tool = MockTool()
        
        executor.execute_tool(tool, context)
        
        assert len(context.state.tool_outputs) == 1
        assert context.state.tool_outputs[0]["tool_id"] == "mock_tool"


class TestBatchExecution:
    """Tests for batch execution."""
    
    def test_execute_tools_parallel(self, executor, context):
        """Test parallel tool execution."""
        tools = [
            (MockTool(output=f"result_{i}"), {}) for i in range(3)
        ]
        
        results = executor.execute_tools_parallel(tools, context)
        
        assert len(results) == 3
        assert all(r.is_success() for r in results)


class TestExecutorMetrics:
    """Tests for executor metrics."""
    
    def test_metrics_collection(self, executor, context):
        """Test metrics are collected."""
        skill = MockSkill()
        
        executor.execute_skill(skill, context)
        executor.execute_skill(skill, context)
        
        metrics = executor.get_metrics()
        
        assert metrics.total_executions == 2
        assert metrics.successful_executions == 2
    
    def test_metrics_failure_tracking(self, executor, context):
        """Test failure metrics tracking."""
        skill = MockSkill(should_fail=True)
        
        executor.execute_skill(skill, context)
        
        metrics = executor.get_metrics()
        
        assert metrics.failed_executions == 1
    
    def test_reset_metrics(self, executor, context):
        """Test resetting metrics."""
        skill = MockSkill()
        executor.execute_skill(skill, context)
        
        executor.reset_metrics()
        
        metrics = executor.get_metrics()
        assert metrics.total_executions == 0


class TestRetryLogic:
    """Tests for retry logic."""
    
    def test_execute_with_retry_success(self, executor):
        """Test retry eventually succeeds."""
        call_count = 0
        
        def flaky_fn():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    error="Temporary failure",
                )
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                output="success",
            )
        
        result = executor.execute_with_retry(flaky_fn, max_retries=3, retry_delay=0.01)
        
        assert result.is_success()
        assert call_count == 2
    
    def test_execute_with_retry_exhausted(self, executor):
        """Test retry exhausts attempts."""
        def always_fail():
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error="Always fails",
            )
        
        result = executor.execute_with_retry(always_fail, max_retries=2, retry_delay=0.01)
        
        assert result.is_failure()
