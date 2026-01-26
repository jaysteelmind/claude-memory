"""
Unit tests for execution context.

Tests cover:
- Context creation and configuration
- State management
- Memory context
- Resource access
- Serialization
"""

import pytest
from datetime import datetime

from dmm.agentos.orchestration import (
    ExecutionContext,
    ContextBuilder,
    ContextConfig,
    ContextState,
    MemoryContext,
)


class TestContextConfig:
    """Tests for ContextConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = ContextConfig()
        
        assert config.max_context_tokens == 8000
        assert config.timeout_seconds == 300.0
        assert config.include_baseline is True
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = ContextConfig(
            max_context_tokens=4000,
            timeout_seconds=60.0,
            memory_query_limit=10,
        )
        
        assert config.max_context_tokens == 4000
        assert config.timeout_seconds == 60.0
        assert config.memory_query_limit == 10


class TestContextState:
    """Tests for ContextState."""
    
    def test_create_state(self):
        """Test creating context state."""
        state = ContextState()
        
        assert state.started_at is None
        assert state.step_count == 0
        assert len(state.errors) == 0
    
    def test_add_error(self):
        """Test adding error to state."""
        state = ContextState()
        state.add_error("Test error")
        
        assert len(state.errors) == 1
        assert "Test error" in state.errors[0]
    
    def test_add_warning(self):
        """Test adding warning to state."""
        state = ContextState()
        state.add_warning("Test warning")
        
        assert len(state.warnings) == 1
        assert "Test warning" in state.warnings[0]
    
    def test_set_step(self):
        """Test setting execution step."""
        state = ContextState()
        state.set_step("initialization")
        state.set_step("processing")
        
        assert state.current_step == "processing"
        assert state.step_count == 2
    
    def test_add_intermediate_result(self):
        """Test adding intermediate result."""
        state = ContextState()
        state.add_intermediate_result("key1", "value1")
        state.add_intermediate_result("key2", {"nested": "data"})
        
        assert state.intermediate_results["key1"] == "value1"
        assert state.intermediate_results["key2"]["nested"] == "data"
    
    def test_add_tool_output(self):
        """Test adding tool output."""
        state = ContextState()
        state.add_tool_output("tool_1", {"result": "success"}, success=True)
        
        assert len(state.tool_outputs) == 1
        assert state.tool_outputs[0]["tool_id"] == "tool_1"
        assert state.tool_outputs[0]["success"] is True
    
    def test_add_skill_output(self):
        """Test adding skill output."""
        state = ContextState()
        state.add_skill_output("skill_1", "output data", success=True)
        
        assert len(state.skill_outputs) == 1
        assert state.skill_outputs[0]["skill_id"] == "skill_1"
    
    def test_to_dict(self):
        """Test state serialization."""
        state = ContextState()
        state.set_step("test")
        state.add_error("error")
        
        data = state.to_dict()
        
        assert data["current_step"] == "test"
        assert data["step_count"] == 1
        assert len(data["errors"]) == 1


class TestMemoryContext:
    """Tests for MemoryContext."""
    
    def test_create_memory_context(self):
        """Test creating memory context."""
        ctx = MemoryContext()
        
        assert len(ctx.baseline_memories) == 0
        assert ctx.total_tokens == 0
    
    def test_get_all_memories(self):
        """Test getting all memories."""
        ctx = MemoryContext()
        ctx.baseline_memories = [{"id": "1", "content": "baseline"}]
        ctx.task_memories = [{"id": "2", "content": "task"}]
        
        all_memories = ctx.get_all_memories()
        
        assert len(all_memories) == 2
    
    def test_get_memory_ids(self):
        """Test getting memory IDs."""
        ctx = MemoryContext()
        ctx.task_memories = [
            {"id": "mem_1", "content": "a"},
            {"id": "mem_2", "content": "b"},
        ]
        
        ids = ctx.get_memory_ids()
        
        assert "mem_1" in ids
        assert "mem_2" in ids


class TestExecutionContext:
    """Tests for ExecutionContext."""
    
    def test_create_context(self):
        """Test creating execution context."""
        context = ExecutionContext(
            task_id="task_123",
            task_name="Test Task",
            task_description="A test task",
        )
        
        assert context.task_id == "task_123"
        assert context.task_name == "Test Task"
        assert context.created_at is not None
    
    def test_context_with_inputs(self):
        """Test context with task inputs."""
        context = ExecutionContext(
            task_id="task_123",
            task_name="Test",
            task_description="Test",
            task_inputs={"file": "test.py", "mode": "review"},
        )
        
        assert context.get_input("file") == "test.py"
        assert context.get_input("mode") == "review"
        assert context.get_input("missing", "default") == "default"
    
    def test_context_dependency_outputs(self):
        """Test accessing dependency outputs."""
        context = ExecutionContext(
            task_id="task_123",
            task_name="Test",
            task_description="Test",
            dependency_outputs={
                "task_prev": {"result": "success", "data": [1, 2, 3]},
            },
        )
        
        assert context.get_dependency_output("task_prev", "result") == "success"
        assert context.get_dependency_output("task_prev")["data"] == [1, 2, 3]
        assert context.get_dependency_output("missing") is None
    
    def test_context_loaded_resources(self):
        """Test loaded skills and tools."""
        context = ExecutionContext(
            task_id="task_123",
            task_name="Test",
            task_description="Test",
            loaded_skills={"skill_1": "mock_skill"},
            loaded_tools={"tool_1": "mock_tool"},
        )
        
        assert context.has_skill("skill_1")
        assert not context.has_skill("skill_2")
        assert context.has_tool("tool_1")
        assert context.get_skill("skill_1") == "mock_skill"
    
    def test_context_memory_operations(self):
        """Test memory operation requests."""
        context = ExecutionContext(
            task_id="task_123",
            task_name="Test",
            task_description="Test",
        )
        
        context.request_memory_write(
            content="New insight discovered",
            tags=["insight", "test"],
            scope="project",
        )
        
        assert len(context.state.memories_to_write) == 1
        assert context.state.memories_to_write[0]["content"] == "New insight discovered"
    
    def test_context_memory_update(self):
        """Test memory update request."""
        context = ExecutionContext(
            task_id="task_123",
            task_name="Test",
            task_description="Test",
        )
        
        context.request_memory_update("mem_1", {"importance": 0.9})
        
        assert len(context.state.memories_to_update) == 1
        assert context.state.memories_to_update[0]["memory_id"] == "mem_1"
    
    def test_context_messaging(self):
        """Test message requests."""
        context = ExecutionContext(
            task_id="task_123",
            task_name="Test",
            task_description="Test",
        )
        
        context.request_message(
            recipient="agent_2",
            content="Task completed",
            message_type="inform",
        )
        
        assert len(context.state.messages_to_send) == 1
        assert context.state.messages_to_send[0]["recipient"] == "agent_2"
    
    def test_context_execution_lifecycle(self):
        """Test execution lifecycle methods."""
        context = ExecutionContext(
            task_id="task_123",
            task_name="Test",
            task_description="Test",
        )
        
        context.start_execution()
        
        assert context.state.started_at is not None
        assert context.state.current_step == "initialization"
        
        context.set_step("processing")
        assert context.state.current_step == "processing"
    
    def test_context_token_management(self):
        """Test token budget management."""
        config = ContextConfig(max_context_tokens=1000)
        context = ExecutionContext(
            task_id="task_123",
            task_name="Test",
            task_description="Test",
            config=config,
        )
        
        assert context.get_remaining_tokens() == 1000
        assert context.consume_tokens(500)
        assert context.get_remaining_tokens() == 500
        assert not context.consume_tokens(600)  # Would exceed budget
    
    def test_context_to_dict(self):
        """Test context serialization."""
        context = ExecutionContext(
            task_id="task_123",
            task_name="Test Task",
            task_description="A test",
            agent_id="agent_1",
        )
        
        data = context.to_dict()
        
        assert data["task_id"] == "task_123"
        assert data["task_name"] == "Test Task"
        assert data["agent_id"] == "agent_1"
    
    def test_context_clone(self):
        """Test context cloning."""
        context = ExecutionContext(
            task_id="task_123",
            task_name="Test",
            task_description="Test",
            task_inputs={"key": "value"},
        )
        context.state.add_error("Original error")
        
        cloned = context.clone()
        
        assert cloned.task_id == context.task_id
        assert cloned.task_inputs["key"] == "value"
        assert len(cloned.state.errors) == 0  # Fresh state


class TestContextBuilder:
    """Tests for ContextBuilder."""
    
    def test_create_builder(self):
        """Test creating context builder."""
        builder = ContextBuilder()
        assert builder is not None
    
    def test_build_basic_context(self):
        """Test building basic context."""
        builder = ContextBuilder()
        
        context = builder.build(
            task_id="task_123",
            task_name="Test Task",
            task_description="A test task",
        )
        
        assert context.task_id == "task_123"
        assert context.task_name == "Test Task"
    
    def test_build_with_inputs(self):
        """Test building context with inputs."""
        builder = ContextBuilder()
        
        context = builder.build(
            task_id="task_123",
            task_name="Test",
            task_description="Test",
            task_inputs={"file": "test.py"},
            agent_id="agent_1",
        )
        
        assert context.task_inputs["file"] == "test.py"
        assert context.agent_id == "agent_1"
    
    def test_build_with_custom_config(self):
        """Test building context with custom config."""
        builder = ContextBuilder()
        custom_config = ContextConfig(max_context_tokens=4000)
        
        context = builder.build(
            task_id="task_123",
            task_name="Test",
            task_description="Test",
            config=custom_config,
        )
        
        assert context.config.max_context_tokens == 4000
