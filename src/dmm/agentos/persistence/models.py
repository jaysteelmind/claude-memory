"""Data models for AgentOS persistence.

These models represent runtime state that is persisted to SQLite,
as opposed to configuration which is stored in YAML files.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AgentStatus(str, Enum):
    """Agent runtime status."""
    
    IDLE = "idle"
    BUSY = "busy"
    PAUSED = "paused"
    ERROR = "error"
    OFFLINE = "offline"


class MessageDirection(str, Enum):
    """Message direction."""
    
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class ModificationLevel(str, Enum):
    """Self-modification approval level."""
    
    AUTOMATIC = "automatic"      # Level 1: Memory updates
    LOGGED = "logged"            # Level 2: Skill changes
    HUMAN_REQUIRED = "human_required"  # Level 3-4: Behavior/goal changes


class ModificationStatus(str, Enum):
    """Status of a modification request."""
    
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"


@dataclass
class AgentState:
    """Runtime state of an agent.
    
    This captures the dynamic state of an agent during execution,
    complementing the static configuration stored in YAML.
    
    Attributes:
        agent_id: Agent identifier.
        session_id: Current session identifier.
        status: Current runtime status.
        current_task_id: ID of task being executed.
        tokens_used: Tokens consumed in current session.
        api_calls_made: API calls made in current session.
        last_active: Last activity timestamp.
        error_message: Most recent error, if any.
        context_data: Arbitrary context data.
        created_at: State record creation time.
        updated_at: Last update time.
    """
    
    agent_id: str
    session_id: str
    status: AgentStatus = AgentStatus.IDLE
    current_task_id: str | None = None
    tokens_used: int = 0
    api_calls_made: int = 0
    last_active: datetime | None = None
    error_message: str | None = None
    context_data: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "status": self.status.value,
            "current_task_id": self.current_task_id,
            "tokens_used": self.tokens_used,
            "api_calls_made": self.api_calls_made,
            "last_active": self.last_active.isoformat() if self.last_active else None,
            "error_message": self.error_message,
            "context_data": self.context_data,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentState":
        """Create from dictionary."""
        return cls(
            agent_id=data["agent_id"],
            session_id=data["session_id"],
            status=AgentStatus(data.get("status", "idle")),
            current_task_id=data.get("current_task_id"),
            tokens_used=data.get("tokens_used", 0),
            api_calls_made=data.get("api_calls_made", 0),
            last_active=datetime.fromisoformat(data["last_active"]) if data.get("last_active") else None,
            error_message=data.get("error_message"),
            context_data=data.get("context_data", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(),
        )


@dataclass
class MessageRecord:
    """Persisted record of an inter-agent message.
    
    Attributes:
        message_id: Unique message identifier.
        session_id: Session in which message was sent.
        sender_id: Sending agent ID.
        recipient_id: Receiving agent ID (or "broadcast").
        message_type: Type of message (request, response, etc.).
        direction: Inbound or outbound relative to recipient.
        content: Message content (JSON serialized).
        correlation_id: ID linking request/response pairs.
        timestamp: When message was sent.
        delivered_at: When message was delivered.
        read_at: When message was read by recipient.
    """
    
    message_id: str
    session_id: str
    sender_id: str
    recipient_id: str
    message_type: str
    direction: MessageDirection
    content: dict[str, Any]
    correlation_id: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "message_id": self.message_id,
            "session_id": self.session_id,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "message_type": self.message_type,
            "direction": self.direction.value,
            "content": self.content,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp.isoformat(),
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MessageRecord":
        """Create from dictionary."""
        return cls(
            message_id=data["message_id"],
            session_id=data["session_id"],
            sender_id=data["sender_id"],
            recipient_id=data["recipient_id"],
            message_type=data["message_type"],
            direction=MessageDirection(data["direction"]),
            content=data.get("content", {}),
            correlation_id=data.get("correlation_id"),
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.now(),
            delivered_at=datetime.fromisoformat(data["delivered_at"]) if data.get("delivered_at") else None,
            read_at=datetime.fromisoformat(data["read_at"]) if data.get("read_at") else None,
        )


@dataclass
class ModificationRecord:
    """Record of a self-modification request or action.
    
    Attributes:
        modification_id: Unique identifier.
        session_id: Session in which modification was requested.
        agent_id: Agent requesting modification.
        level: Approval level required.
        status: Current status of modification.
        target_type: What is being modified (memory, skill, behavior, goal).
        target_id: ID of target being modified.
        description: Human-readable description.
        diff: Detailed diff of changes.
        reason: Reason for modification.
        requested_at: When modification was requested.
        reviewed_at: When modification was reviewed.
        reviewed_by: Who reviewed (agent or human).
        applied_at: When modification was applied.
        rollback_at: When modification was rolled back (if applicable).
    """
    
    modification_id: str
    session_id: str
    agent_id: str
    level: ModificationLevel
    status: ModificationStatus
    target_type: str
    target_id: str
    description: str
    diff: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    requested_at: datetime = field(default_factory=datetime.now)
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    applied_at: datetime | None = None
    rollback_at: datetime | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "modification_id": self.modification_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "level": self.level.value,
            "status": self.status.value,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "description": self.description,
            "diff": self.diff,
            "reason": self.reason,
            "requested_at": self.requested_at.isoformat(),
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewed_by": self.reviewed_by,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "rollback_at": self.rollback_at.isoformat() if self.rollback_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModificationRecord":
        """Create from dictionary."""
        return cls(
            modification_id=data["modification_id"],
            session_id=data["session_id"],
            agent_id=data["agent_id"],
            level=ModificationLevel(data["level"]),
            status=ModificationStatus(data["status"]),
            target_type=data["target_type"],
            target_id=data["target_id"],
            description=data["description"],
            diff=data.get("diff", {}),
            reason=data.get("reason", ""),
            requested_at=datetime.fromisoformat(data["requested_at"]) if data.get("requested_at") else datetime.now(),
            reviewed_at=datetime.fromisoformat(data["reviewed_at"]) if data.get("reviewed_at") else None,
            reviewed_by=data.get("reviewed_by"),
            applied_at=datetime.fromisoformat(data["applied_at"]) if data.get("applied_at") else None,
            rollback_at=datetime.fromisoformat(data["rollback_at"]) if data.get("rollback_at") else None,
        )


@dataclass
class SessionRecord:
    """Record of an AgentOS session.
    
    A session represents a period of agent activity, typically
    corresponding to a single conversation or task execution.
    
    Attributes:
        session_id: Unique session identifier.
        started_at: When session started.
        ended_at: When session ended (None if active).
        primary_agent_id: Main agent for this session.
        active_agents: All agents active in session.
        tasks_created: Number of tasks created.
        tasks_completed: Number of tasks completed.
        messages_sent: Number of messages exchanged.
        total_tokens: Total tokens consumed.
        metadata: Additional session metadata.
    """
    
    session_id: str
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: datetime | None = None
    primary_agent_id: str | None = None
    active_agents: list[str] = field(default_factory=list)
    tasks_created: int = 0
    tasks_completed: int = 0
    messages_sent: int = 0
    total_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_active(self) -> bool:
        """Check if session is still active."""
        return self.ended_at is None
    
    @property
    def duration_seconds(self) -> float | None:
        """Get session duration in seconds."""
        if self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "primary_agent_id": self.primary_agent_id,
            "active_agents": self.active_agents,
            "tasks_created": self.tasks_created,
            "tasks_completed": self.tasks_completed,
            "messages_sent": self.messages_sent,
            "total_tokens": self.total_tokens,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionRecord":
        """Create from dictionary."""
        return cls(
            session_id=data["session_id"],
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else datetime.now(),
            ended_at=datetime.fromisoformat(data["ended_at"]) if data.get("ended_at") else None,
            primary_agent_id=data.get("primary_agent_id"),
            active_agents=data.get("active_agents", []),
            tasks_created=data.get("tasks_created", 0),
            tasks_completed=data.get("tasks_completed", 0),
            messages_sent=data.get("messages_sent", 0),
            total_tokens=data.get("total_tokens", 0),
            metadata=data.get("metadata", {}),
        )
