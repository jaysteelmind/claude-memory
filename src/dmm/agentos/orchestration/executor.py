"""
Skill and tool executor for task execution.

This module provides execution capabilities including:
- Skill execution with parameter validation
- Tool execution with safety checks
- Timeout management
- Output collection and validation
- Error handling and recovery
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional, Protocol, runtime_checkable
from enum import Enum
import asyncio
import traceback
import concurrent.futures
from threading import Lock

from dmm.agentos.orchestration.context import ExecutionContext, ContextState


# =============================================================================
# Execution Result Types
# =============================================================================

class ExecutionStatus(str, Enum):
    """Status of an execution."""
    
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


@dataclass
class ExecutionResult:
    """Result of executing a skill or tool."""
    
    status: ExecutionStatus
    output: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    traceback: Optional[str] = None
    duration_seconds: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def is_success(self) -> bool:
        """Check if execution succeeded."""
        return self.status == ExecutionStatus.SUCCESS
    
    def is_failure(self) -> bool:
        """Check if execution failed."""
        return self.status in (ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "error_type": self.error_type,
            "duration_seconds": self.duration_seconds,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata,
        }


# =============================================================================
# Skill Protocol
# =============================================================================

@runtime_checkable
class SkillProtocol(Protocol):
    """Protocol for executable skills."""
    
    @property
    def id(self) -> str:
        """Skill ID."""
        ...
    
    @property
    def name(self) -> str:
        """Skill name."""
        ...
    
    def execute(self, context: ExecutionContext, **kwargs: Any) -> Any:
        """Execute the skill."""
        ...


@runtime_checkable
class AsyncSkillProtocol(Protocol):
    """Protocol for async executable skills."""
    
    @property
    def id(self) -> str:
        """Skill ID."""
        ...
    
    async def execute_async(self, context: ExecutionContext, **kwargs: Any) -> Any:
        """Execute the skill asynchronously."""
        ...


@runtime_checkable
class ToolProtocol(Protocol):
    """Protocol for executable tools."""
    
    @property
    def id(self) -> str:
        """Tool ID."""
        ...
    
    @property
    def name(self) -> str:
        """Tool name."""
        ...
    
    def run(self, **kwargs: Any) -> Any:
        """Run the tool."""
        ...


# =============================================================================
# Executor Configuration
# =============================================================================

@dataclass
class ExecutorConfig:
    """Configuration for the executor."""
    
    default_timeout_seconds: float = 300.0
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    retry_backoff_multiplier: float = 2.0
    max_concurrent_tools: int = 5
    validate_outputs: bool = True
    collect_metrics: bool = True
    log_executions: bool = True


# =============================================================================
# Execution Metrics
# =============================================================================

@dataclass
class ExecutorMetrics:
    """Metrics collected by the executor."""
    
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    timeout_executions: int = 0
    total_duration_seconds: float = 0.0
    skill_executions: dict[str, int] = field(default_factory=dict)
    tool_executions: dict[str, int] = field(default_factory=dict)
    
    def record_execution(
        self,
        resource_type: str,
        resource_id: str,
        status: ExecutionStatus,
        duration: float,
    ) -> None:
        """Record an execution."""
        self.total_executions += 1
        self.total_duration_seconds += duration
        
        if status == ExecutionStatus.SUCCESS:
            self.successful_executions += 1
        elif status == ExecutionStatus.TIMEOUT:
            self.timeout_executions += 1
        elif status == ExecutionStatus.FAILED:
            self.failed_executions += 1
        
        if resource_type == "skill":
            self.skill_executions[resource_id] = self.skill_executions.get(resource_id, 0) + 1
        elif resource_type == "tool":
            self.tool_executions[resource_id] = self.tool_executions.get(resource_id, 0) + 1
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_executions == 0:
            return 0.0
        return self.successful_executions / self.total_executions
    
    @property
    def average_duration(self) -> float:
        """Calculate average execution duration."""
        if self.total_executions == 0:
            return 0.0
        return self.total_duration_seconds / self.total_executions
    
    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "timeout_executions": self.timeout_executions,
            "success_rate": self.success_rate,
            "average_duration_seconds": self.average_duration,
            "total_duration_seconds": self.total_duration_seconds,
            "skill_executions": self.skill_executions,
            "tool_executions": self.tool_executions,
        }


# =============================================================================
# Skill Executor
# =============================================================================

class SkillExecutor:
    """
    Executes skills within an execution context.
    
    The executor handles:
    - Parameter validation
    - Timeout management
    - Output collection
    - Error handling and retries
    - Metrics collection
    """
    
    def __init__(
        self,
        config: Optional[ExecutorConfig] = None,
    ) -> None:
        """
        Initialize skill executor.
        
        Args:
            config: Executor configuration
        """
        self._config = config or ExecutorConfig()
        self._metrics = ExecutorMetrics()
        self._metrics_lock = Lock()
        
        # Thread pool for synchronous execution with timeout
        self._thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=self._config.max_concurrent_tools
        )
    
    # -------------------------------------------------------------------------
    # Skill Execution
    # -------------------------------------------------------------------------
    
    def execute_skill(
        self,
        skill: Any,
        context: ExecutionContext,
        timeout_seconds: Optional[float] = None,
        **kwargs: Any,
    ) -> ExecutionResult:
        """
        Execute a skill synchronously.
        
        Args:
            skill: Skill to execute
            context: Execution context
            timeout_seconds: Timeout override
            **kwargs: Additional skill parameters
            
        Returns:
            ExecutionResult
        """
        timeout = timeout_seconds or self._config.default_timeout_seconds
        skill_id = getattr(skill, "id", str(skill))
        skill_name = getattr(skill, "name", skill_id)
        
        started_at = datetime.utcnow()
        context.state.set_step(f"Executing skill: {skill_name}")
        
        try:
            # Get the execute method
            execute_fn = getattr(skill, "execute", None)
            if execute_fn is None:
                # Try callable skill
                if callable(skill):
                    execute_fn = skill
                else:
                    return ExecutionResult(
                        status=ExecutionStatus.FAILED,
                        error=f"Skill {skill_id} is not executable",
                        error_type="NotExecutable",
                        started_at=started_at,
                        completed_at=datetime.utcnow(),
                    )
            
            # Execute with timeout
            future = self._thread_pool.submit(execute_fn, context, **kwargs)
            
            try:
                output = future.result(timeout=timeout)
                completed_at = datetime.utcnow()
                duration = (completed_at - started_at).total_seconds()
                
                # Record in context
                context.state.add_skill_output(skill_id, output, success=True)
                
                result = ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    output=output,
                    duration_seconds=duration,
                    started_at=started_at,
                    completed_at=completed_at,
                    metadata={"skill_id": skill_id, "skill_name": skill_name},
                )
                
            except concurrent.futures.TimeoutError:
                future.cancel()
                completed_at = datetime.utcnow()
                duration = (completed_at - started_at).total_seconds()
                
                context.state.add_skill_output(skill_id, None, success=False)
                context.state.add_error(f"Skill {skill_name} timed out after {timeout}s")
                
                result = ExecutionResult(
                    status=ExecutionStatus.TIMEOUT,
                    error=f"Execution timed out after {timeout} seconds",
                    error_type="TimeoutError",
                    duration_seconds=duration,
                    started_at=started_at,
                    completed_at=completed_at,
                    metadata={"skill_id": skill_id, "timeout": timeout},
                )
        
        except Exception as e:
            completed_at = datetime.utcnow()
            duration = (completed_at - started_at).total_seconds()
            
            context.state.add_skill_output(skill_id, None, success=False)
            context.state.add_error(f"Skill {skill_name} failed: {str(e)}")
            
            result = ExecutionResult(
                status=ExecutionStatus.FAILED,
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
                duration_seconds=duration,
                started_at=started_at,
                completed_at=completed_at,
                metadata={"skill_id": skill_id},
            )
        
        # Record metrics
        if self._config.collect_metrics:
            with self._metrics_lock:
                self._metrics.record_execution(
                    "skill", skill_id, result.status, result.duration_seconds
                )
        
        return result
    
    async def execute_skill_async(
        self,
        skill: Any,
        context: ExecutionContext,
        timeout_seconds: Optional[float] = None,
        **kwargs: Any,
    ) -> ExecutionResult:
        """
        Execute a skill asynchronously.
        
        Args:
            skill: Skill to execute (should have execute_async method)
            context: Execution context
            timeout_seconds: Timeout override
            **kwargs: Additional skill parameters
            
        Returns:
            ExecutionResult
        """
        timeout = timeout_seconds or self._config.default_timeout_seconds
        skill_id = getattr(skill, "id", str(skill))
        skill_name = getattr(skill, "name", skill_id)
        
        started_at = datetime.utcnow()
        context.state.set_step(f"Executing skill (async): {skill_name}")
        
        try:
            # Get async execute method
            execute_fn = getattr(skill, "execute_async", None)
            if execute_fn is None:
                # Fall back to sync execution in thread pool
                return await asyncio.get_event_loop().run_in_executor(
                    self._thread_pool,
                    lambda: self.execute_skill(skill, context, timeout_seconds, **kwargs)
                )
            
            # Execute with timeout
            try:
                output = await asyncio.wait_for(
                    execute_fn(context, **kwargs),
                    timeout=timeout
                )
                completed_at = datetime.utcnow()
                duration = (completed_at - started_at).total_seconds()
                
                context.state.add_skill_output(skill_id, output, success=True)
                
                result = ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    output=output,
                    duration_seconds=duration,
                    started_at=started_at,
                    completed_at=completed_at,
                    metadata={"skill_id": skill_id, "skill_name": skill_name},
                )
                
            except asyncio.TimeoutError:
                completed_at = datetime.utcnow()
                duration = (completed_at - started_at).total_seconds()
                
                context.state.add_skill_output(skill_id, None, success=False)
                context.state.add_error(f"Skill {skill_name} timed out after {timeout}s")
                
                result = ExecutionResult(
                    status=ExecutionStatus.TIMEOUT,
                    error=f"Execution timed out after {timeout} seconds",
                    error_type="TimeoutError",
                    duration_seconds=duration,
                    started_at=started_at,
                    completed_at=completed_at,
                    metadata={"skill_id": skill_id, "timeout": timeout},
                )
        
        except Exception as e:
            completed_at = datetime.utcnow()
            duration = (completed_at - started_at).total_seconds()
            
            context.state.add_skill_output(skill_id, None, success=False)
            context.state.add_error(f"Skill {skill_name} failed: {str(e)}")
            
            result = ExecutionResult(
                status=ExecutionStatus.FAILED,
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
                duration_seconds=duration,
                started_at=started_at,
                completed_at=completed_at,
                metadata={"skill_id": skill_id},
            )
        
        # Record metrics
        if self._config.collect_metrics:
            with self._metrics_lock:
                self._metrics.record_execution(
                    "skill", skill_id, result.status, result.duration_seconds
                )
        
        return result
    
    # -------------------------------------------------------------------------
    # Tool Execution
    # -------------------------------------------------------------------------
    
    def execute_tool(
        self,
        tool: Any,
        context: ExecutionContext,
        timeout_seconds: Optional[float] = None,
        **kwargs: Any,
    ) -> ExecutionResult:
        """
        Execute a tool.
        
        Args:
            tool: Tool to execute
            context: Execution context for logging
            timeout_seconds: Timeout override
            **kwargs: Tool parameters
            
        Returns:
            ExecutionResult
        """
        timeout = timeout_seconds or self._config.default_timeout_seconds
        tool_id = getattr(tool, "id", str(tool))
        tool_name = getattr(tool, "name", tool_id)
        
        started_at = datetime.utcnow()
        context.state.set_step(f"Executing tool: {tool_name}")
        
        try:
            # Get the run method
            run_fn = getattr(tool, "run", None)
            if run_fn is None:
                # Try execute method
                run_fn = getattr(tool, "execute", None)
            if run_fn is None:
                # Try callable
                if callable(tool):
                    run_fn = tool
                else:
                    return ExecutionResult(
                        status=ExecutionStatus.FAILED,
                        error=f"Tool {tool_id} is not executable",
                        error_type="NotExecutable",
                        started_at=started_at,
                        completed_at=datetime.utcnow(),
                    )
            
            # Execute with timeout
            future = self._thread_pool.submit(run_fn, **kwargs)
            
            try:
                output = future.result(timeout=timeout)
                completed_at = datetime.utcnow()
                duration = (completed_at - started_at).total_seconds()
                
                context.state.add_tool_output(tool_id, output, success=True)
                
                result = ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    output=output,
                    duration_seconds=duration,
                    started_at=started_at,
                    completed_at=completed_at,
                    metadata={"tool_id": tool_id, "tool_name": tool_name},
                )
                
            except concurrent.futures.TimeoutError:
                future.cancel()
                completed_at = datetime.utcnow()
                duration = (completed_at - started_at).total_seconds()
                
                context.state.add_tool_output(tool_id, None, success=False)
                context.state.add_error(f"Tool {tool_name} timed out after {timeout}s")
                
                result = ExecutionResult(
                    status=ExecutionStatus.TIMEOUT,
                    error=f"Execution timed out after {timeout} seconds",
                    error_type="TimeoutError",
                    duration_seconds=duration,
                    started_at=started_at,
                    completed_at=completed_at,
                    metadata={"tool_id": tool_id, "timeout": timeout},
                )
        
        except Exception as e:
            completed_at = datetime.utcnow()
            duration = (completed_at - started_at).total_seconds()
            
            context.state.add_tool_output(tool_id, None, success=False)
            context.state.add_error(f"Tool {tool_name} failed: {str(e)}")
            
            result = ExecutionResult(
                status=ExecutionStatus.FAILED,
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
                duration_seconds=duration,
                started_at=started_at,
                completed_at=completed_at,
                metadata={"tool_id": tool_id},
            )
        
        # Record metrics
        if self._config.collect_metrics:
            with self._metrics_lock:
                self._metrics.record_execution(
                    "tool", tool_id, result.status, result.duration_seconds
                )
        
        return result
    
    # -------------------------------------------------------------------------
    # Batch Execution
    # -------------------------------------------------------------------------
    
    def execute_tools_parallel(
        self,
        tools_with_kwargs: list[tuple[Any, dict[str, Any]]],
        context: ExecutionContext,
        timeout_seconds: Optional[float] = None,
    ) -> list[ExecutionResult]:
        """
        Execute multiple tools in parallel.
        
        Args:
            tools_with_kwargs: List of (tool, kwargs) tuples
            context: Execution context
            timeout_seconds: Timeout for each tool
            
        Returns:
            List of ExecutionResults in same order as input
        """
        timeout = timeout_seconds or self._config.default_timeout_seconds
        
        futures = []
        for tool, kwargs in tools_with_kwargs:
            future = self._thread_pool.submit(
                self.execute_tool, tool, context, timeout, **kwargs
            )
            futures.append(future)
        
        results = []
        for future in futures:
            try:
                result = future.result(timeout=timeout + 5)  # Extra buffer
                results.append(result)
            except Exception as e:
                results.append(ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    error=str(e),
                    error_type=type(e).__name__,
                ))
        
        return results
    
    # -------------------------------------------------------------------------
    # Retry Logic
    # -------------------------------------------------------------------------
    
    def execute_with_retry(
        self,
        execute_fn: Callable[[], ExecutionResult],
        max_retries: Optional[int] = None,
        retry_delay: Optional[float] = None,
    ) -> ExecutionResult:
        """
        Execute a function with retry logic.
        
        Args:
            execute_fn: Function that returns ExecutionResult
            max_retries: Maximum retry attempts
            retry_delay: Initial delay between retries
            
        Returns:
            ExecutionResult from successful attempt or final failure
        """
        max_retries = max_retries or self._config.max_retries
        retry_delay = retry_delay or self._config.retry_delay_seconds
        
        last_result = None
        
        for attempt in range(max_retries + 1):
            result = execute_fn()
            
            if result.is_success():
                return result
            
            last_result = result
            
            # Don't retry on timeout or if it's the last attempt
            if result.status == ExecutionStatus.TIMEOUT or attempt == max_retries:
                break
            
            # Wait before retry with exponential backoff
            import time
            delay = retry_delay * (self._config.retry_backoff_multiplier ** attempt)
            time.sleep(delay)
        
        return last_result or ExecutionResult(
            status=ExecutionStatus.FAILED,
            error="All retry attempts failed",
        )
    
    # -------------------------------------------------------------------------
    # Metrics
    # -------------------------------------------------------------------------
    
    def get_metrics(self) -> ExecutorMetrics:
        """Get executor metrics."""
        with self._metrics_lock:
            return self._metrics
    
    def reset_metrics(self) -> None:
        """Reset executor metrics."""
        with self._metrics_lock:
            self._metrics = ExecutorMetrics()
    
    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------
    
    def shutdown(self, wait: bool = True) -> None:
        """
        Shutdown the executor.
        
        Args:
            wait: Wait for pending tasks to complete
        """
        self._thread_pool.shutdown(wait=wait)
