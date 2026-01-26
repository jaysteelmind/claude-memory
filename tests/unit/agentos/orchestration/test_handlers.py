"""
Unit tests for error handlers.

Tests cover:
- Error classification
- Recovery strategies
- Error handling flow
- Error tracking
"""

import pytest
from datetime import datetime

from dmm.agentos.orchestration import (
    ErrorHandler,
    ExecutionError,
    ErrorCategory,
    ErrorSeverity,
    RecoveryAction,
    RecoveryStrategy,
    RecoveryResult,
)


class TestExecutionError:
    """Tests for ExecutionError."""
    
    def test_create_error(self):
        """Test creating execution error."""
        error = ExecutionError(
            message="Something went wrong",
            category=ErrorCategory.SKILL_EXECUTION_FAILED,
            severity=ErrorSeverity.ERROR,
        )
        
        assert error.message == "Something went wrong"
        assert error.category == ErrorCategory.SKILL_EXECUTION_FAILED
        assert error.timestamp is not None
    
    def test_error_from_exception(self):
        """Test creating error from exception."""
        try:
            raise ValueError("Invalid value")
        except Exception as e:
            error = ExecutionError.from_exception(e, task_id="task_123")
        
        assert error.message == "Invalid value"
        assert error.error_type == "ValueError"
        assert error.task_id == "task_123"
        assert error.traceback_str is not None
    
    def test_error_classification_timeout(self):
        """Test timeout error classification."""
        try:
            raise TimeoutError("Operation timed out")
        except Exception as e:
            error = ExecutionError.from_exception(e)
        
        assert error.category == ErrorCategory.TIMEOUT
    
    def test_error_classification_permission(self):
        """Test permission error classification."""
        try:
            raise PermissionError("Access denied")
        except Exception as e:
            error = ExecutionError.from_exception(e)
        
        assert error.category == ErrorCategory.PERMISSION_DENIED
    
    def test_error_can_retry(self):
        """Test retry check."""
        error = ExecutionError(
            message="Test",
            recoverable=True,
            max_recovery_attempts=3,
        )
        
        assert error.can_retry()
        error.recovery_attempts = 3
        assert not error.can_retry()
    
    def test_error_increment_attempts(self):
        """Test incrementing recovery attempts."""
        error = ExecutionError(message="Test")
        
        error.increment_attempts()
        error.increment_attempts()
        
        assert error.recovery_attempts == 2
    
    def test_error_to_dict(self):
        """Test error serialization."""
        error = ExecutionError(
            message="Test error",
            category=ErrorCategory.NETWORK_ERROR,
            severity=ErrorSeverity.WARNING,
            task_id="task_123",
        )
        
        data = error.to_dict()
        
        assert data["message"] == "Test error"
        assert data["category"] == "network_error"
        assert data["severity"] == "warning"
        assert data["task_id"] == "task_123"


class TestRecoveryStrategy:
    """Tests for RecoveryStrategy."""
    
    def test_create_strategy(self):
        """Test creating recovery strategy."""
        strategy = RecoveryStrategy(
            category=ErrorCategory.TIMEOUT,
            actions=[RecoveryAction.RETRY, RecoveryAction.ESCALATE],
            max_retries=3,
        )
        
        assert strategy.category == ErrorCategory.TIMEOUT
        assert len(strategy.actions) == 2
    
    def test_get_next_action(self):
        """Test getting next recovery action."""
        strategy = RecoveryStrategy(
            category=ErrorCategory.TIMEOUT,
            actions=[
                RecoveryAction.RETRY,
                RecoveryAction.RETRY_WITH_BACKOFF,
                RecoveryAction.ESCALATE,
            ],
        )
        
        assert strategy.get_next_action(0) == RecoveryAction.RETRY
        assert strategy.get_next_action(1) == RecoveryAction.RETRY_WITH_BACKOFF
        assert strategy.get_next_action(2) == RecoveryAction.ESCALATE
        assert strategy.get_next_action(10) == RecoveryAction.ESCALATE  # Last action
    
    def test_should_escalate(self):
        """Test escalation threshold."""
        strategy = RecoveryStrategy(
            category=ErrorCategory.TIMEOUT,
            actions=[RecoveryAction.RETRY],
            escalate_after_attempts=2,
        )
        
        assert not strategy.should_escalate(1)
        assert strategy.should_escalate(2)
        assert strategy.should_escalate(3)


class TestErrorHandler:
    """Tests for ErrorHandler."""
    
    @pytest.fixture
    def handler(self):
        """Create error handler."""
        return ErrorHandler()
    
    def test_create_handler(self):
        """Test creating error handler."""
        handler = ErrorHandler()
        assert handler is not None
    
    def test_handle_error_with_retry(self, handler):
        """Test handling error with retry."""
        error = ExecutionError(
            message="Temporary failure",
            category=ErrorCategory.TIMEOUT,
        )
        
        retry_called = False
        def retry_fn():
            nonlocal retry_called
            retry_called = True
            return "retry_result"
        
        result = handler.handle_error(error, retry_fn=retry_fn)
        
        # Strategy should attempt retry
        assert result.action_taken in [
            RecoveryAction.RETRY,
            RecoveryAction.RETRY_WITH_BACKOFF,
        ]
    
    def test_handle_error_abort_on_invalid_input(self, handler):
        """Test abort on invalid input errors."""
        error = ExecutionError(
            message="Invalid input",
            category=ErrorCategory.INVALID_INPUT,
        )
        
        result = handler.handle_error(error)
        
        assert result.action_taken == RecoveryAction.ABORT
        assert not result.success
    
    def test_handle_error_with_fallback(self, handler):
        """Test handling error with fallback."""
        error = ExecutionError(
            message="Resource unavailable",
            category=ErrorCategory.RESOURCE_UNAVAILABLE,
        )
        error.recovery_attempts = 1  # Skip first retry
        
        fallback_called = False
        def fallback_fn():
            nonlocal fallback_called
            fallback_called = True
            return "fallback_result"
        
        result = handler.handle_error(error, fallback_fn=fallback_fn)
        
        if result.action_taken == RecoveryAction.USE_FALLBACK:
            assert fallback_called or not result.success
    
    def test_handle_exception(self, handler):
        """Test handling exception directly."""
        try:
            raise ValueError("Test exception")
        except Exception as e:
            result = handler.handle_exception(
                e,
                task_id="task_123",
                skill_id="skill_1",
            )
        
        assert result.action_taken is not None
    
    def test_error_tracking(self, handler):
        """Test error tracking."""
        error1 = ExecutionError(message="Error 1", category=ErrorCategory.TIMEOUT)
        error2 = ExecutionError(message="Error 2", category=ErrorCategory.NETWORK_ERROR)
        
        handler.handle_error(error1)
        handler.handle_error(error2)
        
        errors = handler.get_errors()
        assert len(errors) == 2
    
    def test_get_errors_by_category(self, handler):
        """Test filtering errors by category."""
        handler.handle_error(ExecutionError(
            message="Timeout 1",
            category=ErrorCategory.TIMEOUT,
        ))
        handler.handle_error(ExecutionError(
            message="Network error",
            category=ErrorCategory.NETWORK_ERROR,
        ))
        handler.handle_error(ExecutionError(
            message="Timeout 2",
            category=ErrorCategory.TIMEOUT,
        ))
        
        timeouts = handler.get_errors_by_category(ErrorCategory.TIMEOUT)
        assert len(timeouts) == 2
    
    def test_get_errors_by_severity(self, handler):
        """Test filtering errors by severity."""
        handler.handle_error(ExecutionError(
            message="Warning",
            severity=ErrorSeverity.WARNING,
            category=ErrorCategory.TIMEOUT,
        ))
        handler.handle_error(ExecutionError(
            message="Critical",
            severity=ErrorSeverity.CRITICAL,
            category=ErrorCategory.SYSTEM_ERROR,
        ))
        
        critical = handler.get_errors_by_severity(ErrorSeverity.CRITICAL)
        assert len(critical) == 1
    
    def test_clear_errors(self, handler):
        """Test clearing errors."""
        handler.handle_error(ExecutionError(
            message="Test",
            category=ErrorCategory.UNKNOWN,
        ))
        
        handler.clear_errors()
        
        assert len(handler.get_errors()) == 0
    
    def test_has_fatal_errors(self, handler):
        """Test checking for fatal errors."""
        handler.handle_error(ExecutionError(
            message="Warning",
            severity=ErrorSeverity.WARNING,
            category=ErrorCategory.TIMEOUT,
        ))
        
        assert not handler.has_fatal_errors()
        
        handler.handle_error(ExecutionError(
            message="Fatal",
            severity=ErrorSeverity.FATAL,
            category=ErrorCategory.SYSTEM_ERROR,
        ))
        
        assert handler.has_fatal_errors()
    
    def test_get_summary(self, handler):
        """Test getting error summary."""
        handler.handle_error(ExecutionError(
            message="Error 1",
            category=ErrorCategory.TIMEOUT,
        ))
        handler.handle_error(ExecutionError(
            message="Error 2",
            category=ErrorCategory.NETWORK_ERROR,
        ))
        
        summary = handler.get_summary()
        
        assert summary["total_errors"] == 2
        assert "errors_by_category" in summary
        assert "errors_by_severity" in summary
    
    def test_custom_strategy(self, handler):
        """Test setting custom recovery strategy."""
        custom_strategy = RecoveryStrategy(
            category=ErrorCategory.TIMEOUT,
            actions=[RecoveryAction.SKIP],
            max_retries=0,
        )
        
        handler.set_strategy(ErrorCategory.TIMEOUT, custom_strategy)
        
        error = ExecutionError(
            message="Timeout",
            category=ErrorCategory.TIMEOUT,
        )
        
        result = handler.handle_error(error)
        
        assert result.action_taken == RecoveryAction.SKIP
    
    def test_escalation_callback(self):
        """Test escalation callback is called."""
        escalated_errors = []
        
        def on_escalate(error):
            escalated_errors.append(error)
        
        handler = ErrorHandler(on_escalate=on_escalate)
        
        error = ExecutionError(
            message="Permission denied",
            category=ErrorCategory.PERMISSION_DENIED,
        )
        
        handler.handle_error(error)
        
        assert len(escalated_errors) == 1
