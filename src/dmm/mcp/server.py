"""
DMM MCP Server - Model Context Protocol server for automatic memory operations.

This server exposes DMM functionality through MCP, enabling Claude Code
to automatically query and create memories without explicit user commands.

Usage:
    dmm mcp serve              # Start with stdio transport (default)
    dmm mcp serve --port 3000  # Start with HTTP transport
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from dmm.mcp.tools.query import execute_query
from dmm.mcp.tools.remember import execute_remember
from dmm.mcp.tools.forget import execute_forget
from dmm.mcp.tools.status import execute_status
from dmm.mcp.tools.conflicts import execute_conflicts

logger = logging.getLogger(__name__)

DMM_SERVER_NAME = "dmm"
DMM_SERVER_VERSION = "1.0.0"
DMM_SERVER_DESCRIPTION = "Dynamic Markdown Memory - Automatic context management for Claude Code"


def create_server() -> FastMCP:
    """
    Create and configure the DMM MCP server.

    Returns:
        Configured FastMCP server instance with all tools and resources registered
    """
    mcp = FastMCP(
        name=DMM_SERVER_NAME,
        instructions=DMM_SERVER_DESCRIPTION,
    )

    _register_tools(mcp)
    _register_resources(mcp)
    _register_prompts(mcp)

    logger.info("DMM MCP server created with %s tools", len(_get_tool_names()))

    return mcp


def _register_tools(mcp: FastMCP) -> None:
    """Register all MCP tools."""

    @mcp.tool()
    async def dmm_query(
        query: str,
        budget: int = 1500,
        include_graph: bool = True,
        scope: str | None = None,
    ) -> str:
        """
        Query DMM for memories relevant to a task or topic.

        Call this tool at the START of any task to get relevant context.
        The returned memories contain project decisions, patterns, and constraints
        that should inform your response.

        Args:
            query: Natural language description of the task or topic
            budget: Maximum tokens to return (default 1500)
            include_graph: Whether to expand via knowledge graph (default True)
            scope: Optional scope filter (baseline, global, agent, project, ephemeral)

        Returns:
            Formatted memories with metadata, ready for context injection

        Examples:
            dmm_query("implementing user authentication")
            dmm_query("database schema design", budget=2000)
            dmm_query("coding standards", scope="baseline")
        """
        return await execute_query(query, budget, include_graph, scope)

    @mcp.tool()
    async def dmm_remember(
        content: str,
        scope: str = "project",
        tags: list[str] | None = None,
        priority: float = 0.6,
        confidence: str = "active",
    ) -> str:
        """
        Create a new memory from important information learned during the conversation.

        Call this tool when you discover:
        - Project decisions or conventions
        - Architectural patterns
        - Constraints or requirements
        - Solutions to problems
        - User preferences

        Args:
            content: The information to remember (will be formatted as markdown)
            scope: Memory scope - baseline, global, agent, project, or ephemeral
            tags: Optional list of tags for categorization (auto-generated if not provided)
            priority: Importance from 0.0 to 1.0 (default 0.6)
            confidence: Confidence level - experimental, active, or stable

        Returns:
            Confirmation with memory ID and details

        Examples:
            dmm_remember(
                "We use PostgreSQL with read replicas for scaling.",
                scope="project",
                tags=["database", "architecture"]
            )
            dmm_remember(
                "User prefers concise responses without code comments.",
                scope="agent",
                priority=0.8
            )
        """
        return await execute_remember(content, scope, tags, priority, confidence)

    @mcp.tool()
    async def dmm_forget(
        memory_id: str,
        reason: str,
        permanent: bool = False,
    ) -> str:
        """
        Deprecate a memory that is no longer accurate or relevant.

        Call this tool when you discover that stored information is:
        - Outdated or superseded
        - Incorrect
        - No longer applicable

        Args:
            memory_id: The ID of the memory to deprecate (format: mem_YYYY_MM_DD_NNN)
            reason: Explanation for why this memory should be deprecated
            permanent: If True, move to deprecated folder; if False, just mark status

        Returns:
            Confirmation of deprecation

        Examples:
            dmm_forget("mem_2026_01_15_042", "Superseded by new caching strategy")
            dmm_forget("mem_2026_01_10_001", "Project no longer uses Redis", permanent=True)
        """
        return await execute_forget(memory_id, reason, permanent)

    @mcp.tool()
    async def dmm_status(verbose: bool = False) -> str:
        """
        Check DMM system health and statistics.

        Call this tool to verify the system is working or to get
        an overview of available memories.

        Args:
            verbose: If True, include additional configuration details

        Returns:
            System status including daemon state, memory counts, and health

        Examples:
            dmm_status()
            dmm_status(verbose=True)
        """
        return await execute_status(verbose)

    @mcp.tool()
    async def dmm_conflicts(
        include_resolved: bool = False,
        min_severity: str = "low",
    ) -> str:
        """
        Check for conflicting memories that need resolution.

        Call this tool periodically or when you suspect contradictory information.
        Conflicts should be reported to the user for resolution.

        Args:
            include_resolved: If True, include previously resolved conflicts
            min_severity: Minimum severity to include (low, medium, high, critical)

        Returns:
            List of detected conflicts with severity and suggested resolutions

        Examples:
            dmm_conflicts()
            dmm_conflicts(min_severity="high")
            dmm_conflicts(include_resolved=True)
        """
        return await execute_conflicts(include_resolved, min_severity)


def _register_resources(mcp: FastMCP) -> None:
    """Register all MCP resources."""
    from dmm.mcp.resources.baseline import get_baseline
    from dmm.mcp.resources.recent import get_recent
    from dmm.mcp.resources.conflicts import get_conflicts

    @mcp.resource("memory://baseline")
    async def baseline_resource() -> str:
        """
        Always-loaded baseline memories containing core project context.

        This resource provides critical information that should inform
        every interaction: project identity, hard constraints, and principles.
        """
        return await get_baseline()

    @mcp.resource("memory://recent")
    async def recent_resource() -> str:
        """
        Recently accessed or created memories.

        Useful for maintaining continuity across conversation turns.
        """
        return await get_recent()

    @mcp.resource("memory://conflicts")
    async def conflicts_resource() -> str:
        """
        Currently detected memory conflicts.

        Subscribe to this resource to be notified when conflicts arise.
        """
        return await get_conflicts()


def _register_prompts(mcp: FastMCP) -> None:
    """Register all MCP prompts."""
    from dmm.mcp.prompts.context_injection import generate_context_injection
    from dmm.mcp.prompts.memory_proposal import generate_memory_proposal

    @mcp.prompt()
    def context_injection(task: str) -> str:
        """
        Template for automatically injecting relevant context at task start.

        This prompt guides Claude to query memories and incorporate them
        before responding to the user.

        Args:
            task: Description of the current task or user request
        """
        return generate_context_injection(task)

    @mcp.prompt()
    def memory_proposal(conversation_summary: str) -> str:
        """
        Template for identifying learnings worth remembering.

        This prompt guides Claude to extract memorable information
        from a conversation and propose appropriate memories.

        Args:
            conversation_summary: Summary of the conversation so far
        """
        return generate_memory_proposal(conversation_summary)


def _get_tool_names() -> list[str]:
    """Get list of registered tool names."""
    return ["dmm_query", "dmm_remember", "dmm_forget", "dmm_status", "dmm_conflicts"]


def run_server(transport: str = "stdio", port: int = 3000) -> None:
    """
    Run the DMM MCP server.

    Args:
        transport: Transport type - 'stdio' or 'sse'
        port: Port for SSE transport (default 3000)
    """
    mcp = create_server()

    logger.info("Starting DMM MCP server with %s transport", transport)

    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport == "sse":
        mcp.run(transport="sse", port=port)
    else:
        raise ValueError(f"Unknown transport: {transport}. Use 'stdio' or 'sse'.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_server()
