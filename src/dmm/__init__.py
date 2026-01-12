"""DMM - Dynamic Markdown Memory for AI Agents.

A file-native cognitive memory system that replaces monolithic instruction
files with a semantic, hierarchical collection of atomic markdown micro-files.
"""

__version__ = "0.1.0"

from dmm.core import (
    Confidence,
    DMMConfig,
    DMMError,
    Scope,
    Status,
)

__all__ = [
    "__version__",
    # Core enums
    "Scope",
    "Confidence",
    "Status",
    # Config
    "DMMConfig",
    # Base exception
    "DMMError",
]
