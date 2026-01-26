"""
Unit tests for code analyzer.

Tests cover:
- Source code analysis
- Element extraction
- Metrics calculation
- Issue detection
"""

import pytest

from dmm.agentos.selfmod import (
    CodeAnalyzer,
    AnalysisResult,
    CodeElement,
    CodeElementType,
    ComplexityLevel,
)


@pytest.fixture
def analyzer():
    """Create code analyzer."""
    return CodeAnalyzer()


@pytest.fixture
def sample_source():
    """Sample Python source code."""
    return '''
"""Sample module docstring."""

import os
from typing import Any, Optional

CONSTANT_VALUE = 42


class SampleClass:
    """A sample class."""
    
    def __init__(self, name: str) -> None:
        """Initialize with name."""
        self.name = name
    
    def greet(self) -> str:
        """Return greeting."""
        return f"Hello, {self.name}"
    
    @property
    def upper_name(self) -> str:
        """Get uppercase name."""
        return self.name.upper()


def standalone_function(x: int, y: int = 0) -> int:
    """Add two numbers."""
    return x + y


async def async_function() -> None:
    """Async function example."""
    pass
'''


class TestCodeAnalyzer:
    """Tests for CodeAnalyzer."""
    
    def test_create_analyzer(self):
        """Test creating analyzer."""
        analyzer = CodeAnalyzer()
        assert analyzer is not None
    
    def test_analyze_source(self, analyzer, sample_source):
        """Test analyzing source code."""
        result = analyzer.analyze_source(sample_source)
        
        assert result.success
        assert result.error is None
        assert len(result.elements) > 0
    
    def test_analyze_syntax_error(self, analyzer):
        """Test analyzing code with syntax error."""
        result = analyzer.analyze_source("def broken(")
        
        assert not result.success
        assert "Syntax error" in result.error
    
    def test_extracts_classes(self, analyzer, sample_source):
        """Test class extraction."""
        result = analyzer.analyze_source(sample_source)
        
        classes = result.get_classes()
        assert len(classes) == 1
        assert classes[0].name == "SampleClass"
        assert "A sample class" in classes[0].docstring
    
    def test_extracts_functions(self, analyzer, sample_source):
        """Test function extraction."""
        result = analyzer.analyze_source(sample_source)
        
        functions = result.get_functions()
        names = [f.name for f in functions]
        
        assert "standalone_function" in names
        assert "async_function" in names
    
    def test_extracts_methods(self, analyzer, sample_source):
        """Test method extraction."""
        result = analyzer.analyze_source(sample_source)
        
        methods = result.get_elements_by_type(CodeElementType.METHOD)
        names = [m.name for m in methods]
        
        assert "__init__" in names
        assert "greet" in names
    
    def test_extracts_properties(self, analyzer, sample_source):
        """Test property extraction."""
        result = analyzer.analyze_source(sample_source)
        
        properties = result.get_elements_by_type(CodeElementType.PROPERTY)
        names = [p.name for p in properties]
        
        assert "upper_name" in names
    
    def test_extracts_imports(self, analyzer, sample_source):
        """Test import extraction."""
        result = analyzer.analyze_source(sample_source)
        
        assert len(result.imports) == 2
        modules = [i.module for i in result.imports]
        
        assert "os" in modules
        assert "typing" in modules
    
    def test_extracts_constants(self, analyzer, sample_source):
        """Test constant extraction."""
        result = analyzer.analyze_source(sample_source)
        
        constants = result.get_elements_by_type(CodeElementType.CONSTANT)
        names = [c.name for c in constants]
        
        assert "CONSTANT_VALUE" in names
    
    def test_extracts_parameters(self, analyzer, sample_source):
        """Test parameter extraction."""
        result = analyzer.analyze_source(sample_source)
        
        func = result.get_element("standalone_function")
        assert func is not None
        
        params = func.parameters
        assert len(params) == 2
        assert params[0]["name"] == "x"
        assert params[0]["type"] == "int"
        assert params[1]["default"] == "0"
    
    def test_extracts_return_type(self, analyzer, sample_source):
        """Test return type extraction."""
        result = analyzer.analyze_source(sample_source)
        
        func = result.get_element("standalone_function")
        assert func.return_type == "int"
    
    def test_extracts_decorators(self, analyzer, sample_source):
        """Test decorator extraction."""
        result = analyzer.analyze_source(sample_source)
        
        prop = result.get_element("upper_name")
        assert "property" in prop.decorators or prop.element_type == CodeElementType.PROPERTY


class TestComplexityMetrics:
    """Tests for complexity metrics."""
    
    def test_calculates_loc(self, analyzer, sample_source):
        """Test lines of code calculation."""
        result = analyzer.analyze_source(sample_source)
        
        assert result.metrics.lines_of_code > 0
    
    def test_calculates_cyclomatic(self, analyzer):
        """Test cyclomatic complexity calculation."""
        source = '''
def complex_function(x):
    if x > 0:
        if x > 10:
            return "large"
        else:
            return "small"
    elif x < 0:
        return "negative"
    else:
        return "zero"
'''
        result = analyzer.analyze_source(source)
        
        # Multiple branches should increase complexity
        assert result.metrics.cyclomatic_complexity > 1
    
    def test_complexity_level_low(self, analyzer):
        """Test low complexity detection."""
        source = '''
def simple():
    return 1
'''
        result = analyzer.analyze_source(source)
        
        assert result.metrics.complexity_level == ComplexityLevel.LOW
    
    def test_counts_functions_classes(self, analyzer, sample_source):
        """Test function and class counting."""
        result = analyzer.analyze_source(sample_source)
        
        assert result.metrics.num_classes == 1
        assert result.metrics.num_functions >= 2
        assert result.metrics.num_methods >= 2


class TestCodeIssues:
    """Tests for code issue detection."""
    
    def test_detects_missing_docstring(self, analyzer):
        """Test missing docstring detection."""
        source = '''
def public_function():
    return 1

class PublicClass:
    def public_method(self):
        pass
'''
        result = analyzer.analyze_source(source)
        
        # Should detect missing docstrings
        doc_issues = [i for i in result.issues if "docstring" in i.message.lower()]
        assert len(doc_issues) > 0
    
    def test_no_issues_for_private(self, analyzer):
        """Test no docstring warning for private functions."""
        source = '''
def _private_function():
    return 1
'''
        result = analyzer.analyze_source(source)
        
        # Should not warn about private functions
        doc_issues = [i for i in result.issues if "_private_function" in i.message]
        assert len(doc_issues) == 0


class TestDependencies:
    """Tests for dependency extraction."""
    
    def test_extracts_external_deps(self, analyzer):
        """Test external dependency extraction."""
        source = '''
import numpy
import pandas as pd
from sklearn import metrics
import os
'''
        result = analyzer.analyze_source(source)
        
        # Should identify external deps (not stdlib)
        assert "numpy" in result.dependencies
        assert "pandas" in result.dependencies
        assert "sklearn" in result.dependencies
        assert "os" not in result.dependencies  # stdlib


class TestAnalysisResult:
    """Tests for AnalysisResult."""
    
    def test_get_element(self, analyzer, sample_source):
        """Test getting element by name."""
        result = analyzer.analyze_source(sample_source)
        
        elem = result.get_element("SampleClass")
        assert elem is not None
        assert elem.element_type == CodeElementType.CLASS
    
    def test_get_element_not_found(self, analyzer, sample_source):
        """Test getting nonexistent element."""
        result = analyzer.analyze_source(sample_source)
        
        elem = result.get_element("NonExistent")
        assert elem is None
    
    def test_to_dict(self, analyzer, sample_source):
        """Test result serialization."""
        result = analyzer.analyze_source(sample_source)
        
        data = result.to_dict()
        
        assert "elements" in data
        assert "imports" in data
        assert "metrics" in data
        assert "success" in data


class TestCodeLocation:
    """Tests for code location tracking."""
    
    def test_element_has_location(self, analyzer, sample_source):
        """Test elements have location info."""
        result = analyzer.analyze_source(sample_source)
        
        func = result.get_element("standalone_function")
        assert func.location.line_start > 0
        assert func.location.line_end >= func.location.line_start
    
    def test_get_element_source(self, analyzer, sample_source):
        """Test extracting element source code."""
        result = analyzer.analyze_source(sample_source)
        func = result.get_element("standalone_function")
        
        source = analyzer.get_element_source(sample_source, func)
        
        assert "def standalone_function" in source
        assert "return x + y" in source
