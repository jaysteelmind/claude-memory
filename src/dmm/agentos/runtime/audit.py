"""
Audit logging for runtime accountability.

Provides comprehensive logging of agent actions, decisions, and system events.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Callable
from enum import Enum
from collections import deque
import json
import hashlib


class AuditEventType(str, Enum):
    """Types of audit events."""
    # Agent lifecycle
    AGENT_START = "agent_start"
    AGENT_STOP = "agent_stop"
    AGENT_ERROR = "agent_error"
    # Task events
    TASK_CREATE = "task_create"
    TASK_START = "task_start"
    TASK_COMPLETE = "task_complete"
    TASK_FAIL = "task_fail"
    # Resource events
    RESOURCE_ALLOCATE = "resource_allocate"
    RESOURCE_RELEASE = "resource_release"
    RESOURCE_LIMIT = "resource_limit"
    # Safety events
    SAFETY_CHECK = "safety_check"
    SAFETY_VIOLATION = "safety_violation"
    PERMISSION_GRANT = "permission_grant"
    PERMISSION_DENY = "permission_deny"
    # Data events
    MEMORY_READ = "memory_read"
    MEMORY_WRITE = "memory_write"
    MEMORY_DELETE = "memory_delete"
    FILE_ACCESS = "file_access"
    # Communication
    MESSAGE_SEND = "message_send"
    MESSAGE_RECEIVE = "message_receive"
    # Modification
    CODE_ANALYZE = "code_analyze"
    CODE_GENERATE = "code_generate"
    PROPOSAL_CREATE = "proposal_create"
    PROPOSAL_APPLY = "proposal_apply"
    # System
    CONFIG_CHANGE = "config_change"
    SYSTEM_ERROR = "system_error"


class AuditLevel(str, Enum):
    """Audit level (verbosity)."""
    MINIMAL = "minimal"    # Only critical events
    STANDARD = "standard"  # Important events
    DETAILED = "detailed"  # All events
    DEBUG = "debug"        # Everything + debug info


@dataclass
class AuditEvent:
    """An audit log event."""
    id: str
    event_type: AuditEventType
    timestamp: datetime
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    action: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    outcome: str = "success"  # success, failure, blocked
    duration_ms: Optional[float] = None
    parent_event_id: Optional[str] = None
    
    def __post_init__(self):
        if not self.id:
            self.id = self._generate_id()
    
    def _generate_id(self) -> str:
        data = f"{self.timestamp.isoformat()}{self.event_type}{self.agent_id}"
        return f"evt_{hashlib.sha256(data.encode()).hexdigest()[:12]}"
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "action": self.action,
            "details": self.details,
            "outcome": self.outcome,
            "duration_ms": self.duration_ms,
            "parent_event_id": self.parent_event_id,
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuditEvent":
        return cls(
            id=data.get("id", ""),
            event_type=AuditEventType(data["event_type"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            agent_id=data.get("agent_id"),
            task_id=data.get("task_id"),
            action=data.get("action", ""),
            details=data.get("details", {}),
            outcome=data.get("outcome", "success"),
            duration_ms=data.get("duration_ms"),
            parent_event_id=data.get("parent_event_id"),
        )


@dataclass
class AuditQuery:
    """Query parameters for audit log search."""
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    event_types: Optional[list[AuditEventType]] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    outcome: Optional[str] = None
    limit: int = 100
    
    def matches(self, event: AuditEvent) -> bool:
        if self.agent_id and event.agent_id != self.agent_id:
            return False
        if self.task_id and event.task_id != self.task_id:
            return False
        if self.event_types and event.event_type not in self.event_types:
            return False
        if self.start_time and event.timestamp < self.start_time:
            return False
        if self.end_time and event.timestamp > self.end_time:
            return False
        if self.outcome and event.outcome != self.outcome:
            return False
        return True


class AuditLogger:
    """
    Comprehensive audit logging system.
    
    Features:
    - Event logging with context
    - Query and filtering
    - Export capabilities
    - Retention management
    """
    
    def __init__(
        self,
        level: AuditLevel = AuditLevel.STANDARD,
        max_events: int = 100000,
    ) -> None:
        self._level = level
        self._max_events = max_events
        self._events: deque[AuditEvent] = deque(maxlen=max_events)
        self._listeners: list[Callable[[AuditEvent], None]] = []
        
        # Event type to minimum level mapping
        self._level_map = {
            AuditLevel.MINIMAL: {
                AuditEventType.AGENT_ERROR,
                AuditEventType.SAFETY_VIOLATION,
                AuditEventType.SYSTEM_ERROR,
                AuditEventType.PROPOSAL_APPLY,
            },
            AuditLevel.STANDARD: {
                AuditEventType.AGENT_START, AuditEventType.AGENT_STOP,
                AuditEventType.TASK_CREATE, AuditEventType.TASK_COMPLETE, AuditEventType.TASK_FAIL,
                AuditEventType.SAFETY_CHECK, AuditEventType.PERMISSION_DENY,
                AuditEventType.MEMORY_WRITE, AuditEventType.MEMORY_DELETE,
                AuditEventType.PROPOSAL_CREATE, AuditEventType.CODE_GENERATE,
                AuditEventType.CONFIG_CHANGE, AuditEventType.RESOURCE_LIMIT,
            },
        }
    
    def _should_log(self, event_type: AuditEventType) -> bool:
        """Check if event should be logged at current level."""
        if self._level == AuditLevel.DEBUG:
            return True
        if self._level == AuditLevel.DETAILED:
            return True
        if self._level == AuditLevel.STANDARD:
            return (event_type in self._level_map[AuditLevel.MINIMAL] or
                    event_type in self._level_map[AuditLevel.STANDARD])
        if self._level == AuditLevel.MINIMAL:
            return event_type in self._level_map[AuditLevel.MINIMAL]
        return False
    
    def log(
        self,
        event_type: AuditEventType,
        action: str = "",
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        outcome: str = "success",
        duration_ms: Optional[float] = None,
        parent_event_id: Optional[str] = None,
    ) -> Optional[AuditEvent]:
        """Log an audit event."""
        if not self._should_log(event_type):
            return None
        
        event = AuditEvent(
            id="",
            event_type=event_type,
            timestamp=datetime.utcnow(),
            agent_id=agent_id,
            task_id=task_id,
            action=action,
            details=details or {},
            outcome=outcome,
            duration_ms=duration_ms,
            parent_event_id=parent_event_id,
        )
        
        self._events.append(event)
        
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                pass
        
        return event
    
    # Convenience methods
    def log_agent_start(self, agent_id: str, **details) -> Optional[AuditEvent]:
        return self.log(AuditEventType.AGENT_START, "Agent started", agent_id, details=details)
    
    def log_agent_stop(self, agent_id: str, **details) -> Optional[AuditEvent]:
        return self.log(AuditEventType.AGENT_STOP, "Agent stopped", agent_id, details=details)
    
    def log_task_start(self, task_id: str, agent_id: str, **details) -> Optional[AuditEvent]:
        return self.log(AuditEventType.TASK_START, "Task started", agent_id, task_id, details)
    
    def log_task_complete(self, task_id: str, agent_id: str, duration_ms: float, **details) -> Optional[AuditEvent]:
        return self.log(AuditEventType.TASK_COMPLETE, "Task completed", agent_id, task_id, details, "success", duration_ms)
    
    def log_task_fail(self, task_id: str, agent_id: str, error: str, **details) -> Optional[AuditEvent]:
        details["error"] = error
        return self.log(AuditEventType.TASK_FAIL, "Task failed", agent_id, task_id, details, "failure")
    
    def log_safety_violation(self, agent_id: str, rule: str, action: str, **details) -> Optional[AuditEvent]:
        details["rule"] = rule
        return self.log(AuditEventType.SAFETY_VIOLATION, action, agent_id, details=details, outcome="blocked")
    
    def log_memory_write(self, agent_id: str, memory_id: str, **details) -> Optional[AuditEvent]:
        details["memory_id"] = memory_id
        return self.log(AuditEventType.MEMORY_WRITE, "Memory written", agent_id, details=details)
    
    def log_proposal_apply(self, agent_id: str, proposal_id: str, **details) -> Optional[AuditEvent]:
        details["proposal_id"] = proposal_id
        return self.log(AuditEventType.PROPOSAL_APPLY, "Proposal applied", agent_id, details=details)
    
    def query(self, query: AuditQuery) -> list[AuditEvent]:
        """Query audit events."""
        results = [e for e in self._events if query.matches(e)]
        return results[-query.limit:]
    
    def get_events(
        self,
        agent_id: Optional[str] = None,
        event_types: Optional[list[AuditEventType]] = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Get events with simple filtering."""
        return self.query(AuditQuery(
            agent_id=agent_id,
            event_types=event_types,
            limit=limit,
        ))
    
    def get_recent(self, limit: int = 50) -> list[AuditEvent]:
        """Get most recent events."""
        return list(self._events)[-limit:]
    
    def get_stats(self) -> dict[str, Any]:
        """Get audit statistics."""
        events = list(self._events)
        by_type = {}
        by_outcome = {"success": 0, "failure": 0, "blocked": 0}
        by_agent: dict[str, int] = {}
        
        for e in events:
            by_type[e.event_type.value] = by_type.get(e.event_type.value, 0) + 1
            by_outcome[e.outcome] = by_outcome.get(e.outcome, 0) + 1
            if e.agent_id:
                by_agent[e.agent_id] = by_agent.get(e.agent_id, 0) + 1
        
        return {
            "total_events": len(events),
            "by_type": by_type,
            "by_outcome": by_outcome,
            "by_agent": by_agent,
            "level": self._level.value,
        }
    
    def export(self, query: Optional[AuditQuery] = None) -> list[dict[str, Any]]:
        """Export events as dictionaries."""
        if query:
            events = self.query(query)
        else:
            events = list(self._events)
        return [e.to_dict() for e in events]
    
    def clear(self) -> int:
        """Clear all events."""
        count = len(self._events)
        self._events.clear()
        return count
    
    def add_listener(self, callback: Callable[[AuditEvent], None]) -> None:
        """Add event listener."""
        self._listeners.append(callback)
    
    def remove_listener(self, callback: Callable[[AuditEvent], None]) -> None:
        """Remove event listener."""
        if callback in self._listeners:
            self._listeners.remove(callback)
    
    def set_level(self, level: AuditLevel) -> None:
        """Set audit level."""
        self._level = level
