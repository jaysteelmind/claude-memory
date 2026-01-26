"""
DMM Task System Module.

This module provides the task management system for the Agent OS,
including task creation, planning, scheduling, and tracking.

Public API:
-----------

Constants and Enums:
    TaskStatus - Task execution status
    TaskPriority - Task priority levels
    TaskType - Type of task (simple, composite, etc.)
    DependencyType - Type of task dependency
    ExecutionMode - How tasks should be executed

Models:
    Task - Main task model
    TaskDependency - Dependency between tasks
    TaskRequirements - Task skill/tool requirements
    TaskConstraints - Task execution constraints
    TaskExecution - Task execution state
    TaskOutput - Task output data
    TaskError - Task error information
    TaskResult - Result of task execution
    TaskPlan - Execution plan for a task

Planning:
    TaskPlanner - Decomposes and plans task execution
    PlanConstraints - Constraints for planning
    PlanningResult - Result of planning operation
    SkillMatch - Matched skill for a task
    DecompositionResult - Result of task decomposition

Scheduling:
    TaskScheduler - Manages task queue and execution order
    SchedulerConfig - Scheduler configuration
    ScheduledTask - Task entry in scheduler queue
    SchedulerStats - Scheduler statistics
    BatchResult - Result of getting task batch

Tracking:
    TaskTracker - Monitors task progress and events
    TaskProgress - Progress information for a task
    TaskHierarchy - Hierarchical view of tasks
    AggregateStatus - Aggregated status for composite tasks
    TaskEvent - Task lifecycle event
    TaskEventType - Types of task events

Storage:
    TaskStore - Task persistence layer

Utilities:
    generate_task_id - Generate unique task ID
    validate_task_id - Validate task ID format
    is_valid_transition - Check if status transition is valid

Example Usage:
--------------

    from dmm.agentos.tasks import (
        Task,
        TaskStore,
        TaskPlanner,
        TaskScheduler,
        TaskTracker,
        TaskStatus,
    )
    
    # Initialize components
    store = TaskStore(base_path)
    store.initialize()
    
    planner = TaskPlanner()
    scheduler = TaskScheduler(store)
    tracker = TaskTracker(store)
    
    # Plan a task
    result = planner.plan("Review the authentication module")
    if result.success:
        # Schedule the plan
        scheduler.schedule_plan(result.plan)
        
        # Get next task to execute
        task = scheduler.get_next_task()
        if task:
            scheduler.mark_running(task.id)
            # ... execute task ...
            scheduler.mark_completed(task.id)
    
    # Monitor progress
    progress = tracker.get_progress(task.id)
    print(f"Progress: {progress.progress_percent}%")
"""

# Constants and Enums
from dmm.agentos.tasks.constants import (
    TaskStatus,
    TaskPriority,
    TaskType,
    DependencyType,
    ExecutionMode,
    TASK_ID_PREFIX,
    TASK_ID_SEPARATOR,
    DEFAULT_PRIORITY,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_RETRY_DELAY_SECONDS,
    DEFAULT_RETRY_BACKOFF_MULTIPLIER,
    MAX_SUBTASK_DEPTH,
    MAX_SUBTASKS_PER_TASK,
    MAX_DEPENDENCIES_PER_TASK,
    MAX_TASK_NAME_LENGTH,
    MAX_TASK_DESCRIPTION_LENGTH,
    MAX_EXECUTION_LOG_ENTRIES,
    TASK_POLL_INTERVAL_SECONDS,
    TASK_STALE_THRESHOLD_SECONDS,
    TASK_CLEANUP_AGE_DAYS,
    TASKS_DB_NAME,
    TASKS_TABLE_NAME,
    TASK_DEPENDENCIES_TABLE_NAME,
    TASK_LOGS_TABLE_NAME,
    TASKS_DIR_NAME,
    ACTIVE_TASKS_DIR,
    PENDING_TASKS_DIR,
    COMPLETED_TASKS_DIR,
    FAILED_TASKS_DIR,
    TASK_INDEX_FILE,
    TASK_FILE_EXTENSION,
    TASK_ID_PATTERN,
    VALID_STATUS_TRANSITIONS,
    is_valid_transition,
)

# Models
from dmm.agentos.tasks.models import (
    Task,
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
)

# Planner
from dmm.agentos.tasks.planner import (
    TaskPlanner,
    PlanConstraints,
    PlanningResult,
    SkillMatch,
    DecompositionResult,
    SkillRegistryProtocol,
    ToolRegistryProtocol,
    AgentMatcherProtocol,
)

# Scheduler
from dmm.agentos.tasks.scheduler import (
    TaskScheduler,
    SchedulerConfig,
    ScheduledTask,
    SchedulerStats,
    BatchResult,
)

# Tracker
from dmm.agentos.tasks.tracker import (
    TaskTracker,
    TaskProgress,
    TaskHierarchy,
    AggregateStatus,
    TaskEvent,
    TaskEventType,
)

# Store
from dmm.agentos.tasks.store import (
    TaskStore,
)

__all__ = [
    # Constants and Enums
    "TaskStatus",
    "TaskPriority",
    "TaskType",
    "DependencyType",
    "ExecutionMode",
    "TASK_ID_PREFIX",
    "TASK_ID_SEPARATOR",
    "DEFAULT_PRIORITY",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_RETRY_DELAY_SECONDS",
    "DEFAULT_RETRY_BACKOFF_MULTIPLIER",
    "MAX_SUBTASK_DEPTH",
    "MAX_SUBTASKS_PER_TASK",
    "MAX_DEPENDENCIES_PER_TASK",
    "MAX_TASK_NAME_LENGTH",
    "MAX_TASK_DESCRIPTION_LENGTH",
    "MAX_EXECUTION_LOG_ENTRIES",
    "TASK_POLL_INTERVAL_SECONDS",
    "TASK_STALE_THRESHOLD_SECONDS",
    "TASK_CLEANUP_AGE_DAYS",
    "TASKS_DB_NAME",
    "TASKS_TABLE_NAME",
    "TASK_DEPENDENCIES_TABLE_NAME",
    "TASK_LOGS_TABLE_NAME",
    "TASKS_DIR_NAME",
    "ACTIVE_TASKS_DIR",
    "PENDING_TASKS_DIR",
    "COMPLETED_TASKS_DIR",
    "FAILED_TASKS_DIR",
    "TASK_INDEX_FILE",
    "TASK_FILE_EXTENSION",
    "TASK_ID_PATTERN",
    "VALID_STATUS_TRANSITIONS",
    "is_valid_transition",
    # Models
    "Task",
    "TaskDependency",
    "TaskRequirements",
    "TaskConstraints",
    "TaskExecution",
    "TaskOutput",
    "TaskError",
    "TaskResult",
    "TaskPlan",
    "generate_task_id",
    "validate_task_id",
    # Planner
    "TaskPlanner",
    "PlanConstraints",
    "PlanningResult",
    "SkillMatch",
    "DecompositionResult",
    "SkillRegistryProtocol",
    "ToolRegistryProtocol",
    "AgentMatcherProtocol",
    # Scheduler
    "TaskScheduler",
    "SchedulerConfig",
    "ScheduledTask",
    "SchedulerStats",
    "BatchResult",
    # Tracker
    "TaskTracker",
    "TaskProgress",
    "TaskHierarchy",
    "AggregateStatus",
    "TaskEvent",
    "TaskEventType",
    # Store
    "TaskStore",
]
