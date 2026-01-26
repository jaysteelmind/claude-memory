"""
Code generator for self-modification framework.

This module provides safe code generation capabilities including:
- Code templates
- AST-based code building
- Code formatting
- Safety validation
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from enum import Enum
import ast
import re
import textwrap


# =============================================================================
# Generation Types
# =============================================================================

class GenerationType(str, Enum):
    """Types of code generation."""
    
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    MODULE = "module"
    PROPERTY = "property"
    DECORATOR = "decorator"
    TEST = "test"
    DOCSTRING = "docstring"


class ValidationResult(str, Enum):
    """Result of code validation."""
    
    VALID = "valid"
    SYNTAX_ERROR = "syntax_error"
    SAFETY_ERROR = "safety_error"
    STYLE_ERROR = "style_error"


# =============================================================================
# Code Specifications
# =============================================================================

@dataclass
class ParameterSpec:
    """Specification for a function parameter."""
    
    name: str
    type_hint: Optional[str] = None
    default: Optional[str] = None
    is_args: bool = False
    is_kwargs: bool = False
    
    def to_code(self) -> str:
        """Generate parameter code."""
        if self.is_args:
            prefix = "*"
        elif self.is_kwargs:
            prefix = "**"
        else:
            prefix = ""
        
        code = f"{prefix}{self.name}"
        
        if self.type_hint:
            code += f": {self.type_hint}"
        
        if self.default is not None and not self.is_args and not self.is_kwargs:
            code += f" = {self.default}"
        
        return code


@dataclass
class FunctionSpec:
    """Specification for generating a function."""
    
    name: str
    parameters: list[ParameterSpec] = field(default_factory=list)
    return_type: Optional[str] = None
    body: str = "pass"
    docstring: str = ""
    decorators: list[str] = field(default_factory=list)
    is_async: bool = False
    is_method: bool = False
    is_classmethod: bool = False
    is_staticmethod: bool = False
    is_property: bool = False
    
    def to_code(self, indent: int = 0) -> str:
        """Generate function code."""
        lines = []
        prefix = "    " * indent
        
        # Decorators
        for dec in self.decorators:
            lines.append(f"{prefix}@{dec}")
        
        if self.is_property:
            lines.append(f"{prefix}@property")
        if self.is_classmethod:
            lines.append(f"{prefix}@classmethod")
        if self.is_staticmethod:
            lines.append(f"{prefix}@staticmethod")
        
        # Function definition
        async_prefix = "async " if self.is_async else ""
        params = ", ".join(p.to_code() for p in self.parameters)
        
        if self.return_type:
            signature = f"{prefix}{async_prefix}def {self.name}({params}) -> {self.return_type}:"
        else:
            signature = f"{prefix}{async_prefix}def {self.name}({params}):"
        
        lines.append(signature)
        
        # Docstring
        if self.docstring:
            doc_lines = self.docstring.strip().split('\n')
            if len(doc_lines) == 1:
                lines.append(f'{prefix}    """{doc_lines[0]}"""')
            else:
                lines.append(f'{prefix}    """')
                for doc_line in doc_lines:
                    lines.append(f'{prefix}    {doc_line}')
                lines.append(f'{prefix}    """')
        
        # Body
        body_lines = self.body.strip().split('\n')
        for body_line in body_lines:
            lines.append(f"{prefix}    {body_line}")
        
        return '\n'.join(lines)


@dataclass
class ClassSpec:
    """Specification for generating a class."""
    
    name: str
    bases: list[str] = field(default_factory=list)
    docstring: str = ""
    decorators: list[str] = field(default_factory=list)
    attributes: list[tuple[str, str, Optional[str]]] = field(default_factory=list)  # (name, type, default)
    methods: list[FunctionSpec] = field(default_factory=list)
    is_dataclass: bool = False
    
    def to_code(self) -> str:
        """Generate class code."""
        lines = []
        
        # Decorators
        for dec in self.decorators:
            lines.append(f"@{dec}")
        
        if self.is_dataclass:
            lines.append("@dataclass")
        
        # Class definition
        if self.bases:
            bases_str = ", ".join(self.bases)
            lines.append(f"class {self.name}({bases_str}):")
        else:
            lines.append(f"class {self.name}:")
        
        # Docstring
        if self.docstring:
            doc_lines = self.docstring.strip().split('\n')
            if len(doc_lines) == 1:
                lines.append(f'    """{doc_lines[0]}"""')
            else:
                lines.append('    """')
                for doc_line in doc_lines:
                    lines.append(f'    {doc_line}')
                lines.append('    """')
        
        # Attributes (for dataclass)
        if self.is_dataclass:
            for attr_name, attr_type, default in self.attributes:
                if default is not None:
                    lines.append(f"    {attr_name}: {attr_type} = {default}")
                else:
                    lines.append(f"    {attr_name}: {attr_type}")
        
        # Methods
        if self.methods:
            if self.is_dataclass and self.attributes:
                lines.append("")  # Blank line after attributes
            
            for i, method in enumerate(self.methods):
                if i > 0:
                    lines.append("")  # Blank line between methods
                lines.append(method.to_code(indent=1))
        elif not self.attributes:
            lines.append("    pass")
        
        return '\n'.join(lines)


@dataclass
class ModuleSpec:
    """Specification for generating a module."""
    
    name: str
    docstring: str = ""
    imports: list[str] = field(default_factory=list)
    from_imports: list[tuple[str, list[str]]] = field(default_factory=list)  # (module, names)
    constants: list[tuple[str, str]] = field(default_factory=list)  # (name, value)
    classes: list[ClassSpec] = field(default_factory=list)
    functions: list[FunctionSpec] = field(default_factory=list)
    
    def to_code(self) -> str:
        """Generate module code."""
        sections = []
        
        # Module docstring
        if self.docstring:
            doc_lines = self.docstring.strip().split('\n')
            sections.append('"""')
            for line in doc_lines:
                sections.append(line)
            sections.append('"""')
            sections.append("")
        
        # Imports
        import_lines = []
        for imp in sorted(self.imports):
            import_lines.append(f"import {imp}")
        
        for module, names in sorted(self.from_imports):
            names_str = ", ".join(sorted(names))
            import_lines.append(f"from {module} import {names_str}")
        
        if import_lines:
            sections.extend(import_lines)
            sections.append("")
        
        # Constants
        if self.constants:
            for const_name, const_value in self.constants:
                sections.append(f"{const_name} = {const_value}")
            sections.append("")
        
        # Classes
        for cls in self.classes:
            sections.append(cls.to_code())
            sections.append("")
        
        # Functions
        for func in self.functions:
            sections.append(func.to_code())
            sections.append("")
        
        return '\n'.join(sections).rstrip() + '\n'


# =============================================================================
# Code Templates
# =============================================================================

class CodeTemplates:
    """Pre-defined code templates."""
    
    @staticmethod
    def init_method(parameters: list[ParameterSpec]) -> FunctionSpec:
        """Create __init__ method template."""
        # Add self parameter
        all_params = [ParameterSpec(name="self")] + parameters
        
        # Generate body
        body_lines = []
        for param in parameters:
            if not param.is_args and not param.is_kwargs:
                body_lines.append(f"self.{param.name} = {param.name}")
        
        return FunctionSpec(
            name="__init__",
            parameters=all_params,
            return_type="None",
            body='\n'.join(body_lines) if body_lines else "pass",
            is_method=True,
        )
    
    @staticmethod
    def property_getter(name: str, return_type: str, docstring: str = "") -> FunctionSpec:
        """Create property getter template."""
        return FunctionSpec(
            name=name,
            parameters=[ParameterSpec(name="self")],
            return_type=return_type,
            body=f"return self._{name}",
            docstring=docstring,
            is_method=True,
            is_property=True,
        )
    
    @staticmethod
    def property_setter(name: str, value_type: str) -> FunctionSpec:
        """Create property setter template."""
        return FunctionSpec(
            name=name,
            parameters=[
                ParameterSpec(name="self"),
                ParameterSpec(name="value", type_hint=value_type),
            ],
            return_type="None",
            body=f"self._{name} = value",
            decorators=[f"{name}.setter"],
            is_method=True,
        )
    
    @staticmethod
    def to_dict_method(attributes: list[str]) -> FunctionSpec:
        """Create to_dict method template."""
        if not attributes:
            body = "return {}"
        else:
            items = [f'"{attr}": self.{attr}' for attr in attributes]
            body = "return {\n    " + ",\n    ".join(items) + ",\n}"
        
        return FunctionSpec(
            name="to_dict",
            parameters=[ParameterSpec(name="self")],
            return_type="dict[str, Any]",
            body=body,
            docstring="Convert to dictionary.",
            is_method=True,
        )
    
    @staticmethod
    def from_dict_classmethod(class_name: str, attributes: list[str]) -> FunctionSpec:
        """Create from_dict classmethod template."""
        if not attributes:
            body = f"return cls()"
        else:
            items = [f'{attr}=data.get("{attr}")' for attr in attributes]
            body = f"return cls(\n    " + ",\n    ".join(items) + ",\n)"
        
        return FunctionSpec(
            name="from_dict",
            parameters=[
                ParameterSpec(name="cls"),
                ParameterSpec(name="data", type_hint="dict[str, Any]"),
            ],
            return_type=f'"{class_name}"',
            body=body,
            docstring="Create from dictionary.",
            is_method=True,
            is_classmethod=True,
        )
    
    @staticmethod
    def test_function(name: str, test_body: str = "pass") -> FunctionSpec:
        """Create test function template."""
        return FunctionSpec(
            name=f"test_{name}",
            parameters=[],
            return_type="None",
            body=test_body,
            docstring=f"Test {name}.",
        )
    
    @staticmethod
    def test_class(class_name: str, test_methods: list[FunctionSpec]) -> ClassSpec:
        """Create test class template."""
        return ClassSpec(
            name=f"Test{class_name}",
            docstring=f"Tests for {class_name}.",
            methods=test_methods,
        )


# =============================================================================
# Code Generator
# =============================================================================

@dataclass
class GenerationResult:
    """Result of code generation."""
    
    success: bool
    code: str = ""
    validation: ValidationResult = ValidationResult.VALID
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "code": self.code,
            "validation": self.validation.value,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class CodeGenerator:
    """
    Generates Python code safely.
    
    Capabilities:
    - Generate from specifications
    - Apply templates
    - Validate generated code
    - Format output
    """
    
    # Forbidden patterns for safety
    FORBIDDEN_PATTERNS = [
        r'\bexec\s*\(',
        r'\beval\s*\(',
        r'\b__import__\s*\(',
        r'\bcompile\s*\(',
        r'\bgetattr\s*\([^,]+,\s*["\'][^"\']*["\']',  # Dynamic attribute access
        r'\bsetattr\s*\(',
        r'\bdelattr\s*\(',
        r'\bglobals\s*\(\s*\)',
        r'\blocals\s*\(\s*\)',
        r'\bopen\s*\([^)]*["\']w',  # Write mode file access
        r'\bos\.system\s*\(',
        r'\bsubprocess\.',
        r'\b__builtins__',
    ]
    
    def __init__(self, strict_mode: bool = True) -> None:
        """
        Initialize code generator.
        
        Args:
            strict_mode: Enable strict safety checks
        """
        self.strict_mode = strict_mode
        self._forbidden_re = [re.compile(p) for p in self.FORBIDDEN_PATTERNS]
    
    def generate_function(self, spec: FunctionSpec) -> GenerationResult:
        """Generate a function from specification."""
        code = spec.to_code()
        return self._finalize(code)
    
    def generate_class(self, spec: ClassSpec) -> GenerationResult:
        """Generate a class from specification."""
        code = spec.to_code()
        return self._finalize(code)
    
    def generate_module(self, spec: ModuleSpec) -> GenerationResult:
        """Generate a module from specification."""
        code = spec.to_code()
        return self._finalize(code)
    
    def generate_from_template(
        self,
        template: str,
        **variables: Any,
    ) -> GenerationResult:
        """
        Generate code from a template string.
        
        Args:
            template: Template string with {variable} placeholders
            **variables: Variable values to substitute
            
        Returns:
            GenerationResult
        """
        try:
            code = template.format(**variables)
            return self._finalize(code)
        except KeyError as e:
            return GenerationResult(
                success=False,
                errors=[f"Missing template variable: {e}"],
            )
        except Exception as e:
            return GenerationResult(
                success=False,
                errors=[f"Template error: {e}"],
            )
    
    def _finalize(self, code: str) -> GenerationResult:
        """Finalize generated code with validation and formatting."""
        result = GenerationResult(success=True, code=code)
        
        # Validate syntax
        syntax_valid, syntax_error = self._validate_syntax(code)
        if not syntax_valid:
            result.success = False
            result.validation = ValidationResult.SYNTAX_ERROR
            result.errors.append(f"Syntax error: {syntax_error}")
            return result
        
        # Safety validation
        if self.strict_mode:
            safety_valid, safety_errors = self._validate_safety(code)
            if not safety_valid:
                result.success = False
                result.validation = ValidationResult.SAFETY_ERROR
                result.errors.extend(safety_errors)
                return result
        
        # Format code
        result.code = self._format_code(code)
        
        return result
    
    def _validate_syntax(self, code: str) -> tuple[bool, str]:
        """Validate Python syntax."""
        try:
            ast.parse(code)
            return True, ""
        except SyntaxError as e:
            return False, str(e)
    
    def _validate_safety(self, code: str) -> tuple[bool, list[str]]:
        """Validate code safety."""
        errors = []
        
        for pattern in self._forbidden_re:
            if pattern.search(code):
                errors.append(f"Forbidden pattern detected: {pattern.pattern}")
        
        return len(errors) == 0, errors
    
    def _format_code(self, code: str) -> str:
        """Format generated code."""
        # Basic formatting - ensure consistent line endings
        code = code.replace('\r\n', '\n')
        
        # Remove trailing whitespace
        lines = [line.rstrip() for line in code.split('\n')]
        
        # Ensure single newline at end
        code = '\n'.join(lines)
        if not code.endswith('\n'):
            code += '\n'
        
        return code
    
    def validate_code(self, code: str) -> GenerationResult:
        """
        Validate existing code.
        
        Args:
            code: Code to validate
            
        Returns:
            GenerationResult with validation status
        """
        return self._finalize(code)
    
    def add_docstring(
        self,
        code: str,
        docstring: str,
        element_name: Optional[str] = None,
    ) -> GenerationResult:
        """
        Add or update docstring in code.
        
        Args:
            code: Existing code
            docstring: Docstring to add
            element_name: Specific element to add docstring to (None for module)
            
        Returns:
            GenerationResult with modified code
        """
        try:
            tree = ast.parse(code)
            
            # Find target node
            if element_name is None:
                # Module docstring
                if (tree.body and isinstance(tree.body[0], ast.Expr) and
                    isinstance(tree.body[0].value, ast.Constant) and
                    isinstance(tree.body[0].value.value, str)):
                    # Replace existing docstring
                    tree.body[0].value.value = docstring
                else:
                    # Insert new docstring
                    doc_node = ast.Expr(value=ast.Constant(value=docstring))
                    tree.body.insert(0, doc_node)
            else:
                # Find named element
                for node in ast.walk(tree):
                    if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and
                        node.name == element_name):
                        # Add/update docstring
                        if (node.body and isinstance(node.body[0], ast.Expr) and
                            isinstance(node.body[0].value, ast.Constant)):
                            node.body[0].value.value = docstring
                        else:
                            doc_node = ast.Expr(value=ast.Constant(value=docstring))
                            node.body.insert(0, doc_node)
                        break
            
            # Unparse
            new_code = ast.unparse(tree)
            return self._finalize(new_code)
            
        except Exception as e:
            return GenerationResult(
                success=False,
                errors=[f"Error adding docstring: {e}"],
            )
