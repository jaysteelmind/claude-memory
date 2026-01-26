"""
DMM Self-Modification Module.

This module provides safe self-modification capabilities for the Agent OS,
including code analysis, generation, and modification proposals.

Public API:
-----------

Code Analysis:
    CodeAnalyzer - Analyzes Python code structure and metrics
    AnalysisResult - Complete analysis result
    CodeElement - A code element (function, class, etc.)
    CodeElementType - Types of code elements
    CodeLocation - Location in source code
    ImportInfo - Import statement information
    ComplexityMetrics - Code complexity metrics
    ComplexityLevel - Complexity levels
    CodeIssue - A code quality issue

Code Generation:
    CodeGenerator - Generates Python code safely
    GenerationResult - Result of code generation
    ValidationResult - Result of code validation
    GenerationType - Types of code generation
    FunctionSpec - Specification for generating a function
    ClassSpec - Specification for generating a class
    ModuleSpec - Specification for generating a module
    ParameterSpec - Specification for a function parameter
    CodeTemplates - Pre-defined code templates

Modification Proposals:
    ProposalManager - Manages modification proposals
    ModificationProposal - A proposal for code modification
    ModificationType - Types of code modifications
    ProposalStatus - Status of a modification proposal
    RiskLevel - Risk level of a modification
    CodeChange - A specific code change
    ReviewResult - Result of a proposal review
    ReviewComment - A review comment on a proposal
    generate_proposal_id - Generate unique proposal ID

Example Usage:
--------------

    from dmm.agentos.selfmod import (
        CodeAnalyzer,
        CodeGenerator,
        ProposalManager,
        FunctionSpec,
        ParameterSpec,
    )
    
    # Analyze existing code
    analyzer = CodeAnalyzer()
    result = analyzer.analyze_file("src/module.py")
    
    print(f"Classes: {len(result.get_classes())}")
    print(f"Functions: {len(result.get_functions())}")
    print(f"Complexity: {result.metrics.complexity_level}")
    
    # Generate new code
    generator = CodeGenerator()
    
    spec = FunctionSpec(
        name="calculate_total",
        parameters=[
            ParameterSpec(name="items", type_hint="list[int]"),
            ParameterSpec(name="tax_rate", type_hint="float", default="0.0"),
        ],
        return_type="float",
        body="return sum(items) * (1 + tax_rate)",
        docstring="Calculate total with optional tax.",
    )
    
    result = generator.generate_function(spec)
    if result.success:
        print(result.code)
    
    # Create modification proposal
    manager = ProposalManager(analyzer, generator)
    
    proposal = manager.create_function_addition(
        file_path="src/module.py",
        original_source=open("src/module.py").read(),
        function_code=result.code,
        author="agent_1",
        description="Add calculate_total function",
    )
    
    print(f"Risk level: {proposal.risk_level}")
"""

# Code Analysis
from dmm.agentos.selfmod.analyzer import (
    CodeAnalyzer,
    AnalysisResult,
    CodeElement,
    CodeElementType,
    CodeLocation,
    ImportInfo,
    ComplexityMetrics,
    ComplexityLevel,
    CodeIssue,
)

# Code Generation
from dmm.agentos.selfmod.generator import (
    CodeGenerator,
    GenerationResult,
    ValidationResult,
    GenerationType,
    FunctionSpec,
    ClassSpec,
    ModuleSpec,
    ParameterSpec,
    CodeTemplates,
)

# Modification Proposals
from dmm.agentos.selfmod.proposals import (
    ProposalManager,
    ModificationProposal,
    ModificationType,
    ProposalStatus,
    RiskLevel,
    CodeChange,
    ReviewResult,
    ReviewComment,
    generate_proposal_id,
)

__all__ = [
    # Code Analysis
    "CodeAnalyzer",
    "AnalysisResult",
    "CodeElement",
    "CodeElementType",
    "CodeLocation",
    "ImportInfo",
    "ComplexityMetrics",
    "ComplexityLevel",
    "CodeIssue",
    # Code Generation
    "CodeGenerator",
    "GenerationResult",
    "ValidationResult",
    "GenerationType",
    "FunctionSpec",
    "ClassSpec",
    "ModuleSpec",
    "ParameterSpec",
    "CodeTemplates",
    # Modification Proposals
    "ProposalManager",
    "ModificationProposal",
    "ModificationType",
    "ProposalStatus",
    "RiskLevel",
    "CodeChange",
    "ReviewResult",
    "ReviewComment",
    "generate_proposal_id",
]
