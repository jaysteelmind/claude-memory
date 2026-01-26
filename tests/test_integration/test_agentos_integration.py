"""Integration tests for AgentOS components.

These tests verify end-to-end workflows across multiple AgentOS
components working together.
"""

import tempfile
from datetime import datetime, timezone
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
from dmm.agentos.persistence.store import AgentOSStore


class TestSessionLifecycleIntegration:
    """Integration tests for complete session lifecycle."""

    @pytest.fixture
    def store(self) -> AgentOSStore:
        """Create a temporary store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "agentos.db"
            store = AgentOSStore(db_path)
            store.initialize()
            yield store
            store.close()

    def test_complete_session_lifecycle(self, store: AgentOSStore) -> None:
        """Test a complete session from start to end."""
        # 1. Create session
        session = SessionRecord(
            session_id="session_integration_001",
            primary_agent_id="agent_coordinator",
            active_agents=["agent_coordinator", "agent_worker"],
            metadata={"purpose": "integration_test"},
        )
        store.create_session(session)
        
        # Verify session is active
        active_sessions = store.get_active_sessions()
        assert len(active_sessions) == 1
        assert active_sessions[0].session_id == "session_integration_001"
        
        # 2. Initialize agent states
        for agent_id in ["agent_coordinator", "agent_worker"]:
            state = AgentState(
                agent_id=agent_id,
                session_id="session_integration_001",
                status=AgentStatus.IDLE,
            )
            store.save_agent_state(state)
        
        # 3. Coordinator starts working
        store.update_agent_status(
            "agent_coordinator",
            "session_integration_001",
            AgentStatus.BUSY,
        )
        
        # 4. Coordinator sends message to worker
        message = MessageRecord(
            message_id="msg_001",
            session_id="session_integration_001",
            sender_id="agent_coordinator",
            recipient_id="agent_worker",
            message_type="delegate",
            direction=MessageDirection.OUTBOUND,
            content={"task": "process_data", "priority": "high"},
        )
        store.save_message(message)
        
        # 5. Worker receives and processes
        store.mark_message_delivered("msg_001")
        store.update_agent_status(
            "agent_worker",
            "session_integration_001",
            AgentStatus.BUSY,
        )
        
        # Worker reads message
        store.mark_message_read("msg_001")
        
        # 6. Worker sends response
        response = MessageRecord(
            message_id="msg_002",
            session_id="session_integration_001",
            sender_id="agent_worker",
            recipient_id="agent_coordinator",
            message_type="response",
            direction=MessageDirection.OUTBOUND,
            content={"status": "completed", "result": "success"},
            correlation_id="msg_001",
        )
        store.save_message(response)
        
        # 7. Update session stats
        store.update_session_stats(
            "session_integration_001",
            tasks_created=1,
            tasks_completed=1,
            messages_sent=2,
            total_tokens=500,
        )
        
        # 8. Agents return to idle
        for agent_id in ["agent_coordinator", "agent_worker"]:
            store.update_agent_status(
                agent_id,
                "session_integration_001",
                AgentStatus.IDLE,
            )
        
        # 9. End session
        store.end_session("session_integration_001")
        
        # Verify final state
        final_session = store.get_session("session_integration_001")
        assert final_session.is_active is False
        assert final_session.tasks_completed == 1
        assert final_session.messages_sent == 2
        
        messages = store.get_messages_for_session("session_integration_001")
        assert len(messages) == 2
        
        # Verify message delivery chain
        delivered = [m for m in messages if m.delivered_at is not None]
        assert len(delivered) >= 1


class TestMultiAgentCollaborationIntegration:
    """Integration tests for multi-agent collaboration patterns."""

    @pytest.fixture
    def store(self) -> AgentOSStore:
        """Create a temporary store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "agentos.db"
            store = AgentOSStore(db_path)
            store.initialize()
            yield store
            store.close()

    def test_broadcast_message_pattern(self, store: AgentOSStore) -> None:
        """Test broadcast message to multiple agents."""
        # Setup session with multiple agents
        session = SessionRecord(
            session_id="session_broadcast",
            primary_agent_id="agent_broadcaster",
            active_agents=["agent_broadcaster", "agent_a", "agent_b", "agent_c"],
        )
        store.create_session(session)
        
        # Initialize all agents
        for agent_id in session.active_agents:
            store.save_agent_state(AgentState(
                agent_id=agent_id,
                session_id="session_broadcast",
            ))
        
        # Broadcast message
        for i, recipient in enumerate(["agent_a", "agent_b", "agent_c"]):
            message = MessageRecord(
                message_id=f"broadcast_{i}",
                session_id="session_broadcast",
                sender_id="agent_broadcaster",
                recipient_id=recipient,
                message_type="broadcast",
                direction=MessageDirection.OUTBOUND,
                content={"announcement": "System update"},
                correlation_id="broadcast_group_001",
            )
            store.save_message(message)
        
        # Verify all messages sent
        messages = store.get_messages_for_agent("agent_broadcaster")
        assert len(messages) == 3
        
        # Each recipient should have 1 message
        for recipient in ["agent_a", "agent_b", "agent_c"]:
            messages = store.get_messages_for_agent(recipient)
            assert len(messages) == 1

    def test_request_response_chain(self, store: AgentOSStore) -> None:
        """Test request-response message chain."""
        session = SessionRecord(
            session_id="session_chain",
            active_agents=["agent_1", "agent_2", "agent_3"],
        )
        store.create_session(session)
        
        # Chain: agent_1 -> agent_2 -> agent_3 -> agent_2 -> agent_1
        messages = [
            ("agent_1", "agent_2", "request", "req_001", None),
            ("agent_2", "agent_3", "delegate", "req_002", "req_001"),
            ("agent_3", "agent_2", "response", "resp_001", "req_002"),
            ("agent_2", "agent_1", "response", "resp_002", "req_001"),
        ]
        
        for i, (sender, recipient, msg_type, msg_id, corr_id) in enumerate(messages):
            message = MessageRecord(
                message_id=msg_id,
                session_id="session_chain",
                sender_id=sender,
                recipient_id=recipient,
                message_type=msg_type,
                direction=MessageDirection.OUTBOUND,
                content={"step": i},
                correlation_id=corr_id,
            )
            store.save_message(message)
        
        # Verify chain
        all_messages = store.get_messages_for_session("session_chain")
        assert len(all_messages) == 4
        
        # Verify correlation
        correlated = [m for m in all_messages if m.correlation_id == "req_001"]
        assert len(correlated) == 2


class TestSelfModificationWorkflowIntegration:
    """Integration tests for self-modification approval workflow."""

    @pytest.fixture
    def store(self) -> AgentOSStore:
        """Create a temporary store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "agentos.db"
            store = AgentOSStore(db_path)
            store.initialize()
            yield store
            store.close()

    def test_automatic_modification_workflow(self, store: AgentOSStore) -> None:
        """Test automatic (level 1) modification workflow."""
        # Create modification request
        mod = ModificationRecord(
            modification_id="mod_auto_001",
            session_id="session_001",
            agent_id="agent_001",
            level=ModificationLevel.AUTOMATIC,
            status=ModificationStatus.PENDING,
            target_type="memory",
            target_id="mem_001",
            description="Update memory content",
            diff={"old": "value1", "new": "value2"},
            reason="Outdated information",
        )
        store.save_modification(mod)
        
        # Automatic approval (no human review needed)
        store.update_modification_status(
            "mod_auto_001",
            ModificationStatus.APPROVED,
            reviewed_by="system",
        )
        
        # Apply modification
        store.update_modification_status(
            "mod_auto_001",
            ModificationStatus.APPLIED,
        )
        
        # Verify
        final = store.get_modification("mod_auto_001")
        assert final.status == ModificationStatus.APPLIED
        assert final.applied_at is not None

    def test_human_required_modification_workflow(self, store: AgentOSStore) -> None:
        """Test human-required (level 3+) modification workflow."""
        # Create modification request
        mod = ModificationRecord(
            modification_id="mod_human_001",
            session_id="session_001",
            agent_id="agent_001",
            level=ModificationLevel.HUMAN_REQUIRED,
            status=ModificationStatus.PENDING,
            target_type="behavior",
            target_id="behavior_risk_tolerance",
            description="Increase risk tolerance",
            diff={"old": 0.3, "new": 0.7},
            reason="User requested more aggressive behavior",
        )
        store.save_modification(mod)
        
        # Verify pending
        pending = store.get_pending_modifications(
            level=ModificationLevel.HUMAN_REQUIRED
        )
        assert len(pending) == 1
        
        # Human rejects
        store.update_modification_status(
            "mod_human_001",
            ModificationStatus.REJECTED,
            reviewed_by="human_admin",
        )
        
        # Verify rejected
        final = store.get_modification("mod_human_001")
        assert final.status == ModificationStatus.REJECTED
        assert final.reviewed_by == "human_admin"
        assert final.reviewed_at is not None
        assert final.applied_at is None

    def test_modification_rollback_workflow(self, store: AgentOSStore) -> None:
        """Test modification rollback workflow."""
        # Create and apply modification
        mod = ModificationRecord(
            modification_id="mod_rollback_001",
            session_id="session_001",
            agent_id="agent_001",
            level=ModificationLevel.LOGGED,
            status=ModificationStatus.PENDING,
            target_type="skill",
            target_id="skill_001",
            description="Update skill parameters",
            diff={"timeout": {"old": 30, "new": 60}},
        )
        store.save_modification(mod)
        
        # Approve and apply
        store.update_modification_status(
            "mod_rollback_001",
            ModificationStatus.APPROVED,
            reviewed_by="system",
        )
        store.update_modification_status(
            "mod_rollback_001",
            ModificationStatus.APPLIED,
        )
        
        # Rollback
        store.update_modification_status(
            "mod_rollback_001",
            ModificationStatus.ROLLED_BACK,
        )
        
        # Verify
        final = store.get_modification("mod_rollback_001")
        assert final.status == ModificationStatus.ROLLED_BACK
        assert final.rollback_at is not None


class TestPersistenceRecoveryIntegration:
    """Integration tests for persistence and recovery scenarios."""

    def test_store_survives_close_and_reopen(self) -> None:
        """Test that data persists across store close/reopen."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "agentos.db"
            
            # First session: create data
            store1 = AgentOSStore(db_path)
            store1.initialize()
            
            session = SessionRecord(
                session_id="persistent_session",
                primary_agent_id="agent_001",
            )
            store1.create_session(session)
            
            state = AgentState(
                agent_id="agent_001",
                session_id="persistent_session",
                tokens_used=1000,
            )
            store1.save_agent_state(state)
            
            store1.close()
            
            # Second session: verify data
            store2 = AgentOSStore(db_path)
            store2.initialize()
            
            recovered_session = store2.get_session("persistent_session")
            assert recovered_session is not None
            assert recovered_session.primary_agent_id == "agent_001"
            
            recovered_state = store2.get_agent_state("agent_001", "persistent_session")
            assert recovered_state is not None
            assert recovered_state.tokens_used == 1000
            
            store2.close()

    def test_concurrent_session_handling(self) -> None:
        """Test multiple concurrent sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "agentos.db"
            store = AgentOSStore(db_path)
            store.initialize()
            
            # Create multiple concurrent sessions
            for i in range(5):
                session = SessionRecord(
                    session_id=f"concurrent_{i}",
                    primary_agent_id=f"agent_{i}",
                )
                store.create_session(session)
                
                state = AgentState(
                    agent_id=f"agent_{i}",
                    session_id=f"concurrent_{i}",
                )
                store.save_agent_state(state)
            
            # Verify all active
            active = store.get_active_sessions()
            assert len(active) == 5
            
            # End some sessions
            for i in range(3):
                store.end_session(f"concurrent_{i}")
            
            # Verify active count
            active = store.get_active_sessions()
            assert len(active) == 2
            
            store.close()


class TestExampleAgentsIntegration:
    """Integration tests using the example agents."""

    def test_code_review_agent_basic(self) -> None:
        """Test CodeReviewAgent basic functionality."""
        from examples.agents.code_review_agent import (
            CodeReviewAgent,
            CodeReviewAgentConfig,
        )
        
        agent = CodeReviewAgent(CodeReviewAgentConfig(
            max_line_length=100,
            check_docstrings=True,
        ))
        
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write('''"""Test module."""

def hello(name: str) -> str:
    """Say hello."""
    return f"Hello, {name}!"
''')
            f.flush()
            
            result = agent.review_file(f.name)
            
            assert result.metrics["function_count"] == 1
            assert "hello" in result.summary.lower() or "PASS" in result.summary

    def test_task_manager_agent_workflow(self) -> None:
        """Test TaskManagerAgent workflow."""
        from examples.agents.task_manager_agent import (
            TaskManagerAgent,
            TaskPriority,
            TaskStatus,
        )
        
        agent = TaskManagerAgent()
        
        # Create main task
        main = agent.create_task(
            name="Review Project",
            description="Review the entire project",
            priority=TaskPriority.HIGH,
        )
        
        # Decompose
        subtasks = agent.decompose_task(
            main.task_id,
            subtask_definitions=[
                {"name": "Analyze", "description": "Analyze code"},
                {"name": "Report", "description": "Generate report"},
            ],
        )
        
        assert len(subtasks) == 2
        assert all(st.parent_id == main.task_id for st in subtasks)
        
        # Execute subtasks
        for st in subtasks:
            agent.start_task(st.task_id)
            agent.complete_task(st.task_id)
        
        # Verify progress
        assert main.progress == 1.0

    def test_research_assistant_workflow(self) -> None:
        """Test ResearchAssistantAgent workflow."""
        from examples.agents.research_assistant_agent import (
            ResearchAssistantAgent,
            ResearchDepth,
        )
        
        agent = ResearchAssistantAgent()
        
        report = agent.research(
            query="What are Python best practices?",
            depth=ResearchDepth.STANDARD,
        )
        
        assert report.query == "What are Python best practices?"
        assert len(report.questions) > 1
        assert report.synthesis is not None
        
        # Generate markdown
        markdown = agent.generate_report_markdown(report)
        assert "# " in markdown
        assert "Python" in markdown or "python" in markdown


class TestWorkflowsIntegration:
    """Integration tests for example workflows."""

    def test_code_review_pipeline_on_examples(self) -> None:
        """Test code review pipeline on examples directory."""
        from examples.workflows.code_review_pipeline import run_code_review_pipeline
        
        result = run_code_review_pipeline(
            target_path="examples/agents",
            recursive=False,
        )
        
        assert result["success"] is True
        assert result["files_reviewed"] >= 1
        assert "report" in result
        assert "# Code Review Report" in result["report"]

    def test_system_maintenance_workflow(self) -> None:
        """Test system maintenance workflow."""
        from examples.workflows.system_maintenance import run_system_maintenance
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_system_maintenance(
                memory_dir=Path(tmpdir),
                auto_fix=False,
            )
            
            assert result["success"] is True
            assert "health_status" in result
            assert "recommendations" in result
            assert len(result["recommendations"]) >= 1
