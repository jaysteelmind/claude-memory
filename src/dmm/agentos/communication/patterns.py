"""
Collaboration patterns for multi-agent coordination.

This module provides high-level patterns for agent collaboration
including delegation, assistance, consensus, and workflow orchestration.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional, Protocol, runtime_checkable
from enum import Enum
import asyncio


from dmm.agentos.communication.messages import (
    Message,
    MessageType,
    MessagePriority,
    MessageFactory,
    TaskContent,
    QueryContent,
    generate_conversation_id,
)
from dmm.agentos.communication.bus import MessageBus


# =============================================================================
# Collaboration Status
# =============================================================================

class CollaborationStatus(str, Enum):
    """Status of a collaboration."""
    
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    WAITING_RESPONSE = "waiting_response"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class DelegationResult(str, Enum):
    """Result of a delegation attempt."""
    
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    COMPLETED = "completed"
    FAILED = "failed"


# =============================================================================
# Agent Protocol
# =============================================================================

@runtime_checkable
class AgentProtocol(Protocol):
    """Protocol for agents participating in collaboration."""
    
    @property
    def id(self) -> str:
        """Agent ID."""
        ...
    
    @property
    def capabilities(self) -> list[str]:
        """Agent capabilities."""
        ...
    
    def get_load(self) -> float:
        """Get current load (0.0 to 1.0)."""
        ...


# =============================================================================
# Collaboration Records
# =============================================================================

@dataclass
class DelegationRecord:
    """Record of a task delegation."""
    
    id: str
    delegator: str
    delegate: str
    task: TaskContent
    reason: str = ""
    status: CollaborationStatus = CollaborationStatus.PENDING
    result: Optional[DelegationResult] = None
    response: Any = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    timeout_seconds: float = 300.0
    
    def is_complete(self) -> bool:
        """Check if delegation is complete."""
        return self.status in (
            CollaborationStatus.COMPLETED,
            CollaborationStatus.FAILED,
            CollaborationStatus.CANCELLED,
            CollaborationStatus.TIMEOUT,
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "delegator": self.delegator,
            "delegate": self.delegate,
            "task": self.task.to_dict(),
            "reason": self.reason,
            "status": self.status.value,
            "result": self.result.value if self.result else None,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass
class AssistanceRequest:
    """Record of an assistance request."""
    
    id: str
    requester: str
    helper: Optional[str] = None
    query: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    status: CollaborationStatus = CollaborationStatus.PENDING
    response: Any = None
    helpers_asked: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "requester": self.requester,
            "helper": self.helper,
            "query": self.query,
            "status": self.status.value,
            "helpers_asked": self.helpers_asked,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


@dataclass
class ConsensusRound:
    """A round of consensus building."""
    
    id: str
    initiator: str
    topic: str
    proposal: Any
    participants: list[str] = field(default_factory=list)
    votes: dict[str, bool] = field(default_factory=dict)
    comments: dict[str, str] = field(default_factory=dict)
    status: CollaborationStatus = CollaborationStatus.PENDING
    threshold: float = 0.5  # Fraction needed for consensus
    created_at: datetime = field(default_factory=datetime.utcnow)
    deadline: Optional[datetime] = None
    
    def record_vote(self, agent_id: str, vote: bool, comment: str = "") -> None:
        """Record a vote."""
        self.votes[agent_id] = vote
        if comment:
            self.comments[agent_id] = comment
    
    def get_result(self) -> Optional[bool]:
        """Get consensus result if complete."""
        if len(self.votes) < len(self.participants):
            return None
        
        yes_votes = sum(1 for v in self.votes.values() if v)
        return yes_votes / len(self.participants) >= self.threshold
    
    def is_complete(self) -> bool:
        """Check if all votes are in."""
        return len(self.votes) >= len(self.participants)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "initiator": self.initiator,
            "topic": self.topic,
            "participants": self.participants,
            "votes": self.votes,
            "status": self.status.value,
            "threshold": self.threshold,
            "result": self.get_result(),
            "created_at": self.created_at.isoformat(),
        }


# =============================================================================
# Collaboration Coordinator
# =============================================================================

class CollaborationCoordinator:
    """
    Coordinates collaboration patterns between agents.
    
    Provides high-level patterns including:
    - Task delegation
    - Assistance requests
    - Consensus building
    - Workflow coordination
    """
    
    def __init__(
        self,
        message_bus: MessageBus,
        agent_registry: Optional[Callable[[str], Optional[AgentProtocol]]] = None,
    ) -> None:
        """
        Initialize collaboration coordinator.
        
        Args:
            message_bus: Message bus for communication
            agent_registry: Function to look up agents by ID
        """
        self._bus = message_bus
        self._get_agent = agent_registry or (lambda x: None)
        
        # Active collaborations
        self._delegations: dict[str, DelegationRecord] = {}
        self._assistance_requests: dict[str, AssistanceRequest] = {}
        self._consensus_rounds: dict[str, ConsensusRound] = {}
        
        # Callbacks
        self._on_delegation_complete: Optional[Callable[[DelegationRecord], None]] = None
        self._on_assistance_resolved: Optional[Callable[[AssistanceRequest], None]] = None
        self._on_consensus_reached: Optional[Callable[[ConsensusRound], None]] = None
    
    # -------------------------------------------------------------------------
    # Task Delegation
    # -------------------------------------------------------------------------
    
    def delegate_task(
        self,
        delegator: str,
        delegate: str,
        task: TaskContent,
        reason: str = "",
        timeout_seconds: float = 300.0,
    ) -> DelegationRecord:
        """
        Delegate a task to another agent.
        
        Args:
            delegator: Agent delegating the task
            delegate: Agent receiving the task
            task: Task to delegate
            reason: Reason for delegation
            timeout_seconds: Timeout for delegation
            
        Returns:
            DelegationRecord tracking the delegation
        """
        record = DelegationRecord(
            id=generate_conversation_id(),
            delegator=delegator,
            delegate=delegate,
            task=task,
            reason=reason,
            timeout_seconds=timeout_seconds,
        )
        
        self._delegations[record.id] = record
        
        # Send delegation message
        message = MessageFactory.create_delegation(
            sender=delegator,
            recipient=delegate,
            task=task,
            reason=reason,
        )
        message.conversation_id = record.id
        
        self._bus.send(message)
        record.status = CollaborationStatus.WAITING_RESPONSE
        
        return record
    
    def accept_delegation(
        self,
        delegation_id: str,
        agent_id: str,
    ) -> bool:
        """
        Accept a delegated task.
        
        Args:
            delegation_id: Delegation record ID
            agent_id: Agent accepting
            
        Returns:
            True if accepted
        """
        record = self._delegations.get(delegation_id)
        if not record or record.delegate != agent_id:
            return False
        
        record.result = DelegationResult.ACCEPTED
        record.status = CollaborationStatus.IN_PROGRESS
        
        # Send acceptance
        message = Message(
            sender=agent_id,
            recipient=record.delegator,
            message_type=MessageType.ACK,
            conversation_id=delegation_id,
            content={"accepted": True, "delegation_id": delegation_id},
        )
        self._bus.send(message)
        
        return True
    
    def reject_delegation(
        self,
        delegation_id: str,
        agent_id: str,
        reason: str = "",
    ) -> bool:
        """
        Reject a delegated task.
        
        Args:
            delegation_id: Delegation record ID
            agent_id: Agent rejecting
            reason: Reason for rejection
            
        Returns:
            True if rejected
        """
        record = self._delegations.get(delegation_id)
        if not record or record.delegate != agent_id:
            return False
        
        record.result = DelegationResult.REJECTED
        record.status = CollaborationStatus.FAILED
        record.completed_at = datetime.utcnow()
        record.response = reason
        
        # Send rejection
        message = Message(
            sender=agent_id,
            recipient=record.delegator,
            message_type=MessageType.NACK,
            conversation_id=delegation_id,
            content={"accepted": False, "reason": reason},
        )
        self._bus.send(message)
        
        return True
    
    def complete_delegation(
        self,
        delegation_id: str,
        agent_id: str,
        result: Any,
        success: bool = True,
    ) -> bool:
        """
        Complete a delegated task.
        
        Args:
            delegation_id: Delegation record ID
            agent_id: Agent completing
            result: Task result
            success: Whether task succeeded
            
        Returns:
            True if completed
        """
        record = self._delegations.get(delegation_id)
        if not record or record.delegate != agent_id:
            return False
        
        record.result = DelegationResult.COMPLETED if success else DelegationResult.FAILED
        record.status = CollaborationStatus.COMPLETED if success else CollaborationStatus.FAILED
        record.completed_at = datetime.utcnow()
        record.response = result
        
        # Send completion message
        message = Message(
            sender=agent_id,
            recipient=record.delegator,
            message_type=MessageType.TASK_COMPLETE if success else MessageType.TASK_FAILED,
            conversation_id=delegation_id,
            content={
                "delegation_id": delegation_id,
                "success": success,
                "result": result,
            },
        )
        self._bus.send(message)
        
        if self._on_delegation_complete:
            self._on_delegation_complete(record)
        
        return True
    
    def find_delegate(
        self,
        required_capabilities: list[str],
        exclude: Optional[list[str]] = None,
        max_load: float = 0.8,
    ) -> Optional[str]:
        """
        Find a suitable agent for delegation.
        
        Args:
            required_capabilities: Required capabilities
            exclude: Agents to exclude
            max_load: Maximum acceptable load
            
        Returns:
            Agent ID or None if no suitable agent
        """
        exclude = exclude or []
        
        # Get all registered agents
        agent_ids = self._bus.get_registered_agents()
        
        best_agent = None
        best_load = 1.0
        
        for agent_id in agent_ids:
            if agent_id in exclude:
                continue
            
            agent = self._get_agent(agent_id)
            if agent is None:
                continue
            
            # Check capabilities
            if not all(cap in agent.capabilities for cap in required_capabilities):
                continue
            
            # Check load
            load = agent.get_load()
            if load > max_load:
                continue
            
            # Find lowest load
            if load < best_load:
                best_agent = agent_id
                best_load = load
        
        return best_agent
    
    # -------------------------------------------------------------------------
    # Assistance Requests
    # -------------------------------------------------------------------------
    
    def request_assistance(
        self,
        requester: str,
        query: str,
        context: Optional[dict[str, Any]] = None,
        preferred_helpers: Optional[list[str]] = None,
    ) -> AssistanceRequest:
        """
        Request assistance from other agents.
        
        Args:
            requester: Agent requesting help
            query: The query or problem
            context: Additional context
            preferred_helpers: Preferred agents to ask
            
        Returns:
            AssistanceRequest tracking the request
        """
        request = AssistanceRequest(
            id=generate_conversation_id(),
            requester=requester,
            query=query,
            context=context or {},
        )
        
        self._assistance_requests[request.id] = request
        
        # Determine who to ask
        helpers = preferred_helpers or self._bus.get_registered_agents()
        helpers = [h for h in helpers if h != requester]
        
        if not helpers:
            request.status = CollaborationStatus.FAILED
            return request
        
        # Send query to helpers
        query_content = QueryContent(
            query=query,
            context=context or {},
        )
        
        for helper in helpers:
            message = MessageFactory.create_query(
                sender=requester,
                recipient=helper,
                query=query_content,
            )
            message.conversation_id = request.id
            self._bus.send(message)
            request.helpers_asked.append(helper)
        
        request.status = CollaborationStatus.WAITING_RESPONSE
        return request
    
    def provide_assistance(
        self,
        request_id: str,
        helper: str,
        response: Any,
    ) -> bool:
        """
        Provide assistance for a request.
        
        Args:
            request_id: Assistance request ID
            helper: Agent providing help
            response: The assistance response
            
        Returns:
            True if response recorded
        """
        request = self._assistance_requests.get(request_id)
        if not request:
            return False
        
        # Record first response
        if request.status == CollaborationStatus.WAITING_RESPONSE:
            request.helper = helper
            request.response = response
            request.status = CollaborationStatus.COMPLETED
            request.resolved_at = datetime.utcnow()
            
            # Send response to requester
            message = Message(
                sender=helper,
                recipient=request.requester,
                message_type=MessageType.ANSWER,
                conversation_id=request_id,
                content=response,
            )
            self._bus.send(message)
            
            if self._on_assistance_resolved:
                self._on_assistance_resolved(request)
            
            return True
        
        return False
    
    # -------------------------------------------------------------------------
    # Consensus Building
    # -------------------------------------------------------------------------
    
    def initiate_consensus(
        self,
        initiator: str,
        topic: str,
        proposal: Any,
        participants: list[str],
        threshold: float = 0.5,
        timeout_seconds: float = 300.0,
    ) -> ConsensusRound:
        """
        Initiate a consensus round.
        
        Args:
            initiator: Agent initiating consensus
            topic: Topic of consensus
            proposal: The proposal to vote on
            participants: Agents to participate
            threshold: Fraction needed for consensus
            timeout_seconds: Voting timeout
            
        Returns:
            ConsensusRound tracking the consensus
        """
        consensus = ConsensusRound(
            id=generate_conversation_id(),
            initiator=initiator,
            topic=topic,
            proposal=proposal,
            participants=participants,
            threshold=threshold,
            deadline=datetime.utcnow() + timedelta(seconds=timeout_seconds),
        )
        
        self._consensus_rounds[consensus.id] = consensus
        
        # Send vote requests
        for participant in participants:
            message = Message(
                sender=initiator,
                recipient=participant,
                message_type=MessageType.REQUEST,
                subject=f"Vote: {topic}",
                conversation_id=consensus.id,
                content={
                    "type": "vote_request",
                    "consensus_id": consensus.id,
                    "topic": topic,
                    "proposal": proposal,
                    "threshold": threshold,
                },
                requires_response=True,
            )
            self._bus.send(message)
        
        consensus.status = CollaborationStatus.WAITING_RESPONSE
        return consensus
    
    def cast_vote(
        self,
        consensus_id: str,
        voter: str,
        vote: bool,
        comment: str = "",
    ) -> bool:
        """
        Cast a vote in a consensus round.
        
        Args:
            consensus_id: Consensus round ID
            voter: Agent voting
            vote: The vote (True = yes, False = no)
            comment: Optional comment
            
        Returns:
            True if vote recorded
        """
        consensus = self._consensus_rounds.get(consensus_id)
        if not consensus or voter not in consensus.participants:
            return False
        
        if voter in consensus.votes:
            return False  # Already voted
        
        consensus.record_vote(voter, vote, comment)
        
        # Send vote to initiator
        message = Message(
            sender=voter,
            recipient=consensus.initiator,
            message_type=MessageType.RESPONSE,
            conversation_id=consensus_id,
            content={
                "type": "vote",
                "consensus_id": consensus_id,
                "vote": vote,
                "comment": comment,
            },
        )
        self._bus.send(message)
        
        # Check if consensus is complete
        if consensus.is_complete():
            consensus.status = CollaborationStatus.COMPLETED
            result = consensus.get_result()
            
            # Broadcast result
            self._broadcast_consensus_result(consensus, result)
            
            if self._on_consensus_reached:
                self._on_consensus_reached(consensus)
        
        return True
    
    def _broadcast_consensus_result(
        self,
        consensus: ConsensusRound,
        result: Optional[bool],
    ) -> None:
        """Broadcast consensus result to all participants."""
        for participant in consensus.participants:
            message = Message(
                sender=consensus.initiator,
                recipient=participant,
                message_type=MessageType.INFORM,
                subject=f"Consensus Result: {consensus.topic}",
                conversation_id=consensus.id,
                content={
                    "type": "consensus_result",
                    "consensus_id": consensus.id,
                    "topic": consensus.topic,
                    "result": result,
                    "votes": consensus.votes,
                },
            )
            self._bus.send(message)
    
    # -------------------------------------------------------------------------
    # Workflow Coordination
    # -------------------------------------------------------------------------
    
    def broadcast_to_all(
        self,
        sender: str,
        subject: str,
        content: Any,
        tags: Optional[list[str]] = None,
    ) -> int:
        """
        Broadcast a message to all agents.
        
        Args:
            sender: Sending agent
            subject: Message subject
            content: Message content
            tags: Optional tags
            
        Returns:
            Number of recipients
        """
        recipients = [a for a in self._bus.get_registered_agents() if a != sender]
        
        message = MessageFactory.create_broadcast(
            sender=sender,
            recipients=recipients,
            subject=subject,
            content=content,
        )
        
        if tags:
            message.tags = tags
        
        self._bus.send(message)
        return len(recipients)
    
    def notify_task_update(
        self,
        sender: str,
        interested_agents: list[str],
        task: TaskContent,
    ) -> None:
        """
        Notify agents about a task update.
        
        Args:
            sender: Sending agent
            interested_agents: Agents to notify
            task: Task information
        """
        for agent in interested_agents:
            message = MessageFactory.create_task_update(
                sender=sender,
                recipient=agent,
                task=task,
            )
            self._bus.send(message)
    
    # -------------------------------------------------------------------------
    # Callbacks
    # -------------------------------------------------------------------------
    
    def on_delegation_complete(
        self,
        callback: Callable[[DelegationRecord], None],
    ) -> None:
        """Set callback for delegation completion."""
        self._on_delegation_complete = callback
    
    def on_assistance_resolved(
        self,
        callback: Callable[[AssistanceRequest], None],
    ) -> None:
        """Set callback for assistance resolution."""
        self._on_assistance_resolved = callback
    
    def on_consensus_reached(
        self,
        callback: Callable[[ConsensusRound], None],
    ) -> None:
        """Set callback for consensus reached."""
        self._on_consensus_reached = callback
    
    # -------------------------------------------------------------------------
    # Status Queries
    # -------------------------------------------------------------------------
    
    def get_delegation(self, delegation_id: str) -> Optional[DelegationRecord]:
        """Get a delegation record."""
        return self._delegations.get(delegation_id)
    
    def get_assistance_request(self, request_id: str) -> Optional[AssistanceRequest]:
        """Get an assistance request."""
        return self._assistance_requests.get(request_id)
    
    def get_consensus_round(self, consensus_id: str) -> Optional[ConsensusRound]:
        """Get a consensus round."""
        return self._consensus_rounds.get(consensus_id)
    
    def get_active_delegations(self, agent_id: str) -> list[DelegationRecord]:
        """Get active delegations for an agent."""
        return [
            d for d in self._delegations.values()
            if (d.delegator == agent_id or d.delegate == agent_id)
            and not d.is_complete()
        ]
    
    def get_pending_consensus(self, agent_id: str) -> list[ConsensusRound]:
        """Get pending consensus rounds for an agent."""
        return [
            c for c in self._consensus_rounds.values()
            if agent_id in c.participants
            and agent_id not in c.votes
            and c.status == CollaborationStatus.WAITING_RESPONSE
        ]
