"""
Code analyzer for self-modification framework.

This module provides capabilities for analyzing Python code including:
- AST parsing and traversal
- Code structure extraction
- Pattern identification
- Quality metrics
- Dependency analysis
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from pathlib import Path
from enum import Enum
import ast
import re


# =============================================================================
# Analysis Types
# =============================================================================

class CodeElementType(str, Enum):
    """Types of code elements."""
    
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    PROPERTY = "property"
    VARIABLE = "variable"
    CONSTANT = "constant"
    IMPORT = "import"
    DECORATOR = "decorator"


class ComplexityLevel(str, Enum):
    """Complexity levels."""
    
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


# =============================================================================
# Code Elements
# =============================================================================

@dataclass
class CodeLocation:
    """Location in source code."""
    
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    col_start: int = 0
    col_end: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "col_start": self.col_start,
            "col_end": self.col_end,
        }


@dataclass
class CodeElement:
    """A code element (function, class, etc.)."""
    
    name: str
    element_type: CodeElementType
    location: CodeLocation = field(default_factory=CodeLocation)
    docstring: str = ""
    decorators: list[str] = field(default_factory=list)
    parent: Optional[str] = None
    children: list[str] = field(default_factory=list)
    parameters: list[dict[str, Any]] = field(default_factory=list)
    return_type: Optional[str] = None
    bases: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "element_type": self.element_type.value,
            "location": self.location.to_dict(),
            "docstring": self.docstring[:200] if self.docstring else "",
            "decorators": self.decorators,
            "parent": self.parent,
            "children": self.children,
            "parameters": self.parameters,
            "return_type": self.return_type,
            "bases": self.bases,
        }


@dataclass
class ImportInfo:
    """Information about an import."""
    
    module: str
    names: list[str] = field(default_factory=list)
    alias: Optional[str] = None
    is_from_import: bool = False
    level: int = 0  # For relative imports
    location: CodeLocation = field(default_factory=CodeLocation)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "names": self.names,
            "alias": self.alias,
            "is_from_import": self.is_from_import,
            "level": self.level,
        }


# =============================================================================
# Analysis Results
# =============================================================================

@dataclass
class ComplexityMetrics:
    """Code complexity metrics."""
    
    cyclomatic_complexity: int = 0
    cognitive_complexity: int = 0
    lines_of_code: int = 0
    lines_of_comments: int = 0
    blank_lines: int = 0
    num_functions: int = 0
    num_classes: int = 0
    num_methods: int = 0
    max_nesting_depth: int = 0
    avg_function_length: float = 0.0
    
    @property
    def complexity_level(self) -> ComplexityLevel:
        """Get overall complexity level."""
        if self.cyclomatic_complexity <= 5:
            return ComplexityLevel.LOW
        elif self.cyclomatic_complexity <= 10:
            return ComplexityLevel.MEDIUM
        elif self.cyclomatic_complexity <= 20:
            return ComplexityLevel.HIGH
        return ComplexityLevel.VERY_HIGH
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "cyclomatic_complexity": self.cyclomatic_complexity,
            "cognitive_complexity": self.cognitive_complexity,
            "lines_of_code": self.lines_of_code,
            "lines_of_comments": self.lines_of_comments,
            "blank_lines": self.blank_lines,
            "num_functions": self.num_functions,
            "num_classes": self.num_classes,
            "num_methods": self.num_methods,
            "max_nesting_depth": self.max_nesting_depth,
            "avg_function_length": self.avg_function_length,
            "complexity_level": self.complexity_level.value,
        }


@dataclass
class CodeIssue:
    """A code quality issue."""
    
    code: str
    message: str
    severity: str = "warning"  # info, warning, error
    location: CodeLocation = field(default_factory=CodeLocation)
    suggestion: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "location": self.location.to_dict(),
            "suggestion": self.suggestion,
        }


@dataclass
class AnalysisResult:
    """Complete analysis result for a code unit."""
    
    file_path: str = ""
    module_name: str = ""
    elements: list[CodeElement] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    metrics: ComplexityMetrics = field(default_factory=ComplexityMetrics)
    issues: list[CodeIssue] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    analyzed_at: datetime = field(default_factory=datetime.utcnow)
    success: bool = True
    error: Optional[str] = None
    
    def get_element(self, name: str) -> Optional[CodeElement]:
        """Get element by name."""
        for elem in self.elements:
            if elem.name == name:
                return elem
        return None
    
    def get_elements_by_type(self, element_type: CodeElementType) -> list[CodeElement]:
        """Get elements by type."""
        return [e for e in self.elements if e.element_type == element_type]
    
    def get_classes(self) -> list[CodeElement]:
        """Get all classes."""
        return self.get_elements_by_type(CodeElementType.CLASS)
    
    def get_functions(self) -> list[CodeElement]:
        """Get all functions."""
        return self.get_elements_by_type(CodeElementType.FUNCTION)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "module_name": self.module_name,
            "elements": [e.to_dict() for e in self.elements],
            "imports": [i.to_dict() for i in self.imports],
            "metrics": self.metrics.to_dict(),
            "issues": [i.to_dict() for i in self.issues],
            "dependencies": self.dependencies,
            "analyzed_at": self.analyzed_at.isoformat(),
            "success": self.success,
            "error": self.error,
        }


# =============================================================================
# AST Visitor
# =============================================================================

class CodeVisitor(ast.NodeVisitor):
    """AST visitor for code analysis."""
    
    def __init__(self, file_path: str = "") -> None:
        self.file_path = file_path
        self.elements: list[CodeElement] = []
        self.imports: list[ImportInfo] = []
        self.current_class: Optional[str] = None
        self._nesting_depth = 0
        self._max_nesting = 0
        self._function_lengths: list[int] = []
    
    def _get_location(self, node: ast.AST) -> CodeLocation:
        """Get location from AST node."""
        return CodeLocation(
            file_path=self.file_path,
            line_start=getattr(node, 'lineno', 0),
            line_end=getattr(node, 'end_lineno', 0) or getattr(node, 'lineno', 0),
            col_start=getattr(node, 'col_offset', 0),
            col_end=getattr(node, 'end_col_offset', 0),
        )
    
    def _get_docstring(self, node: ast.AST) -> str:
        """Extract docstring from node."""
        return ast.get_docstring(node) or ""
    
    def _get_decorators(self, node: ast.AST) -> list[str]:
        """Extract decorator names."""
        decorators = []
        for dec in getattr(node, 'decorator_list', []):
            if isinstance(dec, ast.Name):
                decorators.append(dec.id)
            elif isinstance(dec, ast.Attribute):
                decorators.append(f"{self._get_attr_chain(dec)}")
            elif isinstance(dec, ast.Call):
                if isinstance(dec.func, ast.Name):
                    decorators.append(dec.func.id)
                elif isinstance(dec.func, ast.Attribute):
                    decorators.append(self._get_attr_chain(dec.func))
        return decorators
    
    def _get_attr_chain(self, node: ast.Attribute) -> str:
        """Get full attribute chain."""
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
    
    def _get_annotation(self, node: Optional[ast.AST]) -> Optional[str]:
        """Get type annotation as string."""
        if node is None:
            return None
        return ast.unparse(node)
    
    def _get_parameters(self, args: ast.arguments) -> list[dict[str, Any]]:
        """Extract function parameters."""
        params = []
        
        # Regular args
        defaults_offset = len(args.args) - len(args.defaults)
        for i, arg in enumerate(args.args):
            param = {
                "name": arg.arg,
                "type": self._get_annotation(arg.annotation),
                "default": None,
            }
            if i >= defaults_offset:
                default_node = args.defaults[i - defaults_offset]
                try:
                    param["default"] = ast.unparse(default_node)
                except Exception:
                    param["default"] = "..."
            params.append(param)
        
        # *args
        if args.vararg:
            params.append({
                "name": f"*{args.vararg.arg}",
                "type": self._get_annotation(args.vararg.annotation),
                "default": None,
            })
        
        # **kwargs
        if args.kwarg:
            params.append({
                "name": f"**{args.kwarg.arg}",
                "type": self._get_annotation(args.kwarg.annotation),
                "default": None,
            })
        
        return params
    
    def visit_Import(self, node: ast.Import) -> None:
        """Visit import statement."""
        for alias in node.names:
            self.imports.append(ImportInfo(
                module=alias.name,
                names=[alias.name],
                alias=alias.asname,
                is_from_import=False,
                location=self._get_location(node),
            ))
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Visit from-import statement."""
        module = node.module or ""
        names = [alias.name for alias in node.names]
        self.imports.append(ImportInfo(
            module=module,
            names=names,
            is_from_import=True,
            level=node.level,
            location=self._get_location(node),
        ))
        self.generic_visit(node)
    
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition."""
        bases = []
        for base in node.bases:
            try:
                bases.append(ast.unparse(base))
            except Exception:
                bases.append("...")
        
        element = CodeElement(
            name=node.name,
            element_type=CodeElementType.CLASS,
            location=self._get_location(node),
            docstring=self._get_docstring(node),
            decorators=self._get_decorators(node),
            bases=bases,
        )
        self.elements.append(element)
        
        # Visit children
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class
    
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definition."""
        self._visit_function(node)
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definition."""
        self._visit_function(node, is_async=True)
    
    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool = False) -> None:
        """Visit function or method."""
        is_method = self.current_class is not None
        
        # Check if property
        decorators = self._get_decorators(node)
        is_property = "property" in decorators
        
        element_type = CodeElementType.PROPERTY if is_property else (
            CodeElementType.METHOD if is_method else CodeElementType.FUNCTION
        )
        
        element = CodeElement(
            name=node.name,
            element_type=element_type,
            location=self._get_location(node),
            docstring=self._get_docstring(node),
            decorators=decorators,
            parent=self.current_class,
            parameters=self._get_parameters(node.args),
            return_type=self._get_annotation(node.returns),
        )
        
        if is_async:
            element.attributes["async"] = True
        
        self.elements.append(element)
        
        # Track function length
        length = (node.end_lineno or node.lineno) - node.lineno + 1
        self._function_lengths.append(length)
        
        # Track nesting
        self._nesting_depth += 1
        self._max_nesting = max(self._max_nesting, self._nesting_depth)
        self.generic_visit(node)
        self._nesting_depth -= 1
    
    def visit_Assign(self, node: ast.Assign) -> None:
        """Visit assignment (module-level constants)."""
        if self.current_class is None and self._nesting_depth == 0:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    is_constant = name.isupper()
                    element = CodeElement(
                        name=name,
                        element_type=CodeElementType.CONSTANT if is_constant else CodeElementType.VARIABLE,
                        location=self._get_location(node),
                    )
                    self.elements.append(element)
        self.generic_visit(node)


# =============================================================================
# Code Analyzer
# =============================================================================

class CodeAnalyzer:
    """
    Analyzes Python code for structure, metrics, and issues.
    
    Capabilities:
    - Parse and traverse AST
    - Extract code elements (classes, functions, etc.)
    - Calculate complexity metrics
    - Identify code issues
    - Analyze dependencies
    """
    
    def __init__(self) -> None:
        """Initialize code analyzer."""
        pass
    
    def analyze_source(self, source: str, file_path: str = "<string>") -> AnalysisResult:
        """
        Analyze Python source code.
        
        Args:
            source: Python source code
            file_path: Optional file path for location info
            
        Returns:
            AnalysisResult with analysis data
        """
        result = AnalysisResult(file_path=file_path)
        
        try:
            # Parse AST
            tree = ast.parse(source)
            
            # Visit nodes
            visitor = CodeVisitor(file_path)
            visitor.visit(tree)
            
            result.elements = visitor.elements
            result.imports = visitor.imports
            
            # Calculate metrics
            result.metrics = self._calculate_metrics(source, tree, visitor)
            
            # Find issues
            result.issues = self._find_issues(source, tree, visitor)
            
            # Extract dependencies
            result.dependencies = self._extract_dependencies(visitor.imports)
            
            # Get module docstring
            module_doc = ast.get_docstring(tree)
            if module_doc:
                result.module_name = file_path
            
        except SyntaxError as e:
            result.success = False
            result.error = f"Syntax error: {e}"
        except Exception as e:
            result.success = False
            result.error = f"Analysis error: {e}"
        
        return result
    
    def analyze_file(self, file_path: str | Path) -> AnalysisResult:
        """
        Analyze a Python file.
        
        Args:
            file_path: Path to Python file
            
        Returns:
            AnalysisResult with analysis data
        """
        path = Path(file_path)
        
        if not path.exists():
            return AnalysisResult(
                file_path=str(path),
                success=False,
                error=f"File not found: {path}",
            )
        
        if not path.suffix == ".py":
            return AnalysisResult(
                file_path=str(path),
                success=False,
                error="Not a Python file",
            )
        
        try:
            source = path.read_text(encoding="utf-8")
            return self.analyze_source(source, str(path))
        except Exception as e:
            return AnalysisResult(
                file_path=str(path),
                success=False,
                error=f"Error reading file: {e}",
            )
    
    def _calculate_metrics(
        self,
        source: str,
        tree: ast.Module,
        visitor: CodeVisitor,
    ) -> ComplexityMetrics:
        """Calculate code metrics."""
        lines = source.split('\n')
        
        # Count lines
        loc = len([l for l in lines if l.strip()])
        comments = len([l for l in lines if l.strip().startswith('#')])
        blanks = len([l for l in lines if not l.strip()])
        
        # Count elements
        functions = len([e for e in visitor.elements if e.element_type == CodeElementType.FUNCTION])
        methods = len([e for e in visitor.elements if e.element_type == CodeElementType.METHOD])
        classes = len([e for e in visitor.elements if e.element_type == CodeElementType.CLASS])
        
        # Calculate cyclomatic complexity
        cyclomatic = self._calculate_cyclomatic(tree)
        
        # Average function length
        avg_length = (
            sum(visitor._function_lengths) / len(visitor._function_lengths)
            if visitor._function_lengths else 0
        )
        
        return ComplexityMetrics(
            cyclomatic_complexity=cyclomatic,
            lines_of_code=loc,
            lines_of_comments=comments,
            blank_lines=blanks,
            num_functions=functions,
            num_classes=classes,
            num_methods=methods,
            max_nesting_depth=visitor._max_nesting,
            avg_function_length=round(avg_length, 1),
        )
    
    def _calculate_cyclomatic(self, tree: ast.Module) -> int:
        """Calculate cyclomatic complexity."""
        complexity = 1  # Base complexity
        
        for node in ast.walk(tree):
            # Decision points
            if isinstance(node, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(node, ast.ExceptHandler):
                complexity += 1
            elif isinstance(node, (ast.And, ast.Or)):
                complexity += 1
            elif isinstance(node, ast.comprehension):
                complexity += 1
                if node.ifs:
                    complexity += len(node.ifs)
            elif isinstance(node, ast.Match):
                complexity += 1
            elif isinstance(node, ast.match_case):
                complexity += 1
        
        return complexity
    
    def _find_issues(
        self,
        source: str,
        tree: ast.Module,
        visitor: CodeVisitor,
    ) -> list[CodeIssue]:
        """Find code quality issues."""
        issues = []
        
        # Check for missing docstrings
        for elem in visitor.elements:
            if elem.element_type in (CodeElementType.CLASS, CodeElementType.FUNCTION, CodeElementType.METHOD):
                if not elem.docstring and not elem.name.startswith('_'):
                    issues.append(CodeIssue(
                        code="D100",
                        message=f"Missing docstring for {elem.element_type.value} '{elem.name}'",
                        severity="warning",
                        location=elem.location,
                        suggestion="Add a docstring explaining the purpose and usage",
                    ))
        
        # Check for long functions
        for elem in visitor.elements:
            if elem.element_type in (CodeElementType.FUNCTION, CodeElementType.METHOD):
                length = elem.location.line_end - elem.location.line_start
                if length > 50:
                    issues.append(CodeIssue(
                        code="C901",
                        message=f"Function '{elem.name}' is too long ({length} lines)",
                        severity="warning",
                        location=elem.location,
                        suggestion="Consider breaking into smaller functions",
                    ))
        
        # Check for too many parameters
        for elem in visitor.elements:
            if elem.element_type in (CodeElementType.FUNCTION, CodeElementType.METHOD):
                param_count = len([p for p in elem.parameters if not p["name"].startswith("*")])
                if param_count > 5:
                    issues.append(CodeIssue(
                        code="R913",
                        message=f"Function '{elem.name}' has too many parameters ({param_count})",
                        severity="info",
                        location=elem.location,
                        suggestion="Consider using a configuration object",
                    ))
        
        return issues
    
    def _extract_dependencies(self, imports: list[ImportInfo]) -> list[str]:
        """Extract external dependencies."""
        deps = set()
        
        stdlib_modules = {
            'os', 'sys', 're', 'json', 'ast', 'typing', 'pathlib', 'dataclasses',
            'datetime', 'collections', 'itertools', 'functools', 'abc', 'enum',
            'threading', 'asyncio', 'logging', 'unittest', 'uuid', 'copy', 'time',
            'hashlib', 'tempfile', 'shutil', 'sqlite3', 'heapq', 'traceback',
        }
        
        for imp in imports:
            module = imp.module.split('.')[0] if imp.module else ""
            if module and module not in stdlib_modules and not imp.level > 0:
                deps.add(module)
        
        return sorted(deps)
    
    def get_element_source(self, source: str, element: CodeElement) -> str:
        """Extract source code for an element."""
        lines = source.split('\n')
        start = element.location.line_start - 1
        end = element.location.line_end
        return '\n'.join(lines[start:end])
