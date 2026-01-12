"""Tests for the schema validator."""

import pytest

from dmm.reviewer.validators.schema import SchemaValidator


@pytest.fixture
def validator() -> SchemaValidator:
    """Create a schema validator."""
    return SchemaValidator()


class TestSchemaValidatorBasics:
    """Tests for basic schema validation."""

    def test_valid_content(self, validator: SchemaValidator) -> None:
        """Test validation of valid content."""
        content = """---
id: mem_2025_01_11_001
tags: [test, example]
scope: project
priority: 0.8
confidence: active
status: active
---

# Test Memory

This is valid test content.
"""
        issues = validator.validate(content)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_empty_content(self, validator: SchemaValidator) -> None:
        """Test validation of empty content."""
        issues = validator.validate("")
        assert len(issues) > 0
        assert any(i.code == "empty_content" for i in issues)

    def test_missing_frontmatter(self, validator: SchemaValidator) -> None:
        """Test validation without frontmatter."""
        content = "# Just a title\n\nNo frontmatter here."
        issues = validator.validate(content)
        assert any(i.code == "missing_frontmatter" for i in issues)

    def test_invalid_yaml(self, validator: SchemaValidator) -> None:
        """Test validation with invalid YAML."""
        content = """---
id: test
tags: [unclosed
---

# Title
"""
        issues = validator.validate(content)
        assert any(i.code == "invalid_yaml" for i in issues)


class TestSchemaValidatorRequiredFields:
    """Tests for required field validation."""

    def test_missing_required_fields(self, validator: SchemaValidator) -> None:
        """Test detection of missing required fields."""
        content = """---
id: mem_2025_01_11_001
tags: [test]
---

# Title

Body content.
"""
        issues = validator.validate(content)
        assert any(i.code == "missing_required_fields" for i in issues)

    def test_all_required_fields_present(self, validator: SchemaValidator) -> None:
        """Test that all required fields pass validation."""
        content = """---
id: mem_2025_01_11_001
tags: [test]
scope: project
priority: 0.5
confidence: active
status: active
---

# Title

Body content.
"""
        issues = validator.validate(content)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0


class TestSchemaValidatorFieldTypes:
    """Tests for field type validation."""

    def test_invalid_id_type(self, validator: SchemaValidator) -> None:
        """Test validation of non-string id."""
        content = """---
id: 12345
tags: [test]
scope: project
priority: 0.5
confidence: active
status: active
---

# Title

Body.
"""
        issues = validator.validate(content)
        assert any(i.code == "invalid_type" and i.field == "id" for i in issues)

    def test_invalid_tags_type(self, validator: SchemaValidator) -> None:
        """Test validation of non-list tags."""
        content = """---
id: mem_2025_01_11_001
tags: "not a list"
scope: project
priority: 0.5
confidence: active
status: active
---

# Title

Body.
"""
        issues = validator.validate(content)
        assert any(i.code == "invalid_type" and i.field == "tags" for i in issues)

    def test_invalid_priority_type(self, validator: SchemaValidator) -> None:
        """Test validation of non-numeric priority."""
        content = """---
id: mem_2025_01_11_001
tags: [test]
scope: project
priority: "high"
confidence: active
status: active
---

# Title

Body.
"""
        issues = validator.validate(content)
        assert any(i.code == "invalid_type" and i.field == "priority" for i in issues)


class TestSchemaValidatorEnumValues:
    """Tests for enum value validation."""

    def test_invalid_scope(self, validator: SchemaValidator) -> None:
        """Test validation of invalid scope."""
        content = """---
id: mem_2025_01_11_001
tags: [test]
scope: invalid_scope
priority: 0.5
confidence: active
status: active
---

# Title

Body.
"""
        issues = validator.validate(content)
        assert any(i.code == "invalid_enum" and i.field == "scope" for i in issues)

    def test_invalid_confidence(self, validator: SchemaValidator) -> None:
        """Test validation of invalid confidence."""
        content = """---
id: mem_2025_01_11_001
tags: [test]
scope: project
priority: 0.5
confidence: very_confident
status: active
---

# Title

Body.
"""
        issues = validator.validate(content)
        assert any(i.code == "invalid_enum" and i.field == "confidence" for i in issues)

    def test_invalid_status(self, validator: SchemaValidator) -> None:
        """Test validation of invalid status."""
        content = """---
id: mem_2025_01_11_001
tags: [test]
scope: project
priority: 0.5
confidence: active
status: archived
---

# Title

Body.
"""
        issues = validator.validate(content)
        assert any(i.code == "invalid_enum" and i.field == "status" for i in issues)

    def test_valid_all_scopes(self, validator: SchemaValidator) -> None:
        """Test that all valid scopes pass."""
        valid_scopes = ["baseline", "global", "agent", "project", "ephemeral"]
        
        for scope in valid_scopes:
            content = f"""---
id: mem_2025_01_11_001
tags: [test]
scope: {scope}
priority: 0.5
confidence: active
status: active
---

# Title

Body.
"""
            issues = validator.validate(content)
            scope_errors = [i for i in issues if i.field == "scope" and i.severity == "error"]
            assert len(scope_errors) == 0, f"Scope '{scope}' should be valid"


class TestSchemaValidatorPriority:
    """Tests for priority validation."""

    def test_priority_out_of_range_high(self, validator: SchemaValidator) -> None:
        """Test validation of priority > 1.0."""
        content = """---
id: mem_2025_01_11_001
tags: [test]
scope: project
priority: 1.5
confidence: active
status: active
---

# Title

Body.
"""
        issues = validator.validate(content)
        assert any(i.code == "out_of_range" and i.field == "priority" for i in issues)

    def test_priority_out_of_range_low(self, validator: SchemaValidator) -> None:
        """Test validation of priority < 0.0."""
        content = """---
id: mem_2025_01_11_001
tags: [test]
scope: project
priority: -0.5
confidence: active
status: active
---

# Title

Body.
"""
        issues = validator.validate(content)
        assert any(i.code == "out_of_range" and i.field == "priority" for i in issues)

    def test_priority_boundary_values(self, validator: SchemaValidator) -> None:
        """Test that boundary priority values are valid."""
        for priority in [0.0, 0.5, 1.0]:
            content = f"""---
id: mem_2025_01_11_001
tags: [test]
scope: project
priority: {priority}
confidence: active
status: active
---

# Title

Body.
"""
            issues = validator.validate(content)
            priority_errors = [i for i in issues if i.field == "priority" and i.code == "out_of_range"]
            assert len(priority_errors) == 0


class TestSchemaValidatorWarnings:
    """Tests for warning-level validations."""

    def test_id_format_warning(self, validator: SchemaValidator) -> None:
        """Test warning for non-standard ID format."""
        content = """---
id: custom_id_format
tags: [test]
scope: project
priority: 0.5
confidence: active
status: active
---

# Title

Body.
"""
        issues = validator.validate(content)
        assert any(i.code == "invalid_format" and i.severity == "warning" for i in issues)

    def test_empty_tags_warning(self, validator: SchemaValidator) -> None:
        """Test warning for empty tags list."""
        content = """---
id: mem_2025_01_11_001
tags: []
scope: project
priority: 0.5
confidence: active
status: active
---

# Title

Body.
"""
        issues = validator.validate(content)
        assert any(i.code == "empty_tags" for i in issues)

    def test_ephemeral_without_expires(self, validator: SchemaValidator) -> None:
        """Test warning for ephemeral scope without expires."""
        content = """---
id: mem_2025_01_11_001
tags: [test]
scope: ephemeral
priority: 0.5
confidence: active
status: active
---

# Title

Body.
"""
        issues = validator.validate(content)
        assert any(i.code == "missing_expires" for i in issues)

    def test_status_mismatch(self, validator: SchemaValidator) -> None:
        """Test warning for deprecated confidence with active status."""
        content = """---
id: mem_2025_01_11_001
tags: [test]
scope: project
priority: 0.5
confidence: deprecated
status: active
---

# Title

Body.
"""
        issues = validator.validate(content)
        assert any(i.code == "status_mismatch" for i in issues)


class TestSchemaValidatorBody:
    """Tests for body validation."""

    def test_empty_body(self, validator: SchemaValidator) -> None:
        """Test validation of empty body."""
        content = """---
id: mem_2025_01_11_001
tags: [test]
scope: project
priority: 0.5
confidence: active
status: active
---
"""
        issues = validator.validate(content)
        assert any(i.code == "empty_body" for i in issues)

    def test_missing_title(self, validator: SchemaValidator) -> None:
        """Test warning for missing H1 title."""
        content = """---
id: mem_2025_01_11_001
tags: [test]
scope: project
priority: 0.5
confidence: active
status: active
---

This is content without a title heading.
"""
        issues = validator.validate(content)
        assert any(i.code == "missing_title" for i in issues)


class TestSchemaValidatorExtractMetadata:
    """Tests for metadata extraction."""

    def test_extract_metadata(self, validator: SchemaValidator) -> None:
        """Test extracting metadata from content."""
        content = """---
id: mem_2025_01_11_001
tags: [test, example]
scope: project
priority: 0.8
confidence: active
status: active
custom_field: custom_value
---

# Title

Body.
"""
        metadata = validator.extract_metadata(content)
        assert metadata is not None
        assert metadata["id"] == "mem_2025_01_11_001"
        assert metadata["scope"] == "project"
        assert metadata["custom_field"] == "custom_value"

    def test_extract_metadata_invalid(self, validator: SchemaValidator) -> None:
        """Test extracting metadata from invalid content."""
        content = "No frontmatter here"
        metadata = validator.extract_metadata(content)
        assert metadata is None
