"""Tests for CodeReviewAgent."""

import tempfile
from pathlib import Path

import pytest

from examples.agents.code_review_agent import (
    CodeReviewAgent,
    CodeReviewAgentConfig,
    CodeIssue,
    ReviewResult,
)


class TestCodeReviewAgent:
    """Tests for CodeReviewAgent."""

    def test_init_default_config(self) -> None:
        """Agent initializes with default config."""
        agent = CodeReviewAgent()
        assert agent.config.max_line_length == 100
        assert agent.config.max_function_lines == 50
        assert agent.config.check_docstrings is True

    def test_init_custom_config(self) -> None:
        """Agent initializes with custom config."""
        config = CodeReviewAgentConfig(
            max_line_length=80,
            max_function_lines=30,
            check_docstrings=False,
        )
        agent = CodeReviewAgent(config=config)
        assert agent.config.max_line_length == 80
        assert agent.config.check_docstrings is False

    def test_review_file_not_found(self) -> None:
        """Review raises error for missing file."""
        agent = CodeReviewAgent()
        with pytest.raises(FileNotFoundError):
            agent.review_file("/nonexistent/file.py")

    def test_review_file_syntax_error(self) -> None:
        """Review raises error for invalid syntax."""
        agent = CodeReviewAgent()
        
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write("def broken(\n")
            f.flush()
            
            with pytest.raises(SyntaxError):
                agent.review_file(f.name)

    def test_review_valid_file(self) -> None:
        """Review succeeds for valid Python file."""
        agent = CodeReviewAgent()
        
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write('''"""Module docstring."""

def hello(name: str) -> str:
    """Say hello."""
    return f"Hello, {name}!"

class Greeter:
    """A greeter class."""
    
    def greet(self, name: str) -> str:
        """Greet someone."""
        return hello(name)
''')
            f.flush()
            
            result = agent.review_file(f.name)
            
            assert isinstance(result, ReviewResult)
            assert result.file_path == f.name
            assert result.metrics["function_count"] == 2
            assert result.metrics["class_count"] == 1

    def test_review_detects_long_lines(self) -> None:
        """Review detects lines exceeding max length."""
        config = CodeReviewAgentConfig(max_line_length=50)
        agent = CodeReviewAgent(config=config)
        
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write('x = "This is a very long line that exceeds the maximum allowed length limit"\n')
            f.flush()
            
            result = agent.review_file(f.name)
            
            style_issues = [i for i in result.issues if i.category == "style"]
            assert any("exceeds" in i.message for i in style_issues)

    def test_review_detects_missing_docstring(self) -> None:
        """Review detects missing docstrings."""
        agent = CodeReviewAgent()
        
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write('def no_docstring():\n    pass\n')
            f.flush()
            
            result = agent.review_file(f.name)
            
            assert any("missing docstring" in i.message for i in result.issues)

    def test_review_detects_missing_type_hint(self) -> None:
        """Review detects missing return type hints."""
        agent = CodeReviewAgent()
        
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write('def no_return_type():\n    """Has docstring."""\n    pass\n')
            f.flush()
            
            result = agent.review_file(f.name)
            
            assert any("return type" in i.message for i in result.issues)

    def test_review_directory(self) -> None:
        """Review directory finds Python files."""
        agent = CodeReviewAgent()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            
            (path / "file1.py").write_text('"""Module."""\nx = 1\n')
            (path / "file2.py").write_text('"""Module."""\ny = 2\n')
            (path / "not_python.txt").write_text("text file\n")
            
            results = agent.review_directory(path, recursive=False)
            
            assert len(results) == 2

    def test_generate_report_markdown(self) -> None:
        """Generate report in markdown format."""
        agent = CodeReviewAgent()
        
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write('"""Module."""\nx = 1\n')
            f.flush()
            
            agent.review_file(f.name)
            report = agent.generate_report(format="markdown")
            
            assert "# Code Review Report" in report
            assert "## Summary" in report

    def test_generate_report_json(self) -> None:
        """Generate report in JSON format."""
        agent = CodeReviewAgent()
        
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write('"""Module."""\nx = 1\n')
            f.flush()
            
            agent.review_file(f.name)
            report = agent.generate_report(format="json")
            
            import json
            data = json.loads(report)
            assert isinstance(data, list)
            assert len(data) == 1

    def test_metrics_calculation(self) -> None:
        """Metrics are calculated correctly."""
        agent = CodeReviewAgent()
        
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write('''"""Module."""
# Comment line
import os

def func1():
    """Doc."""
    pass

def func2():
    """Doc."""
    if True:
        pass
''')
            f.flush()
            
            result = agent.review_file(f.name)
            
            assert result.metrics["function_count"] == 2
            assert result.metrics["import_count"] == 1
            assert result.metrics["comment_lines"] >= 1


class TestCodeIssue:
    """Tests for CodeIssue dataclass."""

    def test_create_issue(self) -> None:
        """Issue is created with all fields."""
        issue = CodeIssue(
            severity="warning",
            category="style",
            line=10,
            message="Test message",
            suggestion="Fix it",
        )
        
        assert issue.severity == "warning"
        assert issue.category == "style"
        assert issue.line == 10
        assert issue.message == "Test message"
        assert issue.suggestion == "Fix it"


class TestReviewResult:
    """Tests for ReviewResult dataclass."""

    def test_to_dict(self) -> None:
        """ReviewResult converts to dictionary."""
        from datetime import datetime, timezone
        
        result = ReviewResult(
            file_path="/test/file.py",
            reviewed_at=datetime.now(timezone.utc),
            metrics={"lines": 100},
            issues=[],
            summary="Test summary",
        )
        
        data = result.to_dict()
        
        assert data["file_path"] == "/test/file.py"
        assert "reviewed_at" in data
        assert data["metrics"] == {"lines": 100}
        assert data["summary"] == "Test summary"
