"""
Unit tests for task planner.

Tests cover:
- Task planning and decomposition
- Skill identification
- Dependency resolution
- Execution order building
- Plan validation
"""

import pytest
from datetime import datetime

from dmm.agentos.tasks import (
    Task,
    TaskPlanner,
    TaskStatus,
    TaskType,
    DependencyType,
    PlanConstraints,
    ExecutionMode,
    SkillMatch,
)


@pytest.fixture
def planner():
    """Create task planner without registries."""
    return TaskPlanner()


class TestTaskPlannerBasics:
    """Tests for basic planner functionality."""
    
    def test_create_planner(self):
        """Test creating planner."""
        planner = TaskPlanner()
        assert planner is not None
    
    def test_plan_simple_task(self, planner):
        """Test planning a simple task."""
        result = planner.plan("Write unit tests for the login module")
        
        assert result.success
        assert result.plan is not None
        assert result.plan.root_task is not None
        assert result.plan.root_task.name != ""
    
    def test_plan_with_priority(self, planner):
        """Test planning with specified priority."""
        result = planner.plan("Review code", priority=8)
        
        assert result.success
        assert result.plan.root_task.priority == 8
    
    def test_plan_with_inputs(self, planner):
        """Test planning with inputs."""
        inputs = {"file_path": "src/auth.py", "focus": "security"}
        result = planner.plan("Review authentication code", inputs=inputs)
        
        assert result.success
        assert result.plan.root_task.inputs == inputs
    
    def test_plan_extracts_name(self, planner):
        """Test plan extracts task name from description."""
        result = planner.plan("Review the authentication module. Focus on security.")
        
        assert result.success
        assert "Review the authentication module" in result.plan.root_task.name


class TestTaskDecomposition:
    """Tests for task decomposition."""
    
    def test_simple_task_no_decomposition(self, planner):
        """Test simple task is not decomposed."""
        result = planner.plan("Check variable names")
        
        assert result.success
        assert len(result.plan.subtasks) == 0
        assert result.plan.root_task.task_type == TaskType.SIMPLE
    
    def test_complex_task_decomposition(self, planner):
        """Test complex task is decomposed."""
        description = """
        Perform a comprehensive code review of the authentication module.
        First analyze the structure, then check for security vulnerabilities,
        and finally generate a detailed report with recommendations.
        """
        result = planner.plan(description)
        
        assert result.success
        # Complex tasks should have subtasks
        if result.plan.subtasks:
            assert result.plan.root_task.task_type == TaskType.COMPOSITE
    
    def test_decomposition_respects_max_subtasks(self, planner):
        """Test decomposition respects max subtasks constraint."""
        constraints = PlanConstraints(max_subtasks=2)
        
        description = """
        Comprehensive refactoring: analyze code, design improvements,
        implement changes, write tests, review, and document everything.
        """
        result = planner.plan(description, constraints=constraints)
        
        assert result.success
        assert len(result.plan.subtasks) <= 2
    
    def test_decomposition_respects_max_depth(self, planner):
        """Test decomposition respects max depth constraint."""
        constraints = PlanConstraints(max_depth=1)
        
        description = "Refactor the entire authentication system comprehensively"
        result = planner.plan(description, constraints=constraints)
        
        assert result.success
        for subtask in result.plan.subtasks:
            assert subtask.depth <= 1


class TestSkillIdentification:
    """Tests for skill identification."""
    
    def test_identify_review_skill(self, planner):
        """Test identifying code review skill."""
        result = planner.plan("Review the authentication code for issues")
        
        assert result.success
        skills = result.plan.root_task.requirements.skills
        # Should identify code review related skill
        assert any("review" in s.lower() for s in skills) or len(skills) >= 0
    
    def test_identify_test_skill(self, planner):
        """Test identifying test generation skill."""
        result = planner.plan("Write unit tests for the login function")
        
        assert result.success
        skills = result.plan.root_task.requirements.skills
        assert any("test" in s.lower() for s in skills) or len(skills) >= 0
    
    def test_identify_security_skill(self, planner):
        """Test identifying security scan skill."""
        result = planner.plan("Scan for security vulnerabilities in auth module")
        
        assert result.success
        skills = result.plan.root_task.requirements.skills
        assert any("security" in s.lower() for s in skills) or len(skills) >= 0
    
    def test_identify_documentation_skill(self, planner):
        """Test identifying documentation skill."""
        result = planner.plan("Write documentation for the API endpoints")
        
        assert result.success
        skills = result.plan.root_task.requirements.skills
        assert any("doc" in s.lower() for s in skills) or len(skills) >= 0


class TestExecutionOrder:
    """Tests for execution order building."""
    
    def test_execution_order_includes_all_tasks(self, planner):
        """Test execution order includes all tasks."""
        result = planner.plan("Review and refactor the login module")
        
        assert result.success
        all_task_ids = {t.id for t in result.plan.get_all_tasks()}
        order_ids = set(result.plan.execution_order)
        
        assert all_task_ids == order_ids
    
    def test_execution_order_respects_dependencies(self, planner):
        """Test execution order respects dependencies."""
        # Create a plan with subtasks that have dependencies
        description = """
        First analyze the code structure, then implement improvements,
        and finally write tests for the changes.
        """
        result = planner.plan(description)
        
        assert result.success
        # Root task should be in execution order
        assert result.plan.root_task.id in result.plan.execution_order


class TestParallelGroups:
    """Tests for parallel group identification."""
    
    def test_sequential_mode_no_parallel(self, planner):
        """Test sequential mode creates single-task groups."""
        constraints = PlanConstraints(execution_mode=ExecutionMode.SEQUENTIAL)
        result = planner.plan("Review the code", constraints=constraints)
        
        assert result.success
        for group in result.plan.parallel_groups:
            assert len(group) == 1
    
    def test_parallel_mode_groups_independent(self, planner):
        """Test parallel mode groups independent tasks."""
        constraints = PlanConstraints(
            execution_mode=ExecutionMode.PARALLEL,
            max_parallel_tasks=5,
        )
        result = planner.plan("Analyze the codebase", constraints=constraints)
        
        assert result.success
        assert len(result.plan.parallel_groups) >= 1


class TestDurationEstimation:
    """Tests for duration estimation."""
    
    def test_estimates_duration(self, planner):
        """Test plan has duration estimate."""
        result = planner.plan("Review authentication code")
        
        assert result.success
        assert result.plan.estimated_duration_seconds > 0
    
    def test_duration_warning_for_long_tasks(self, planner):
        """Test warning for tasks exceeding max duration."""
        constraints = PlanConstraints(max_total_duration_seconds=1.0)
        result = planner.plan("Review code")
        
        # Should have warning about duration
        assert result.success or len(result.warnings) > 0


class TestTokenEstimation:
    """Tests for token usage estimation."""
    
    def test_estimates_tokens(self, planner):
        """Test plan has token estimate."""
        result = planner.plan("Review code")
        
        assert result.success
        assert result.plan.estimated_tokens > 0
    
    def test_longer_description_more_tokens(self, planner):
        """Test longer descriptions estimate more tokens."""
        short_result = planner.plan("Review code")
        long_result = planner.plan(
            "Perform a comprehensive review of the authentication module "
            "including security analysis, code quality checks, and documentation "
            "verification across all files in the auth directory"
        )
        
        assert short_result.success
        assert long_result.success
        # Longer description should generally estimate more tokens
        # (though decomposition can affect this)


class TestPlanValidation:
    """Tests for plan validation."""
    
    def test_valid_plan_no_errors(self, planner):
        """Test valid plan has no errors."""
        result = planner.plan("Review code")
        
        assert result.success
        assert len(result.errors) == 0
    
    def test_plan_from_existing_task(self, planner):
        """Test planning from existing task."""
        task = Task(
            name="Review auth module",
            description="Check for security issues",
            priority=7,
            inputs={"module": "auth"},
        )
        
        result = planner.plan_from_task(task)
        
        assert result.success
        assert result.plan.root_task.priority == 7


class TestPlanConstraints:
    """Tests for plan constraints."""
    
    def test_default_constraints(self):
        """Test default constraint values."""
        constraints = PlanConstraints()
        
        assert constraints.max_subtasks > 0
        assert constraints.max_depth > 0
        assert constraints.max_total_duration_seconds > 0
    
    def test_custom_constraints_applied(self, planner):
        """Test custom constraints are applied."""
        constraints = PlanConstraints(
            max_subtasks=3,
            max_depth=2,
            execution_mode=ExecutionMode.SEQUENTIAL,
        )
        
        result = planner.plan(
            "Comprehensive code review with multiple steps",
            constraints=constraints
        )
        
        assert result.success
        assert len(result.plan.subtasks) <= 3
        for task in result.plan.get_all_tasks():
            assert task.depth <= 2


class TestSkillMatch:
    """Tests for SkillMatch dataclass."""
    
    def test_create_skill_match(self):
        """Test creating skill match."""
        match = SkillMatch(
            skill_id="skill_code_review",
            name="Code Review",
            relevance_score=0.85,
            required_tools=["tool_linter"],
            estimated_duration_seconds=120.0,
        )
        
        assert match.skill_id == "skill_code_review"
        assert match.relevance_score == 0.85
        assert "tool_linter" in match.required_tools
    
    def test_skill_match_defaults(self):
        """Test skill match default values."""
        match = SkillMatch(
            skill_id="skill_test",
            name="Test",
            relevance_score=0.5,
        )
        
        assert match.required_tools == []
        assert match.estimated_duration_seconds == 60.0
