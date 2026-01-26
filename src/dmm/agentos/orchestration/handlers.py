"""
Error handlers for task execution.

This module provides error handling capabilities including:
- Structured error classification
- Recovery strategies
- Escalation logic
- Fallback mechanisms
- Error aggregation and reporting
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional, TypeVar, Generic
from enum import Enum
import traceback


# =============================================================================
# Error Classification
# =============================================================================

class ErrorSeverity(str, Enum):
    """Severity level of errors."""
    
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    FATAL = "fatal"


class ErrorCategory(str, Enum):
    """Category of errors."""
    
    # Execution errors
    TIMEOUT = "timeout"
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    PERMISSION_DENIED = "permission_denied"
    INVALID_INPUT = "invalid_input"
    INVALID_OUTPUT = "invalid_output"
    
    # Skill/Tool errors
    SKILL_NOT_FOUND = "skill_not_found"
    TOOL_NOT_FOUND = "tool_not_found"
    SKILL_EXECUTION_FAILED = "skill_execution_failed"
    TOOL_EXECUTION_FAILED = "tool_execution_failed"
    
    # Context errors
    CONTEXT_INVALID = "context_invalid"
    MEMORY_ERROR = "memory_error"
    DEPENDENCY_FAILED = "dependency_failed"
    
    # System errors
    SYSTEM_ERROR = "system_error"
    NETWORK_ERROR = "network_error"
    STORAGE_ERROR = "storage_error"
    
    # Agent errors
    AGENT_UNAVAILABLE = "agent_unavailable"
    AGENT_OVERLOADED = "agent_overloaded"
    
    # Unknown
    UNKNOWN = "unknown"


class RecoveryAction(str, Enum):
    """Actions that can be taken to recover from errors."""
    
    RETRY = "retry"
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    USE_FALLBACK = "use_fallback"
    SKIP = "skip"
    ESCALATE = "escalate"
    ABORT = "abort"
    WAIT_AND_RETRY = "wait_and_retry"
    REDUCE_SCOPE = "reduce_scope"
    REQUEST_HUMAN = "request_human"


# =============================================================================
# Error Models
# =============================================================================

@dataclass
class ExecutionError:
    """Structured execution error."""
    
    message: str
    category: ErrorCategory = ErrorCategory.UNKNOWN
    severity: ErrorSeverity = ErrorSeverity.ERROR
    error_type: str = "Error"
    details: dict[str, Any] = field(default_factory=dict)
    traceback_str: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    task_id: Optional[str] = None
    skill_id: Optional[str] = None
    tool_id: Optional[str] = None
    recoverable: bool = True
    recovery_attempts: int = 0
    max_recovery_attempts: int = 3
    
    @classmethod
    def from_exception(
        cls,
        exception: Exception,
        category: Optional[ErrorCategory] = None,
        task_id: Optional[str] = None,
        skill_id: Optional[str] = None,
        tool_id: Optional[str] = None,
    ) -> "ExecutionError":
        """Create ExecutionError from an exception."""
        # Classify exception
        if category is None:
            category = cls._classify_exception(exception)
        
        # Determine severity
        severity = cls._determine_severity(category, exception)
        
        # Check if recoverable
        recoverable = category not in (
            ErrorCategory.PERMISSION_DENIED,
            ErrorCategory.INVALID_INPUT,
        )
        
        return cls(
            message=str(exception),
            category=category,
            severity=severity,
            error_type=type(exception).__name__,
            traceback_str=traceback.format_exc(),
            task_id=task_id,
            skill_id=skill_id,
            tool_id=tool_id,
            recoverable=recoverable,
        )
    
    @staticmethod
    def _classify_exception(exception: Exception) -> ErrorCategory:
        """Classify an exception into an error category."""
        error_name = type(exception).__name__.lower()
        error_msg = str(exception).lower()
        
        if "timeout" in error_name or "timeout" in error_msg:
            return ErrorCategory.TIMEOUT
        elif "permission" in error_msg or "access denied" in error_msg:
            return ErrorCategory.PERMISSION_DENIED
        elif "not found" in error_msg:
            if "skill" in error_msg:
                return ErrorCategory.SKILL_NOT_FOUND
            elif "tool" in error_msg:
                return ErrorCategory.TOOL_NOT_FOUND
            return ErrorCategory.RESOURCE_UNAVAILABLE
        elif "invalid" in error_msg:
            if "input" in error_msg:
                return ErrorCategory.INVALID_INPUT
            elif "output" in error_msg:
                return ErrorCategory.INVALID_OUTPUT
            return ErrorCategory.INVALID_INPUT
        elif "network" in error_msg or "connection" in error_msg:
            return ErrorCategory.NETWORK_ERROR
        elif "storage" in error_msg or "disk" in error_msg or "file" in error_msg:
            return ErrorCategory.STORAGE_ERROR
        elif "memory" in error_msg:
            return ErrorCategory.MEMORY_ERROR
        
        return ErrorCategory.UNKNOWN
    
    @staticmethod
    def _determine_severity(category: ErrorCategory, exception: Exception) -> ErrorSeverity:
        """Determine error severity based on category and exception."""
        critical_categories = {
            ErrorCategory.SYSTEM_ERROR,
            ErrorCategory.STORAGE_ERROR,
            ErrorCategory.PERMISSION_DENIED,
        }
        
        warning_categories = {
            ErrorCategory.TIMEOUT,
            ErrorCategory.RESOURCE_UNAVAILABLE,
        }
        
        if category in critical_categories:
            return ErrorSeverity.CRITICAL
        elif category in warning_categories:
            return ErrorSeverity.WARNING
        
        return ErrorSeverity.ERROR
    
    def can_retry(self) -> bool:
        """Check if error can be retried."""
        return self.recoverable and self.recovery_attempts < self.max_recovery_attempts
    
    def increment_attempts(self) -> None:
        """Increment recovery attempts."""
        self.recovery_attempts += 1
    
    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary."""
        return {
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "error_type": self.error_type,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "task_id": self.task_id,
            "skill_id": self.skill_id,
            "tool_id": self.tool_id,
            "recoverable": self.recoverable,
            "recovery_attempts": self.recovery_attempts,
        }


@dataclass
class RecoveryResult:
    """Result of a recovery attempt."""
    
    success: bool
    action_taken: RecoveryAction
    error: Optional[ExecutionError] = None
    output: Any = None
    message: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "success": self.success,
            "action_taken": self.action_taken.value,
            "error": self.error.to_dict() if self.error else None,
            "message": self.message,
        }


# =============================================================================
# Recovery Strategies
# =============================================================================

@dataclass
class RecoveryStrategy:
    """Strategy for recovering from a specific error category."""
    
    category: ErrorCategory
    actions: list[RecoveryAction]
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    fallback_skill_id: Optional[str] = None
    fallback_tool_id: Optional[str] = None
    escalate_after_attempts: int = 2
    
    def get_next_action(self, attempt: int) -> RecoveryAction:
        """Get the next recovery action based on attempt number."""
        if attempt >= len(self.actions):
            return self.actions[-1] if self.actions else RecoveryAction.ABORT
        return self.actions[attempt]
    
    def should_escalate(self, attempt: int) -> bool:
        """Check if error should be escalated."""
        return attempt >= self.escalate_after_attempts


# Default recovery strategies
DEFAULT_RECOVERY_STRATEGIES: dict[ErrorCategory, RecoveryStrategy] = {
    ErrorCategory.TIMEOUT: RecoveryStrategy(
        category=ErrorCategory.TIMEOUT,
        actions=[
            RecoveryAction.RETRY_WITH_BACKOFF,
            RecoveryAction.RETRY_WITH_BACKOFF,
            RecoveryAction.ESCALATE,
        ],
        max_retries=3,
        retry_delay_seconds=2.0,
    ),
    ErrorCategory.RESOURCE_UNAVAILABLE: RecoveryStrategy(
        category=ErrorCategory.RESOURCE_UNAVAILABLE,
        actions=[
            RecoveryAction.WAIT_AND_RETRY,
            RecoveryAction.USE_FALLBACK,
            RecoveryAction.ESCALATE,
        ],
        max_retries=3,
    ),
    ErrorCategory.SKILL_EXECUTION_FAILED: RecoveryStrategy(
        category=ErrorCategory.SKILL_EXECUTION_FAILED,
        actions=[
            RecoveryAction.RETRY,
            RecoveryAction.USE_FALLBACK,
            RecoveryAction.ESCALATE,
        ],
        max_retries=2,
    ),
    ErrorCategory.TOOL_EXECUTION_FAILED: RecoveryStrategy(
        category=ErrorCategory.TOOL_EXECUTION_FAILED,
        actions=[
            RecoveryAction.RETRY,
            RecoveryAction.USE_FALLBACK,
            RecoveryAction.ABORT,
        ],
        max_retries=2,
    ),
    ErrorCategory.NETWORK_ERROR: RecoveryStrategy(
        category=ErrorCategory.NETWORK_ERROR,
        actions=[
            RecoveryAction.RETRY_WITH_BACKOFF,
            RecoveryAction.RETRY_WITH_BACKOFF,
            RecoveryAction.RETRY_WITH_BACKOFF,
            RecoveryAction.ABORT,
        ],
        max_retries=4,
        retry_delay_seconds=1.0,
        backoff_multiplier=2.0,
    ),
    ErrorCategory.DEPENDENCY_FAILED: RecoveryStrategy(
        category=ErrorCategory.DEPENDENCY_FAILED,
        actions=[
            RecoveryAction.WAIT_AND_RETRY,
            RecoveryAction.SKIP,
            RecoveryAction.ESCALATE,
        ],
        max_retries=2,
    ),
    ErrorCategory.AGENT_UNAVAILABLE: RecoveryStrategy(
        category=ErrorCategory.AGENT_UNAVAILABLE,
        actions=[
            RecoveryAction.WAIT_AND_RETRY,
            RecoveryAction.USE_FALLBACK,
            RecoveryAction.ESCALATE,
        ],
        max_retries=3,
    ),
    ErrorCategory.INVALID_INPUT: RecoveryStrategy(
        category=ErrorCategory.INVALID_INPUT,
        actions=[RecoveryAction.ABORT],
        max_retries=0,
    ),
    ErrorCategory.PERMISSION_DENIED: RecoveryStrategy(
        category=ErrorCategory.PERMISSION_DENIED,
        actions=[RecoveryAction.ESCALATE],
        max_retries=0,
    ),
}


# =============================================================================
# Error Handler
# =============================================================================

class ErrorHandler:
    """
    Handles errors during task execution.
    
    The handler provides:
    - Error classification and tracking
    - Recovery strategy selection
    - Escalation logic
    - Error aggregation
    """
    
    def __init__(
        self,
        strategies: Optional[dict[ErrorCategory, RecoveryStrategy]] = None,
        on_escalate: Optional[Callable[[ExecutionError], None]] = None,
        on_abort: Optional[Callable[[ExecutionError], None]] = None,
    ) -> None:
        """
        Initialize error handler.
        
        Args:
            strategies: Custom recovery strategies
            on_escalate: Callback when error is escalated
            on_abort: Callback when execution is aborted
        """
        self._strategies = strategies or DEFAULT_RECOVERY_STRATEGIES.copy()
        self._on_escalate = on_escalate
        self._on_abort = on_abort
        
        # Error tracking
        self._errors: list[ExecutionError] = []
        self._recovery_results: list[RecoveryResult] = []
    
    # -------------------------------------------------------------------------
    # Error Handling
    # -------------------------------------------------------------------------
    
    def handle_error(
        self,
        error: ExecutionError,
        retry_fn: Optional[Callable[[], Any]] = None,
        fallback_fn: Optional[Callable[[], Any]] = None,
    ) -> RecoveryResult:
        """
        Handle an error with appropriate recovery strategy.
        
        Args:
            error: The error to handle
            retry_fn: Function to retry the failed operation
            fallback_fn: Function to execute as fallback
            
        Returns:
            RecoveryResult indicating outcome
        """
        self._errors.append(error)
        
        # Get recovery strategy
        strategy = self._strategies.get(error.category)
        if strategy is None:
            strategy = RecoveryStrategy(
                category=error.category,
                actions=[RecoveryAction.ABORT],
            )
        
        # Get next action
        action = strategy.get_next_action(error.recovery_attempts)
        
        # Execute recovery action
        result = self._execute_recovery(error, action, strategy, retry_fn, fallback_fn)
        
        self._recovery_results.append(result)
        return result
    
    def handle_exception(
        self,
        exception: Exception,
        task_id: Optional[str] = None,
        skill_id: Optional[str] = None,
        tool_id: Optional[str] = None,
        retry_fn: Optional[Callable[[], Any]] = None,
        fallback_fn: Optional[Callable[[], Any]] = None,
    ) -> RecoveryResult:
        """
        Handle an exception by converting to ExecutionError and handling.
        
        Args:
            exception: The exception to handle
            task_id: Associated task ID
            skill_id: Associated skill ID
            tool_id: Associated tool ID
            retry_fn: Function to retry
            fallback_fn: Function for fallback
            
        Returns:
            RecoveryResult
        """
        error = ExecutionError.from_exception(
            exception,
            task_id=task_id,
            skill_id=skill_id,
            tool_id=tool_id,
        )
        return self.handle_error(error, retry_fn, fallback_fn)
    
    def _execute_recovery(
        self,
        error: ExecutionError,
        action: RecoveryAction,
        strategy: RecoveryStrategy,
        retry_fn: Optional[Callable[[], Any]],
        fallback_fn: Optional[Callable[[], Any]],
    ) -> RecoveryResult:
        """Execute a recovery action."""
        error.increment_attempts()
        
        if action == RecoveryAction.ABORT:
            if self._on_abort:
                self._on_abort(error)
            return RecoveryResult(
                success=False,
                action_taken=action,
                error=error,
                message="Execution aborted due to unrecoverable error",
            )
        
        elif action == RecoveryAction.ESCALATE:
            if self._on_escalate:
                self._on_escalate(error)
            return RecoveryResult(
                success=False,
                action_taken=action,
                error=error,
                message="Error escalated for human intervention",
            )
        
        elif action == RecoveryAction.SKIP:
            return RecoveryResult(
                success=True,
                action_taken=action,
                message="Operation skipped due to error",
            )
        
        elif action in (RecoveryAction.RETRY, RecoveryAction.RETRY_WITH_BACKOFF):
            if retry_fn is None:
                return RecoveryResult(
                    success=False,
                    action_taken=action,
                    error=error,
                    message="No retry function provided",
                )
            
            # Apply backoff delay if needed
            if action == RecoveryAction.RETRY_WITH_BACKOFF:
                delay = strategy.retry_delay_seconds * (
                    strategy.backoff_multiplier ** (error.recovery_attempts - 1)
                )
                import time
                time.sleep(delay)
            
            try:
                output = retry_fn()
                return RecoveryResult(
                    success=True,
                    action_taken=action,
                    output=output,
                    message=f"Retry successful on attempt {error.recovery_attempts}",
                )
            except Exception as e:
                new_error = ExecutionError.from_exception(
                    e,
                    category=error.category,
                    task_id=error.task_id,
                    skill_id=error.skill_id,
                    tool_id=error.tool_id,
                )
                new_error.recovery_attempts = error.recovery_attempts
                return RecoveryResult(
                    success=False,
                    action_taken=action,
                    error=new_error,
                    message=f"Retry failed: {str(e)}",
                )
        
        elif action == RecoveryAction.USE_FALLBACK:
            if fallback_fn is None:
                return RecoveryResult(
                    success=False,
                    action_taken=action,
                    error=error,
                    message="No fallback function provided",
                )
            
            try:
                output = fallback_fn()
                return RecoveryResult(
                    success=True,
                    action_taken=action,
                    output=output,
                    message="Fallback execution successful",
                )
            except Exception as e:
                return RecoveryResult(
                    success=False,
                    action_taken=action,
                    error=ExecutionError.from_exception(e),
                    message=f"Fallback failed: {str(e)}",
                )
        
        elif action == RecoveryAction.WAIT_AND_RETRY:
            if retry_fn is None:
                return RecoveryResult(
                    success=False,
                    action_taken=action,
                    error=error,
                    message="No retry function provided",
                )
            
            # Wait before retry
            import time
            time.sleep(strategy.retry_delay_seconds * error.recovery_attempts)
            
            try:
                output = retry_fn()
                return RecoveryResult(
                    success=True,
                    action_taken=action,
                    output=output,
                    message=f"Wait and retry successful on attempt {error.recovery_attempts}",
                )
            except Exception as e:
                return RecoveryResult(
                    success=False,
                    action_taken=action,
                    error=ExecutionError.from_exception(e),
                    message=f"Wait and retry failed: {str(e)}",
                )
        
        elif action == RecoveryAction.REQUEST_HUMAN:
            if self._on_escalate:
                self._on_escalate(error)
            return RecoveryResult(
                success=False,
                action_taken=action,
                error=error,
                message="Human intervention requested",
            )
        
        # Default: abort
        return RecoveryResult(
            success=False,
            action_taken=RecoveryAction.ABORT,
            error=error,
            message=f"Unknown recovery action: {action}",
        )
    
    # -------------------------------------------------------------------------
    # Strategy Management
    # -------------------------------------------------------------------------
    
    def set_strategy(self, category: ErrorCategory, strategy: RecoveryStrategy) -> None:
        """Set recovery strategy for an error category."""
        self._strategies[category] = strategy
    
    def get_strategy(self, category: ErrorCategory) -> Optional[RecoveryStrategy]:
        """Get recovery strategy for an error category."""
        return self._strategies.get(category)
    
    # -------------------------------------------------------------------------
    # Error Tracking
    # -------------------------------------------------------------------------
    
    def get_errors(self) -> list[ExecutionError]:
        """Get all tracked errors."""
        return list(self._errors)
    
    def get_errors_by_category(self, category: ErrorCategory) -> list[ExecutionError]:
        """Get errors by category."""
        return [e for e in self._errors if e.category == category]
    
    def get_errors_by_severity(self, severity: ErrorSeverity) -> list[ExecutionError]:
        """Get errors by severity."""
        return [e for e in self._errors if e.severity == severity]
    
    def get_recovery_results(self) -> list[RecoveryResult]:
        """Get all recovery results."""
        return list(self._recovery_results)
    
    def clear_errors(self) -> None:
        """Clear tracked errors."""
        self._errors.clear()
        self._recovery_results.clear()
    
    def has_fatal_errors(self) -> bool:
        """Check if any fatal errors occurred."""
        return any(e.severity == ErrorSeverity.FATAL for e in self._errors)
    
    def has_unrecovered_errors(self) -> bool:
        """Check if any errors were not recovered."""
        return any(not r.success for r in self._recovery_results)
    
    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    
    def get_summary(self) -> dict[str, Any]:
        """Get error handling summary."""
        return {
            "total_errors": len(self._errors),
            "errors_by_category": {
                cat.value: len(self.get_errors_by_category(cat))
                for cat in ErrorCategory
                if self.get_errors_by_category(cat)
            },
            "errors_by_severity": {
                sev.value: len(self.get_errors_by_severity(sev))
                for sev in ErrorSeverity
                if self.get_errors_by_severity(sev)
            },
            "recovery_attempts": len(self._recovery_results),
            "successful_recoveries": sum(1 for r in self._recovery_results if r.success),
            "failed_recoveries": sum(1 for r in self._recovery_results if not r.success),
            "has_fatal_errors": self.has_fatal_errors(),
        }
