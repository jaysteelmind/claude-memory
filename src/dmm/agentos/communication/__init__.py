"""
DMM Communication Module.

This module provides multi-agent communication infrastructure for the
Agent OS, including message protocols, routing, and collaboration patterns.

Public API:
-----------

Messages:
    Message - Core message class
    MessageType - Types of messages
    MessagePriority - Message priority levels
    DeliveryStatus - Message delivery status
    MessageFactory - Factory for creating common messages
    generate_message_id - Generate unique message ID
    generate_conversation_id - Generate conversation ID

Content Types:
    TaskContent - Content for task-related messages
    QueryContent - Content for query messages
    ErrorContent - Content for error messages
    StatusContent - Content for status messages

Message Bus:
    MessageBus - Central message routing infrastructure
    MessageBusConfig - Bus configuration
    MessageBusStats - Bus statistics
    AgentMailbox - Agent's message mailbox
    Subscription - Message subscription

Collaboration:
    CollaborationCoordinator - High-level collaboration patterns
    CollaborationStatus - Status of collaborations
    DelegationResult - Result of task delegation
    DelegationRecord - Record of task delegation
    AssistanceRequest - Record of assistance request
    ConsensusRound - Record of consensus building

Protocols:
    AgentProtocol - Protocol for agents in collaboration

Example Usage:
--------------

    from dmm.agentos.communication import (
        MessageBus,
        Message,
        MessageType,
        MessageFactory,
        CollaborationCoordinator,
        TaskContent,
    )
    
    # Create message bus
    bus = MessageBus()
    
    # Register agents
    bus.register_agent("agent_1")
    bus.register_agent("agent_2")
    
    # Send a message
    message = Message(
        sender="agent_1",
        recipient="agent_2",
        message_type=MessageType.INFORM,
        subject="Hello",
        content="Hello from agent 1!",
    )
    bus.send(message)
    
    # Receive messages
    received = bus.receive("agent_2")
    print(f"Received: {received.content}")
    
    # Create collaboration coordinator
    coordinator = CollaborationCoordinator(bus)
    
    # Delegate a task
    task = TaskContent(
        task_id="task_123",
        task_name="Review Code",
        task_description="Review the authentication module",
    )
    delegation = coordinator.delegate_task(
        delegator="agent_1",
        delegate="agent_2",
        task=task,
    )
"""

# Messages
from dmm.agentos.communication.messages import (
    Message,
    MessageType,
    MessagePriority,
    DeliveryStatus,
    MessageFactory,
    generate_message_id,
    generate_conversation_id,
    TaskContent,
    QueryContent,
    ErrorContent,
    StatusContent,
)

# Message Bus
from dmm.agentos.communication.bus import (
    MessageBus,
    MessageBusConfig,
    MessageBusStats,
    AgentMailbox,
    Subscription,
)

# Collaboration Patterns
from dmm.agentos.communication.patterns import (
    CollaborationCoordinator,
    CollaborationStatus,
    DelegationResult,
    DelegationRecord,
    AssistanceRequest,
    ConsensusRound,
    AgentProtocol,
)

__all__ = [
    # Messages
    "Message",
    "MessageType",
    "MessagePriority",
    "DeliveryStatus",
    "MessageFactory",
    "generate_message_id",
    "generate_conversation_id",
    "TaskContent",
    "QueryContent",
    "ErrorContent",
    "StatusContent",
    # Message Bus
    "MessageBus",
    "MessageBusConfig",
    "MessageBusStats",
    "AgentMailbox",
    "Subscription",
    # Collaboration
    "CollaborationCoordinator",
    "CollaborationStatus",
    "DelegationResult",
    "DelegationRecord",
    "AssistanceRequest",
    "ConsensusRound",
    "AgentProtocol",
]
