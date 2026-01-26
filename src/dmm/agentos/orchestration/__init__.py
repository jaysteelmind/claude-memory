"""
DMM Orchestration Module.

This module provides task execution orchestration for the Agent OS,
including context management, skill/tool execution, and error handling.

Public API:
-----------

Context:
    ExecutionContext - Runtime context for task execution
    ContextBuilder - Builds execution contexts
    ContextConfig - Configuration for context building
    ContextState - Mutable execution state
    MemoryContext - Retrieved memories for context

Execution:
    SkillExecutor - Executes skills and tools
    ExecutorConfig - Executor configuration
    ExecutionResult - Result of skill/tool execution
    ExecutionStatus - Status of execution
    ExecutorMetrics - Metrics collected by executor

Error Handling:
    ErrorHandler - Handles execution errors
    ExecutionError - Structured execution error
    ErrorCategory - Category of errors
    ErrorSeverity - Severity level of errors
    RecoveryAction - Recovery actions
    RecoveryStrategy - Strategy for error recovery
    RecoveryResult - Result of recovery attempt

Orchestration:
    TaskOrchestrator - Main orchestration coordinator
    OrchestratorConfig - Orchestrator configuration
    OrchestratorMode - Mode of operation
    OrchestratorState - Orchestrator state
    OrchestratorCallbacks - Event callbacks
    TaskExecutionResult - Complete task execution result

Protocols:
    MemoryRetrieverProtocol - Protocol for memory retrieval
    SkillLoaderProtocol - Protocol for skill loading
    ToolLoaderProtocol - Protocol for tool loading
    SkillProtocol - Protocol for executable skills
    AsyncSkillProtocol - Protocol for async skills
    ToolProtocol - Protocol for executable tools

Example Usage:
--------------

    from dmm.agentos.orchestration import (
        TaskOrchestrator,
        OrchestratorConfig,
        ExecutionContext,
        ContextBuilder,
    )
    
    # Create orchestrator
    orchestrator = TaskOrchestrator(
        config=OrchestratorConfig(
            max_concurrent_tasks=5,
            enable_error_recovery=True,
        ),
        skill_loader=my_skill_loader,
        tool_loader=my_tool_loader,
    )
    
    # Execute a task
    result = orchestrator.execute_task(task)
    
    if result.success:
        print(f"Task completed: {result.outputs}")
    else:
        print(f"Task failed: {result.errors}")
    
    # Get metrics
    metrics = orchestrator.get_executor_metrics()
    print(f"Success rate: {metrics['success_rate']}")
"""

# Context
from dmm.agentos.orchestration.context import (
    ExecutionContext,
    ContextBuilder,
    ContextConfig,
    ContextState,
    MemoryContext,
    MemoryRetrieverProtocol,
    SkillLoaderProtocol,
    ToolLoaderProtocol,
)

# Executor
from dmm.agentos.orchestration.executor import (
    SkillExecutor,
    ExecutorConfig,
    ExecutionResult,
    ExecutionStatus,
    ExecutorMetrics,
    SkillProtocol,
    AsyncSkillProtocol,
    ToolProtocol,
)

# Error Handling
from dmm.agentos.orchestration.handlers import (
    ErrorHandler,
    ExecutionError,
    ErrorCategory,
    ErrorSeverity,
    RecoveryAction,
    RecoveryStrategy,
    RecoveryResult,
    DEFAULT_RECOVERY_STRATEGIES,
)

# Orchestrator
from dmm.agentos.orchestration.orchestrator import (
    TaskOrchestrator,
    OrchestratorConfig,
    OrchestratorMode,
    OrchestratorState,
    OrchestratorCallbacks,
    TaskExecutionResult,
)

__all__ = [
    # Context
    "ExecutionContext",
    "ContextBuilder",
    "ContextConfig",
    "ContextState",
    "MemoryContext",
    "MemoryRetrieverProtocol",
    "SkillLoaderProtocol",
    "ToolLoaderProtocol",
    # Executor
    "SkillExecutor",
    "ExecutorConfig",
    "ExecutionResult",
    "ExecutionStatus",
    "ExecutorMetrics",
    "SkillProtocol",
    "AsyncSkillProtocol",
    "ToolProtocol",
    # Error Handling
    "ErrorHandler",
    "ExecutionError",
    "ErrorCategory",
    "ErrorSeverity",
    "RecoveryAction",
    "RecoveryStrategy",
    "RecoveryResult",
    "DEFAULT_RECOVERY_STRATEGIES",
    # Orchestrator
    "TaskOrchestrator",
    "OrchestratorConfig",
    "OrchestratorMode",
    "OrchestratorState",
    "OrchestratorCallbacks",
    "TaskExecutionResult",
]
