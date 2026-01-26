"""
Message bus for multi-agent communication.

This module provides the infrastructure for routing and delivering
messages between agents, including queuing, subscriptions, and
delivery tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional
from collections import defaultdict
from threading import Lock, RLock
from queue import PriorityQueue, Empty
import asyncio
import heapq


from dmm.agentos.communication.messages import (
    Message,
    MessageType,
    MessagePriority,
    DeliveryStatus,
    generate_conversation_id,
)


# =============================================================================
# Bus Configuration
# =============================================================================

@dataclass
class MessageBusConfig:
    """Configuration for the message bus."""
    
    max_queue_size: int = 10000
    default_ttl_seconds: float = 3600.0
    delivery_timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    enable_persistence: bool = False
    enable_dead_letter_queue: bool = True
    max_dead_letter_size: int = 1000
    cleanup_interval_seconds: float = 60.0


# =============================================================================
# Subscription
# =============================================================================

@dataclass
class Subscription:
    """A subscription to messages."""
    
    subscriber_id: str
    callback: Callable[[Message], None]
    message_types: Optional[list[MessageType]] = None
    sender_filter: Optional[str] = None
    tag_filter: Optional[list[str]] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    active: bool = True
    
    def matches(self, message: Message) -> bool:
        """Check if a message matches this subscription."""
        if not self.active:
            return False
        
        # Check message type filter
        if self.message_types and message.message_type not in self.message_types:
            return False
        
        # Check sender filter
        if self.sender_filter and message.sender != self.sender_filter:
            return False
        
        # Check tag filter
        if self.tag_filter:
            if not any(tag in message.tags for tag in self.tag_filter):
                return False
        
        return True


# =============================================================================
# Agent Mailbox
# =============================================================================

@dataclass
class AgentMailbox:
    """Mailbox for an agent's messages."""
    
    agent_id: str
    inbox: list[tuple[int, int, Message]] = field(default_factory=list)
    outbox: list[Message] = field(default_factory=list)
    sent_count: int = 0
    received_count: int = 0
    _counter: int = 0
    _lock: Lock = field(default_factory=Lock)
    
    def push(self, message: Message) -> None:
        """Push a message to the inbox."""
        with self._lock:
            # Use negative priority for max-heap behavior with heapq (min-heap)
            priority = -message.priority.value
            self._counter += 1
            heapq.heappush(self.inbox, (priority, self._counter, message))
            self.received_count += 1
    
    def pop(self) -> Optional[Message]:
        """Pop the highest priority message from inbox."""
        with self._lock:
            if not self.inbox:
                return None
            _, _, message = heapq.heappop(self.inbox)
            return message
    
    def peek(self) -> Optional[Message]:
        """Peek at the highest priority message without removing."""
        with self._lock:
            if not self.inbox:
                return None
            return self.inbox[0][2]
    
    def get_all(self, limit: int = 100) -> list[Message]:
        """Get all messages up to limit."""
        with self._lock:
            messages = []
            temp = []
            while self.inbox and len(messages) < limit:
                item = heapq.heappop(self.inbox)
                messages.append(item[2])
                temp.append(item)
            # Put messages back
            for item in temp:
                heapq.heappush(self.inbox, item)
            return messages
    
    def size(self) -> int:
        """Get inbox size."""
        with self._lock:
            return len(self.inbox)
    
    def clear(self) -> int:
        """Clear the inbox."""
        with self._lock:
            count = len(self.inbox)
            self.inbox.clear()
            return count
    
    def record_sent(self, message: Message) -> None:
        """Record a sent message."""
        with self._lock:
            self.outbox.append(message)
            self.sent_count += 1
            # Keep outbox bounded
            if len(self.outbox) > 100:
                self.outbox = self.outbox[-100:]


# =============================================================================
# Message Bus Statistics
# =============================================================================

@dataclass
class MessageBusStats:
    """Statistics for the message bus."""
    
    total_messages_sent: int = 0
    total_messages_delivered: int = 0
    total_messages_failed: int = 0
    total_broadcasts: int = 0
    active_subscriptions: int = 0
    registered_agents: int = 0
    dead_letter_count: int = 0
    messages_by_type: dict[str, int] = field(default_factory=dict)
    
    def record_sent(self, message: Message) -> None:
        """Record a sent message."""
        self.total_messages_sent += 1
        msg_type = message.message_type.value
        self.messages_by_type[msg_type] = self.messages_by_type.get(msg_type, 0) + 1
        
        if message.is_broadcast():
            self.total_broadcasts += 1
    
    def record_delivered(self) -> None:
        """Record a delivered message."""
        self.total_messages_delivered += 1
    
    def record_failed(self) -> None:
        """Record a failed delivery."""
        self.total_messages_failed += 1
    
    def to_dict(self) -> dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "total_messages_sent": self.total_messages_sent,
            "total_messages_delivered": self.total_messages_delivered,
            "total_messages_failed": self.total_messages_failed,
            "total_broadcasts": self.total_broadcasts,
            "active_subscriptions": self.active_subscriptions,
            "registered_agents": self.registered_agents,
            "dead_letter_count": self.dead_letter_count,
            "messages_by_type": self.messages_by_type,
            "delivery_rate": (
                self.total_messages_delivered / self.total_messages_sent
                if self.total_messages_sent > 0 else 0.0
            ),
        }


# =============================================================================
# Message Bus
# =============================================================================

class MessageBus:
    """
    Central message bus for agent communication.
    
    The message bus handles:
    - Message routing between agents
    - Topic-based subscriptions
    - Priority-based delivery
    - Message persistence (optional)
    - Dead letter queue for failed deliveries
    """
    
    def __init__(self, config: Optional[MessageBusConfig] = None) -> None:
        """
        Initialize message bus.
        
        Args:
            config: Bus configuration
        """
        self._config = config or MessageBusConfig()
        
        # Agent mailboxes
        self._mailboxes: dict[str, AgentMailbox] = {}
        self._mailboxes_lock = RLock()
        
        # Subscriptions
        self._subscriptions: dict[str, list[Subscription]] = defaultdict(list)
        self._topic_subscriptions: dict[str, list[Subscription]] = defaultdict(list)
        self._subscriptions_lock = Lock()
        
        # Message tracking
        self._pending_responses: dict[str, Message] = {}
        self._pending_lock = Lock()
        
        # Dead letter queue
        self._dead_letters: list[tuple[Message, str]] = []
        self._dead_letter_lock = Lock()
        
        # Statistics
        self._stats = MessageBusStats()
        
        # Callbacks for message handlers
        self._handlers: dict[str, Callable[[Message], Optional[Message]]] = {}
    
    # -------------------------------------------------------------------------
    # Agent Registration
    # -------------------------------------------------------------------------
    
    def register_agent(self, agent_id: str) -> AgentMailbox:
        """
        Register an agent with the bus.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            Agent's mailbox
        """
        with self._mailboxes_lock:
            if agent_id not in self._mailboxes:
                self._mailboxes[agent_id] = AgentMailbox(agent_id=agent_id)
                self._stats.registered_agents += 1
            return self._mailboxes[agent_id]
    
    def unregister_agent(self, agent_id: str) -> bool:
        """
        Unregister an agent from the bus.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            True if unregistered
        """
        with self._mailboxes_lock:
            if agent_id in self._mailboxes:
                del self._mailboxes[agent_id]
                self._stats.registered_agents -= 1
                
                # Remove subscriptions
                with self._subscriptions_lock:
                    if agent_id in self._subscriptions:
                        del self._subscriptions[agent_id]
                
                return True
            return False
    
    def is_registered(self, agent_id: str) -> bool:
        """Check if an agent is registered."""
        with self._mailboxes_lock:
            return agent_id in self._mailboxes
    
    def get_mailbox(self, agent_id: str) -> Optional[AgentMailbox]:
        """Get an agent's mailbox."""
        with self._mailboxes_lock:
            return self._mailboxes.get(agent_id)
    
    # -------------------------------------------------------------------------
    # Message Sending
    # -------------------------------------------------------------------------
    
    def send(self, message: Message) -> bool:
        """
        Send a message.
        
        Args:
            message: Message to send
            
        Returns:
            True if sent successfully
        """
        # Validate message
        if not message.sender:
            return False
        
        # Record in sender's outbox
        sender_mailbox = self.get_mailbox(message.sender)
        if sender_mailbox:
            sender_mailbox.record_sent(message)
        
        # Mark as sent
        message.mark_sent()
        self._stats.record_sent(message)
        
        # Handle broadcast
        if message.is_broadcast():
            return self._send_broadcast(message)
        
        # Handle direct message
        return self._send_direct(message)
    
    def _send_direct(self, message: Message) -> bool:
        """Send a direct message to a single recipient."""
        recipient = message.recipient
        
        if not recipient:
            self._add_to_dead_letter(message, "No recipient specified")
            return False
        
        # Get recipient's mailbox
        mailbox = self.get_mailbox(recipient)
        if mailbox is None:
            # Auto-register if not exists (configurable)
            mailbox = self.register_agent(recipient)
        
        # Deliver message
        mailbox.push(message)
        message.mark_delivered()
        self._stats.record_delivered()
        
        # Track if response is required
        if message.requires_response:
            with self._pending_lock:
                self._pending_responses[message.id] = message
        
        # Notify subscriptions
        self._notify_subscriptions(recipient, message)
        
        return True
    
    def _send_broadcast(self, message: Message) -> bool:
        """Send a broadcast message to multiple recipients."""
        recipients = message.get_all_recipients()
        
        if not recipients:
            # Send to all registered agents
            with self._mailboxes_lock:
                recipients = list(self._mailboxes.keys())
        
        # Remove sender from recipients
        recipients = [r for r in recipients if r != message.sender]
        
        success_count = 0
        for recipient in recipients:
            # Create a copy for each recipient
            msg_copy = Message.from_dict(message.to_dict())
            msg_copy.recipient = recipient
            
            if self._send_direct(msg_copy):
                success_count += 1
        
        return success_count > 0
    
    def _notify_subscriptions(self, agent_id: str, message: Message) -> None:
        """Notify subscriptions about a message."""
        with self._subscriptions_lock:
            # Agent-specific subscriptions
            for subscription in self._subscriptions.get(agent_id, []):
                if subscription.matches(message):
                    try:
                        subscription.callback(message)
                    except Exception:
                        pass
            
            # Topic subscriptions
            for tag in message.tags:
                for subscription in self._topic_subscriptions.get(tag, []):
                    if subscription.matches(message):
                        try:
                            subscription.callback(message)
                        except Exception:
                            pass
    
    # -------------------------------------------------------------------------
    # Message Receiving
    # -------------------------------------------------------------------------
    
    def receive(self, agent_id: str) -> Optional[Message]:
        """
        Receive the next message for an agent.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            Next message or None if no messages
        """
        mailbox = self.get_mailbox(agent_id)
        if mailbox is None:
            return None
        
        message = mailbox.pop()
        if message:
            message.mark_read()
        
        return message
    
    def receive_all(self, agent_id: str, limit: int = 100) -> list[Message]:
        """
        Receive all pending messages for an agent.
        
        Args:
            agent_id: Agent identifier
            limit: Maximum messages to return
            
        Returns:
            List of messages
        """
        mailbox = self.get_mailbox(agent_id)
        if mailbox is None:
            return []
        
        messages = []
        while len(messages) < limit:
            message = mailbox.pop()
            if message is None:
                break
            message.mark_read()
            messages.append(message)
        
        return messages
    
    def peek(self, agent_id: str) -> Optional[Message]:
        """Peek at next message without removing."""
        mailbox = self.get_mailbox(agent_id)
        if mailbox is None:
            return None
        return mailbox.peek()
    
    def get_pending_count(self, agent_id: str) -> int:
        """Get count of pending messages for an agent."""
        mailbox = self.get_mailbox(agent_id)
        if mailbox is None:
            return 0
        return mailbox.size()
    
    # -------------------------------------------------------------------------
    # Request/Response
    # -------------------------------------------------------------------------
    
    def send_request(
        self,
        message: Message,
        timeout_seconds: Optional[float] = None,
    ) -> Optional[Message]:
        """
        Send a request and wait for response (synchronous).
        
        Args:
            message: Request message
            timeout_seconds: Response timeout
            
        Returns:
            Response message or None if timeout
        """
        message.requires_response = True
        timeout = timeout_seconds or message.response_timeout_seconds
        
        # Send the request
        if not self.send(message):
            return None
        
        # Wait for response (polling)
        start_time = datetime.utcnow()
        while (datetime.utcnow() - start_time).total_seconds() < timeout:
            # Check for response in sender's mailbox
            mailbox = self.get_mailbox(message.sender)
            if mailbox:
                # Look for response
                for _, _, msg in mailbox.inbox:
                    if msg.reply_to == message.id:
                        mailbox.pop()  # Remove from queue
                        return msg
            
            # Small delay before next check
            import time
            time.sleep(0.1)
        
        return None
    
    async def send_request_async(
        self,
        message: Message,
        timeout_seconds: Optional[float] = None,
    ) -> Optional[Message]:
        """
        Send a request and wait for response (async).
        
        Args:
            message: Request message
            timeout_seconds: Response timeout
            
        Returns:
            Response message or None if timeout
        """
        message.requires_response = True
        timeout = timeout_seconds or message.response_timeout_seconds
        
        if not self.send(message):
            return None
        
        start_time = datetime.utcnow()
        while (datetime.utcnow() - start_time).total_seconds() < timeout:
            mailbox = self.get_mailbox(message.sender)
            if mailbox:
                for _, _, msg in mailbox.inbox:
                    if msg.reply_to == message.id:
                        mailbox.pop()
                        return msg
            
            await asyncio.sleep(0.1)
        
        return None
    
    def reply(self, original: Message, response_content: Any) -> bool:
        """
        Reply to a message.
        
        Args:
            original: Original message to reply to
            response_content: Response content
            
        Returns:
            True if reply sent
        """
        response = original.create_response(response_content)
        return self.send(response)
    
    # -------------------------------------------------------------------------
    # Subscriptions
    # -------------------------------------------------------------------------
    
    def subscribe(
        self,
        subscriber_id: str,
        callback: Callable[[Message], None],
        message_types: Optional[list[MessageType]] = None,
        sender_filter: Optional[str] = None,
        tag_filter: Optional[list[str]] = None,
    ) -> Subscription:
        """
        Subscribe to messages.
        
        Args:
            subscriber_id: Subscriber agent ID
            callback: Function to call when message matches
            message_types: Filter by message types
            sender_filter: Filter by sender
            tag_filter: Filter by tags
            
        Returns:
            Subscription object
        """
        subscription = Subscription(
            subscriber_id=subscriber_id,
            callback=callback,
            message_types=message_types,
            sender_filter=sender_filter,
            tag_filter=tag_filter,
        )
        
        with self._subscriptions_lock:
            self._subscriptions[subscriber_id].append(subscription)
            self._stats.active_subscriptions += 1
        
        return subscription
    
    def subscribe_to_topic(
        self,
        subscriber_id: str,
        topic: str,
        callback: Callable[[Message], None],
    ) -> Subscription:
        """
        Subscribe to a topic (tag-based).
        
        Args:
            subscriber_id: Subscriber agent ID
            topic: Topic to subscribe to
            callback: Function to call
            
        Returns:
            Subscription object
        """
        subscription = Subscription(
            subscriber_id=subscriber_id,
            callback=callback,
            tag_filter=[topic],
        )
        
        with self._subscriptions_lock:
            self._topic_subscriptions[topic].append(subscription)
            self._stats.active_subscriptions += 1
        
        return subscription
    
    def unsubscribe(self, subscription: Subscription) -> bool:
        """
        Unsubscribe from messages.
        
        Args:
            subscription: Subscription to remove
            
        Returns:
            True if removed
        """
        subscription.active = False
        
        with self._subscriptions_lock:
            # Remove from agent subscriptions
            if subscription.subscriber_id in self._subscriptions:
                subs = self._subscriptions[subscription.subscriber_id]
                if subscription in subs:
                    subs.remove(subscription)
                    self._stats.active_subscriptions -= 1
                    return True
            
            # Remove from topic subscriptions
            if subscription.tag_filter:
                for tag in subscription.tag_filter:
                    if tag in self._topic_subscriptions:
                        if subscription in self._topic_subscriptions[tag]:
                            self._topic_subscriptions[tag].remove(subscription)
                            self._stats.active_subscriptions -= 1
                            return True
        
        return False
    
    # -------------------------------------------------------------------------
    # Dead Letter Queue
    # -------------------------------------------------------------------------
    
    def _add_to_dead_letter(self, message: Message, reason: str) -> None:
        """Add a message to the dead letter queue."""
        if not self._config.enable_dead_letter_queue:
            return
        
        with self._dead_letter_lock:
            self._dead_letters.append((message, reason))
            self._stats.dead_letter_count += 1
            self._stats.record_failed()
            
            # Trim if too large
            if len(self._dead_letters) > self._config.max_dead_letter_size:
                self._dead_letters = self._dead_letters[-self._config.max_dead_letter_size:]
    
    def get_dead_letters(self, limit: int = 100) -> list[tuple[Message, str]]:
        """Get dead letters."""
        with self._dead_letter_lock:
            return self._dead_letters[:limit]
    
    def clear_dead_letters(self) -> int:
        """Clear dead letter queue."""
        with self._dead_letter_lock:
            count = len(self._dead_letters)
            self._dead_letters.clear()
            self._stats.dead_letter_count = 0
            return count
    
    # -------------------------------------------------------------------------
    # Statistics and Management
    # -------------------------------------------------------------------------
    
    def get_stats(self) -> MessageBusStats:
        """Get bus statistics."""
        return self._stats
    
    def get_registered_agents(self) -> list[str]:
        """Get list of registered agent IDs."""
        with self._mailboxes_lock:
            return list(self._mailboxes.keys())
    
    def clear_agent_mailbox(self, agent_id: str) -> int:
        """Clear an agent's mailbox."""
        mailbox = self.get_mailbox(agent_id)
        if mailbox:
            return mailbox.clear()
        return 0
    
    def shutdown(self) -> None:
        """Shutdown the message bus."""
        with self._mailboxes_lock:
            self._mailboxes.clear()
        
        with self._subscriptions_lock:
            self._subscriptions.clear()
            self._topic_subscriptions.clear()
        
        with self._dead_letter_lock:
            self._dead_letters.clear()
