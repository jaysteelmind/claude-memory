"""
Task planner for decomposition and planning.

This module provides task planning capabilities including:
- Task decomposition into subtasks
- Skill and tool requirement identification
- Dependency graph construction
- Execution order determination
- Duration estimation
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol, runtime_checkable
import re

from dmm.agentos.tasks.constants import (
    TaskStatus,
    TaskType,
    DependencyType,
    ExecutionMode,
    DEFAULT_PRIORITY,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_SUBTASK_DEPTH,
    MAX_SUBTASKS_PER_TASK,
)
from dmm.agentos.tasks.models import (
    Task,
    TaskPlan,
    TaskDependency,
    TaskRequirements,
    TaskConstraints,
    generate_task_id,
)


# =============================================================================
# Protocols for External Dependencies
# =============================================================================

@runtime_checkable
class SkillRegistryProtocol(Protocol):
    """Protocol for skill registry integration."""
    
    def find_by_tags(self, tags: list[str], match_all: bool = False) -> list[Any]:
        """Find skills by tags."""
        ...
    
    def search(self, query: str) -> list[Any]:
        """Search for skills by query."""
        ...
    
    def get_dependencies(self, skill_id: str, transitive: bool = True) -> list[Any]:
        """Get skill dependencies."""
        ...


@runtime_checkable
class ToolRegistryProtocol(Protocol):
    """Protocol for tool registry integration."""
    
    def find_by_tags(self, tags: list[str], match_all: bool = False) -> list[Any]:
        """Find tools by tags."""
        ...


@runtime_checkable
class AgentMatcherProtocol(Protocol):
    """Protocol for agent matching integration."""
    
    def find_for_task(self, task_description: str) -> list[Any]:
        """Find agents suitable for a task."""
        ...


# =============================================================================
# Planning Configuration
# =============================================================================

@dataclass
class PlanConstraints:
    """Constraints for task planning."""
    
    max_subtasks: int = MAX_SUBTASKS_PER_TASK
    max_depth: int = MAX_SUBTASK_DEPTH
    max_total_duration_seconds: float = 3600.0
    max_parallel_tasks: int = 5
    require_all_skills: bool = False
    require_all_tools: bool = False
    allowed_agents: Optional[list[str]] = None
    execution_mode: ExecutionMode = ExecutionMode.SEQUENTIAL


@dataclass
class SkillMatch:
    """A matched skill for a task."""
    
    skill_id: str
    name: str
    relevance_score: float
    required_tools: list[str] = field(default_factory=list)
    estimated_duration_seconds: float = 60.0


@dataclass
class DecompositionResult:
    """Result of task decomposition."""
    
    should_decompose: bool
    subtasks: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""
    estimated_complexity: float = 0.0


@dataclass
class PlanningResult:
    """Result of task planning."""
    
    success: bool
    plan: Optional[TaskPlan] = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# =============================================================================
# Task Planner Implementation
# =============================================================================

class TaskPlanner:
    """
    Plans task execution by decomposing complex tasks and resolving dependencies.
    
    The planner:
    1. Analyzes task descriptions to identify required skills
    2. Determines if decomposition is needed
    3. Creates subtasks with proper dependencies
    4. Builds execution order respecting dependencies
    5. Estimates durations and resource requirements
    """
    
    def __init__(
        self,
        skill_registry: Optional[SkillRegistryProtocol] = None,
        tool_registry: Optional[ToolRegistryProtocol] = None,
        agent_matcher: Optional[AgentMatcherProtocol] = None,
    ) -> None:
        """
        Initialize task planner.
        
        Args:
            skill_registry: Optional skill registry for skill matching
            tool_registry: Optional tool registry for tool matching
            agent_matcher: Optional agent matcher for agent assignment
        """
        self._skill_registry = skill_registry
        self._tool_registry = tool_registry
        self._agent_matcher = agent_matcher
        
        # Decomposition patterns - maps keywords to subtask templates
        self._decomposition_patterns = self._build_decomposition_patterns()
    
    # -------------------------------------------------------------------------
    # Main Planning Interface
    # -------------------------------------------------------------------------
    
    def plan(
        self,
        task_description: str,
        constraints: Optional[PlanConstraints] = None,
        inputs: Optional[dict[str, Any]] = None,
        priority: int = DEFAULT_PRIORITY,
        parent_task: Optional[Task] = None,
    ) -> PlanningResult:
        """
        Create an execution plan for a task.
        
        Args:
            task_description: Natural language task description
            constraints: Planning constraints
            inputs: Task inputs
            priority: Task priority
            parent_task: Parent task if this is a subtask
            
        Returns:
            PlanningResult with plan or errors
        """
        constraints = constraints or PlanConstraints()
        inputs = inputs or {}
        errors: list[str] = []
        warnings: list[str] = []
        
        # Step 1: Create root task
        root_task = self._create_task_from_description(
            description=task_description,
            priority=priority,
            inputs=inputs,
            parent_task=parent_task,
        )
        
        # Step 2: Identify required skills
        skill_matches = self._identify_required_skills(task_description)
        if skill_matches:
            root_task.requirements.skills = [s.skill_id for s in skill_matches]
        
        # Step 3: Determine if decomposition is needed
        decomposition = self._analyze_decomposition(
            task_description,
            skill_matches,
            constraints,
        )
        
        # Step 4: Create subtasks if needed
        subtasks: list[Task] = []
        if decomposition.should_decompose:
            depth = (parent_task.depth + 1) if parent_task else 1
            
            if depth > constraints.max_depth:
                warnings.append(f"Max depth {constraints.max_depth} reached, skipping decomposition")
            else:
                subtasks = self._create_subtasks(
                    root_task=root_task,
                    decomposition=decomposition,
                    constraints=constraints,
                    depth=depth,
                )
                root_task.task_type = TaskType.COMPOSITE
                root_task.subtask_ids = [st.id for st in subtasks]
        
        # Step 5: Resolve dependencies and build execution order
        all_tasks = [root_task] + subtasks
        execution_order = self._build_execution_order(all_tasks)
        parallel_groups = self._identify_parallel_groups(all_tasks, constraints)
        
        # Step 6: Estimate total duration
        estimated_duration = self._estimate_total_duration(all_tasks, parallel_groups)
        
        if estimated_duration > constraints.max_total_duration_seconds:
            warnings.append(
                f"Estimated duration {estimated_duration:.0f}s exceeds max {constraints.max_total_duration_seconds:.0f}s"
            )
        
        # Step 7: Estimate token usage
        estimated_tokens = self._estimate_token_usage(all_tasks)
        
        # Step 8: Assign agents if matcher available
        if self._agent_matcher:
            self._assign_agents(all_tasks, constraints)
        
        # Create plan
        plan = TaskPlan(
            root_task=root_task,
            subtasks=subtasks,
            execution_order=execution_order,
            parallel_groups=parallel_groups,
            estimated_duration_seconds=estimated_duration,
            estimated_tokens=estimated_tokens,
        )
        
        # Validate plan
        validation_errors = self._validate_plan(plan, constraints)
        errors.extend(validation_errors)
        
        return PlanningResult(
            success=len(errors) == 0,
            plan=plan if len(errors) == 0 else None,
            errors=errors,
            warnings=warnings,
        )
    
    def plan_from_task(
        self,
        task: Task,
        constraints: Optional[PlanConstraints] = None,
    ) -> PlanningResult:
        """
        Create an execution plan for an existing task.
        
        Args:
            task: Existing task to plan
            constraints: Planning constraints
            
        Returns:
            PlanningResult with plan or errors
        """
        return self.plan(
            task_description=f"{task.name}: {task.description}",
            constraints=constraints,
            inputs=task.inputs,
            priority=task.priority,
        )
    
    # -------------------------------------------------------------------------
    # Task Creation
    # -------------------------------------------------------------------------
    
    def _create_task_from_description(
        self,
        description: str,
        priority: int,
        inputs: dict[str, Any],
        parent_task: Optional[Task],
    ) -> Task:
        """Create a task from a natural language description."""
        # Extract task name (first sentence or line)
        name = self._extract_task_name(description)
        
        # Determine depth
        depth = 0
        parent_id = None
        if parent_task:
            depth = parent_task.depth + 1
            parent_id = parent_task.id
        
        return Task(
            id=generate_task_id(),
            name=name,
            description=description,
            task_type=TaskType.SIMPLE,
            parent_id=parent_id,
            depth=depth,
            priority=priority,
            inputs=inputs,
            requirements=TaskRequirements(),
            constraints=TaskConstraints(),
        )
    
    def _extract_task_name(self, description: str) -> str:
        """Extract a concise task name from description."""
        # Take first line or sentence
        lines = description.strip().split("\n")
        first_line = lines[0].strip()
        
        # If it's a sentence, take up to first period
        if "." in first_line:
            first_line = first_line.split(".")[0]
        
        # Truncate if too long
        if len(first_line) > 100:
            first_line = first_line[:97] + "..."
        
        return first_line
    
    # -------------------------------------------------------------------------
    # Skill Identification
    # -------------------------------------------------------------------------
    
    def _identify_required_skills(self, description: str) -> list[SkillMatch]:
        """Identify skills required for a task."""
        matches: list[SkillMatch] = []
        
        # If we have a skill registry, use it for matching
        if self._skill_registry:
            try:
                # Extract keywords from description
                keywords = self._extract_keywords(description)
                
                # Search for matching skills
                for keyword in keywords:
                    found_skills = self._skill_registry.search(keyword)
                    for skill in found_skills:
                        skill_id = getattr(skill, "id", str(skill))
                        skill_name = getattr(skill, "name", skill_id)
                        
                        # Avoid duplicates
                        if not any(m.skill_id == skill_id for m in matches):
                            matches.append(SkillMatch(
                                skill_id=skill_id,
                                name=skill_name,
                                relevance_score=0.8,
                                estimated_duration_seconds=60.0,
                            ))
            except Exception:
                pass
        
        # Fallback: pattern-based skill inference
        if not matches:
            matches = self._infer_skills_from_patterns(description)
        
        return matches
    
    def _extract_keywords(self, text: str) -> list[str]:
        """Extract relevant keywords from text."""
        # Common task-related keywords
        task_keywords = [
            "review", "analyze", "implement", "create", "build", "test",
            "refactor", "debug", "document", "optimize", "deploy", "configure",
            "security", "performance", "quality", "code", "api", "database",
            "authentication", "authorization", "validation", "error", "logging",
        ]
        
        text_lower = text.lower()
        found = []
        
        for keyword in task_keywords:
            if keyword in text_lower:
                found.append(keyword)
        
        return found
    
    def _infer_skills_from_patterns(self, description: str) -> list[SkillMatch]:
        """Infer skills from description patterns."""
        matches: list[SkillMatch] = []
        description_lower = description.lower()
        
        # Pattern to skill mapping
        patterns = {
            r"\b(review|check|inspect)\b.*\b(code|implementation)\b": SkillMatch(
                skill_id="skill_code_review",
                name="Code Review",
                relevance_score=0.9,
                estimated_duration_seconds=120.0,
            ),
            r"\b(test|testing|unit test)\b": SkillMatch(
                skill_id="skill_test_generation",
                name="Test Generation",
                relevance_score=0.85,
                estimated_duration_seconds=180.0,
            ),
            r"\b(document|documentation|docs)\b": SkillMatch(
                skill_id="skill_documentation",
                name="Documentation",
                relevance_score=0.85,
                estimated_duration_seconds=120.0,
            ),
            r"\b(refactor|restructure|improve)\b": SkillMatch(
                skill_id="skill_refactoring",
                name="Refactoring",
                relevance_score=0.85,
                estimated_duration_seconds=240.0,
            ),
            r"\b(security|vulnerabilit|auth)\b": SkillMatch(
                skill_id="skill_security_scan",
                name="Security Scan",
                relevance_score=0.9,
                estimated_duration_seconds=180.0,
            ),
            r"\b(analyze|analysis|inspect)\b": SkillMatch(
                skill_id="skill_code_analysis",
                name="Code Analysis",
                relevance_score=0.8,
                estimated_duration_seconds=90.0,
            ),
            r"\b(implement|create|build|develop)\b": SkillMatch(
                skill_id="skill_code_generation",
                name="Code Generation",
                relevance_score=0.85,
                estimated_duration_seconds=300.0,
            ),
            r"\b(debug|fix|troubleshoot)\b": SkillMatch(
                skill_id="skill_debugging",
                name="Debugging",
                relevance_score=0.9,
                estimated_duration_seconds=180.0,
            ),
        }
        
        for pattern, skill_match in patterns.items():
            if re.search(pattern, description_lower):
                if not any(m.skill_id == skill_match.skill_id for m in matches):
                    matches.append(skill_match)
        
        return matches
    
    # -------------------------------------------------------------------------
    # Decomposition Analysis
    # -------------------------------------------------------------------------
    
    def _analyze_decomposition(
        self,
        description: str,
        skill_matches: list[SkillMatch],
        constraints: PlanConstraints,
    ) -> DecompositionResult:
        """Analyze whether a task should be decomposed."""
        # Indicators for decomposition
        complexity_indicators = [
            (r"\band\b", 0.2),  # Multiple actions connected by "and"
            (r"\bthen\b", 0.3),  # Sequential steps
            (r"\bfirst\b.*\bthen\b", 0.4),  # Explicit sequencing
            (r"\b(multiple|several|various)\b", 0.3),  # Multiple items
            (r"\b(step|phase|stage)\b", 0.4),  # Explicit phases
            (r"\bcomprehensive\b", 0.3),  # Comprehensive work
            (r"\bfull\b", 0.2),  # Full scope
        ]
        
        description_lower = description.lower()
        complexity_score = 0.0
        
        for pattern, weight in complexity_indicators:
            if re.search(pattern, description_lower):
                complexity_score += weight
        
        # Multiple skills also indicate complexity
        if len(skill_matches) > 1:
            complexity_score += 0.2 * len(skill_matches)
        
        # Length of description indicates complexity
        if len(description) > 200:
            complexity_score += 0.2
        if len(description) > 500:
            complexity_score += 0.3
        
        should_decompose = complexity_score >= 0.5
        
        subtasks: list[dict[str, Any]] = []
        if should_decompose:
            subtasks = self._generate_subtask_definitions(description, skill_matches)
        
        return DecompositionResult(
            should_decompose=should_decompose,
            subtasks=subtasks,
            reason=f"Complexity score: {complexity_score:.2f}",
            estimated_complexity=complexity_score,
        )
    
    def _build_decomposition_patterns(self) -> dict[str, list[dict[str, Any]]]:
        """Build patterns for task decomposition."""
        return {
            "review": [
                {"name": "Analyze structure", "skill": "skill_code_analysis", "order": 1},
                {"name": "Check quality", "skill": "skill_code_review", "order": 2},
                {"name": "Generate report", "skill": "skill_documentation", "order": 3},
            ],
            "refactor": [
                {"name": "Analyze current implementation", "skill": "skill_code_analysis", "order": 1},
                {"name": "Design improvements", "skill": "skill_code_analysis", "order": 2},
                {"name": "Implement changes", "skill": "skill_code_generation", "order": 3},
                {"name": "Write tests", "skill": "skill_test_generation", "order": 3},  # Parallel
                {"name": "Review changes", "skill": "skill_code_review", "order": 4},
            ],
            "implement": [
                {"name": "Design solution", "skill": "skill_code_analysis", "order": 1},
                {"name": "Implement code", "skill": "skill_code_generation", "order": 2},
                {"name": "Write tests", "skill": "skill_test_generation", "order": 3},
                {"name": "Document", "skill": "skill_documentation", "order": 4},
            ],
            "security": [
                {"name": "Scan for vulnerabilities", "skill": "skill_security_scan", "order": 1},
                {"name": "Analyze findings", "skill": "skill_code_analysis", "order": 2},
                {"name": "Generate recommendations", "skill": "skill_documentation", "order": 3},
            ],
        }
    
    def _generate_subtask_definitions(
        self,
        description: str,
        skill_matches: list[SkillMatch],
    ) -> list[dict[str, Any]]:
        """Generate subtask definitions based on description and skills."""
        description_lower = description.lower()
        subtasks: list[dict[str, Any]] = []
        
        # Check for matching decomposition patterns
        for keyword, pattern_subtasks in self._decomposition_patterns.items():
            if keyword in description_lower:
                for st in pattern_subtasks:
                    subtasks.append({
                        "name": st["name"],
                        "skill": st.get("skill"),
                        "order": st.get("order", 1),
                        "description": f"{st['name']} for: {description[:100]}",
                    })
                break
        
        # If no pattern matched, create subtasks from skill matches
        if not subtasks and skill_matches:
            for i, skill in enumerate(skill_matches):
                subtasks.append({
                    "name": f"Execute {skill.name}",
                    "skill": skill.skill_id,
                    "order": i + 1,
                    "description": f"Apply {skill.name} to: {description[:100]}",
                })
        
        # If still no subtasks, create generic analysis and execution
        if not subtasks:
            subtasks = [
                {"name": "Analyze requirements", "order": 1, "description": f"Analyze: {description[:100]}"},
                {"name": "Execute task", "order": 2, "description": f"Execute: {description[:100]}"},
                {"name": "Verify results", "order": 3, "description": f"Verify: {description[:100]}"},
            ]
        
        return subtasks
    
    # -------------------------------------------------------------------------
    # Subtask Creation
    # -------------------------------------------------------------------------
    
    def _create_subtasks(
        self,
        root_task: Task,
        decomposition: DecompositionResult,
        constraints: PlanConstraints,
        depth: int,
    ) -> list[Task]:
        """Create subtasks from decomposition result."""
        subtasks: list[Task] = []
        
        # Group by order for dependency tracking
        order_groups: dict[int, list[str]] = {}
        
        for i, st_def in enumerate(decomposition.subtasks):
            if len(subtasks) >= constraints.max_subtasks:
                break
            
            subtask = Task(
                id=generate_task_id(),
                name=st_def.get("name", f"Subtask {i+1}"),
                description=st_def.get("description", ""),
                task_type=TaskType.SIMPLE,
                parent_id=root_task.id,
                depth=depth,
                priority=root_task.priority,
                inputs=root_task.inputs.copy(),
            )
            
            # Set skill requirement if specified
            if "skill" in st_def and st_def["skill"]:
                subtask.requirements.skills = [st_def["skill"]]
            
            # Track order for dependencies
            order = st_def.get("order", i + 1)
            if order not in order_groups:
                order_groups[order] = []
            order_groups[order].append(subtask.id)
            
            subtasks.append(subtask)
        
        # Set up dependencies based on order
        sorted_orders = sorted(order_groups.keys())
        for i, order in enumerate(sorted_orders):
            if i > 0:
                prev_order = sorted_orders[i - 1]
                prev_task_ids = order_groups[prev_order]
                
                # Current order tasks depend on all previous order tasks
                for task_id in order_groups[order]:
                    task = next(t for t in subtasks if t.id == task_id)
                    for prev_id in prev_task_ids:
                        task.add_dependency(prev_id, DependencyType.COMPLETION)
        
        return subtasks
    
    # -------------------------------------------------------------------------
    # Execution Order and Parallelization
    # -------------------------------------------------------------------------
    
    def _build_execution_order(self, tasks: list[Task]) -> list[str]:
        """Build execution order using topological sort."""
        # Build adjacency list
        graph: dict[str, list[str]] = {t.id: [] for t in tasks}
        in_degree: dict[str, int] = {t.id: 0 for t in tasks}
        
        for task in tasks:
            for dep in task.dependencies:
                if dep.task_id in graph:
                    graph[dep.task_id].append(task.id)
                    in_degree[task.id] += 1
        
        # Kahn's algorithm for topological sort
        queue = [tid for tid, degree in in_degree.items() if degree == 0]
        order: list[str] = []
        
        while queue:
            # Sort by priority (higher first) for deterministic ordering
            queue.sort(key=lambda tid: next(
                (t.priority for t in tasks if t.id == tid), 0
            ), reverse=True)
            
            current = queue.pop(0)
            order.append(current)
            
            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # Check for cycles
        if len(order) != len(tasks):
            # Cycle detected, return simple order
            return [t.id for t in sorted(tasks, key=lambda t: t.priority, reverse=True)]
        
        return order
    
    def _identify_parallel_groups(
        self,
        tasks: list[Task],
        constraints: PlanConstraints,
    ) -> list[list[str]]:
        """Identify groups of tasks that can run in parallel."""
        if constraints.execution_mode == ExecutionMode.SEQUENTIAL:
            return [[t.id] for t in tasks]
        
        # Group tasks by their dependency depth
        depth_map: dict[str, int] = {}
        
        def get_depth(task_id: str, visited: set[str]) -> int:
            if task_id in depth_map:
                return depth_map[task_id]
            if task_id in visited:
                return 0  # Cycle detected
            
            visited.add(task_id)
            task = next((t for t in tasks if t.id == task_id), None)
            if not task:
                return 0
            
            if not task.dependencies:
                depth_map[task_id] = 0
                return 0
            
            max_dep_depth = 0
            for dep in task.dependencies:
                if dep.required:
                    dep_depth = get_depth(dep.task_id, visited)
                    max_dep_depth = max(max_dep_depth, dep_depth + 1)
            
            depth_map[task_id] = max_dep_depth
            return max_dep_depth
        
        for task in tasks:
            get_depth(task.id, set())
        
        # Group by depth
        depth_groups: dict[int, list[str]] = {}
        for task_id, depth in depth_map.items():
            if depth not in depth_groups:
                depth_groups[depth] = []
            depth_groups[depth].append(task_id)
        
        # Convert to list of groups, respecting max parallel limit
        parallel_groups: list[list[str]] = []
        for depth in sorted(depth_groups.keys()):
            group = depth_groups[depth]
            
            # Split large groups
            for i in range(0, len(group), constraints.max_parallel_tasks):
                parallel_groups.append(group[i:i + constraints.max_parallel_tasks])
        
        return parallel_groups
    
    # -------------------------------------------------------------------------
    # Estimation
    # -------------------------------------------------------------------------
    
    def _estimate_total_duration(
        self,
        tasks: list[Task],
        parallel_groups: list[list[str]],
    ) -> float:
        """Estimate total execution duration."""
        total = 0.0
        
        for group in parallel_groups:
            # For parallel groups, take the max duration
            group_max = 0.0
            for task_id in group:
                task = next((t for t in tasks if t.id == task_id), None)
                if task:
                    task_duration = task.constraints.timeout_seconds
                    group_max = max(group_max, task_duration)
            total += group_max
        
        return total
    
    def _estimate_token_usage(self, tasks: list[Task]) -> int:
        """Estimate total token usage."""
        total = 0
        
        for task in tasks:
            # Base estimate per task
            base_tokens = 500
            
            # Add for description length
            base_tokens += len(task.description) // 4
            
            # Add for each skill
            base_tokens += len(task.requirements.skills) * 200
            
            total += min(base_tokens, task.requirements.max_context_tokens)
        
        return total
    
    # -------------------------------------------------------------------------
    # Agent Assignment
    # -------------------------------------------------------------------------
    
    def _assign_agents(
        self,
        tasks: list[Task],
        constraints: PlanConstraints,
    ) -> None:
        """Assign agents to tasks."""
        if not self._agent_matcher:
            return
        
        for task in tasks:
            if task.assigned_agent:
                continue
            
            try:
                matches = self._agent_matcher.find_for_task(
                    f"{task.name}: {task.description}"
                )
                
                if matches:
                    # Filter by allowed agents if specified
                    if constraints.allowed_agents:
                        matches = [
                            m for m in matches
                            if getattr(m, "agent_id", None) in constraints.allowed_agents
                        ]
                    
                    if matches:
                        best_match = matches[0]
                        task.assigned_agent = getattr(best_match, "agent_id", str(best_match))
            except Exception:
                pass
    
    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------
    
    def _validate_plan(
        self,
        plan: TaskPlan,
        constraints: PlanConstraints,
    ) -> list[str]:
        """Validate a task plan."""
        errors: list[str] = []
        
        # Validate root task
        root_errors = plan.root_task.validate()
        errors.extend([f"Root task: {e}" for e in root_errors])
        
        # Validate subtasks
        for subtask in plan.subtasks:
            subtask_errors = subtask.validate()
            errors.extend([f"Subtask {subtask.id}: {e}" for e in subtask_errors])
        
        # Check subtask count
        if len(plan.subtasks) > constraints.max_subtasks:
            errors.append(f"Too many subtasks: {len(plan.subtasks)} > {constraints.max_subtasks}")
        
        # Check depth
        max_depth = max((t.depth for t in plan.get_all_tasks()), default=0)
        if max_depth > constraints.max_depth:
            errors.append(f"Max depth exceeded: {max_depth} > {constraints.max_depth}")
        
        # Check for circular dependencies
        if self._has_circular_dependencies(plan.get_all_tasks()):
            errors.append("Circular dependencies detected")
        
        # Check execution order covers all tasks
        all_ids = {t.id for t in plan.get_all_tasks()}
        order_ids = set(plan.execution_order)
        if all_ids != order_ids:
            missing = all_ids - order_ids
            errors.append(f"Execution order missing tasks: {missing}")
        
        return errors
    
    def _has_circular_dependencies(self, tasks: list[Task]) -> bool:
        """Check for circular dependencies using DFS."""
        task_map = {t.id: t for t in tasks}
        visited: set[str] = set()
        rec_stack: set[str] = set()
        
        def has_cycle(task_id: str) -> bool:
            visited.add(task_id)
            rec_stack.add(task_id)
            
            task = task_map.get(task_id)
            if task:
                for dep in task.dependencies:
                    if dep.task_id not in visited:
                        if has_cycle(dep.task_id):
                            return True
                    elif dep.task_id in rec_stack:
                        return True
            
            rec_stack.remove(task_id)
            return False
        
        for task in tasks:
            if task.id not in visited:
                if has_cycle(task.id):
                    return True
        
        return False
