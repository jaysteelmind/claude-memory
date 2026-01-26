"""Unit tests for AgentOS CLI commands."""

import pytest
from typer.testing import CliRunner
from dmm.cli.main import app

runner = CliRunner()


class TestAgentOSCLI:
    """Tests for AgentOS CLI."""
    
    def test_agentos_help(self):
        """Test agentos help shows."""
        result = runner.invoke(app, ["agentos", "--help"])
        assert result.exit_code == 0
        assert "AgentOS" in result.stdout or "agent" in result.stdout.lower()
    
    def test_agent_list(self):
        """Test agent list command."""
        result = runner.invoke(app, ["agentos", "agent", "list"])
        # May show empty or list - should not error
        assert result.exit_code == 0
    
    def test_task_list(self):
        """Test task list command."""
        result = runner.invoke(app, ["agentos", "task", "list"])
        assert result.exit_code == 0
    
    def test_skill_list(self):
        """Test skill list command."""
        result = runner.invoke(app, ["agentos", "skill", "list"])
        assert result.exit_code == 0
    
    def test_system_status(self):
        """Test system status command."""
        result = runner.invoke(app, ["agentos", "system", "status"])
        assert result.exit_code == 0
        assert "Status" in result.stdout or "status" in result.stdout.lower()
    
    def test_system_stats(self):
        """Test system stats command."""
        result = runner.invoke(app, ["agentos", "system", "stats"])
        assert result.exit_code == 0
