"""
MCP Tools - Model-controlled actions for memory operations.

Tools are invoked by the AI model to perform actions:
- dmm_query: Retrieve relevant memories
- dmm_remember: Create new memories
- dmm_forget: Deprecate outdated memories
- dmm_status: Check system health
- dmm_conflicts: Detect contradictions
"""

from dmm.mcp.tools.query import execute_query
from dmm.mcp.tools.remember import execute_remember
from dmm.mcp.tools.forget import execute_forget
from dmm.mcp.tools.status import execute_status
from dmm.mcp.tools.conflicts import execute_conflicts

__all__ = [
    "execute_query",
    "execute_remember",
    "execute_forget",
    "execute_status",
    "execute_conflicts",
]
