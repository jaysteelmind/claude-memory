"""Tests for the quality checker."""

import pytest

from dmm.reviewer.validators.quality import QualityChecker


@pytest.fixture
def checker() -> QualityChecker:
    """Create a quality checker."""
    return QualityChecker()


def make_content(body: str, tags: list | None = None) -> str:
    """Helper to create valid content with given body."""
    tag_list = tags or ["test"]
    return f"""---
id: mem_2025_01_11_001
tags: {tag_list}
scope: project
priority: 0.5
confidence: active
status: active
---

{body}
"""


class TestQualityCheckerTokenCount:
    """Tests for token count validation."""

    def test_token_count_within_range(self, checker: QualityChecker) -> None:
        """Test content with acceptable token count."""
        body = "# Test Memory\n\n" + "This is test content. " * 50
        content = make_content(body)
        
        issues = checker.check(content)
        token_errors = [i for i in issues if "token_count" in i.code and i.severity == "error"]
        assert len(token_errors) == 0

    def test_token_count_too_low(self, checker: QualityChecker) -> None:
        """Test content with too few tokens."""
        body = "# Short\n\nToo short."
        content = make_content(body)
        
        issues = checker.check(content)
        assert any(i.code == "token_count_low" for i in issues)

    def test_token_count_too_high(self, checker: QualityChecker) -> None:
        """Test content with too many tokens (warning level)."""
        body = "# Long Memory\n\n" + "This is very long content that exceeds the recommended maximum. " * 100
        content = make_content(body)
        
        issues = checker.check(content)
        assert any(i.code == "token_count_high" for i in issues)

    def test_token_count_hard_limit(self, checker: QualityChecker) -> None:
        """Test content exceeding hard limit."""
        body = "# Extremely Long\n\n" + "Content " * 3000
        content = make_content(body)
        
        issues = checker.check(content)
        assert any(i.code == "token_count_hard_limit" for i in issues)


class TestQualityCheckerSingleConcept:
    """Tests for single concept validation."""

    def test_single_h1_passes(self, checker: QualityChecker) -> None:
        """Test that single H1 passes."""
        body = """# Single Topic

This memory focuses on one topic.

## Details

More details here.
"""
        content = make_content(body)
        
        issues = checker.check(content)
        assert not any(i.code == "multiple_concepts" for i in issues)

    def test_multiple_h1_fails(self, checker: QualityChecker) -> None:
        """Test that multiple H1 headings are flagged."""
        body = """# First Topic

Content about first topic.

# Second Topic

Content about second topic.
"""
        content = make_content(body)
        
        issues = checker.check(content)
        assert any(i.code == "multiple_concepts" for i in issues)

    def test_too_many_sections_warning(self, checker: QualityChecker) -> None:
        """Test warning for too many H2 sections."""
        sections = "\n\n".join([f"## Section {i}\n\nContent for section {i}." for i in range(8)])
        body = f"# Main Topic\n\n{sections}"
        content = make_content(body)
        
        issues = checker.check(content)
        assert any(i.code == "too_many_sections" for i in issues)


class TestQualityCheckerTitleQuality:
    """Tests for title quality validation."""

    def test_good_title(self, checker: QualityChecker) -> None:
        """Test that good title passes."""
        body = """# Database Connection Configuration

Details about database configuration.
""" + "More content here. " * 30
        content = make_content(body)
        
        issues = checker.check(content)
        title_issues = [i for i in issues if "title" in i.code]
        assert len(title_issues) == 0

    def test_missing_title(self, checker: QualityChecker) -> None:
        """Test warning for missing title."""
        body = "Content without a heading.\n" * 20
        content = make_content(body)
        
        issues = checker.check(content)
        assert any(i.code == "missing_title" for i in issues)

    def test_title_too_short(self, checker: QualityChecker) -> None:
        """Test warning for short title."""
        body = "# Hi\n\n" + "Content here. " * 30
        content = make_content(body)
        
        issues = checker.check(content)
        assert any(i.code == "title_too_short" for i in issues)

    def test_vague_title(self, checker: QualityChecker) -> None:
        """Test warning for vague title."""
        body = "# Notes\n\n" + "Content here. " * 30
        content = make_content(body)
        
        issues = checker.check(content)
        assert any(i.code == "vague_title" for i in issues)


class TestQualityCheckerBodyQuality:
    """Tests for body quality validation."""

    def test_body_too_short(self, checker: QualityChecker) -> None:
        """Test warning for short body."""
        body = "# Title\n\nShort."
        content = make_content(body)
        
        issues = checker.check(content)
        assert any(i.code == "body_too_short" for i in issues)

    def test_missing_rationale_info(self, checker: QualityChecker) -> None:
        """Test info message for missing rationale."""
        body = """# Configuration Setting

Set the value to 42.
""" + "More content. " * 30
        content = make_content(body)
        
        issues = checker.check(content)
        rationale_issues = [i for i in issues if i.code == "missing_rationale"]
        assert len(rationale_issues) > 0
        assert rationale_issues[0].severity == "info"

    def test_has_rationale_section(self, checker: QualityChecker) -> None:
        """Test that rationale section is detected."""
        body = """# Configuration Setting

Set the value to 42.

## Rationale

We chose 42 because it is the answer to everything.
""" + "More content. " * 20
        content = make_content(body)
        
        issues = checker.check(content)
        assert not any(i.code == "missing_rationale" for i in issues)

    def test_has_inline_rationale(self, checker: QualityChecker) -> None:
        """Test that inline rationale is detected."""
        body = """# Configuration Setting

Set the value to 42 because it provides optimal performance.
""" + "More content. " * 30
        content = make_content(body)
        
        issues = checker.check(content)
        assert not any(i.code == "missing_rationale" for i in issues)


class TestQualityCheckerTagQuality:
    """Tests for tag quality validation."""

    def test_too_few_tags(self, checker: QualityChecker) -> None:
        """Test warning for too few tags."""
        body = "# Title\n\n" + "Content. " * 30
        content = f"""---
id: mem_2025_01_11_001
tags: []
scope: project
priority: 0.5
confidence: active
status: active
---

{body}
"""
        issues = checker.check(content)
        assert any(i.code == "too_few_tags" for i in issues)

    def test_too_many_tags(self, checker: QualityChecker) -> None:
        """Test warning for too many tags."""
        tags = [f"tag{i}" for i in range(15)]
        body = "# Title\n\n" + "Content. " * 30
        content = make_content(body, tags)
        
        issues = checker.check(content)
        assert any(i.code == "too_many_tags" for i in issues)

    def test_vague_tags(self, checker: QualityChecker) -> None:
        """Test info for vague tags."""
        body = "# Title\n\n" + "Content. " * 30
        content = make_content(body, ["misc", "stuff", "other"])
        
        issues = checker.check(content)
        vague_issues = [i for i in issues if i.code == "vague_tag"]
        assert len(vague_issues) >= 1

    def test_duplicate_tags(self, checker: QualityChecker) -> None:
        """Test warning for duplicate tags."""
        body = "# Title\n\n" + "Content. " * 30
        content = make_content(body, ["test", "example", "test"])
        
        issues = checker.check(content)
        assert any(i.code == "duplicate_tags" for i in issues)


class TestQualityCheckerCoherence:
    """Tests for coherence validation."""

    def test_coherent_title_and_tags(self, checker: QualityChecker) -> None:
        """Test that coherent title and tags pass."""
        body = """# Database Connection Pool Configuration

This memory documents the database connection pool settings.
""" + "More content. " * 30
        content = make_content(body, ["database", "connection", "pool", "configuration"])
        
        issues = checker.check(content)
        assert not any(i.code == "low_coherence" for i in issues)

    def test_incoherent_title_and_tags(self, checker: QualityChecker) -> None:
        """Test that incoherent title and tags are flagged."""
        body = """# Database Connection Pool Configuration

This memory documents the database connection pool settings.
""" + "More content. " * 30
        content = make_content(body, ["authentication", "security", "login"])
        
        issues = checker.check(content)
        coherence_issues = [i for i in issues if i.code == "low_coherence"]
        assert len(coherence_issues) > 0


class TestQualityCheckerTokenCounting:
    """Tests for token counting utility."""

    def test_count_tokens(self, checker: QualityChecker) -> None:
        """Test token counting."""
        text = "Hello world, this is a test."
        count = checker.count_tokens(text)
        assert count > 0
        assert count < 20

    def test_count_empty(self, checker: QualityChecker) -> None:
        """Test counting empty string."""
        count = checker.count_tokens("")
        assert count == 0


class TestQualityCheckerParseError:
    """Tests for handling parse errors."""

    def test_invalid_yaml_content(self, checker: QualityChecker) -> None:
        """Test handling of invalid YAML in frontmatter."""
        content = """---
id: test
tags: [unclosed bracket
scope: project
---

# Title

Body content.
"""
        issues = checker.check(content)
        assert any(i.code == "parse_error" for i in issues)

    def test_plain_text_content(self, checker: QualityChecker) -> None:
        """Test that plain text without frontmatter still gets checked."""
        content = "Not valid markdown frontmatter"
        
        # Plain text is parsed as body-only, so we get token count issues
        issues = checker.check(content)
        # Should have issues (likely token_count_low since body is short)
        assert len(issues) > 0
