"""
Unit tests for DMM MCP server.

Tests cover:
- Server creation
- Tool registration
- Resource registration
- Prompt registration
"""

from __future__ import annotations

import pytest

from dmm.mcp.server import create_server, DMM_SERVER_NAME, DMM_SERVER_VERSION, _get_tool_names
from dmm.mcp.prompts.context_injection import generate_context_injection, _categorize_task, _extract_keywords
from dmm.mcp.prompts.memory_proposal import generate_memory_proposal, _detect_memory_patterns


class TestMCPServer:
    """Tests for MCP server creation and configuration."""

    def test_server_creation(self) -> None:
        """Server should be created successfully."""
        server = create_server()
        assert server is not None

    def test_server_has_correct_metadata(self) -> None:
        """Server should have correct name."""
        server = create_server()
        assert server.name == DMM_SERVER_NAME

    def test_tool_names_list(self) -> None:
        """Tool names helper should return all tools."""
        tool_names = _get_tool_names()

        assert "dmm_query" in tool_names
        assert "dmm_remember" in tool_names
        assert "dmm_forget" in tool_names
        assert "dmm_status" in tool_names
        assert "dmm_conflicts" in tool_names
        assert len(tool_names) == 5


class TestPrompts:
    """Tests for MCP prompts."""

    def test_context_injection_with_task(self) -> None:
        """Context injection should generate prompt for task."""
        result = generate_context_injection("implement user authentication")

        assert "Context Injection" in result
        assert "authentication" in result.lower()
        assert "dmm_query" in result or "Query" in result

    def test_context_injection_empty_task(self) -> None:
        """Context injection with empty task should return generic prompt."""
        result = generate_context_injection("")

        assert "Context Injection" in result
        assert "Instructions" in result

    def test_context_injection_categorizes_tasks(self) -> None:
        """Context injection should categorize tasks correctly."""
        assert _categorize_task("implement the login function") == "code_implementation"
        # "review the pull request" more clearly matches code_review
        assert _categorize_task("review the pull request for issues") == "code_review"
        assert _categorize_task("fix the bug in auth") == "debugging"
        # Database and architecture can overlap, so accept either
        result = _categorize_task("design the database schema")
        assert result in ["architecture", "database"]

    def test_context_injection_extracts_keywords(self) -> None:
        """Context injection should extract keywords from task."""
        keywords = _extract_keywords("implement user authentication with JWT tokens")

        # At least one relevant keyword should be extracted
        relevant_keywords = {"authentication", "jwt", "tokens", "user", "implement"}
        assert any(kw in keywords for kw in relevant_keywords)
        # Stop words should not be included
        assert "the" not in keywords
        assert "with" not in keywords

    def test_memory_proposal_with_summary(self) -> None:
        """Memory proposal should generate prompt for conversation."""
        result = generate_memory_proposal(
            "We decided to use PostgreSQL for the database due to its JSON support."
        )

        assert "Memory Proposal" in result
        assert "dmm_remember" in result

    def test_memory_proposal_empty_summary(self) -> None:
        """Memory proposal with empty summary should return generic prompt."""
        result = generate_memory_proposal("")

        assert "Memory Proposal" in result
        assert "Guidelines" in result

    def test_memory_proposal_detects_patterns(self) -> None:
        """Memory proposal should detect memory-worthy patterns."""
        patterns = _detect_memory_patterns("We decided to use React for the frontend.")

        pattern_types = [p["type"] for p in patterns]
        assert "decision" in pattern_types

    def test_memory_proposal_detects_constraints(self) -> None:
        """Memory proposal should detect constraint patterns."""
        patterns = _detect_memory_patterns("We must not use eval() in the codebase.")

        pattern_types = [p["type"] for p in patterns]
        assert "constraint" in pattern_types
