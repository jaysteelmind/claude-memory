"""Task Manager Agent - Manages and coordinates tasks across the system.

This agent demonstrates:
- Task creation and decomposition
- Priority-based scheduling
- Progress tracking
- Task delegation to other agents
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable


class TaskPriority(str, Enum):
    """Task priority levels."""
    
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class TaskStatus(str, Enum):
    """Task status values."""
    
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """Represents a task in the system."""
    
    task_id: str
    name: str
    description: str
    priority: TaskPriority
    status: TaskStatus = TaskStatus.PENDING
    parent_id: str | None = None
    subtasks: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    assigned_agent: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    progress: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "parent_id": self.parent_id,
            "subtasks": self.subtasks,
            "dependencies": self.dependencies,
            "assigned_agent": self.assigned_agent,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "progress": self.progress,
        }


@dataclass
class TaskManagerConfig:
    """Configuration for TaskManagerAgent."""
    
    max_concurrent_tasks: int = 5
    default_priority: TaskPriority = TaskPriority.NORMAL
    enable_auto_scheduling: bool = True
    task_timeout_seconds: int = 300


class TaskManagerAgent:
    """Agent that manages and coordinates tasks.
    
    This agent provides:
    - Task creation and decomposition
    - Dependency-aware scheduling
    - Progress tracking and reporting
    - Task delegation capabilities
    
    Example:
        agent = TaskManagerAgent()
        task = agent.create_task("Review codebase", "Review all Python files")
        subtasks = agent.decompose_task(task.task_id)
        agent.schedule_tasks()
    """
    
    def __init__(self, config: TaskManagerConfig | None = None) -> None:
        """Initialize the agent.
        
        Args:
            config: Optional configuration.
        """
        self.config = config or TaskManagerConfig()
        self._tasks: dict[str, Task] = {}
        self._subscribers: list[Callable[[Task, str], None]] = []
    
    def create_task(
        self,
        name: str,
        description: str,
        priority: TaskPriority | None = None,
        dependencies: list[str] | None = None,
        inputs: dict[str, Any] | None = None,
        parent_id: str | None = None,
    ) -> Task:
        """Create a new task.
        
        Args:
            name: Task name.
            description: Task description.
            priority: Optional priority level.
            dependencies: Optional list of task IDs this depends on.
            inputs: Optional input data.
            parent_id: Optional parent task ID.
            
        Returns:
            Created Task object.
        """
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        
        task = Task(
            task_id=task_id,
            name=name,
            description=description,
            priority=priority or self.config.default_priority,
            dependencies=dependencies or [],
            inputs=inputs or {},
            parent_id=parent_id,
        )
        
        self._tasks[task_id] = task
        
        if parent_id and parent_id in self._tasks:
            self._tasks[parent_id].subtasks.append(task_id)
        
        self._notify_subscribers(task, "created")
        return task
    
    def decompose_task(
        self,
        task_id: str,
        subtask_definitions: list[dict[str, Any]] | None = None,
    ) -> list[Task]:
        """Decompose a task into subtasks.
        
        Args:
            task_id: ID of task to decompose.
            subtask_definitions: Optional list of subtask definitions.
                Each should have 'name' and 'description' keys.
            
        Returns:
            List of created subtasks.
            
        Raises:
            KeyError: If task not found.
        """
        if task_id not in self._tasks:
            raise KeyError(f"Task not found: {task_id}")
        
        parent_task = self._tasks[task_id]
        
        if subtask_definitions is None:
            subtask_definitions = self._auto_decompose(parent_task)
        
        subtasks = []
        prev_task_id = None
        
        for i, definition in enumerate(subtask_definitions):
            dependencies = []
            if prev_task_id:
                dependencies.append(prev_task_id)
            
            subtask = self.create_task(
                name=definition.get("name", f"Subtask {i + 1}"),
                description=definition.get("description", ""),
                priority=parent_task.priority,
                dependencies=dependencies,
                parent_id=task_id,
            )
            
            subtasks.append(subtask)
            prev_task_id = subtask.task_id
        
        return subtasks
    
    def _auto_decompose(self, task: Task) -> list[dict[str, Any]]:
        """Automatically decompose a task based on its description."""
        description_lower = task.description.lower()
        
        if "review" in description_lower and "code" in description_lower:
            return [
                {"name": "Analyze code structure", "description": "Parse and analyze code structure"},
                {"name": "Check code quality", "description": "Run quality checks and linting"},
                {"name": "Identify issues", "description": "Find potential issues and improvements"},
                {"name": "Generate report", "description": "Create review report with findings"},
            ]
        elif "test" in description_lower:
            return [
                {"name": "Setup test environment", "description": "Prepare testing environment"},
                {"name": "Run tests", "description": "Execute test suite"},
                {"name": "Analyze results", "description": "Analyze test results"},
                {"name": "Report findings", "description": "Generate test report"},
            ]
        else:
            return [
                {"name": "Analyze requirements", "description": "Understand task requirements"},
                {"name": "Execute main work", "description": "Perform the main task work"},
                {"name": "Verify results", "description": "Verify task completion"},
            ]
    
    def schedule_tasks(self) -> list[Task]:
        """Schedule pending tasks based on priority and dependencies.
        
        Returns:
            List of newly scheduled tasks.
        """
        pending = [
            t for t in self._tasks.values()
            if t.status == TaskStatus.PENDING
        ]
        
        pending.sort(key=lambda t: (
            {"critical": 0, "high": 1, "normal": 2, "low": 3}[t.priority.value],
            t.created_at,
        ))
        
        scheduled = []
        running_count = sum(
            1 for t in self._tasks.values()
            if t.status == TaskStatus.RUNNING
        )
        
        for task in pending:
            if running_count >= self.config.max_concurrent_tasks:
                break
            
            if self._dependencies_satisfied(task):
                task.status = TaskStatus.SCHEDULED
                scheduled.append(task)
                self._notify_subscribers(task, "scheduled")
        
        return scheduled
    
    def _dependencies_satisfied(self, task: Task) -> bool:
        """Check if all dependencies are completed."""
        for dep_id in task.dependencies:
            if dep_id not in self._tasks:
                return False
            if self._tasks[dep_id].status != TaskStatus.COMPLETED:
                return False
        return True
    
    def start_task(self, task_id: str) -> Task:
        """Start a scheduled task.
        
        Args:
            task_id: ID of task to start.
            
        Returns:
            Updated task.
            
        Raises:
            KeyError: If task not found.
            ValueError: If task cannot be started.
        """
        if task_id not in self._tasks:
            raise KeyError(f"Task not found: {task_id}")
        
        task = self._tasks[task_id]
        
        if task.status not in (TaskStatus.PENDING, TaskStatus.SCHEDULED):
            raise ValueError(f"Task cannot be started from status: {task.status.value}")
        
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(timezone.utc)
        
        self._notify_subscribers(task, "started")
        return task
    
    def complete_task(
        self,
        task_id: str,
        outputs: dict[str, Any] | None = None,
    ) -> Task:
        """Mark a task as completed.
        
        Args:
            task_id: ID of task to complete.
            outputs: Optional output data.
            
        Returns:
            Updated task.
        """
        if task_id not in self._tasks:
            raise KeyError(f"Task not found: {task_id}")
        
        task = self._tasks[task_id]
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(timezone.utc)
        task.progress = 1.0
        
        if outputs:
            task.outputs = outputs
        
        if task.parent_id:
            self._update_parent_progress(task.parent_id)
        
        self._notify_subscribers(task, "completed")
        return task
    
    def fail_task(self, task_id: str, error: str) -> Task:
        """Mark a task as failed.
        
        Args:
            task_id: ID of task that failed.
            error: Error description.
            
        Returns:
            Updated task.
        """
        if task_id not in self._tasks:
            raise KeyError(f"Task not found: {task_id}")
        
        task = self._tasks[task_id]
        task.status = TaskStatus.FAILED
        task.completed_at = datetime.now(timezone.utc)
        task.outputs["error"] = error
        
        self._notify_subscribers(task, "failed")
        return task
    
    def update_progress(self, task_id: str, progress: float) -> Task:
        """Update task progress.
        
        Args:
            task_id: ID of task.
            progress: Progress value (0.0 to 1.0).
            
        Returns:
            Updated task.
        """
        if task_id not in self._tasks:
            raise KeyError(f"Task not found: {task_id}")
        
        task = self._tasks[task_id]
        task.progress = max(0.0, min(1.0, progress))
        
        if task.parent_id:
            self._update_parent_progress(task.parent_id)
        
        self._notify_subscribers(task, "progress")
        return task
    
    def _update_parent_progress(self, parent_id: str) -> None:
        """Update parent task progress based on subtasks."""
        if parent_id not in self._tasks:
            return
        
        parent = self._tasks[parent_id]
        if not parent.subtasks:
            return
        
        total_progress = sum(
            self._tasks[st].progress
            for st in parent.subtasks
            if st in self._tasks
        )
        
        parent.progress = total_progress / len(parent.subtasks)
    
    def delegate_task(self, task_id: str, agent_id: str) -> Task:
        """Delegate a task to another agent.
        
        Args:
            task_id: ID of task to delegate.
            agent_id: ID of agent to assign.
            
        Returns:
            Updated task.
        """
        if task_id not in self._tasks:
            raise KeyError(f"Task not found: {task_id}")
        
        task = self._tasks[task_id]
        task.assigned_agent = agent_id
        
        self._notify_subscribers(task, "delegated")
        return task
    
    def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID."""
        return self._tasks.get(task_id)
    
    def get_all_tasks(self) -> list[Task]:
        """Get all tasks."""
        return list(self._tasks.values())
    
    def get_tasks_by_status(self, status: TaskStatus) -> list[Task]:
        """Get tasks with a specific status."""
        return [t for t in self._tasks.values() if t.status == status]
    
    def get_execution_order(self) -> list[Task]:
        """Get tasks in recommended execution order.
        
        Uses topological sort based on dependencies.
        
        Returns:
            List of tasks in execution order.
        """
        visited = set()
        order = []
        
        def visit(task_id: str) -> None:
            if task_id in visited or task_id not in self._tasks:
                return
            
            visited.add(task_id)
            task = self._tasks[task_id]
            
            for dep_id in task.dependencies:
                visit(dep_id)
            
            order.append(task)
        
        for task_id in self._tasks:
            visit(task_id)
        
        return order
    
    def subscribe(self, callback: Callable[[Task, str], None]) -> None:
        """Subscribe to task events.
        
        Args:
            callback: Function called with (task, event_type).
        """
        self._subscribers.append(callback)
    
    def _notify_subscribers(self, task: Task, event: str) -> None:
        """Notify subscribers of task event."""
        for callback in self._subscribers:
            try:
                callback(task, event)
            except Exception:
                pass
    
    def get_status_report(self) -> str:
        """Generate a status report of all tasks.
        
        Returns:
            Formatted status report.
        """
        lines = [
            "# Task Status Report",
            "",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            f"Total tasks: {len(self._tasks)}",
            "",
            "## Summary",
            "",
        ]
        
        for status in TaskStatus:
            count = len(self.get_tasks_by_status(status))
            if count > 0:
                lines.append(f"- {status.value.title()}: {count}")
        
        lines.extend(["", "## Tasks", ""])
        
        for task in self.get_execution_order():
            status_icon = {
                TaskStatus.COMPLETED: "[x]",
                TaskStatus.RUNNING: "[>]",
                TaskStatus.FAILED: "[!]",
            }.get(task.status, "[ ]")
            
            lines.append(f"{status_icon} **{task.name}** ({task.priority.value})")
            if task.progress > 0 and task.progress < 1:
                lines.append(f"    Progress: {task.progress:.0%}")
        
        return "\n".join(lines)
