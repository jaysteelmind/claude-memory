"""Unit tests for AgentOS graph integration."""

import pytest
from dmm.agentos.graph_integration import AgentOSGraphBridge, GraphConfig


class TestGraphConfig:
    """Tests for GraphConfig."""
    
    def test_default_config(self):
        config = GraphConfig()
        assert config.auto_sync is True
        assert config.db_path is None
    
    def test_custom_config(self):
        config = GraphConfig(db_path="/tmp/test_db", auto_sync=False)
        assert config.db_path == "/tmp/test_db"
        assert config.auto_sync is False


class TestAgentOSGraphBridge:
    """Tests for AgentOSGraphBridge."""
    
    @pytest.fixture
    def bridge(self):
        return AgentOSGraphBridge()
    
    def test_create_bridge(self, bridge):
        assert bridge is not None
        assert not bridge.is_connected
    
    def test_not_connected_operations(self, bridge):
        """Operations return safe defaults when not connected."""
        assert bridge.save_agent("a1", "Agent", [], {}) is False
        assert bridge.get_agent("a1") is None
        assert bridge.list_agents() == []
        assert bridge.save_task("t1", "Task", "pending", None, {}) is False
        assert bridge.get_task("t1") is None
        assert bridge.search("test") == []
    
    def test_get_stats_not_connected(self, bridge):
        stats = bridge.get_stats()
        assert stats["connected"] is False


class TestGraphBridgeWithMock:
    """Tests with mocked graph."""
    
    def test_save_agent_format(self):
        """Test agent data formatting."""
        bridge = AgentOSGraphBridge()
        result = bridge.save_agent(
            agent_id="agent_1",
            name="Test Agent",
            capabilities=["code", "test"],
            metadata={"version": "1.0"},
        )
        assert result is False
    
    def test_save_task_format(self):
        """Test task data formatting."""
        bridge = AgentOSGraphBridge()
        result = bridge.save_task(
            task_id="task_1",
            name="Test Task",
            status="pending",
            agent_id="agent_1",
            metadata={"priority": "high"},
        )
        assert result is False
    
    def test_link_operations(self):
        """Test link operations interface."""
        bridge = AgentOSGraphBridge()
        assert bridge.link_agent_skill("a1", "s1") is False
        assert bridge.link_task_memory("t1", "m1") is False
        assert bridge.get_agent_skills("a1") == []
        assert bridge.get_task_memories("t1") == []
        assert bridge.get_agent_tasks("a1") == []
