"""Code Review Agent - Analyzes code and provides improvement suggestions.

This agent demonstrates:
- Using the CodeAnalyzer from selfmod module
- Generating structured reports
- Creating modification proposals
- Integration with DMM memory system
"""

import ast
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class CodeIssue:
    """Represents a code issue found during review."""
    
    severity: str  # critical, warning, info
    category: str  # complexity, style, security, performance
    line: int
    message: str
    suggestion: str | None = None


@dataclass
class ReviewResult:
    """Result of a code review."""
    
    file_path: str
    reviewed_at: datetime
    metrics: dict[str, Any]
    issues: list[CodeIssue]
    summary: str
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file_path": self.file_path,
            "reviewed_at": self.reviewed_at.isoformat(),
            "metrics": self.metrics,
            "issues": [
                {
                    "severity": i.severity,
                    "category": i.category,
                    "line": i.line,
                    "message": i.message,
                    "suggestion": i.suggestion,
                }
                for i in self.issues
            ],
            "summary": self.summary,
        }


@dataclass
class CodeReviewAgentConfig:
    """Configuration for CodeReviewAgent."""
    
    max_line_length: int = 100
    max_function_lines: int = 50
    max_complexity: int = 10
    check_docstrings: bool = True
    check_type_hints: bool = True


class CodeReviewAgent:
    """Agent that reviews Python code for quality and best practices.
    
    This agent analyzes Python source files to:
    - Calculate complexity metrics
    - Identify potential issues
    - Suggest improvements
    - Generate review reports
    
    Example:
        agent = CodeReviewAgent()
        result = agent.review_file("src/module.py")
        print(result.summary)
    """
    
    def __init__(self, config: CodeReviewAgentConfig | None = None) -> None:
        """Initialize the agent.
        
        Args:
            config: Optional configuration. Uses defaults if not provided.
        """
        self.config = config or CodeReviewAgentConfig()
        self._reviews: list[ReviewResult] = []
    
    def review_file(self, file_path: str | Path) -> ReviewResult:
        """Review a Python file.
        
        Args:
            file_path: Path to the Python file to review.
            
        Returns:
            ReviewResult with metrics, issues, and summary.
            
        Raises:
            FileNotFoundError: If file does not exist.
            SyntaxError: If file has invalid Python syntax.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        content = path.read_text()
        
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            raise SyntaxError(f"Invalid Python syntax in {file_path}: {e}")
        
        metrics = self._calculate_metrics(content, tree)
        issues = self._find_issues(content, tree)
        summary = self._generate_summary(path.name, metrics, issues)
        
        result = ReviewResult(
            file_path=str(path),
            reviewed_at=datetime.now(timezone.utc),
            metrics=metrics,
            issues=issues,
            summary=summary,
        )
        
        self._reviews.append(result)
        return result
    
    def review_directory(
        self,
        directory: str | Path,
        recursive: bool = True,
    ) -> list[ReviewResult]:
        """Review all Python files in a directory.
        
        Args:
            directory: Path to directory.
            recursive: Whether to search subdirectories.
            
        Returns:
            List of ReviewResults for each file.
        """
        path = Path(directory)
        pattern = "**/*.py" if recursive else "*.py"
        
        results = []
        for py_file in path.glob(pattern):
            if "__pycache__" in str(py_file):
                continue
            try:
                result = self.review_file(py_file)
                results.append(result)
            except (SyntaxError, UnicodeDecodeError):
                continue
        
        return results
    
    def generate_report(
        self,
        results: list[ReviewResult] | None = None,
        format: str = "markdown",
    ) -> str:
        """Generate a review report.
        
        Args:
            results: Results to include. Uses all reviews if not provided.
            format: Output format (markdown, json, text).
            
        Returns:
            Formatted report string.
        """
        results = results or self._reviews
        
        if format == "json":
            return json.dumps(
                [r.to_dict() for r in results],
                indent=2,
            )
        elif format == "markdown":
            return self._format_markdown_report(results)
        else:
            return self._format_text_report(results)
    
    def _calculate_metrics(
        self,
        content: str,
        tree: ast.AST,
    ) -> dict[str, Any]:
        """Calculate code metrics."""
        lines = content.splitlines()
        
        # Basic metrics
        total_lines = len(lines)
        code_lines = sum(1 for line in lines if line.strip() and not line.strip().startswith("#"))
        comment_lines = sum(1 for line in lines if line.strip().startswith("#"))
        blank_lines = sum(1 for line in lines if not line.strip())
        
        # AST-based metrics
        functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
        
        # Complexity (simplified cyclomatic)
        complexity = self._calculate_complexity(tree)
        
        return {
            "total_lines": total_lines,
            "code_lines": code_lines,
            "comment_lines": comment_lines,
            "blank_lines": blank_lines,
            "function_count": len(functions),
            "class_count": len(classes),
            "import_count": len(imports),
            "avg_complexity": complexity / max(len(functions), 1),
            "total_complexity": complexity,
        }
    
    def _calculate_complexity(self, tree: ast.AST) -> int:
        """Calculate cyclomatic complexity."""
        complexity = 1
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                complexity += len(node.values) - 1
            elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                complexity += 1
        
        return complexity
    
    def _find_issues(
        self,
        content: str,
        tree: ast.AST,
    ) -> list[CodeIssue]:
        """Find code issues."""
        issues = []
        lines = content.splitlines()
        
        # Check line lengths
        for i, line in enumerate(lines, 1):
            if len(line) > self.config.max_line_length:
                issues.append(CodeIssue(
                    severity="warning",
                    category="style",
                    line=i,
                    message=f"Line exceeds {self.config.max_line_length} characters ({len(line)})",
                    suggestion=f"Consider breaking this line into multiple lines",
                ))
        
        # Check functions
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                issues.extend(self._check_function(node, lines))
            elif isinstance(node, ast.ClassDef):
                issues.extend(self._check_class(node))
        
        return issues
    
    def _check_function(
        self,
        node: ast.FunctionDef,
        lines: list[str],
    ) -> list[CodeIssue]:
        """Check a function for issues."""
        issues = []
        
        # Check function length
        func_lines = node.end_lineno - node.lineno + 1 if node.end_lineno else 0
        if func_lines > self.config.max_function_lines:
            issues.append(CodeIssue(
                severity="warning",
                category="complexity",
                line=node.lineno,
                message=f"Function '{node.name}' is too long ({func_lines} lines)",
                suggestion="Consider breaking into smaller functions",
            ))
        
        # Check docstring
        if self.config.check_docstrings:
            if not ast.get_docstring(node):
                issues.append(CodeIssue(
                    severity="info",
                    category="style",
                    line=node.lineno,
                    message=f"Function '{node.name}' missing docstring",
                    suggestion="Add a docstring describing the function",
                ))
        
        # Check type hints
        if self.config.check_type_hints:
            if not node.returns and node.name != "__init__":
                issues.append(CodeIssue(
                    severity="info",
                    category="style",
                    line=node.lineno,
                    message=f"Function '{node.name}' missing return type hint",
                    suggestion="Add return type annotation",
                ))
        
        return issues
    
    def _check_class(self, node: ast.ClassDef) -> list[CodeIssue]:
        """Check a class for issues."""
        issues = []
        
        # Check docstring
        if self.config.check_docstrings:
            if not ast.get_docstring(node):
                issues.append(CodeIssue(
                    severity="info",
                    category="style",
                    line=node.lineno,
                    message=f"Class '{node.name}' missing docstring",
                    suggestion="Add a docstring describing the class",
                ))
        
        return issues
    
    def _generate_summary(
        self,
        filename: str,
        metrics: dict[str, Any],
        issues: list[CodeIssue],
    ) -> str:
        """Generate a summary of the review."""
        critical = sum(1 for i in issues if i.severity == "critical")
        warnings = sum(1 for i in issues if i.severity == "warning")
        info = sum(1 for i in issues if i.severity == "info")
        
        status = "PASS"
        if critical > 0:
            status = "FAIL"
        elif warnings > 3:
            status = "NEEDS ATTENTION"
        
        return (
            f"Review of {filename}: {status}\n"
            f"Lines: {metrics['total_lines']} total, {metrics['code_lines']} code\n"
            f"Structure: {metrics['function_count']} functions, {metrics['class_count']} classes\n"
            f"Issues: {critical} critical, {warnings} warnings, {info} info"
        )
    
    def _format_markdown_report(self, results: list[ReviewResult]) -> str:
        """Format results as markdown."""
        lines = [
            "# Code Review Report",
            "",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            f"Files reviewed: {len(results)}",
            "",
        ]
        
        # Summary table
        lines.extend([
            "## Summary",
            "",
            "| File | Lines | Functions | Issues | Status |",
            "|------|-------|-----------|--------|--------|",
        ])
        
        for r in results:
            critical = sum(1 for i in r.issues if i.severity == "critical")
            status = "FAIL" if critical > 0 else "PASS"
            lines.append(
                f"| {Path(r.file_path).name} | "
                f"{r.metrics['total_lines']} | "
                f"{r.metrics['function_count']} | "
                f"{len(r.issues)} | "
                f"{status} |"
            )
        
        lines.append("")
        
        # Detailed issues
        lines.extend(["## Issues", ""])
        
        for r in results:
            if r.issues:
                lines.extend([f"### {Path(r.file_path).name}", ""])
                for issue in r.issues:
                    lines.append(
                        f"- **[{issue.severity.upper()}]** Line {issue.line}: "
                        f"{issue.message}"
                    )
                    if issue.suggestion:
                        lines.append(f"  - Suggestion: {issue.suggestion}")
                lines.append("")
        
        return "\n".join(lines)
    
    def _format_text_report(self, results: list[ReviewResult]) -> str:
        """Format results as plain text."""
        lines = []
        
        for r in results:
            lines.append(r.summary)
            lines.append("-" * 40)
        
        return "\n".join(lines)
