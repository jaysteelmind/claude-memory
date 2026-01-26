"""
Unit tests for collaboration patterns.

Tests cover:
- Task delegation
- Assistance requests
- Consensus building
- Workflow coordination
"""

import pytest
from datetime import datetime

from dmm.agentos.communication import (
    MessageBus,
    Message,
    MessageType,
    TaskContent,
    CollaborationCoordinator,
    CollaborationStatus,
    DelegationResult,
    DelegationRecord,
    AssistanceRequest,
    ConsensusRound,
)


@pytest.fixture
def bus():
    """Create message bus with registered agents."""
    bus = MessageBus()
    bus.register_agent("coordinator")
    bus.register_agent("worker_1")
    bus.register_agent("worker_2")
    bus.register_agent("worker_3")
    return bus


@pytest.fixture
def coordinator(bus):
    """Create collaboration coordinator."""
    return CollaborationCoordinator(bus)


@pytest.fixture
def sample_task():
    """Create sample task content."""
    return TaskContent(
        task_id="task_123",
        task_name="Review Code",
        task_description="Review the authentication module",
        inputs={"file": "auth.py"},
    )


class TestDelegationRecord:
    """Tests for DelegationRecord."""
    
    def test_create_record(self, sample_task):
        """Test creating delegation record."""
        record = DelegationRecord(
            id="del_123",
            delegator="coordinator",
            delegate="worker_1",
            task=sample_task,
            reason="Load balancing",
        )
        
        assert record.delegator == "coordinator"
        assert record.delegate == "worker_1"
        assert record.status == CollaborationStatus.PENDING
    
    def test_is_complete(self, sample_task):
        """Test completion check."""
        record = DelegationRecord(
            id="del_123",
            delegator="coordinator",
            delegate="worker_1",
            task=sample_task,
        )
        
        assert not record.is_complete()
        
        record.status = CollaborationStatus.COMPLETED
        assert record.is_complete()
    
    def test_to_dict(self, sample_task):
        """Test serialization."""
        record = DelegationRecord(
            id="del_123",
            delegator="coordinator",
            delegate="worker_1",
            task=sample_task,
        )
        
        data = record.to_dict()
        
        assert data["id"] == "del_123"
        assert data["delegator"] == "coordinator"
        assert "task" in data


class TestAssistanceRequest:
    """Tests for AssistanceRequest."""
    
    def test_create_request(self):
        """Test creating assistance request."""
        request = AssistanceRequest(
            id="assist_123",
            requester="worker_1",
            query="How do I implement X?",
            context={"language": "Python"},
        )
        
        assert request.requester == "worker_1"
        assert request.query == "How do I implement X?"
        assert request.status == CollaborationStatus.PENDING
    
    def test_to_dict(self):
        """Test serialization."""
        request = AssistanceRequest(
            id="assist_123",
            requester="worker_1",
            query="Help needed",
        )
        
        data = request.to_dict()
        
        assert data["id"] == "assist_123"
        assert data["requester"] == "worker_1"


class TestConsensusRound:
    """Tests for ConsensusRound."""
    
    def test_create_round(self):
        """Test creating consensus round."""
        consensus = ConsensusRound(
            id="cons_123",
            initiator="coordinator",
            topic="Adopt new coding standard",
            proposal={"standard": "PEP8"},
            participants=["worker_1", "worker_2", "worker_3"],
            threshold=0.67,
        )
        
        assert consensus.initiator == "coordinator"
        assert len(consensus.participants) == 3
        assert consensus.threshold == 0.67
    
    def test_record_vote(self):
        """Test recording votes."""
        consensus = ConsensusRound(
            id="cons_123",
            initiator="coordinator",
            topic="Test",
            proposal={},
            participants=["worker_1", "worker_2"],
        )
        
        consensus.record_vote("worker_1", True, "I agree")
        consensus.record_vote("worker_2", False, "I disagree")
        
        assert consensus.votes["worker_1"] is True
        assert consensus.votes["worker_2"] is False
        assert consensus.comments["worker_1"] == "I agree"
    
    def test_get_result(self):
        """Test getting consensus result."""
        consensus = ConsensusRound(
            id="cons_123",
            initiator="coordinator",
            topic="Test",
            proposal={},
            participants=["worker_1", "worker_2", "worker_3"],
            threshold=0.5,
        )
        
        # Not complete yet
        assert consensus.get_result() is None
        
        # Add votes
        consensus.record_vote("worker_1", True)
        consensus.record_vote("worker_2", True)
        consensus.record_vote("worker_3", False)
        
        # 2/3 voted yes, threshold is 0.5
        assert consensus.get_result() is True
    
    def test_is_complete(self):
        """Test completion check."""
        consensus = ConsensusRound(
            id="cons_123",
            initiator="coordinator",
            topic="Test",
            proposal={},
            participants=["worker_1", "worker_2"],
        )
        
        assert not consensus.is_complete()
        
        consensus.record_vote("worker_1", True)
        assert not consensus.is_complete()
        
        consensus.record_vote("worker_2", True)
        assert consensus.is_complete()


class TestTaskDelegation:
    """Tests for task delegation."""
    
    def test_delegate_task(self, coordinator, sample_task):
        """Test delegating a task."""
        record = coordinator.delegate_task(
            delegator="coordinator",
            delegate="worker_1",
            task=sample_task,
            reason="Expertise match",
        )
        
        assert record is not None
        assert record.delegator == "coordinator"
        assert record.delegate == "worker_1"
        assert record.status == CollaborationStatus.WAITING_RESPONSE
    
    def test_accept_delegation(self, coordinator, sample_task):
        """Test accepting a delegation."""
        record = coordinator.delegate_task(
            delegator="coordinator",
            delegate="worker_1",
            task=sample_task,
        )
        
        assert coordinator.accept_delegation(record.id, "worker_1")
        
        updated = coordinator.get_delegation(record.id)
        assert updated.result == DelegationResult.ACCEPTED
        assert updated.status == CollaborationStatus.IN_PROGRESS
    
    def test_reject_delegation(self, coordinator, sample_task):
        """Test rejecting a delegation."""
        record = coordinator.delegate_task(
            delegator="coordinator",
            delegate="worker_1",
            task=sample_task,
        )
        
        assert coordinator.reject_delegation(
            record.id,
            "worker_1",
            reason="Too busy",
        )
        
        updated = coordinator.get_delegation(record.id)
        assert updated.result == DelegationResult.REJECTED
        assert updated.status == CollaborationStatus.FAILED
    
    def test_complete_delegation(self, coordinator, sample_task):
        """Test completing a delegation."""
        record = coordinator.delegate_task(
            delegator="coordinator",
            delegate="worker_1",
            task=sample_task,
        )
        coordinator.accept_delegation(record.id, "worker_1")
        
        assert coordinator.complete_delegation(
            record.id,
            "worker_1",
            result={"findings": ["Issue 1", "Issue 2"]},
            success=True,
        )
        
        updated = coordinator.get_delegation(record.id)
        assert updated.result == DelegationResult.COMPLETED
        assert updated.status == CollaborationStatus.COMPLETED
    
    def test_complete_delegation_failure(self, coordinator, sample_task):
        """Test completing delegation with failure."""
        record = coordinator.delegate_task(
            delegator="coordinator",
            delegate="worker_1",
            task=sample_task,
        )
        coordinator.accept_delegation(record.id, "worker_1")
        
        coordinator.complete_delegation(
            record.id,
            "worker_1",
            result="Error occurred",
            success=False,
        )
        
        updated = coordinator.get_delegation(record.id)
        assert updated.result == DelegationResult.FAILED
        assert updated.status == CollaborationStatus.FAILED
    
    def test_get_active_delegations(self, coordinator, sample_task):
        """Test getting active delegations."""
        coordinator.delegate_task(
            delegator="coordinator",
            delegate="worker_1",
            task=sample_task,
        )
        
        active = coordinator.get_active_delegations("coordinator")
        
        assert len(active) == 1


class TestAssistanceRequests:
    """Tests for assistance requests."""
    
    def test_request_assistance(self, coordinator):
        """Test requesting assistance."""
        request = coordinator.request_assistance(
            requester="worker_1",
            query="How do I implement authentication?",
            context={"language": "Python"},
            preferred_helpers=["worker_2", "worker_3"],
        )
        
        assert request is not None
        assert request.requester == "worker_1"
        assert request.status == CollaborationStatus.WAITING_RESPONSE
        assert "worker_2" in request.helpers_asked
    
    def test_provide_assistance(self, coordinator):
        """Test providing assistance."""
        request = coordinator.request_assistance(
            requester="worker_1",
            query="Help needed",
            preferred_helpers=["worker_2"],
        )
        
        assert coordinator.provide_assistance(
            request.id,
            "worker_2",
            response="Here's how you do it...",
        )
        
        updated = coordinator.get_assistance_request(request.id)
        assert updated.status == CollaborationStatus.COMPLETED
        assert updated.helper == "worker_2"
        assert updated.response == "Here's how you do it..."
    
    def test_request_no_helpers(self, bus):
        """Test request when no helpers available."""
        # Only register requester
        solo_bus = MessageBus()
        solo_bus.register_agent("lonely_agent")
        coord = CollaborationCoordinator(solo_bus)
        
        request = coord.request_assistance(
            requester="lonely_agent",
            query="Help?",
        )
        
        assert request.status == CollaborationStatus.FAILED


class TestConsensusBuilding:
    """Tests for consensus building."""
    
    def test_initiate_consensus(self, coordinator):
        """Test initiating consensus."""
        consensus = coordinator.initiate_consensus(
            initiator="coordinator",
            topic="Adopt new framework",
            proposal={"framework": "FastAPI"},
            participants=["worker_1", "worker_2", "worker_3"],
            threshold=0.67,
        )
        
        assert consensus is not None
        assert consensus.initiator == "coordinator"
        assert consensus.status == CollaborationStatus.WAITING_RESPONSE
        assert len(consensus.participants) == 3
    
    def test_cast_vote(self, coordinator):
        """Test casting a vote."""
        consensus = coordinator.initiate_consensus(
            initiator="coordinator",
            topic="Test vote",
            proposal={},
            participants=["worker_1", "worker_2"],
        )
        
        assert coordinator.cast_vote(
            consensus.id,
            "worker_1",
            vote=True,
            comment="I support this",
        )
        
        updated = coordinator.get_consensus_round(consensus.id)
        assert "worker_1" in updated.votes
        assert updated.votes["worker_1"] is True
    
    def test_consensus_reached(self, coordinator):
        """Test consensus completion."""
        consensus = coordinator.initiate_consensus(
            initiator="coordinator",
            topic="Quick decision",
            proposal={},
            participants=["worker_1", "worker_2"],
            threshold=0.5,
        )
        
        coordinator.cast_vote(consensus.id, "worker_1", True)
        coordinator.cast_vote(consensus.id, "worker_2", True)
        
        updated = coordinator.get_consensus_round(consensus.id)
        assert updated.status == CollaborationStatus.COMPLETED
        assert updated.get_result() is True
    
    def test_consensus_not_reached(self, coordinator):
        """Test consensus not reached."""
        consensus = coordinator.initiate_consensus(
            initiator="coordinator",
            topic="Controversial",
            proposal={},
            participants=["worker_1", "worker_2", "worker_3"],
            threshold=0.67,
        )
        
        coordinator.cast_vote(consensus.id, "worker_1", True)
        coordinator.cast_vote(consensus.id, "worker_2", False)
        coordinator.cast_vote(consensus.id, "worker_3", False)
        
        updated = coordinator.get_consensus_round(consensus.id)
        assert updated.get_result() is False  # 1/3 < 0.67
    
    def test_get_pending_consensus(self, coordinator):
        """Test getting pending consensus for agent."""
        coordinator.initiate_consensus(
            initiator="coordinator",
            topic="Pending vote",
            proposal={},
            participants=["worker_1", "worker_2"],
        )
        
        pending = coordinator.get_pending_consensus("worker_1")
        
        assert len(pending) == 1
    
    def test_duplicate_vote_rejected(self, coordinator):
        """Test duplicate vote is rejected."""
        consensus = coordinator.initiate_consensus(
            initiator="coordinator",
            topic="No duplicates",
            proposal={},
            participants=["worker_1"],
        )
        
        assert coordinator.cast_vote(consensus.id, "worker_1", True)
        assert not coordinator.cast_vote(consensus.id, "worker_1", False)


class TestWorkflowCoordination:
    """Tests for workflow coordination."""
    
    def test_broadcast_to_all(self, coordinator):
        """Test broadcasting to all agents."""
        count = coordinator.broadcast_to_all(
            sender="coordinator",
            subject="Announcement",
            content="Important update",
            tags=["announcement"],
        )
        
        # 3 workers registered (excluding coordinator)
        assert count == 3
    
    def test_notify_task_update(self, coordinator, sample_task, bus):
        """Test notifying task update."""
        sample_task.status = "in_progress"
        sample_task.progress = 50.0
        
        coordinator.notify_task_update(
            sender="worker_1",
            interested_agents=["coordinator", "worker_2"],
            task=sample_task,
        )
        
        # Check messages were sent
        assert bus.get_pending_count("coordinator") == 1
        assert bus.get_pending_count("worker_2") == 1


class TestCallbacks:
    """Tests for collaboration callbacks."""
    
    def test_delegation_complete_callback(self, coordinator, sample_task):
        """Test delegation complete callback."""
        completed_delegations = []
        
        coordinator.on_delegation_complete(
            lambda d: completed_delegations.append(d)
        )
        
        record = coordinator.delegate_task(
            delegator="coordinator",
            delegate="worker_1",
            task=sample_task,
        )
        coordinator.accept_delegation(record.id, "worker_1")
        coordinator.complete_delegation(record.id, "worker_1", "Done")
        
        assert len(completed_delegations) == 1
    
    def test_assistance_resolved_callback(self, coordinator):
        """Test assistance resolved callback."""
        resolved_requests = []
        
        coordinator.on_assistance_resolved(
            lambda r: resolved_requests.append(r)
        )
        
        request = coordinator.request_assistance(
            requester="worker_1",
            query="Help?",
            preferred_helpers=["worker_2"],
        )
        coordinator.provide_assistance(request.id, "worker_2", "Here's help")
        
        assert len(resolved_requests) == 1
    
    def test_consensus_reached_callback(self, coordinator):
        """Test consensus reached callback."""
        reached_consensus = []
        
        coordinator.on_consensus_reached(
            lambda c: reached_consensus.append(c)
        )
        
        consensus = coordinator.initiate_consensus(
            initiator="coordinator",
            topic="Quick",
            proposal={},
            participants=["worker_1"],
        )
        coordinator.cast_vote(consensus.id, "worker_1", True)
        
        assert len(reached_consensus) == 1
