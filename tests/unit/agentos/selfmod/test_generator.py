"""
Unit tests for code generator.

Tests cover:
- Code generation from specs
- Template generation
- Validation
- Safety checks
"""

import pytest

from dmm.agentos.selfmod import (
    CodeGenerator,
    GenerationResult,
    ValidationResult,
    FunctionSpec,
    ClassSpec,
    ModuleSpec,
    ParameterSpec,
    CodeTemplates,
)


@pytest.fixture
def generator():
    """Create code generator."""
    return CodeGenerator()


@pytest.fixture
def lenient_generator():
    """Create generator with strict mode off."""
    return CodeGenerator(strict_mode=False)


class TestParameterSpec:
    """Tests for ParameterSpec."""
    
    def test_simple_parameter(self):
        """Test simple parameter."""
        param = ParameterSpec(name="x")
        assert param.to_code() == "x"
    
    def test_typed_parameter(self):
        """Test typed parameter."""
        param = ParameterSpec(name="x", type_hint="int")
        assert param.to_code() == "x: int"
    
    def test_parameter_with_default(self):
        """Test parameter with default."""
        param = ParameterSpec(name="x", type_hint="int", default="0")
        assert param.to_code() == "x: int = 0"
    
    def test_args_parameter(self):
        """Test *args parameter."""
        param = ParameterSpec(name="args", is_args=True)
        assert param.to_code() == "*args"
    
    def test_kwargs_parameter(self):
        """Test **kwargs parameter."""
        param = ParameterSpec(name="kwargs", is_kwargs=True)
        assert param.to_code() == "**kwargs"


class TestFunctionSpec:
    """Tests for FunctionSpec."""
    
    def test_simple_function(self):
        """Test simple function generation."""
        spec = FunctionSpec(
            name="hello",
            body="return 'hello'",
        )
        
        code = spec.to_code()
        
        assert "def hello():" in code
        assert "return 'hello'" in code
    
    def test_function_with_params(self):
        """Test function with parameters."""
        spec = FunctionSpec(
            name="add",
            parameters=[
                ParameterSpec(name="a", type_hint="int"),
                ParameterSpec(name="b", type_hint="int"),
            ],
            return_type="int",
            body="return a + b",
        )
        
        code = spec.to_code()
        
        assert "def add(a: int, b: int) -> int:" in code
    
    def test_function_with_docstring(self):
        """Test function with docstring."""
        spec = FunctionSpec(
            name="greet",
            docstring="Say hello.",
            body="print('hello')",
        )
        
        code = spec.to_code()
        
        assert '"""Say hello."""' in code
    
    def test_async_function(self):
        """Test async function."""
        spec = FunctionSpec(
            name="async_hello",
            is_async=True,
            body="return 'hello'",
        )
        
        code = spec.to_code()
        
        assert "async def async_hello():" in code
    
    def test_decorated_function(self):
        """Test decorated function."""
        spec = FunctionSpec(
            name="cached",
            decorators=["lru_cache", "staticmethod"],
            body="pass",
        )
        
        code = spec.to_code()
        
        assert "@lru_cache" in code
        assert "@staticmethod" in code


class TestClassSpec:
    """Tests for ClassSpec."""
    
    def test_simple_class(self):
        """Test simple class generation."""
        spec = ClassSpec(name="MyClass")
        
        code = spec.to_code()
        
        assert "class MyClass:" in code
        assert "pass" in code
    
    def test_class_with_bases(self):
        """Test class with inheritance."""
        spec = ClassSpec(
            name="Child",
            bases=["Parent", "Mixin"],
        )
        
        code = spec.to_code()
        
        assert "class Child(Parent, Mixin):" in code
    
    def test_class_with_methods(self):
        """Test class with methods."""
        method = FunctionSpec(
            name="greet",
            parameters=[ParameterSpec(name="self")],
            body="return 'hello'",
            is_method=True,
        )
        
        spec = ClassSpec(
            name="Greeter",
            methods=[method],
        )
        
        code = spec.to_code()
        
        assert "class Greeter:" in code
        assert "def greet(self):" in code
    
    def test_dataclass(self):
        """Test dataclass generation."""
        spec = ClassSpec(
            name="Point",
            is_dataclass=True,
            attributes=[
                ("x", "float", None),
                ("y", "float", None),
                ("z", "float", "0.0"),
            ],
        )
        
        code = spec.to_code()
        
        assert "@dataclass" in code
        assert "x: float" in code
        assert "z: float = 0.0" in code


class TestModuleSpec:
    """Tests for ModuleSpec."""
    
    def test_simple_module(self):
        """Test simple module generation."""
        spec = ModuleSpec(
            name="mymodule",
            docstring="My module.",
        )
        
        code = spec.to_code()
        
        assert '"""' in code
        assert "My module." in code
    
    def test_module_with_imports(self):
        """Test module with imports."""
        spec = ModuleSpec(
            name="mymodule",
            imports=["os", "sys"],
            from_imports=[("typing", ["Any", "Optional"])],
        )
        
        code = spec.to_code()
        
        assert "import os" in code
        assert "import sys" in code
        assert "from typing import Any, Optional" in code
    
    def test_module_with_contents(self):
        """Test module with full contents."""
        spec = ModuleSpec(
            name="mymodule",
            constants=[("VERSION", '"1.0.0"')],
            functions=[FunctionSpec(name="main", body="pass")],
        )
        
        code = spec.to_code()
        
        assert 'VERSION = "1.0.0"' in code
        assert "def main():" in code


class TestCodeGenerator:
    """Tests for CodeGenerator."""
    
    def test_generate_function(self, generator):
        """Test function generation."""
        spec = FunctionSpec(
            name="add",
            parameters=[
                ParameterSpec(name="a", type_hint="int"),
                ParameterSpec(name="b", type_hint="int"),
            ],
            return_type="int",
            body="return a + b",
        )
        
        result = generator.generate_function(spec)
        
        assert result.success
        assert result.validation == ValidationResult.VALID
        assert "def add" in result.code
    
    def test_generate_class(self, generator):
        """Test class generation."""
        spec = ClassSpec(
            name="Calculator",
            docstring="A simple calculator.",
        )
        
        result = generator.generate_class(spec)
        
        assert result.success
        assert "class Calculator:" in result.code
    
    def test_validates_syntax(self, generator):
        """Test syntax validation."""
        spec = FunctionSpec(
            name="broken",
            body="return (",  # Syntax error
        )
        
        result = generator.generate_function(spec)
        
        assert not result.success
        assert result.validation == ValidationResult.SYNTAX_ERROR
    
    def test_safety_check_exec(self, generator):
        """Test safety check blocks exec."""
        spec = FunctionSpec(
            name="dangerous",
            body="exec('print(1)')",
        )
        
        result = generator.generate_function(spec)
        
        assert not result.success
        assert result.validation == ValidationResult.SAFETY_ERROR
    
    def test_safety_check_eval(self, generator):
        """Test safety check blocks eval."""
        spec = FunctionSpec(
            name="dangerous",
            body="return eval('1+1')",
        )
        
        result = generator.generate_function(spec)
        
        assert not result.success
        assert result.validation == ValidationResult.SAFETY_ERROR
    
    def test_lenient_mode(self, lenient_generator):
        """Test lenient mode allows more code."""
        spec = FunctionSpec(
            name="dynamic",
            body="return eval('1+1')",
        )
        
        result = lenient_generator.generate_function(spec)
        
        # Should pass in lenient mode
        assert result.success


class TestCodeTemplates:
    """Tests for CodeTemplates."""
    
    def test_init_method(self):
        """Test __init__ template."""
        params = [
            ParameterSpec(name="name", type_hint="str"),
            ParameterSpec(name="age", type_hint="int"),
        ]
        
        init = CodeTemplates.init_method(params)
        code = init.to_code()
        
        assert "def __init__(self, name: str, age: int)" in code
        assert "self.name = name" in code
        assert "self.age = age" in code
    
    def test_property_getter(self):
        """Test property getter template."""
        prop = CodeTemplates.property_getter(
            name="value",
            return_type="int",
            docstring="Get the value.",
        )
        
        code = prop.to_code()
        
        assert "@property" in code
        assert "def value(self)" in code
        assert "return self._value" in code
    
    def test_to_dict_method(self):
        """Test to_dict template."""
        method = CodeTemplates.to_dict_method(["name", "age"])
        code = method.to_code()
        
        assert "def to_dict(self)" in code
        assert '"name": self.name' in code
        assert '"age": self.age' in code
    
    def test_from_dict_classmethod(self):
        """Test from_dict template."""
        method = CodeTemplates.from_dict_classmethod("Person", ["name", "age"])
        code = method.to_code()
        
        assert "@classmethod" in code
        assert "def from_dict(cls, data:" in code
        assert "return cls(" in code
    
    def test_test_function(self):
        """Test test function template."""
        test = CodeTemplates.test_function("add", "assert add(1, 2) == 3")
        code = test.to_code()
        
        assert "def test_add()" in code
        assert "assert add(1, 2) == 3" in code


class TestValidation:
    """Tests for code validation."""
    
    def test_validate_valid_code(self, generator):
        """Test validating valid code."""
        code = '''
def hello():
    return "world"
'''
        result = generator.validate_code(code)
        
        assert result.success
        assert result.validation == ValidationResult.VALID
    
    def test_validate_invalid_code(self, generator):
        """Test validating invalid code."""
        code = "def broken("
        
        result = generator.validate_code(code)
        
        assert not result.success
        assert result.validation == ValidationResult.SYNTAX_ERROR
