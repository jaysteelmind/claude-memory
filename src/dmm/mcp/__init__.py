"""
DMM MCP Server - Model Context Protocol integration for automatic memory operations.

This module provides a fully automatic memory system for Claude Code through MCP,
enabling transparent context injection and memory capture without explicit commands.
"""

from dmm.mcp.server import create_server, run_server

__all__ = ["create_server", "run_server"]
