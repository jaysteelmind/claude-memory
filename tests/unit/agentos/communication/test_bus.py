"""
Unit tests for message bus.

Tests cover:
- Agent registration
- Message sending and receiving
- Subscriptions
- Dead letter queue
- Statistics
"""

import pytest
from datetime import datetime

from dmm.agentos.communication import (
    MessageBus,
    MessageBusConfig,
    Message,
    MessageType,
    MessagePriority,
    DeliveryStatus,
)


@pytest.fixture
def bus():
    """Create message bus."""
    return MessageBus()


@pytest.fixture
def configured_bus():
    """Create configured message bus."""
    config = MessageBusConfig(
        max_queue_size=100,
        enable_dead_letter_queue=True,
    )
    return MessageBus(config)


class TestAgentRegistration:
    """Tests for agent registration."""
    
    def test_register_agent(self, bus):
        """Test registering an agent."""
        mailbox = bus.register_agent("agent_1")
        
        assert mailbox is not None
        assert mailbox.agent_id == "agent_1"
        assert bus.is_registered("agent_1")
    
    def test_register_duplicate(self, bus):
        """Test registering same agent twice."""
        mailbox1 = bus.register_agent("agent_1")
        mailbox2 = bus.register_agent("agent_1")
        
        assert mailbox1 is mailbox2
    
    def test_unregister_agent(self, bus):
        """Test unregistering an agent."""
        bus.register_agent("agent_1")
        
        assert bus.unregister_agent("agent_1")
        assert not bus.is_registered("agent_1")
    
    def test_unregister_nonexistent(self, bus):
        """Test unregistering nonexistent agent."""
        assert not bus.unregister_agent("nonexistent")
    
    def test_get_mailbox(self, bus):
        """Test getting agent mailbox."""
        bus.register_agent("agent_1")
        
        mailbox = bus.get_mailbox("agent_1")
        assert mailbox is not None
        
        mailbox_none = bus.get_mailbox("nonexistent")
        assert mailbox_none is None
    
    def test_get_registered_agents(self, bus):
        """Test getting list of registered agents."""
        bus.register_agent("agent_1")
        bus.register_agent("agent_2")
        
        agents = bus.get_registered_agents()
        
        assert "agent_1" in agents
        assert "agent_2" in agents


class TestMessageSending:
    """Tests for message sending."""
    
    def test_send_message(self, bus):
        """Test sending a message."""
        bus.register_agent("agent_1")
        bus.register_agent("agent_2")
        
        msg = Message(
            sender="agent_1",
            recipient="agent_2",
            content="Hello",
        )
        
        assert bus.send(msg)
        assert msg.delivery_status == DeliveryStatus.DELIVERED
    
    def test_send_without_sender(self, bus):
        """Test sending message without sender fails."""
        msg = Message(recipient="agent_2", content="Hello")
        
        assert not bus.send(msg)
    
    def test_send_auto_registers_recipient(self, bus):
        """Test sending auto-registers recipient."""
        bus.register_agent("agent_1")
        
        msg = Message(
            sender="agent_1",
            recipient="agent_new",
            content="Hello",
        )
        
        assert bus.send(msg)
        assert bus.is_registered("agent_new")
    
    def test_send_records_in_outbox(self, bus):
        """Test sending records in sender's outbox."""
        bus.register_agent("agent_1")
        bus.register_agent("agent_2")
        
        msg = Message(sender="agent_1", recipient="agent_2", content="Test")
        bus.send(msg)
        
        mailbox = bus.get_mailbox("agent_1")
        assert mailbox.sent_count == 1


class TestBroadcast:
    """Tests for broadcast messages."""
    
    def test_broadcast_to_recipients(self, bus):
        """Test broadcasting to specific recipients."""
        bus.register_agent("agent_1")
        bus.register_agent("agent_2")
        bus.register_agent("agent_3")
        
        msg = Message(
            sender="agent_1",
            recipients=["agent_2", "agent_3"],
            message_type=MessageType.BROADCAST,
            content="Announcement",
        )
        
        assert bus.send(msg)
        
        assert bus.get_pending_count("agent_2") == 1
        assert bus.get_pending_count("agent_3") == 1
    
    def test_broadcast_to_all(self, bus):
        """Test broadcasting to all agents."""
        bus.register_agent("agent_1")
        bus.register_agent("agent_2")
        bus.register_agent("agent_3")
        
        msg = Message(
            sender="agent_1",
            message_type=MessageType.BROADCAST,
            content="To everyone",
        )
        
        bus.send(msg)
        
        # All except sender should receive
        assert bus.get_pending_count("agent_2") == 1
        assert bus.get_pending_count("agent_3") == 1


class TestMessageReceiving:
    """Tests for message receiving."""
    
    def test_receive_message(self, bus):
        """Test receiving a message."""
        bus.register_agent("agent_1")
        bus.register_agent("agent_2")
        
        msg = Message(sender="agent_1", recipient="agent_2", content="Hello")
        bus.send(msg)
        
        received = bus.receive("agent_2")
        
        assert received is not None
        assert received.content == "Hello"
        assert received.delivery_status == DeliveryStatus.READ
    
    def test_receive_empty(self, bus):
        """Test receiving when no messages."""
        bus.register_agent("agent_1")
        
        received = bus.receive("agent_1")
        assert received is None
    
    def test_receive_priority_order(self, bus):
        """Test messages received in priority order."""
        bus.register_agent("agent_1")
        bus.register_agent("agent_2")
        
        # Send low priority first
        low = Message(
            sender="agent_1",
            recipient="agent_2",
            content="Low",
            priority=MessagePriority.LOW,
        )
        bus.send(low)
        
        # Send high priority second
        high = Message(
            sender="agent_1",
            recipient="agent_2",
            content="High",
            priority=MessagePriority.HIGH,
        )
        bus.send(high)
        
        # Should receive high priority first
        first = bus.receive("agent_2")
        assert first.content == "High"
        
        second = bus.receive("agent_2")
        assert second.content == "Low"
    
    def test_receive_all(self, bus):
        """Test receiving all messages."""
        bus.register_agent("agent_1")
        bus.register_agent("agent_2")
        
        for i in range(5):
            msg = Message(sender="agent_1", recipient="agent_2", content=f"Msg {i}")
            bus.send(msg)
        
        messages = bus.receive_all("agent_2", limit=10)
        
        assert len(messages) == 5
    
    def test_peek(self, bus):
        """Test peeking at next message."""
        bus.register_agent("agent_1")
        bus.register_agent("agent_2")
        
        msg = Message(sender="agent_1", recipient="agent_2", content="Peek")
        bus.send(msg)
        
        peeked = bus.peek("agent_2")
        assert peeked is not None
        assert peeked.content == "Peek"
        
        # Message still there
        assert bus.get_pending_count("agent_2") == 1


class TestSubscriptions:
    """Tests for message subscriptions."""
    
    def test_subscribe(self, bus):
        """Test subscribing to messages."""
        bus.register_agent("agent_1")
        received = []
        
        subscription = bus.subscribe(
            subscriber_id="agent_1",
            callback=lambda m: received.append(m),
        )
        
        assert subscription is not None
        assert subscription.active
    
    def test_subscription_callback(self, bus):
        """Test subscription callback is called."""
        bus.register_agent("agent_1")
        bus.register_agent("agent_2")
        received = []
        
        bus.subscribe(
            subscriber_id="agent_2",
            callback=lambda m: received.append(m),
        )
        
        msg = Message(sender="agent_1", recipient="agent_2", content="Test")
        bus.send(msg)
        
        assert len(received) == 1
        assert received[0].content == "Test"
    
    def test_subscription_type_filter(self, bus):
        """Test subscription type filtering."""
        bus.register_agent("agent_1")
        bus.register_agent("agent_2")
        requests = []
        
        bus.subscribe(
            subscriber_id="agent_2",
            callback=lambda m: requests.append(m),
            message_types=[MessageType.REQUEST],
        )
        
        # Send inform (should not trigger)
        bus.send(Message(
            sender="agent_1",
            recipient="agent_2",
            message_type=MessageType.INFORM,
        ))
        
        # Send request (should trigger)
        bus.send(Message(
            sender="agent_1",
            recipient="agent_2",
            message_type=MessageType.REQUEST,
        ))
        
        assert len(requests) == 1
    
    def test_unsubscribe(self, bus):
        """Test unsubscribing."""
        bus.register_agent("agent_1")
        received = []
        
        subscription = bus.subscribe(
            subscriber_id="agent_1",
            callback=lambda m: received.append(m),
        )
        
        assert bus.unsubscribe(subscription)
        assert not subscription.active
    
    def test_subscribe_to_topic(self, bus):
        """Test topic subscription."""
        bus.register_agent("agent_1")
        bus.register_agent("agent_2")
        important = []
        
        bus.subscribe_to_topic(
            subscriber_id="agent_2",
            topic="important",
            callback=lambda m: important.append(m),
        )
        
        bus.send(Message(
            sender="agent_1",
            recipient="agent_2",
            tags=["important"],
            content="Tagged",
        ))
        
        assert len(important) == 1


class TestDeadLetterQueue:
    """Tests for dead letter queue."""
    
    def test_dead_letter_on_no_recipient(self, configured_bus):
        """Test message goes to dead letter when no recipient."""
        configured_bus.register_agent("agent_1")
        
        msg = Message(sender="agent_1", recipient="", content="Lost")
        configured_bus.send(msg)
        
        dead = configured_bus.get_dead_letters()
        assert len(dead) == 1
        assert dead[0][0].content == "Lost"
    
    def test_clear_dead_letters(self, configured_bus):
        """Test clearing dead letters."""
        configured_bus.register_agent("agent_1")
        msg = Message(sender="agent_1", recipient="", content="Lost")
        configured_bus.send(msg)
        
        count = configured_bus.clear_dead_letters()
        
        assert count == 1
        assert len(configured_bus.get_dead_letters()) == 0


class TestStatistics:
    """Tests for bus statistics."""
    
    def test_stats_sent(self, bus):
        """Test sent message stats."""
        bus.register_agent("agent_1")
        bus.register_agent("agent_2")
        
        for _ in range(3):
            bus.send(Message(sender="agent_1", recipient="agent_2"))
        
        stats = bus.get_stats()
        
        assert stats.total_messages_sent == 3
        assert stats.total_messages_delivered == 3
    
    def test_stats_by_type(self, bus):
        """Test stats by message type."""
        bus.register_agent("agent_1")
        bus.register_agent("agent_2")
        
        bus.send(Message(
            sender="agent_1",
            recipient="agent_2",
            message_type=MessageType.REQUEST,
        ))
        bus.send(Message(
            sender="agent_1",
            recipient="agent_2",
            message_type=MessageType.INFORM,
        ))
        
        stats = bus.get_stats()
        
        assert stats.messages_by_type.get("request", 0) == 1
        assert stats.messages_by_type.get("inform", 0) == 1
    
    def test_stats_registered_agents(self, bus):
        """Test registered agents stat."""
        bus.register_agent("agent_1")
        bus.register_agent("agent_2")
        
        stats = bus.get_stats()
        
        assert stats.registered_agents == 2


class TestMailboxOperations:
    """Tests for mailbox operations."""
    
    def test_clear_mailbox(self, bus):
        """Test clearing agent mailbox."""
        bus.register_agent("agent_1")
        bus.register_agent("agent_2")
        
        for _ in range(5):
            bus.send(Message(sender="agent_1", recipient="agent_2"))
        
        cleared = bus.clear_agent_mailbox("agent_2")
        
        assert cleared == 5
        assert bus.get_pending_count("agent_2") == 0
    
    def test_shutdown(self, bus):
        """Test bus shutdown."""
        bus.register_agent("agent_1")
        bus.shutdown()
        
        assert not bus.is_registered("agent_1")
