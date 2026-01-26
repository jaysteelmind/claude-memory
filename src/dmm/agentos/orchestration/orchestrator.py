"""
Task orchestrator for coordinating execution.

This module provides the main orchestration capabilities including:
- Task execution coordination
- Context assembly and management
- Skill and tool invocation
- Error handling and recovery
- Progress tracking and reporting
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional
from enum import Enum
import asyncio

from dmm.agentos.orchestration.context import (
    ExecutionContext,
    ContextBuilder,
    ContextConfig,
    MemoryRetrieverProtocol,
    SkillLoaderProtocol,
    ToolLoaderProtocol,
)
from dmm.agentos.orchestration.executor import (
    SkillExecutor,
    ExecutorConfig,
    ExecutionResult,
    ExecutionStatus,
)
from dmm.agentos.orchestration.handlers import (
    ErrorHandler,
    ExecutionError,
    ErrorCategory,
    ErrorSeverity,
    RecoveryResult,
    RecoveryStrategy,
)


# =============================================================================
# Orchestrator Configuration
# =============================================================================

class OrchestratorMode(str, Enum):
    """Mode of orchestrator operation."""
    
    SYNCHRONOUS = "synchronous"
    ASYNCHRONOUS = "asynchronous"
    PARALLEL = "parallel"


@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator."""
    
    mode: OrchestratorMode = OrchestratorMode.SYNCHRONOUS
    max_concurrent_tasks: int = 5
    default_timeout_seconds: float = 300.0
    max_task_duration_seconds: float = 3600.0
    max_tool_calls_per_task: int = 50
    max_memory_writes_per_task: int = 10
    enable_progress_tracking: bool = True
    enable_error_recovery: bool = True
    stop_on_first_error: bool = False
    collect_metrics: bool = True


# =============================================================================
# Orchestrator State
# =============================================================================

@dataclass
class OrchestratorState:
    """State of the orchestrator."""
    
    is_running: bool = False
    current_task_id: Optional[str] = None
    tasks_executed: int = 0
    tasks_succeeded: int = 0
    tasks_failed: int = 0
    started_at: Optional[datetime] = None
    last_execution_at: Optional[datetime] = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary."""
        return {
            "is_running": self.is_running,
            "current_task_id": self.current_task_id,
            "tasks_executed": self.tasks_executed,
            "tasks_succeeded": self.tasks_succeeded,
            "tasks_failed": self.tasks_failed,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_execution_at": self.last_execution_at.isoformat() if self.last_execution_at else None,
        }


# =============================================================================
# Task Execution Result
# =============================================================================

@dataclass
class TaskExecutionResult:
    """Complete result of task execution."""
    
    task_id: str
    success: bool
    status: ExecutionStatus
    outputs: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    memories_created: list[str] = field(default_factory=list)
    memories_updated: list[str] = field(default_factory=list)
    messages_sent: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    skill_results: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    recovery_attempts: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "task_id": self.task_id,
            "success": self.success,
            "status": self.status.value,
            "outputs": self.outputs,
            "artifacts": self.artifacts,
            "memories_created": self.memories_created,
            "memories_updated": self.memories_updated,
            "messages_sent": self.messages_sent,
            "errors": self.errors,
            "warnings": self.warnings,
            "duration_seconds": self.duration_seconds,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "skill_results": self.skill_results,
            "tool_results": self.tool_results,
            "recovery_attempts": self.recovery_attempts,
        }


# =============================================================================
# Callbacks Protocol
# =============================================================================

@dataclass
class OrchestratorCallbacks:
    """Callbacks for orchestrator events."""
    
    on_task_start: Optional[Callable[[str, ExecutionContext], None]] = None
    on_task_complete: Optional[Callable[[str, TaskExecutionResult], None]] = None
    on_task_error: Optional[Callable[[str, ExecutionError], None]] = None
    on_skill_start: Optional[Callable[[str, str], None]] = None
    on_skill_complete: Optional[Callable[[str, str, ExecutionResult], None]] = None
    on_tool_start: Optional[Callable[[str, str], None]] = None
    on_tool_complete: Optional[Callable[[str, str, ExecutionResult], None]] = None
    on_progress: Optional[Callable[[str, float, str], None]] = None
    on_escalation: Optional[Callable[[ExecutionError], None]] = None


# =============================================================================
# Task Orchestrator
# =============================================================================

class TaskOrchestrator:
    """
    Coordinates task execution across skills, tools, and agents.
    
    The orchestrator:
    1. Builds execution contexts for tasks
    2. Executes skills and tools in order
    3. Handles errors and recovery
    4. Tracks progress and collects metrics
    5. Manages task outputs and side effects
    """
    
    def __init__(
        self,
        config: Optional[OrchestratorConfig] = None,
        memory_retriever: Optional[MemoryRetrieverProtocol] = None,
        skill_loader: Optional[SkillLoaderProtocol] = None,
        tool_loader: Optional[ToolLoaderProtocol] = None,
        callbacks: Optional[OrchestratorCallbacks] = None,
    ) -> None:
        """
        Initialize task orchestrator.
        
        Args:
            config: Orchestrator configuration
            memory_retriever: Memory retrieval service
            skill_loader: Skill loading service
            tool_loader: Tool loading service
            callbacks: Event callbacks
        """
        self._config = config or OrchestratorConfig()
        self._callbacks = callbacks or OrchestratorCallbacks()
        
        # Build components
        self._context_builder = ContextBuilder(
            memory_retriever=memory_retriever,
            skill_loader=skill_loader,
            tool_loader=tool_loader,
            default_config=ContextConfig(
                max_context_tokens=8000,
                timeout_seconds=self._config.default_timeout_seconds,
            ),
        )
        
        self._executor = SkillExecutor(
            config=ExecutorConfig(
                default_timeout_seconds=self._config.default_timeout_seconds,
                max_concurrent_tools=self._config.max_concurrent_tasks,
            )
        )
        
        self._error_handler = ErrorHandler(
            on_escalate=self._handle_escalation,
        )
        
        # State
        self._state = OrchestratorState()
        
        # Skill and tool loaders for direct access
        self._skill_loader = skill_loader
        self._tool_loader = tool_loader
    
    # -------------------------------------------------------------------------
    # Task Execution
    # -------------------------------------------------------------------------
    
    def execute_task(
        self,
        task: Any,
        dependency_outputs: Optional[dict[str, Any]] = None,
    ) -> TaskExecutionResult:
        """
        Execute a task synchronously.
        
        Args:
            task: Task to execute
            dependency_outputs: Outputs from dependency tasks
            
        Returns:
            TaskExecutionResult
        """
        task_id = getattr(task, "id", str(task))
        started_at = datetime.utcnow()
        
        self._state.is_running = True
        self._state.current_task_id = task_id
        self._state.started_at = started_at
        
        try:
            # Build execution context
            context = self._context_builder.build_from_task(
                task=task,
                dependency_outputs=dependency_outputs,
            )
            context.start_execution()
            
            # Notify task start
            if self._callbacks.on_task_start:
                self._callbacks.on_task_start(task_id, context)
            
            # Execute the task
            result = self._execute_with_context(task, context)
            
            # Update state
            self._state.tasks_executed += 1
            if result.success:
                self._state.tasks_succeeded += 1
            else:
                self._state.tasks_failed += 1
            self._state.last_execution_at = datetime.utcnow()
            
            # Notify task complete
            if self._callbacks.on_task_complete:
                self._callbacks.on_task_complete(task_id, result)
            
            return result
            
        except Exception as e:
            completed_at = datetime.utcnow()
            duration = (completed_at - started_at).total_seconds()
            
            error = ExecutionError.from_exception(e, task_id=task_id)
            
            if self._callbacks.on_task_error:
                self._callbacks.on_task_error(task_id, error)
            
            self._state.tasks_executed += 1
            self._state.tasks_failed += 1
            
            return TaskExecutionResult(
                task_id=task_id,
                success=False,
                status=ExecutionStatus.FAILED,
                errors=[error.to_dict()],
                duration_seconds=duration,
                started_at=started_at,
                completed_at=completed_at,
            )
        
        finally:
            self._state.is_running = False
            self._state.current_task_id = None
    
    async def execute_task_async(
        self,
        task: Any,
        dependency_outputs: Optional[dict[str, Any]] = None,
    ) -> TaskExecutionResult:
        """
        Execute a task asynchronously.
        
        Args:
            task: Task to execute
            dependency_outputs: Outputs from dependency tasks
            
        Returns:
            TaskExecutionResult
        """
        task_id = getattr(task, "id", str(task))
        started_at = datetime.utcnow()
        
        self._state.is_running = True
        self._state.current_task_id = task_id
        
        try:
            # Build execution context
            context = self._context_builder.build_from_task(
                task=task,
                dependency_outputs=dependency_outputs,
            )
            context.start_execution()
            
            # Notify task start
            if self._callbacks.on_task_start:
                self._callbacks.on_task_start(task_id, context)
            
            # Execute the task asynchronously
            result = await self._execute_with_context_async(task, context)
            
            # Update state
            self._state.tasks_executed += 1
            if result.success:
                self._state.tasks_succeeded += 1
            else:
                self._state.tasks_failed += 1
            
            # Notify task complete
            if self._callbacks.on_task_complete:
                self._callbacks.on_task_complete(task_id, result)
            
            return result
            
        except Exception as e:
            completed_at = datetime.utcnow()
            duration = (completed_at - started_at).total_seconds()
            
            error = ExecutionError.from_exception(e, task_id=task_id)
            
            self._state.tasks_executed += 1
            self._state.tasks_failed += 1
            
            return TaskExecutionResult(
                task_id=task_id,
                success=False,
                status=ExecutionStatus.FAILED,
                errors=[error.to_dict()],
                duration_seconds=duration,
                started_at=started_at,
                completed_at=completed_at,
            )
        
        finally:
            self._state.is_running = False
            self._state.current_task_id = None
    
    def _execute_with_context(
        self,
        task: Any,
        context: ExecutionContext,
    ) -> TaskExecutionResult:
        """Execute a task with a prepared context."""
        task_id = context.task_id
        started_at = datetime.utcnow()
        skill_results: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []
        recovery_attempts = 0
        
        try:
            # Get required skills from task
            requirements = getattr(task, "requirements", None)
            required_skills = getattr(requirements, "skills", []) if requirements else []
            required_tools = getattr(requirements, "tools", []) if requirements else []
            
            # Execute each required skill
            for skill_id in required_skills:
                skill = context.get_skill(skill_id)
                if skill is None and self._skill_loader:
                    skill = self._skill_loader.get(skill_id)
                
                if skill is None:
                    context.add_warning(f"Skill not found: {skill_id}")
                    continue
                
                # Notify skill start
                if self._callbacks.on_skill_start:
                    self._callbacks.on_skill_start(task_id, skill_id)
                
                # Execute skill with error handling
                result = self._execute_skill_with_recovery(
                    skill, context, task_id, skill_id
                )
                skill_results.append(result.to_dict())
                recovery_attempts += context.state.errors.__len__()
                
                # Notify skill complete
                if self._callbacks.on_skill_complete:
                    self._callbacks.on_skill_complete(task_id, skill_id, result)
                
                # Check for fatal errors
                if result.is_failure() and self._config.stop_on_first_error:
                    break
                
                # Update progress
                if self._callbacks.on_progress:
                    progress = (required_skills.index(skill_id) + 1) / len(required_skills) * 100
                    self._callbacks.on_progress(task_id, progress, f"Completed {skill_id}")
            
            # Execute any required tools
            for tool_id in required_tools:
                tool = context.get_tool(tool_id)
                if tool is None and self._tool_loader:
                    tool = self._tool_loader.get(tool_id)
                
                if tool is None:
                    context.add_warning(f"Tool not found: {tool_id}")
                    continue
                
                # Get tool inputs from context
                tool_inputs = context.get_input(f"{tool_id}_inputs", {})
                
                # Notify tool start
                if self._callbacks.on_tool_start:
                    self._callbacks.on_tool_start(task_id, tool_id)
                
                # Execute tool
                result = self._executor.execute_tool(tool, context, **tool_inputs)
                tool_results.append(result.to_dict())
                
                # Notify tool complete
                if self._callbacks.on_tool_complete:
                    self._callbacks.on_tool_complete(task_id, tool_id, result)
            
            # Determine success
            has_errors = context.has_errors()
            has_fatal_skill_failure = any(
                r.get("status") == "failed" for r in skill_results
            )
            success = not has_fatal_skill_failure and not has_errors
            
            completed_at = datetime.utcnow()
            duration = (completed_at - started_at).total_seconds()
            
            return TaskExecutionResult(
                task_id=task_id,
                success=success,
                status=ExecutionStatus.SUCCESS if success else ExecutionStatus.FAILED,
                outputs=context.state.intermediate_results,
                artifacts=[],
                memories_created=[m.get("id", "") for m in context.state.memories_to_write],
                memories_updated=[m.get("memory_id", "") for m in context.state.memories_to_update],
                messages_sent=[m.get("id", "") for m in context.state.messages_to_send],
                errors=[{"message": e} for e in context.state.errors],
                warnings=context.state.warnings,
                duration_seconds=duration,
                started_at=started_at,
                completed_at=completed_at,
                skill_results=skill_results,
                tool_results=tool_results,
                recovery_attempts=recovery_attempts,
            )
            
        except Exception as e:
            completed_at = datetime.utcnow()
            duration = (completed_at - started_at).total_seconds()
            
            return TaskExecutionResult(
                task_id=task_id,
                success=False,
                status=ExecutionStatus.FAILED,
                errors=[ExecutionError.from_exception(e, task_id=task_id).to_dict()],
                duration_seconds=duration,
                started_at=started_at,
                completed_at=completed_at,
                skill_results=skill_results,
                tool_results=tool_results,
            )
    
    async def _execute_with_context_async(
        self,
        task: Any,
        context: ExecutionContext,
    ) -> TaskExecutionResult:
        """Execute a task asynchronously with a prepared context."""
        task_id = context.task_id
        started_at = datetime.utcnow()
        skill_results: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []
        
        try:
            requirements = getattr(task, "requirements", None)
            required_skills = getattr(requirements, "skills", []) if requirements else []
            
            # Execute skills asynchronously
            for skill_id in required_skills:
                skill = context.get_skill(skill_id)
                if skill is None and self._skill_loader:
                    skill = self._skill_loader.get(skill_id)
                
                if skill is None:
                    context.add_warning(f"Skill not found: {skill_id}")
                    continue
                
                result = await self._executor.execute_skill_async(skill, context)
                skill_results.append(result.to_dict())
                
                if result.is_failure() and self._config.stop_on_first_error:
                    break
            
            success = not context.has_errors()
            completed_at = datetime.utcnow()
            duration = (completed_at - started_at).total_seconds()
            
            return TaskExecutionResult(
                task_id=task_id,
                success=success,
                status=ExecutionStatus.SUCCESS if success else ExecutionStatus.FAILED,
                outputs=context.state.intermediate_results,
                errors=[{"message": e} for e in context.state.errors],
                warnings=context.state.warnings,
                duration_seconds=duration,
                started_at=started_at,
                completed_at=completed_at,
                skill_results=skill_results,
                tool_results=tool_results,
            )
            
        except Exception as e:
            completed_at = datetime.utcnow()
            duration = (completed_at - started_at).total_seconds()
            
            return TaskExecutionResult(
                task_id=task_id,
                success=False,
                status=ExecutionStatus.FAILED,
                errors=[ExecutionError.from_exception(e, task_id=task_id).to_dict()],
                duration_seconds=duration,
                started_at=started_at,
                completed_at=completed_at,
            )
    
    def _execute_skill_with_recovery(
        self,
        skill: Any,
        context: ExecutionContext,
        task_id: str,
        skill_id: str,
    ) -> ExecutionResult:
        """Execute a skill with error recovery."""
        if not self._config.enable_error_recovery:
            return self._executor.execute_skill(skill, context)
        
        def retry_fn() -> ExecutionResult:
            return self._executor.execute_skill(skill, context)
        
        result = self._executor.execute_skill(skill, context)
        
        if result.is_failure():
            error = ExecutionError(
                message=result.error or "Skill execution failed",
                category=ErrorCategory.SKILL_EXECUTION_FAILED,
                task_id=task_id,
                skill_id=skill_id,
            )
            
            recovery = self._error_handler.handle_error(
                error,
                retry_fn=retry_fn,
            )
            
            if recovery.success and recovery.output:
                return recovery.output
        
        return result
    
    # -------------------------------------------------------------------------
    # Batch Execution
    # -------------------------------------------------------------------------
    
    def execute_tasks(
        self,
        tasks: list[Any],
        parallel: bool = False,
    ) -> list[TaskExecutionResult]:
        """
        Execute multiple tasks.
        
        Args:
            tasks: Tasks to execute
            parallel: Whether to execute in parallel
            
        Returns:
            List of TaskExecutionResults
        """
        if parallel and self._config.mode == OrchestratorMode.PARALLEL:
            return self._execute_tasks_parallel(tasks)
        else:
            return self._execute_tasks_sequential(tasks)
    
    def _execute_tasks_sequential(self, tasks: list[Any]) -> list[TaskExecutionResult]:
        """Execute tasks sequentially."""
        results = []
        dependency_outputs: dict[str, Any] = {}
        
        for task in tasks:
            task_id = getattr(task, "id", str(task))
            result = self.execute_task(task, dependency_outputs)
            results.append(result)
            
            # Store outputs for dependent tasks
            if result.success:
                dependency_outputs[task_id] = result.outputs
            
            # Stop on error if configured
            if not result.success and self._config.stop_on_first_error:
                break
        
        return results
    
    def _execute_tasks_parallel(self, tasks: list[Any]) -> list[TaskExecutionResult]:
        """Execute tasks in parallel (limited concurrency)."""
        import concurrent.futures
        
        results: list[TaskExecutionResult] = []
        
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self._config.max_concurrent_tasks
        ) as executor:
            future_to_task = {
                executor.submit(self.execute_task, task): task
                for task in tasks
            }
            
            for future in concurrent.futures.as_completed(future_to_task):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    task = future_to_task[future]
                    task_id = getattr(task, "id", str(task))
                    results.append(TaskExecutionResult(
                        task_id=task_id,
                        success=False,
                        status=ExecutionStatus.FAILED,
                        errors=[ExecutionError.from_exception(e).to_dict()],
                    ))
        
        return results
    
    # -------------------------------------------------------------------------
    # Escalation
    # -------------------------------------------------------------------------
    
    def _handle_escalation(self, error: ExecutionError) -> None:
        """Handle error escalation."""
        if self._callbacks.on_escalation:
            self._callbacks.on_escalation(error)
    
    # -------------------------------------------------------------------------
    # State and Metrics
    # -------------------------------------------------------------------------
    
    def get_state(self) -> OrchestratorState:
        """Get orchestrator state."""
        return self._state
    
    def get_executor_metrics(self) -> dict[str, Any]:
        """Get executor metrics."""
        return self._executor.get_metrics().to_dict()
    
    def get_error_summary(self) -> dict[str, Any]:
        """Get error handling summary."""
        return self._error_handler.get_summary()
    
    def reset_metrics(self) -> None:
        """Reset all metrics."""
        self._executor.reset_metrics()
        self._error_handler.clear_errors()
        self._state = OrchestratorState()
    
    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------
    
    def shutdown(self, wait: bool = True) -> None:
        """
        Shutdown the orchestrator.
        
        Args:
            wait: Wait for pending tasks to complete
        """
        self._executor.shutdown(wait=wait)
        self._state.is_running = False
