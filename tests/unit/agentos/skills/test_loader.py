"""Unit tests for skill loader."""

import pytest
from pathlib import Path
import tempfile

from dmm.agentos.skills.loader import (
    SkillLoader,
    SkillLoadError,
    SkillValidationError,
)


class TestSkillLoader:
    """Tests for SkillLoader class."""

    def test_parse_minimal_yaml(self):
        """Test parsing minimal valid YAML."""
        loader = SkillLoader()
        content = """
id: skill_test
name: Test Skill
description: A test skill
category: general
"""
        skill = loader.parse(content)
        assert skill.id == "skill_test"
        assert skill.name == "Test Skill"
        assert skill.category == "general"

    def test_parse_with_inputs_outputs(self):
        """Test parsing skill with inputs and outputs."""
        loader = SkillLoader()
        content = """
id: skill_test
name: Test Skill
description: A test skill
category: general
inputs:
  - name: code
    type: string
    required: true
outputs:
  - name: result
    type: string
"""
        skill = loader.parse(content)
        assert len(skill.inputs) == 1
        assert skill.inputs[0].name == "code"
        assert len(skill.outputs) == 1

    def test_parse_with_dependencies(self):
        """Test parsing skill with dependencies."""
        loader = SkillLoader()
        content = """
id: skill_test
name: Test Skill
description: A test skill
category: general
dependencies:
  skills:
    - skill_parse
  tools:
    required:
      - tool_ruff
    optional:
      - tool_mypy
"""
        skill = loader.parse(content)
        assert "skill_parse" in skill.dependencies.skills
        assert "tool_ruff" in skill.dependencies.tools.required
        assert "tool_mypy" in skill.dependencies.tools.optional

    def test_parse_with_memory_requirements(self):
        """Test parsing skill with memory requirements."""
        loader = SkillLoader()
        content = """
id: skill_test
name: Test Skill
description: A test skill
category: general
memory_requirements:
  required:
    - scope: project
      tags:
        - standards
      description: Coding standards
  optional:
    - scope: user
      tags:
        - preferences
"""
        skill = loader.parse(content)
        assert len(skill.memory_requirements) == 2
        required = [m for m in skill.memory_requirements if m.required]
        assert len(required) == 1
        assert required[0].scope == "project"

    def test_parse_with_execution_config(self):
        """Test parsing skill with execution config."""
        loader = SkillLoader()
        content = """
id: skill_test
name: Test Skill
description: A test skill
category: general
execution:
  timeout_seconds: 120
  retry_count: 3
  parallel_safe: false
"""
        skill = loader.parse(content)
        assert skill.execution.timeout_seconds == 120
        assert skill.execution.retry_count == 3
        assert skill.execution.parallel_safe is False

    def test_parse_with_examples(self):
        """Test parsing skill with examples."""
        loader = SkillLoader()
        content = """
id: skill_test
name: Test Skill
description: A test skill
category: general
examples:
  - name: Basic example
    input:
      code: "print('hello')"
    output:
      result: "success"
"""
        skill = loader.parse(content)
        assert len(skill.examples) == 1
        assert skill.examples[0].name == "Basic example"

    def test_parse_with_frontmatter(self):
        """Test parsing YAML with frontmatter markers."""
        loader = SkillLoader()
        content = """---
id: skill_test
name: Test Skill
description: A test skill
category: general
---

# Extended Documentation

This is markdown content.
"""
        skill = loader.parse(content)
        assert skill.id == "skill_test"
        assert "Extended Documentation" in skill.markdown_content

    def test_parse_missing_id(self):
        """Test that missing ID raises error."""
        loader = SkillLoader()
        content = """
name: Test Skill
description: A test skill
category: general
"""
        with pytest.raises(SkillLoadError, match="Missing required field: id"):
            loader.parse(content)

    def test_parse_invalid_id_prefix(self):
        """Test that invalid ID prefix raises error in strict mode."""
        loader = SkillLoader(strict=True)
        content = """
id: test_skill
name: Test Skill
description: A test skill
category: general
"""
        with pytest.raises(SkillValidationError, match="must start with 'skill_'"):
            loader.parse(content)

    def test_parse_invalid_yaml(self):
        """Test that invalid YAML raises error."""
        loader = SkillLoader()
        content = """
id: skill_test
name: [invalid yaml
"""
        with pytest.raises(SkillLoadError, match="Invalid YAML"):
            loader.parse(content)

    def test_parse_invalid_category_fallback(self):
        """Test that invalid category falls back to general."""
        loader = SkillLoader()
        content = """
id: skill_test
name: Test Skill
description: A test skill
category: invalid_category
"""
        skill = loader.parse(content)
        assert skill.category == "general"

    def test_load_file(self):
        """Test loading skill from file."""
        loader = SkillLoader()
        content = """
id: skill_test
name: Test Skill
description: A test skill
category: general
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".skill.yaml", delete=False
        ) as f:
            f.write(content)
            f.flush()
            path = Path(f.name)

        try:
            skill = loader.load(path)
            assert skill.id == "skill_test"
            assert skill.file_path == str(path)
        finally:
            path.unlink()

    def test_load_file_not_found(self):
        """Test loading non-existent file raises error."""
        loader = SkillLoader()
        with pytest.raises(SkillLoadError, match="File not found"):
            loader.load(Path("/nonexistent/skill.skill.yaml"))

    def test_load_directory(self):
        """Test loading skills from directory."""
        loader = SkillLoader()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            # Create two skill files
            skill1 = tmppath / "skill1.skill.yaml"
            skill1.write_text("""
id: skill_one
name: Skill One
description: First skill
category: general
""")
            
            skill2 = tmppath / "skill2.skill.yaml"
            skill2.write_text("""
id: skill_two
name: Skill Two
description: Second skill
category: quality
""")
            
            skills = loader.load_directory(tmppath)
            assert len(skills) == 2
            ids = {s.id for s in skills}
            assert "skill_one" in ids
            assert "skill_two" in ids

    def test_load_directory_skips_invalid(self):
        """Test that invalid files are skipped in non-strict mode."""
        loader = SkillLoader(strict=False)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            # Valid skill
            valid = tmppath / "valid.skill.yaml"
            valid.write_text("""
id: skill_valid
name: Valid Skill
description: A valid skill
category: general
""")
            
            # Invalid skill (missing required fields)
            invalid = tmppath / "invalid.skill.yaml"
            invalid.write_text("""
name: Invalid Skill
""")
            
            skills = loader.load_directory(tmppath)
            assert len(skills) == 1
            assert skills[0].id == "skill_valid"

    def test_load_directory_empty(self):
        """Test loading from empty directory."""
        loader = SkillLoader()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skills = loader.load_directory(Path(tmpdir))
            assert len(skills) == 0

    def test_load_directory_nonexistent(self):
        """Test loading from non-existent directory."""
        loader = SkillLoader()
        skills = loader.load_directory(Path("/nonexistent/directory"))
        assert len(skills) == 0

    def test_parse_timestamps(self):
        """Test parsing timestamps."""
        loader = SkillLoader()
        content = """
id: skill_test
name: Test Skill
description: A test skill
category: general
created: "2024-01-15T10:30:00Z"
updated: "2024-06-20T14:45:00Z"
"""
        skill = loader.parse(content)
        assert skill.created is not None
        assert skill.updated is not None
        assert skill.created.year == 2024
        assert skill.created.month == 1

    def test_strict_mode_raises_on_invalid(self):
        """Test strict mode raises on validation errors."""
        loader = SkillLoader(strict=True)
        # Invalid: ID doesn't start with skill_
        content = """
id: invalid_id
name: Test Skill
description: A test skill
category: general
"""
        with pytest.raises(SkillValidationError):
            loader.parse(content)
