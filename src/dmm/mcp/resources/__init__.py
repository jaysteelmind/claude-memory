"""
MCP Resources - Application-controlled data for context provision.

Resources provide data that the application controls:
- memory://baseline: Always-loaded critical context
- memory://recent: Recently accessed memories
- memory://conflicts: Current conflict list
"""

from dmm.mcp.resources.baseline import get_baseline
from dmm.mcp.resources.recent import get_recent
from dmm.mcp.resources.conflicts import get_conflicts

__all__ = [
    "get_baseline",
    "get_recent",
    "get_conflicts",
]
