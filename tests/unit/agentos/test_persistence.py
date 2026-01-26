"""Tests for AgentOS persistence module."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from dmm.agentos.persistence.models import (
    AgentState,
    AgentStatus,
    MessageDirection,
    MessageRecord,
    ModificationLevel,
    ModificationRecord,
    ModificationStatus,
    SessionRecord,
)
from dmm.agentos.persistence.store import AgentOSStore, AgentOSStoreError


class TestAgentState:
    """Tests for AgentState model."""

    def test_create_agent_state(self) -> None:
        """Create agent state with defaults."""
        state = AgentState(
            agent_id="agent_001",
            session_id="session_001",
        )
        
        assert state.agent_id == "agent_001"
        assert state.session_id == "session_001"
        assert state.status == AgentStatus.IDLE
        assert state.tokens_used == 0

    def test_to_dict(self) -> None:
        """Convert to dictionary."""
        state = AgentState(
            agent_id="agent_001",
            session_id="session_001",
            status=AgentStatus.BUSY,
            tokens_used=100,
        )
        
        data = state.to_dict()
        
        assert data["agent_id"] == "agent_001"
        assert data["status"] == "busy"
        assert data["tokens_used"] == 100

    def test_from_dict(self) -> None:
        """Create from dictionary."""
        data = {
            "agent_id": "agent_001",
            "session_id": "session_001",
            "status": "busy",
            "tokens_used": 100,
            "created_at": "2026-01-25T12:00:00",
            "updated_at": "2026-01-25T12:00:00",
        }
        
        state = AgentState.from_dict(data)
        
        assert state.agent_id == "agent_001"
        assert state.status == AgentStatus.BUSY


class TestMessageRecord:
    """Tests for MessageRecord model."""

    def test_create_message(self) -> None:
        """Create message record."""
        message = MessageRecord(
            message_id="msg_001",
            session_id="session_001",
            sender_id="agent_001",
            recipient_id="agent_002",
            message_type="request",
            direction=MessageDirection.OUTBOUND,
            content={"task": "review code"},
        )
        
        assert message.message_id == "msg_001"
        assert message.direction == MessageDirection.OUTBOUND

    def test_to_dict(self) -> None:
        """Convert to dictionary."""
        message = MessageRecord(
            message_id="msg_001",
            session_id="session_001",
            sender_id="agent_001",
            recipient_id="agent_002",
            message_type="request",
            direction=MessageDirection.OUTBOUND,
            content={"task": "test"},
        )
        
        data = message.to_dict()
        
        assert data["message_id"] == "msg_001"
        assert data["direction"] == "outbound"


class TestModificationRecord:
    """Tests for ModificationRecord model."""

    def test_create_modification(self) -> None:
        """Create modification record."""
        mod = ModificationRecord(
            modification_id="mod_001",
            session_id="session_001",
            agent_id="agent_001",
            level=ModificationLevel.LOGGED,
            status=ModificationStatus.PENDING,
            target_type="skill",
            target_id="skill_001",
            description="Update skill parameters",
        )
        
        assert mod.modification_id == "mod_001"
        assert mod.level == ModificationLevel.LOGGED
        assert mod.status == ModificationStatus.PENDING


class TestSessionRecord:
    """Tests for SessionRecord model."""

    def test_create_session(self) -> None:
        """Create session record."""
        session = SessionRecord(
            session_id="session_001",
            primary_agent_id="agent_001",
        )
        
        assert session.session_id == "session_001"
        assert session.is_active is True

    def test_session_duration(self) -> None:
        """Calculate session duration."""
        now = datetime.now()
        session = SessionRecord(
            session_id="session_001",
            started_at=now - timedelta(hours=1),
            ended_at=now,
        )
        
        assert session.is_active is False
        assert session.duration_seconds is not None
        assert 3599 <= session.duration_seconds <= 3601


class TestAgentOSStore:
    """Tests for AgentOSStore."""

    @pytest.fixture
    def store(self) -> AgentOSStore:
        """Create a temporary store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "agentos.db"
            store = AgentOSStore(db_path)
            store.initialize()
            yield store
            store.close()

    # Agent State Tests
    
    def test_save_and_get_agent_state(self, store: AgentOSStore) -> None:
        """Save and retrieve agent state."""
        state = AgentState(
            agent_id="agent_001",
            session_id="session_001",
            status=AgentStatus.BUSY,
            tokens_used=500,
        )
        
        store.save_agent_state(state)
        
        retrieved = store.get_agent_state("agent_001", "session_001")
        
        assert retrieved is not None
        assert retrieved.agent_id == "agent_001"
        assert retrieved.status == AgentStatus.BUSY
        assert retrieved.tokens_used == 500

    def test_get_nonexistent_agent_state(self, store: AgentOSStore) -> None:
        """Get returns None for nonexistent state."""
        result = store.get_agent_state("nonexistent", "session")
        assert result is None

    def test_update_agent_state(self, store: AgentOSStore) -> None:
        """Update existing agent state."""
        state = AgentState(
            agent_id="agent_001",
            session_id="session_001",
            tokens_used=100,
        )
        store.save_agent_state(state)
        
        state.tokens_used = 200
        store.save_agent_state(state)
        
        retrieved = store.get_agent_state("agent_001", "session_001")
        assert retrieved.tokens_used == 200

    def test_update_agent_status(self, store: AgentOSStore) -> None:
        """Update agent status directly."""
        state = AgentState(
            agent_id="agent_001",
            session_id="session_001",
        )
        store.save_agent_state(state)
        
        store.update_agent_status(
            "agent_001",
            "session_001",
            AgentStatus.ERROR,
            error_message="Test error",
        )
        
        retrieved = store.get_agent_state("agent_001", "session_001")
        assert retrieved.status == AgentStatus.ERROR
        assert retrieved.error_message == "Test error"

    def test_get_agent_states_for_session(self, store: AgentOSStore) -> None:
        """Get all agent states for a session."""
        for i in range(3):
            state = AgentState(
                agent_id=f"agent_{i}",
                session_id="session_001",
            )
            store.save_agent_state(state)
        
        states = store.get_agent_states_for_session("session_001")
        assert len(states) == 3

    # Message Tests
    
    def test_save_and_get_message(self, store: AgentOSStore) -> None:
        """Save and retrieve message."""
        message = MessageRecord(
            message_id="msg_001",
            session_id="session_001",
            sender_id="agent_001",
            recipient_id="agent_002",
            message_type="request",
            direction=MessageDirection.OUTBOUND,
            content={"task": "test"},
        )
        
        store.save_message(message)
        
        messages = store.get_messages_for_session("session_001")
        
        assert len(messages) == 1
        assert messages[0].message_id == "msg_001"
        assert messages[0].content == {"task": "test"}

    def test_get_messages_for_agent(self, store: AgentOSStore) -> None:
        """Get messages for an agent."""
        for i in range(3):
            message = MessageRecord(
                message_id=f"msg_{i}",
                session_id="session_001",
                sender_id="agent_001" if i % 2 == 0 else "agent_002",
                recipient_id="agent_002" if i % 2 == 0 else "agent_001",
                message_type="request",
                direction=MessageDirection.OUTBOUND if i % 2 == 0 else MessageDirection.INBOUND,
                content={},
            )
            store.save_message(message)
        
        messages = store.get_messages_for_agent("agent_001")
        assert len(messages) == 3

    def test_mark_message_delivered(self, store: AgentOSStore) -> None:
        """Mark message as delivered."""
        message = MessageRecord(
            message_id="msg_001",
            session_id="session_001",
            sender_id="agent_001",
            recipient_id="agent_002",
            message_type="request",
            direction=MessageDirection.OUTBOUND,
            content={},
        )
        store.save_message(message)
        
        store.mark_message_delivered("msg_001")
        
        messages = store.get_messages_for_session("session_001")
        assert messages[0].delivered_at is not None

    def test_mark_message_read(self, store: AgentOSStore) -> None:
        """Mark message as read."""
        message = MessageRecord(
            message_id="msg_001",
            session_id="session_001",
            sender_id="agent_001",
            recipient_id="agent_002",
            message_type="request",
            direction=MessageDirection.OUTBOUND,
            content={},
        )
        store.save_message(message)
        
        store.mark_message_read("msg_001")
        
        messages = store.get_messages_for_session("session_001")
        assert messages[0].read_at is not None

    # Modification Tests
    
    def test_save_and_get_modification(self, store: AgentOSStore) -> None:
        """Save and retrieve modification."""
        mod = ModificationRecord(
            modification_id="mod_001",
            session_id="session_001",
            agent_id="agent_001",
            level=ModificationLevel.LOGGED,
            status=ModificationStatus.PENDING,
            target_type="skill",
            target_id="skill_001",
            description="Update skill",
        )
        
        store.save_modification(mod)
        
        retrieved = store.get_modification("mod_001")
        
        assert retrieved is not None
        assert retrieved.modification_id == "mod_001"
        assert retrieved.level == ModificationLevel.LOGGED

    def test_get_pending_modifications(self, store: AgentOSStore) -> None:
        """Get pending modifications."""
        for i, level in enumerate([
            ModificationLevel.AUTOMATIC,
            ModificationLevel.LOGGED,
            ModificationLevel.HUMAN_REQUIRED,
        ]):
            mod = ModificationRecord(
                modification_id=f"mod_{i}",
                session_id="session_001",
                agent_id="agent_001",
                level=level,
                status=ModificationStatus.PENDING,
                target_type="skill",
                target_id=f"skill_{i}",
                description=f"Mod {i}",
            )
            store.save_modification(mod)
        
        pending = store.get_pending_modifications()
        assert len(pending) == 3
        
        human_required = store.get_pending_modifications(
            level=ModificationLevel.HUMAN_REQUIRED
        )
        assert len(human_required) == 1

    def test_update_modification_status(self, store: AgentOSStore) -> None:
        """Update modification status."""
        mod = ModificationRecord(
            modification_id="mod_001",
            session_id="session_001",
            agent_id="agent_001",
            level=ModificationLevel.HUMAN_REQUIRED,
            status=ModificationStatus.PENDING,
            target_type="behavior",
            target_id="behavior_001",
            description="Change behavior",
        )
        store.save_modification(mod)
        
        store.update_modification_status(
            "mod_001",
            ModificationStatus.APPROVED,
            reviewed_by="human_reviewer",
        )
        
        retrieved = store.get_modification("mod_001")
        assert retrieved.status == ModificationStatus.APPROVED
        assert retrieved.reviewed_by == "human_reviewer"
        assert retrieved.reviewed_at is not None

    # Session Tests
    
    def test_create_and_get_session(self, store: AgentOSStore) -> None:
        """Create and retrieve session."""
        session = SessionRecord(
            session_id="session_001",
            primary_agent_id="agent_001",
            active_agents=["agent_001", "agent_002"],
        )
        
        store.create_session(session)
        
        retrieved = store.get_session("session_001")
        
        assert retrieved is not None
        assert retrieved.session_id == "session_001"
        assert retrieved.is_active is True
        assert len(retrieved.active_agents) == 2

    def test_get_active_sessions(self, store: AgentOSStore) -> None:
        """Get active sessions."""
        for i in range(3):
            session = SessionRecord(
                session_id=f"session_{i}",
                ended_at=datetime.now() if i == 0 else None,
            )
            store.create_session(session)
        
        active = store.get_active_sessions()
        assert len(active) == 2

    def test_end_session(self, store: AgentOSStore) -> None:
        """End a session."""
        session = SessionRecord(session_id="session_001")
        store.create_session(session)
        
        store.end_session("session_001")
        
        retrieved = store.get_session("session_001")
        assert retrieved.is_active is False
        assert retrieved.ended_at is not None

    def test_update_session_stats(self, store: AgentOSStore) -> None:
        """Update session statistics."""
        session = SessionRecord(session_id="session_001")
        store.create_session(session)
        
        store.update_session_stats(
            "session_001",
            tasks_created=5,
            tasks_completed=3,
            messages_sent=10,
            total_tokens=5000,
        )
        
        retrieved = store.get_session("session_001")
        assert retrieved.tasks_created == 5
        assert retrieved.tasks_completed == 3
        assert retrieved.messages_sent == 10
        assert retrieved.total_tokens == 5000

    # Utility Tests
    
    def test_get_stats(self, store: AgentOSStore) -> None:
        """Get store statistics."""
        # Create some data
        store.save_agent_state(AgentState(
            agent_id="agent_001",
            session_id="session_001",
        ))
        store.create_session(SessionRecord(session_id="session_001"))
        
        stats = store.get_stats()
        
        assert stats["agent_states"] == 1
        assert stats["sessions"] == 1
        assert stats["active_sessions"] == 1

    def test_cleanup_old_data(self, store: AgentOSStore) -> None:
        """Clean up old data."""
        old_time = datetime.now() - timedelta(days=60)
        
        # Create old session
        old_session = SessionRecord(
            session_id="old_session",
            started_at=old_time,
            ended_at=old_time + timedelta(hours=1),
        )
        store.create_session(old_session)
        
        # Create recent session
        store.create_session(SessionRecord(session_id="new_session"))
        
        deleted = store.cleanup_old_data(days=30)
        
        assert deleted["sessions"] == 1
        assert store.get_session("old_session") is None
        assert store.get_session("new_session") is not None
