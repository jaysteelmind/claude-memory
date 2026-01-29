"""
MCP Prompts - Reusable interaction templates.

Prompts provide templates for common interactions:
- context_injection: Auto-query prompt for task start
- memory_proposal: Learning capture template
"""

from dmm.mcp.prompts.context_injection import generate_context_injection
from dmm.mcp.prompts.memory_proposal import generate_memory_proposal

__all__ = [
    "generate_context_injection",
    "generate_memory_proposal",
]
