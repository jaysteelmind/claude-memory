"""
Unit tests for message protocols.

Tests cover:
- Message creation
- Message types and priorities
- Content types
- Serialization
- Message factory
"""

import pytest
from datetime import datetime, timedelta

from dmm.agentos.communication import (
    Message,
    MessageType,
    MessagePriority,
    DeliveryStatus,
    MessageFactory,
    TaskContent,
    QueryContent,
    ErrorContent,
    StatusContent,
    generate_message_id,
    generate_conversation_id,
)


class TestMessageIdGeneration:
    """Tests for ID generation."""
    
    def test_generate_message_id(self):
        """Test message ID generation."""
        msg_id = generate_message_id()
        
        assert msg_id.startswith("msg_")
        assert len(msg_id) == 20  # msg_ + 16 hex chars
    
    def test_message_ids_unique(self):
        """Test message IDs are unique."""
        ids = [generate_message_id() for _ in range(100)]
        assert len(set(ids)) == 100
    
    def test_generate_conversation_id(self):
        """Test conversation ID generation."""
        conv_id = generate_conversation_id()
        
        assert conv_id.startswith("conv_")


class TestMessageCreation:
    """Tests for message creation."""
    
    def test_create_basic_message(self):
        """Test creating basic message."""
        msg = Message(
            sender="agent_1",
            recipient="agent_2",
            message_type=MessageType.INFORM,
            content="Hello",
        )
        
        assert msg.sender == "agent_1"
        assert msg.recipient == "agent_2"
        assert msg.message_type == MessageType.INFORM
        assert msg.content == "Hello"
        assert msg.id.startswith("msg_")
    
    def test_message_defaults(self):
        """Test message default values."""
        msg = Message()
        
        assert msg.message_type == MessageType.INFORM
        assert msg.priority == MessagePriority.NORMAL
        assert msg.delivery_status == DeliveryStatus.PENDING
        assert msg.timestamp is not None
    
    def test_message_with_all_fields(self):
        """Test message with all fields."""
        msg = Message(
            sender="agent_1",
            recipient="agent_2",
            recipients=["agent_3", "agent_4"],
            message_type=MessageType.REQUEST,
            subject="Test Subject",
            content={"key": "value"},
            priority=MessagePriority.HIGH,
            reply_to="msg_previous",
            thread_id="thread_123",
            headers={"custom": "header"},
            tags=["tag1", "tag2"],
            requires_response=True,
        )
        
        assert msg.subject == "Test Subject"
        assert msg.priority == MessagePriority.HIGH
        assert msg.requires_response is True
        assert "tag1" in msg.tags


class TestMessageRouting:
    """Tests for message routing methods."""
    
    def test_is_broadcast(self):
        """Test broadcast detection."""
        direct = Message(recipient="agent_1")
        assert not direct.is_broadcast()
        
        broadcast = Message(recipients=["agent_1", "agent_2"])
        assert broadcast.is_broadcast()
        
        explicit = Message(message_type=MessageType.BROADCAST)
        assert explicit.is_broadcast()
    
    def test_get_all_recipients(self):
        """Test getting all recipients."""
        msg = Message(
            recipient="agent_1",
            recipients=["agent_2", "agent_3"],
        )
        
        all_recips = msg.get_all_recipients()
        
        assert "agent_1" in all_recips
        assert "agent_2" in all_recips
        assert "agent_3" in all_recips


class TestMessageStatus:
    """Tests for message status methods."""
    
    def test_is_expired(self):
        """Test expiration check."""
        # Not expired
        msg1 = Message(expires_at=datetime.utcnow() + timedelta(hours=1))
        assert not msg1.is_expired()
        
        # Expired
        msg2 = Message(expires_at=datetime.utcnow() - timedelta(hours=1))
        assert msg2.is_expired()
        
        # No expiration
        msg3 = Message()
        assert not msg3.is_expired()
    
    def test_mark_sent(self):
        """Test marking as sent."""
        msg = Message()
        msg.mark_sent()
        assert msg.delivery_status == DeliveryStatus.SENT
    
    def test_mark_delivered(self):
        """Test marking as delivered."""
        msg = Message()
        msg.mark_delivered()
        
        assert msg.delivery_status == DeliveryStatus.DELIVERED
        assert msg.delivered_at is not None
    
    def test_mark_read(self):
        """Test marking as read."""
        msg = Message()
        msg.mark_read()
        
        assert msg.delivery_status == DeliveryStatus.READ
        assert msg.read_at is not None


class TestMessageResponses:
    """Tests for response creation methods."""
    
    def test_create_response(self):
        """Test creating response."""
        original = Message(
            sender="agent_1",
            recipient="agent_2",
            subject="Original",
        )
        
        response = original.create_response(content="Response content")
        
        assert response.sender == "agent_2"
        assert response.recipient == "agent_1"
        assert response.reply_to == original.id
        assert response.message_type == MessageType.RESPONSE
    
    def test_create_ack(self):
        """Test creating acknowledgment."""
        original = Message(sender="agent_1", recipient="agent_2")
        ack = original.create_ack()
        
        assert ack.message_type == MessageType.ACK
        assert ack.content["acknowledged"] is True
    
    def test_create_nack(self):
        """Test creating negative acknowledgment."""
        original = Message(sender="agent_1", recipient="agent_2")
        nack = original.create_nack("Unable to process")
        
        assert nack.message_type == MessageType.NACK
        assert nack.content["acknowledged"] is False
        assert nack.content["reason"] == "Unable to process"
    
    def test_create_error_response(self):
        """Test creating error response."""
        original = Message(sender="agent_1", recipient="agent_2")
        error = ErrorContent(
            error_code="ERR001",
            error_message="Something went wrong",
        )
        
        response = original.create_error_response(error)
        
        assert response.message_type == MessageType.ERROR
        assert response.content["error_code"] == "ERR001"


class TestMessageSerialization:
    """Tests for message serialization."""
    
    def test_to_dict(self):
        """Test converting to dictionary."""
        msg = Message(
            sender="agent_1",
            recipient="agent_2",
            message_type=MessageType.INFORM,
            content="Test content",
        )
        
        data = msg.to_dict()
        
        assert data["sender"] == "agent_1"
        assert data["recipient"] == "agent_2"
        assert data["message_type"] == "inform"
        assert data["content"] == "Test content"
    
    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "id": "msg_test123",
            "sender": "agent_1",
            "recipient": "agent_2",
            "message_type": "request",
            "content": {"data": "value"},
            "priority": 8,
        }
        
        msg = Message.from_dict(data)
        
        assert msg.id == "msg_test123"
        assert msg.sender == "agent_1"
        assert msg.message_type == MessageType.REQUEST
        assert msg.priority == MessagePriority.HIGH
    
    def test_round_trip(self):
        """Test serialization round trip."""
        original = Message(
            sender="agent_1",
            recipient="agent_2",
            message_type=MessageType.QUERY,
            content={"query": "test"},
            priority=MessagePriority.URGENT,
            tags=["important"],
        )
        
        restored = Message.from_dict(original.to_dict())
        
        assert restored.sender == original.sender
        assert restored.message_type == original.message_type
        assert restored.priority == original.priority
        assert restored.tags == original.tags
    
    def test_to_json(self):
        """Test JSON serialization."""
        msg = Message(sender="agent_1", content="test")
        json_str = msg.to_json()
        
        assert '"sender": "agent_1"' in json_str
    
    def test_from_json(self):
        """Test JSON deserialization."""
        json_str = '{"sender": "agent_1", "recipient": "agent_2", "message_type": "inform", "content": "test"}'
        msg = Message.from_json(json_str)
        
        assert msg.sender == "agent_1"


class TestContentTypes:
    """Tests for content type classes."""
    
    def test_task_content(self):
        """Test TaskContent."""
        task = TaskContent(
            task_id="task_123",
            task_name="Review Code",
            task_description="Review auth module",
            inputs={"file": "auth.py"},
            status="in_progress",
            progress=50.0,
        )
        
        data = task.to_dict()
        assert data["task_id"] == "task_123"
        assert data["progress"] == 50.0
        
        restored = TaskContent.from_dict(data)
        assert restored.task_name == "Review Code"
    
    def test_query_content(self):
        """Test QueryContent."""
        query = QueryContent(
            query="How do I implement X?",
            context={"language": "Python"},
            max_tokens=500,
        )
        
        data = query.to_dict()
        assert data["query"] == "How do I implement X?"
        
        restored = QueryContent.from_dict(data)
        assert restored.max_tokens == 500
    
    def test_error_content(self):
        """Test ErrorContent."""
        error = ErrorContent(
            error_code="ERR001",
            error_message="Invalid input",
            recoverable=True,
        )
        
        data = error.to_dict()
        assert data["error_code"] == "ERR001"
        
        restored = ErrorContent.from_dict(data)
        assert restored.recoverable is True
    
    def test_status_content(self):
        """Test StatusContent."""
        status = StatusContent(
            agent_id="agent_1",
            status="active",
            load=0.5,
            active_tasks=3,
            capabilities=["code_review", "testing"],
        )
        
        data = status.to_dict()
        assert data["load"] == 0.5
        
        restored = StatusContent.from_dict(data)
        assert "code_review" in restored.capabilities


class TestMessageFactory:
    """Tests for MessageFactory."""
    
    def test_create_request(self):
        """Test creating request message."""
        msg = MessageFactory.create_request(
            sender="agent_1",
            recipient="agent_2",
            subject="Help needed",
            content={"question": "How?"},
        )
        
        assert msg.message_type == MessageType.REQUEST
        assert msg.requires_response is True
    
    def test_create_task_assignment(self):
        """Test creating task assignment."""
        task = TaskContent(
            task_id="task_123",
            task_name="Review Code",
        )
        
        msg = MessageFactory.create_task_assignment(
            sender="agent_1",
            recipient="agent_2",
            task=task,
        )
        
        assert msg.message_type == MessageType.TASK_ASSIGN
        assert msg.requires_response is True
    
    def test_create_broadcast(self):
        """Test creating broadcast message."""
        msg = MessageFactory.create_broadcast(
            sender="agent_1",
            recipients=["agent_2", "agent_3"],
            subject="Announcement",
            content="Important update",
        )
        
        assert msg.message_type == MessageType.BROADCAST
        assert len(msg.recipients) == 2
    
    def test_create_heartbeat(self):
        """Test creating heartbeat message."""
        msg = MessageFactory.create_heartbeat("agent_1")
        
        assert msg.message_type == MessageType.HEARTBEAT
        assert msg.sender == "agent_1"
        assert msg.priority == MessagePriority.LOW
