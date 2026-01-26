"""Unit tests for skill models."""

import pytest
from datetime import datetime

from dmm.agentos.skills.models import (
    PARAM_TYPES,
    SKILL_CATEGORIES,
    MemoryRequirement,
    Skill,
    SkillDependencies,
    SkillExample,
    SkillExecution,
    SkillInput,
    SkillOutput,
    ToolRequirements,
)


class TestSkillInput:
    """Tests for SkillInput dataclass."""

    def test_create_basic(self):
        """Test creating a basic skill input."""
        inp = SkillInput(name="code", param_type="string")
        assert inp.name == "code"
        assert inp.param_type == "string"
        assert inp.required is True
        assert inp.default is None

    def test_create_with_defaults(self):
        """Test creating input with default value."""
        inp = SkillInput(
            name="language",
            param_type="string",
            required=False,
            default="python",
            description="Programming language",
        )
        assert inp.required is False
        assert inp.default == "python"

    def test_to_dict(self):
        """Test serialization to dict."""
        inp = SkillInput(name="code", param_type="string", description="Source code")
        data = inp.to_dict()
        assert data["name"] == "code"
        assert data["type"] == "string"
        assert data["description"] == "Source code"

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {"name": "files", "type": "array", "required": True}
        inp = SkillInput.from_dict(data)
        assert inp.name == "files"
        assert inp.param_type == "array"

    def test_with_enum(self):
        """Test input with enum values."""
        inp = SkillInput(
            name="format",
            param_type="string",
            enum=["json", "text", "html"],
        )
        assert inp.enum == ["json", "text", "html"]


class TestSkillOutput:
    """Tests for SkillOutput dataclass."""

    def test_create_basic(self):
        """Test creating a basic skill output."""
        out = SkillOutput(name="result", param_type="string")
        assert out.name == "result"
        assert out.param_type == "string"

    def test_to_dict(self):
        """Test serialization to dict."""
        out = SkillOutput(name="issues", param_type="array", description="Found issues")
        data = out.to_dict()
        assert data["name"] == "issues"
        assert data["type"] == "array"

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {"name": "summary", "type": "string", "description": "Summary"}
        out = SkillOutput.from_dict(data)
        assert out.name == "summary"


class TestToolRequirements:
    """Tests for ToolRequirements dataclass."""

    def test_create_empty(self):
        """Test creating empty tool requirements."""
        reqs = ToolRequirements()
        assert reqs.required == []
        assert reqs.optional == []

    def test_create_with_tools(self):
        """Test creating with tool lists."""
        reqs = ToolRequirements(
            required=["tool_ruff"],
            optional=["tool_mypy"],
        )
        assert "tool_ruff" in reqs.required
        assert "tool_mypy" in reqs.optional


class TestSkillDependencies:
    """Tests for SkillDependencies dataclass."""

    def test_create_basic(self):
        """Test creating basic dependencies."""
        deps = SkillDependencies(
            skills=["skill_parse"],
            tools=ToolRequirements(required=["tool_ast"]),
        )
        assert "skill_parse" in deps.skills
        assert "tool_ast" in deps.tools.required

    def test_to_dict(self):
        """Test serialization."""
        deps = SkillDependencies(skills=["skill_a", "skill_b"])
        data = deps.to_dict()
        assert data["skills"] == ["skill_a", "skill_b"]


class TestMemoryRequirement:
    """Tests for MemoryRequirement dataclass."""

    def test_create_required(self):
        """Test creating required memory requirement."""
        req = MemoryRequirement(
            scope="project",
            tags=["standards"],
            description="Coding standards",
            required=True,
        )
        assert req.scope == "project"
        assert req.required is True

    def test_create_optional(self):
        """Test creating optional memory requirement."""
        req = MemoryRequirement(
            scope="user",
            tags=["preferences"],
            required=False,
        )
        assert req.required is False


class TestSkillExecution:
    """Tests for SkillExecution dataclass."""

    def test_defaults(self):
        """Test default execution config."""
        exec_config = SkillExecution()
        assert exec_config.timeout_seconds == 60
        assert exec_config.retry_count == 2
        assert exec_config.parallel_safe is True

    def test_custom_values(self):
        """Test custom execution config."""
        exec_config = SkillExecution(
            timeout_seconds=120,
            retry_count=3,
            parallel_safe=False,
        )
        assert exec_config.timeout_seconds == 120


class TestSkillExample:
    """Tests for SkillExample dataclass."""

    def test_create_example(self):
        """Test creating a skill example."""
        example = SkillExample(
            name="Basic test",
            input_data={"code": "print('hello')"},
            output_data={"issues": []},
        )
        assert example.name == "Basic test"
        assert "code" in example.input_data


class TestSkill:
    """Tests for Skill dataclass."""

    def test_create_minimal(self):
        """Test creating minimal skill."""
        skill = Skill(
            id="skill_test",
            name="Test Skill",
            version="1.0.0",
            description="A test skill",
            category="general",
        )
        assert skill.id == "skill_test"
        assert skill.enabled is True

    def test_create_full(self):
        """Test creating fully configured skill."""
        skill = Skill(
            id="skill_review",
            name="Code Review",
            version="1.0.0",
            description="Review code",
            category="quality",
            tags=["review", "quality"],
            inputs=[SkillInput(name="code", param_type="string")],
            outputs=[SkillOutput(name="issues", param_type="array")],
            dependencies=SkillDependencies(skills=["skill_parse"]),
        )
        assert len(skill.inputs) == 1
        assert len(skill.outputs) == 1
        assert "skill_parse" in skill.get_required_skill_ids()

    def test_invalid_category(self):
        """Test that invalid category raises error."""
        with pytest.raises(ValueError, match="Invalid category"):
            Skill(
                id="skill_test",
                name="Test",
                version="1.0.0",
                description="Test",
                category="invalid_category",
            )

    def test_to_dict(self):
        """Test serialization to dict."""
        skill = Skill(
            id="skill_test",
            name="Test",
            version="1.0.0",
            description="Test",
            category="general",
        )
        data = skill.to_dict()
        assert data["id"] == "skill_test"
        assert data["category"] == "general"

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "id": "skill_test",
            "name": "Test",
            "version": "1.0.0",
            "description": "Test skill",
            "category": "general",
            "tags": ["test"],
        }
        skill = Skill.from_dict(data)
        assert skill.id == "skill_test"
        assert "test" in skill.tags

    def test_to_json_schemas(self):
        """Test JSON schema generation."""
        skill = Skill(
            id="skill_test",
            name="Test",
            version="1.0.0",
            description="Test",
            category="general",
            inputs=[SkillInput(name="input1", param_type="string", required=True)],
            outputs=[SkillOutput(name="output1", param_type="string")],
        )
        inputs_schema, outputs_schema = skill.to_json_schemas()
        assert "input1" in inputs_schema
        assert "output1" in outputs_schema

    def test_validate_inputs_valid(self):
        """Test input validation with valid inputs."""
        skill = Skill(
            id="skill_test",
            name="Test",
            version="1.0.0",
            description="Test",
            category="general",
            inputs=[SkillInput(name="code", param_type="string", required=True)],
        )
        errors = skill.validate_inputs({"code": "print('hello')"})
        assert len(errors) == 0

    def test_validate_inputs_missing_required(self):
        """Test input validation with missing required field."""
        skill = Skill(
            id="skill_test",
            name="Test",
            version="1.0.0",
            description="Test",
            category="general",
            inputs=[SkillInput(name="code", param_type="string", required=True)],
        )
        errors = skill.validate_inputs({})
        assert len(errors) == 1
        assert "code" in errors[0]

    def test_get_tool_ids(self):
        """Test getting tool IDs from dependencies."""
        skill = Skill(
            id="skill_test",
            name="Test",
            version="1.0.0",
            description="Test",
            category="general",
            dependencies=SkillDependencies(
                tools=ToolRequirements(
                    required=["tool_a"],
                    optional=["tool_b"],
                )
            ),
        )
        assert skill.get_required_tool_ids() == ["tool_a"]
        assert skill.get_optional_tool_ids() == ["tool_b"]
        assert set(skill.get_all_tool_ids()) == {"tool_a", "tool_b"}


class TestConstants:
    """Tests for module constants."""

    def test_param_types(self):
        """Test PARAM_TYPES contains expected values."""
        assert "string" in PARAM_TYPES
        assert "array" in PARAM_TYPES
        assert "object" in PARAM_TYPES

    def test_skill_categories(self):
        """Test SKILL_CATEGORIES contains expected values."""
        assert "quality" in SKILL_CATEGORIES
        assert "generation" in SKILL_CATEGORIES
        assert "general" in SKILL_CATEGORIES
