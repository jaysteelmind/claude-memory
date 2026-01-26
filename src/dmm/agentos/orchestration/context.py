"""
Execution context for task execution.

This module provides the execution context that manages:
- Runtime environment for task execution
- Memory retrieval and context assembly
- Input/output handling
- State management during execution
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol, runtime_checkable
from pathlib import Path
import copy


# =============================================================================
# Protocols for External Dependencies
# =============================================================================

@runtime_checkable
class MemoryRetrieverProtocol(Protocol):
    """Protocol for memory retrieval integration."""
    
    def query(
        self,
        query: str,
        scopes: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
        limit: int = 10,
    ) -> list[Any]:
        """Query memories."""
        ...


@runtime_checkable
class SkillLoaderProtocol(Protocol):
    """Protocol for skill loading."""
    
    def get(self, skill_id: str) -> Optional[Any]:
        """Get a skill by ID."""
        ...


@runtime_checkable
class ToolLoaderProtocol(Protocol):
    """Protocol for tool loading."""
    
    def get(self, tool_id: str) -> Optional[Any]:
        """Get a tool by ID."""
        ...


# =============================================================================
# Context Configuration
# =============================================================================

@dataclass
class ContextConfig:
    """Configuration for execution context."""
    
    max_context_tokens: int = 8000
    min_context_tokens: int = 500
    baseline_tokens: int = 800
    include_baseline: bool = True
    include_task_history: bool = True
    max_history_entries: int = 10
    memory_query_limit: int = 20
    timeout_seconds: float = 300.0


# =============================================================================
# Context State
# =============================================================================

@dataclass
class ContextState:
    """Mutable state during task execution."""
    
    # Execution tracking
    started_at: Optional[datetime] = None
    current_step: str = ""
    step_count: int = 0
    
    # Accumulated data
    intermediate_results: dict[str, Any] = field(default_factory=dict)
    tool_outputs: list[dict[str, Any]] = field(default_factory=list)
    skill_outputs: list[dict[str, Any]] = field(default_factory=list)
    
    # Memory operations
    memories_read: list[str] = field(default_factory=list)
    memories_to_write: list[dict[str, Any]] = field(default_factory=list)
    memories_to_update: list[dict[str, Any]] = field(default_factory=list)
    
    # Messages
    messages_to_send: list[dict[str, Any]] = field(default_factory=list)
    messages_received: list[dict[str, Any]] = field(default_factory=list)
    
    # Errors and warnings
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    
    # Metrics
    tokens_used: int = 0
    api_calls: int = 0
    
    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(f"[{datetime.utcnow().isoformat()}] {error}")
    
    def add_warning(self, warning: str) -> None:
        """Add a warning message."""
        self.warnings.append(f"[{datetime.utcnow().isoformat()}] {warning}")
    
    def set_step(self, step: str) -> None:
        """Set the current execution step."""
        self.step_count += 1
        self.current_step = step
    
    def add_intermediate_result(self, key: str, value: Any) -> None:
        """Store an intermediate result."""
        self.intermediate_results[key] = value
    
    def add_tool_output(self, tool_id: str, output: Any, success: bool = True) -> None:
        """Record a tool execution output."""
        self.tool_outputs.append({
            "tool_id": tool_id,
            "output": output,
            "success": success,
            "timestamp": datetime.utcnow().isoformat(),
        })
    
    def add_skill_output(self, skill_id: str, output: Any, success: bool = True) -> None:
        """Record a skill execution output."""
        self.skill_outputs.append({
            "skill_id": skill_id,
            "output": output,
            "success": success,
            "timestamp": datetime.utcnow().isoformat(),
        })
    
    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary."""
        return {
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "current_step": self.current_step,
            "step_count": self.step_count,
            "intermediate_results": self.intermediate_results,
            "tool_outputs": self.tool_outputs,
            "skill_outputs": self.skill_outputs,
            "memories_read": self.memories_read,
            "memories_to_write": len(self.memories_to_write),
            "memories_to_update": len(self.memories_to_update),
            "messages_to_send": len(self.messages_to_send),
            "messages_received": len(self.messages_received),
            "errors": self.errors,
            "warnings": self.warnings,
            "tokens_used": self.tokens_used,
            "api_calls": self.api_calls,
        }


# =============================================================================
# Memory Context
# =============================================================================

@dataclass
class MemoryContext:
    """Retrieved memories for task execution."""
    
    baseline_memories: list[dict[str, Any]] = field(default_factory=list)
    task_memories: list[dict[str, Any]] = field(default_factory=list)
    scope_memories: list[dict[str, Any]] = field(default_factory=list)
    dependency_memories: list[dict[str, Any]] = field(default_factory=list)
    
    total_tokens: int = 0
    
    def get_all_memories(self) -> list[dict[str, Any]]:
        """Get all memories in priority order."""
        return (
            self.baseline_memories +
            self.task_memories +
            self.scope_memories +
            self.dependency_memories
        )
    
    def get_memory_ids(self) -> list[str]:
        """Get all memory IDs."""
        return [m.get("id", "") for m in self.get_all_memories() if m.get("id")]


# =============================================================================
# Execution Context
# =============================================================================

@dataclass
class ExecutionContext:
    """
    Complete execution context for a task.
    
    The execution context contains everything needed to execute a task:
    - Task information and inputs
    - Retrieved memories
    - Loaded skills and tools
    - Execution state
    - Configuration
    """
    
    # Task information
    task_id: str
    task_name: str
    task_description: str
    task_inputs: dict[str, Any] = field(default_factory=dict)
    
    # Parent/dependency context
    parent_context: Optional["ExecutionContext"] = None
    dependency_outputs: dict[str, Any] = field(default_factory=dict)
    
    # Memory context
    memory_context: MemoryContext = field(default_factory=MemoryContext)
    
    # Loaded resources
    loaded_skills: dict[str, Any] = field(default_factory=dict)
    loaded_tools: dict[str, Any] = field(default_factory=dict)
    
    # Agent information
    agent_id: Optional[str] = None
    agent_capabilities: list[str] = field(default_factory=list)
    
    # Configuration
    config: ContextConfig = field(default_factory=ContextConfig)
    
    # Execution state
    state: ContextState = field(default_factory=ContextState)
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    # -------------------------------------------------------------------------
    # Input/Output Access
    # -------------------------------------------------------------------------
    
    def get_input(self, key: str, default: Any = None) -> Any:
        """Get a task input value."""
        return self.task_inputs.get(key, default)
    
    def get_dependency_output(self, task_id: str, key: Optional[str] = None) -> Any:
        """Get output from a dependency task."""
        dep_output = self.dependency_outputs.get(task_id)
        if dep_output is None:
            return None
        if key is None:
            return dep_output
        if isinstance(dep_output, dict):
            return dep_output.get(key)
        return dep_output
    
    def get_intermediate(self, key: str, default: Any = None) -> Any:
        """Get an intermediate result."""
        return self.state.intermediate_results.get(key, default)
    
    def set_intermediate(self, key: str, value: Any) -> None:
        """Set an intermediate result."""
        self.state.add_intermediate_result(key, value)
    
    # -------------------------------------------------------------------------
    # Resource Access
    # -------------------------------------------------------------------------
    
    def get_skill(self, skill_id: str) -> Optional[Any]:
        """Get a loaded skill."""
        return self.loaded_skills.get(skill_id)
    
    def get_tool(self, tool_id: str) -> Optional[Any]:
        """Get a loaded tool."""
        return self.loaded_tools.get(tool_id)
    
    def has_skill(self, skill_id: str) -> bool:
        """Check if a skill is loaded."""
        return skill_id in self.loaded_skills
    
    def has_tool(self, tool_id: str) -> bool:
        """Check if a tool is loaded."""
        return tool_id in self.loaded_tools
    
    # -------------------------------------------------------------------------
    # Memory Access
    # -------------------------------------------------------------------------
    
    def get_memories(self) -> list[dict[str, Any]]:
        """Get all retrieved memories."""
        return self.memory_context.get_all_memories()
    
    def get_memory_content(self) -> str:
        """Get concatenated memory content."""
        contents = []
        for memory in self.get_memories():
            content = memory.get("content", "")
            if content:
                contents.append(content)
        return "\n\n".join(contents)
    
    def request_memory_write(self, content: str, tags: list[str], scope: str = "project") -> None:
        """Request a new memory to be written after execution."""
        self.state.memories_to_write.append({
            "content": content,
            "tags": tags,
            "scope": scope,
            "source_task": self.task_id,
            "timestamp": datetime.utcnow().isoformat(),
        })
    
    def request_memory_update(self, memory_id: str, updates: dict[str, Any]) -> None:
        """Request a memory update after execution."""
        self.state.memories_to_update.append({
            "memory_id": memory_id,
            "updates": updates,
            "source_task": self.task_id,
            "timestamp": datetime.utcnow().isoformat(),
        })
    
    # -------------------------------------------------------------------------
    # Messaging
    # -------------------------------------------------------------------------
    
    def request_message(
        self,
        recipient: str,
        content: str,
        message_type: str = "inform",
    ) -> None:
        """Request a message to be sent after execution."""
        self.state.messages_to_send.append({
            "recipient": recipient,
            "content": content,
            "message_type": message_type,
            "source_task": self.task_id,
            "timestamp": datetime.utcnow().isoformat(),
        })
    
    # -------------------------------------------------------------------------
    # State Management
    # -------------------------------------------------------------------------
    
    def start_execution(self) -> None:
        """Mark execution as started."""
        self.state.started_at = datetime.utcnow()
        self.state.set_step("initialization")
    
    def set_step(self, step: str) -> None:
        """Set the current execution step."""
        self.state.set_step(step)
    
    def add_error(self, error: str) -> None:
        """Add an error to the context."""
        self.state.add_error(error)
    
    def add_warning(self, warning: str) -> None:
        """Add a warning to the context."""
        self.state.add_warning(warning)
    
    def has_errors(self) -> bool:
        """Check if context has errors."""
        return len(self.state.errors) > 0
    
    # -------------------------------------------------------------------------
    # Token Management
    # -------------------------------------------------------------------------
    
    def get_remaining_tokens(self) -> int:
        """Get remaining token budget."""
        return max(0, self.config.max_context_tokens - self.state.tokens_used)
    
    def consume_tokens(self, tokens: int) -> bool:
        """
        Consume tokens from budget.
        
        Returns True if tokens were available, False if would exceed budget.
        """
        if self.state.tokens_used + tokens > self.config.max_context_tokens:
            return False
        self.state.tokens_used += tokens
        return True
    
    # -------------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------------
    
    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary for inspection."""
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "task_description": self.task_description,
            "task_inputs": self.task_inputs,
            "agent_id": self.agent_id,
            "loaded_skills": list(self.loaded_skills.keys()),
            "loaded_tools": list(self.loaded_tools.keys()),
            "memory_count": len(self.get_memories()),
            "memory_tokens": self.memory_context.total_tokens,
            "config": {
                "max_context_tokens": self.config.max_context_tokens,
                "timeout_seconds": self.config.timeout_seconds,
            },
            "state": self.state.to_dict(),
            "created_at": self.created_at.isoformat(),
        }
    
    def clone(self) -> "ExecutionContext":
        """Create a deep copy of the context."""
        return ExecutionContext(
            task_id=self.task_id,
            task_name=self.task_name,
            task_description=self.task_description,
            task_inputs=copy.deepcopy(self.task_inputs),
            dependency_outputs=copy.deepcopy(self.dependency_outputs),
            memory_context=copy.deepcopy(self.memory_context),
            loaded_skills=dict(self.loaded_skills),
            loaded_tools=dict(self.loaded_tools),
            agent_id=self.agent_id,
            agent_capabilities=list(self.agent_capabilities),
            config=copy.deepcopy(self.config),
            state=ContextState(),  # Fresh state for clone
        )


# =============================================================================
# Context Builder
# =============================================================================

class ContextBuilder:
    """
    Builds execution contexts for tasks.
    
    The builder handles:
    - Memory retrieval and assembly
    - Skill and tool loading
    - Dependency output collection
    - Token budget management
    """
    
    def __init__(
        self,
        memory_retriever: Optional[MemoryRetrieverProtocol] = None,
        skill_loader: Optional[SkillLoaderProtocol] = None,
        tool_loader: Optional[ToolLoaderProtocol] = None,
        default_config: Optional[ContextConfig] = None,
    ) -> None:
        """
        Initialize context builder.
        
        Args:
            memory_retriever: Memory retrieval service
            skill_loader: Skill loading service
            tool_loader: Tool loading service
            default_config: Default configuration
        """
        self._memory_retriever = memory_retriever
        self._skill_loader = skill_loader
        self._tool_loader = tool_loader
        self._default_config = default_config or ContextConfig()
    
    def build(
        self,
        task_id: str,
        task_name: str,
        task_description: str,
        task_inputs: Optional[dict[str, Any]] = None,
        required_skills: Optional[list[str]] = None,
        required_tools: Optional[list[str]] = None,
        memory_scopes: Optional[list[str]] = None,
        memory_tags: Optional[list[str]] = None,
        dependency_outputs: Optional[dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        config: Optional[ContextConfig] = None,
    ) -> ExecutionContext:
        """
        Build an execution context for a task.
        
        Args:
            task_id: Task ID
            task_name: Task name
            task_description: Task description
            task_inputs: Task input values
            required_skills: Skills to load
            required_tools: Tools to load
            memory_scopes: Memory scopes to query
            memory_tags: Memory tags to filter
            dependency_outputs: Outputs from dependency tasks
            agent_id: Assigned agent ID
            config: Context configuration
            
        Returns:
            Assembled ExecutionContext
        """
        config = config or self._default_config
        
        # Create base context
        context = ExecutionContext(
            task_id=task_id,
            task_name=task_name,
            task_description=task_description,
            task_inputs=task_inputs or {},
            dependency_outputs=dependency_outputs or {},
            agent_id=agent_id,
            config=config,
        )
        
        # Load memories
        if self._memory_retriever:
            context.memory_context = self._retrieve_memories(
                task_description=task_description,
                scopes=memory_scopes,
                tags=memory_tags,
                config=config,
            )
        
        # Load skills
        if self._skill_loader and required_skills:
            for skill_id in required_skills:
                skill = self._skill_loader.get(skill_id)
                if skill:
                    context.loaded_skills[skill_id] = skill
        
        # Load tools
        if self._tool_loader and required_tools:
            for tool_id in required_tools:
                tool = self._tool_loader.get(tool_id)
                if tool:
                    context.loaded_tools[tool_id] = tool
        
        return context
    
    def _retrieve_memories(
        self,
        task_description: str,
        scopes: Optional[list[str]],
        tags: Optional[list[str]],
        config: ContextConfig,
    ) -> MemoryContext:
        """Retrieve memories for task context."""
        memory_context = MemoryContext()
        
        if not self._memory_retriever:
            return memory_context
        
        try:
            # Query task-relevant memories
            results = self._memory_retriever.query(
                query=task_description,
                scopes=scopes,
                tags=tags,
                limit=config.memory_query_limit,
            )
            
            for result in results:
                if isinstance(result, dict):
                    memory_context.task_memories.append(result)
                    # Estimate tokens (rough: 1 token per 4 chars)
                    content = result.get("content", "")
                    memory_context.total_tokens += len(content) // 4
                else:
                    # Handle non-dict results
                    memory_context.task_memories.append({"content": str(result)})
                    memory_context.total_tokens += len(str(result)) // 4
        except Exception:
            pass
        
        return memory_context
    
    def build_from_task(
        self,
        task: Any,
        dependency_outputs: Optional[dict[str, Any]] = None,
        config: Optional[ContextConfig] = None,
    ) -> ExecutionContext:
        """
        Build context from a Task object.
        
        Args:
            task: Task object with standard attributes
            dependency_outputs: Outputs from dependencies
            config: Context configuration
            
        Returns:
            ExecutionContext
        """
        # Extract task attributes
        task_id = getattr(task, "id", str(task))
        task_name = getattr(task, "name", "")
        task_description = getattr(task, "description", "")
        task_inputs = getattr(task, "inputs", {})
        agent_id = getattr(task, "assigned_agent", None)
        
        # Extract requirements
        requirements = getattr(task, "requirements", None)
        required_skills = getattr(requirements, "skills", []) if requirements else []
        required_tools = getattr(requirements, "tools", []) if requirements else []
        memory_scopes = getattr(requirements, "memory_scopes", []) if requirements else []
        memory_tags = getattr(requirements, "memory_tags", []) if requirements else []
        
        return self.build(
            task_id=task_id,
            task_name=task_name,
            task_description=task_description,
            task_inputs=task_inputs,
            required_skills=required_skills,
            required_tools=required_tools,
            memory_scopes=memory_scopes,
            memory_tags=memory_tags,
            dependency_outputs=dependency_outputs,
            agent_id=agent_id,
            config=config,
        )
