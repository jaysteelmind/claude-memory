"""
Message protocols for multi-agent communication.

This module defines message types, structures, and validation for
communication between agents in the system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from enum import Enum
import uuid
import json


# =============================================================================
# Message Types
# =============================================================================

class MessageType(str, Enum):
    """Types of messages that can be exchanged between agents."""
    
    # Request/Response
    REQUEST = "request"
    RESPONSE = "response"
    
    # Notifications
    INFORM = "inform"
    NOTIFY = "notify"
    ALERT = "alert"
    
    # Task-related
    TASK_ASSIGN = "task_assign"
    TASK_UPDATE = "task_update"
    TASK_COMPLETE = "task_complete"
    TASK_FAILED = "task_failed"
    
    # Collaboration
    DELEGATE = "delegate"
    ASSIST = "assist"
    QUERY = "query"
    ANSWER = "answer"
    
    # Control
    COMMAND = "command"
    ACK = "ack"
    NACK = "nack"
    CANCEL = "cancel"
    
    # System
    HEARTBEAT = "heartbeat"
    STATUS = "status"
    ERROR = "error"
    
    # Broadcast
    BROADCAST = "broadcast"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"


class MessagePriority(int, Enum):
    """Priority levels for messages."""
    
    LOW = 1
    NORMAL = 5
    HIGH = 8
    URGENT = 10


class DeliveryStatus(str, Enum):
    """Status of message delivery."""
    
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    EXPIRED = "expired"


# =============================================================================
# Message ID Generation
# =============================================================================

def generate_message_id() -> str:
    """Generate a unique message ID."""
    return f"msg_{uuid.uuid4().hex[:16]}"


def generate_conversation_id() -> str:
    """Generate a unique conversation ID."""
    return f"conv_{uuid.uuid4().hex[:12]}"


# =============================================================================
# Message Content Types
# =============================================================================

@dataclass
class TaskContent:
    """Content for task-related messages."""
    
    task_id: str
    task_name: str
    task_description: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    status: str = ""
    progress: float = 0.0
    error: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "task_description": self.task_description,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "status": self.status,
            "progress": self.progress,
            "error": self.error,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskContent":
        return cls(
            task_id=data.get("task_id", ""),
            task_name=data.get("task_name", ""),
            task_description=data.get("task_description", ""),
            inputs=data.get("inputs", {}),
            outputs=data.get("outputs", {}),
            status=data.get("status", ""),
            progress=data.get("progress", 0.0),
            error=data.get("error"),
        )


@dataclass
class QueryContent:
    """Content for query messages."""
    
    query: str
    context: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    expected_format: str = "text"
    max_tokens: int = 1000
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "context": self.context,
            "constraints": self.constraints,
            "expected_format": self.expected_format,
            "max_tokens": self.max_tokens,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueryContent":
        return cls(
            query=data.get("query", ""),
            context=data.get("context", {}),
            constraints=data.get("constraints", {}),
            expected_format=data.get("expected_format", "text"),
            max_tokens=data.get("max_tokens", 1000),
        )


@dataclass
class ErrorContent:
    """Content for error messages."""
    
    error_code: str
    error_message: str
    error_type: str = "error"
    details: dict[str, Any] = field(default_factory=dict)
    recoverable: bool = True
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "error_message": self.error_message,
            "error_type": self.error_type,
            "details": self.details,
            "recoverable": self.recoverable,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ErrorContent":
        return cls(
            error_code=data.get("error_code", "UNKNOWN"),
            error_message=data.get("error_message", ""),
            error_type=data.get("error_type", "error"),
            details=data.get("details", {}),
            recoverable=data.get("recoverable", True),
        )


@dataclass
class StatusContent:
    """Content for status messages."""
    
    agent_id: str
    status: str
    load: float = 0.0
    active_tasks: int = 0
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "status": self.status,
            "load": self.load,
            "active_tasks": self.active_tasks,
            "capabilities": self.capabilities,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StatusContent":
        return cls(
            agent_id=data.get("agent_id", ""),
            status=data.get("status", ""),
            load=data.get("load", 0.0),
            active_tasks=data.get("active_tasks", 0),
            capabilities=data.get("capabilities", []),
            metadata=data.get("metadata", {}),
        )


# =============================================================================
# Message Model
# =============================================================================

@dataclass
class Message:
    """
    A message exchanged between agents.
    
    Messages support various types of communication including
    requests, responses, notifications, and task-related updates.
    """
    
    # Identity
    id: str = field(default_factory=generate_message_id)
    conversation_id: Optional[str] = None
    
    # Routing
    sender: str = ""
    recipient: str = ""
    recipients: list[str] = field(default_factory=list)
    
    # Type and content
    message_type: MessageType = MessageType.INFORM
    subject: str = ""
    content: Any = None
    
    # Metadata
    priority: MessagePriority = MessagePriority.NORMAL
    timestamp: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    
    # Threading
    reply_to: Optional[str] = None
    thread_id: Optional[str] = None
    
    # Delivery
    delivery_status: DeliveryStatus = DeliveryStatus.PENDING
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    
    # Additional data
    headers: dict[str, str] = field(default_factory=dict)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    
    # Flags
    requires_response: bool = False
    response_timeout_seconds: float = 60.0
    
    def __post_init__(self):
        """Ensure message has an ID."""
        if not self.id:
            self.id = generate_message_id()
    
    # -------------------------------------------------------------------------
    # Routing
    # -------------------------------------------------------------------------
    
    def is_broadcast(self) -> bool:
        """Check if this is a broadcast message."""
        return self.message_type == MessageType.BROADCAST or len(self.recipients) > 1
    
    def get_all_recipients(self) -> list[str]:
        """Get all recipients including main recipient."""
        all_recips = list(self.recipients)
        if self.recipient and self.recipient not in all_recips:
            all_recips.insert(0, self.recipient)
        return all_recips
    
    # -------------------------------------------------------------------------
    # Status
    # -------------------------------------------------------------------------
    
    def is_expired(self) -> bool:
        """Check if message has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at
    
    def mark_sent(self) -> None:
        """Mark message as sent."""
        self.delivery_status = DeliveryStatus.SENT
    
    def mark_delivered(self) -> None:
        """Mark message as delivered."""
        self.delivery_status = DeliveryStatus.DELIVERED
        self.delivered_at = datetime.utcnow()
    
    def mark_read(self) -> None:
        """Mark message as read."""
        self.delivery_status = DeliveryStatus.READ
        self.read_at = datetime.utcnow()
    
    def mark_failed(self) -> None:
        """Mark message as failed."""
        self.delivery_status = DeliveryStatus.FAILED
    
    # -------------------------------------------------------------------------
    # Response Creation
    # -------------------------------------------------------------------------
    
    def create_response(
        self,
        content: Any,
        message_type: MessageType = MessageType.RESPONSE,
    ) -> "Message":
        """Create a response to this message."""
        return Message(
            conversation_id=self.conversation_id or self.id,
            sender=self.recipient,
            recipient=self.sender,
            message_type=message_type,
            subject=f"Re: {self.subject}" if self.subject else "",
            content=content,
            reply_to=self.id,
            thread_id=self.thread_id or self.id,
            priority=self.priority,
        )
    
    def create_ack(self) -> "Message":
        """Create an acknowledgment for this message."""
        return self.create_response(
            content={"acknowledged": True, "message_id": self.id},
            message_type=MessageType.ACK,
        )
    
    def create_nack(self, reason: str) -> "Message":
        """Create a negative acknowledgment."""
        return self.create_response(
            content={"acknowledged": False, "message_id": self.id, "reason": reason},
            message_type=MessageType.NACK,
        )
    
    def create_error_response(self, error: ErrorContent) -> "Message":
        """Create an error response."""
        return self.create_response(
            content=error.to_dict(),
            message_type=MessageType.ERROR,
        )
    
    # -------------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------------
    
    def to_dict(self) -> dict[str, Any]:
        """Convert message to dictionary."""
        content_data = self.content
        if hasattr(self.content, "to_dict"):
            content_data = self.content.to_dict()
        
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "recipients": self.recipients,
            "message_type": self.message_type.value,
            "subject": self.subject,
            "content": content_data,
            "priority": self.priority.value,
            "timestamp": self.timestamp.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "reply_to": self.reply_to,
            "thread_id": self.thread_id,
            "delivery_status": self.delivery_status.value,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "headers": self.headers,
            "attachments": self.attachments,
            "tags": self.tags,
            "requires_response": self.requires_response,
            "response_timeout_seconds": self.response_timeout_seconds,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        """Create message from dictionary."""
        return cls(
            id=data.get("id", generate_message_id()),
            conversation_id=data.get("conversation_id"),
            sender=data.get("sender", ""),
            recipient=data.get("recipient", ""),
            recipients=data.get("recipients", []),
            message_type=MessageType(data.get("message_type", "inform")),
            subject=data.get("subject", ""),
            content=data.get("content"),
            priority=MessagePriority(data.get("priority", 5)),
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.utcnow(),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            reply_to=data.get("reply_to"),
            thread_id=data.get("thread_id"),
            delivery_status=DeliveryStatus(data.get("delivery_status", "pending")),
            delivered_at=datetime.fromisoformat(data["delivered_at"]) if data.get("delivered_at") else None,
            read_at=datetime.fromisoformat(data["read_at"]) if data.get("read_at") else None,
            headers=data.get("headers", {}),
            attachments=data.get("attachments", []),
            tags=data.get("tags", []),
            requires_response=data.get("requires_response", False),
            response_timeout_seconds=data.get("response_timeout_seconds", 60.0),
        )
    
    def to_json(self) -> str:
        """Convert message to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> "Message":
        """Create message from JSON string."""
        return cls.from_dict(json.loads(json_str))


# =============================================================================
# Message Factory
# =============================================================================

class MessageFactory:
    """Factory for creating common message types."""
    
    @staticmethod
    def create_request(
        sender: str,
        recipient: str,
        subject: str,
        content: Any,
        timeout_seconds: float = 60.0,
    ) -> Message:
        """Create a request message expecting a response."""
        return Message(
            sender=sender,
            recipient=recipient,
            message_type=MessageType.REQUEST,
            subject=subject,
            content=content,
            requires_response=True,
            response_timeout_seconds=timeout_seconds,
        )
    
    @staticmethod
    def create_task_assignment(
        sender: str,
        recipient: str,
        task: TaskContent,
    ) -> Message:
        """Create a task assignment message."""
        return Message(
            sender=sender,
            recipient=recipient,
            message_type=MessageType.TASK_ASSIGN,
            subject=f"Task: {task.task_name}",
            content=task.to_dict(),
            requires_response=True,
        )
    
    @staticmethod
    def create_task_update(
        sender: str,
        recipient: str,
        task: TaskContent,
    ) -> Message:
        """Create a task update message."""
        return Message(
            sender=sender,
            recipient=recipient,
            message_type=MessageType.TASK_UPDATE,
            subject=f"Update: {task.task_name}",
            content=task.to_dict(),
        )
    
    @staticmethod
    def create_query(
        sender: str,
        recipient: str,
        query: QueryContent,
    ) -> Message:
        """Create a query message."""
        return Message(
            sender=sender,
            recipient=recipient,
            message_type=MessageType.QUERY,
            subject="Query",
            content=query.to_dict(),
            requires_response=True,
        )
    
    @staticmethod
    def create_broadcast(
        sender: str,
        recipients: list[str],
        subject: str,
        content: Any,
    ) -> Message:
        """Create a broadcast message."""
        return Message(
            sender=sender,
            recipients=recipients,
            message_type=MessageType.BROADCAST,
            subject=subject,
            content=content,
        )
    
    @staticmethod
    def create_delegation(
        sender: str,
        recipient: str,
        task: TaskContent,
        reason: str = "",
    ) -> Message:
        """Create a task delegation message."""
        return Message(
            sender=sender,
            recipient=recipient,
            message_type=MessageType.DELEGATE,
            subject=f"Delegate: {task.task_name}",
            content={
                "task": task.to_dict(),
                "reason": reason,
            },
            requires_response=True,
        )
    
    @staticmethod
    def create_status_update(
        sender: str,
        status: StatusContent,
    ) -> Message:
        """Create a status update message."""
        return Message(
            sender=sender,
            recipient="",  # Broadcast to subscribers
            message_type=MessageType.STATUS,
            subject="Status Update",
            content=status.to_dict(),
        )
    
    @staticmethod
    def create_heartbeat(agent_id: str) -> Message:
        """Create a heartbeat message."""
        return Message(
            sender=agent_id,
            message_type=MessageType.HEARTBEAT,
            content={"timestamp": datetime.utcnow().isoformat()},
            priority=MessagePriority.LOW,
        )
