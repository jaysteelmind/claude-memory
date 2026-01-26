"""
Resource manager for runtime safety.

Handles resource limits, quotas, and usage tracking for agent execution.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional, Callable
from enum import Enum
from threading import Lock
import time


class ResourceType(str, Enum):
    """Types of resources to track."""
    CPU_TIME = "cpu_time"
    MEMORY = "memory"
    TOKENS = "tokens"
    API_CALLS = "api_calls"
    FILE_OPERATIONS = "file_operations"
    NETWORK_REQUESTS = "network_requests"
    TASK_EXECUTIONS = "task_executions"


class LimitAction(str, Enum):
    """Action when limit is reached."""
    WARN = "warn"
    THROTTLE = "throttle"
    BLOCK = "block"
    TERMINATE = "terminate"


@dataclass
class ResourceLimit:
    """A resource limit configuration."""
    resource_type: ResourceType
    max_value: float
    window_seconds: Optional[float] = None  # None = lifetime
    action: LimitAction = LimitAction.BLOCK
    warning_threshold: float = 0.8  # Warn at 80%
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type.value,
            "max_value": self.max_value,
            "window_seconds": self.window_seconds,
            "action": self.action.value,
            "warning_threshold": self.warning_threshold,
        }


@dataclass
class ResourceUsage:
    """Tracked resource usage."""
    resource_type: ResourceType
    current_value: float = 0.0
    window_start: datetime = field(default_factory=datetime.utcnow)
    history: list[tuple[datetime, float]] = field(default_factory=list)
    
    def add(self, amount: float) -> None:
        self.current_value += amount
        self.history.append((datetime.utcnow(), amount))
        # Keep history bounded
        if len(self.history) > 1000:
            self.history = self.history[-500:]
    
    def reset_window(self) -> None:
        self.current_value = 0.0
        self.window_start = datetime.utcnow()
    
    def get_rate(self, seconds: float = 60.0) -> float:
        """Get usage rate over recent period."""
        cutoff = datetime.utcnow() - timedelta(seconds=seconds)
        recent = sum(amt for ts, amt in self.history if ts > cutoff)
        return recent / seconds if seconds > 0 else 0.0


@dataclass 
class ResourceQuota:
    """Resource quota for an agent or task."""
    agent_id: str
    limits: dict[ResourceType, ResourceLimit] = field(default_factory=dict)
    usage: dict[ResourceType, ResourceUsage] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def set_limit(self, limit: ResourceLimit) -> None:
        self.limits[limit.resource_type] = limit
        if limit.resource_type not in self.usage:
            self.usage[limit.resource_type] = ResourceUsage(limit.resource_type)
    
    def get_usage_ratio(self, resource_type: ResourceType) -> float:
        if resource_type not in self.limits or resource_type not in self.usage:
            return 0.0
        limit = self.limits[resource_type]
        usage = self.usage[resource_type]
        return usage.current_value / limit.max_value if limit.max_value > 0 else 0.0


class ResourceManager:
    """
    Manages resource limits and usage tracking.
    
    Features:
    - Per-agent quotas
    - Multiple resource types
    - Windowed limits
    - Usage tracking
    """
    
    def __init__(self) -> None:
        self._quotas: dict[str, ResourceQuota] = {}
        self._global_limits: dict[ResourceType, ResourceLimit] = {}
        self._global_usage: dict[ResourceType, ResourceUsage] = {}
        self._lock = Lock()
        self._on_limit_reached: Optional[Callable[[str, ResourceType, LimitAction], None]] = None
        self._on_warning: Optional[Callable[[str, ResourceType, float], None]] = None
    
    def set_global_limit(self, limit: ResourceLimit) -> None:
        """Set a global resource limit."""
        with self._lock:
            self._global_limits[limit.resource_type] = limit
            if limit.resource_type not in self._global_usage:
                self._global_usage[limit.resource_type] = ResourceUsage(limit.resource_type)
    
    def create_quota(self, agent_id: str) -> ResourceQuota:
        """Create quota for an agent."""
        with self._lock:
            if agent_id not in self._quotas:
                self._quotas[agent_id] = ResourceQuota(agent_id=agent_id)
            return self._quotas[agent_id]
    
    def set_agent_limit(self, agent_id: str, limit: ResourceLimit) -> None:
        """Set limit for specific agent."""
        quota = self.create_quota(agent_id)
        quota.set_limit(limit)
    
    def check_limit(self, agent_id: str, resource_type: ResourceType, amount: float = 1.0) -> tuple[bool, LimitAction]:
        """
        Check if resource usage would exceed limit.
        
        Returns: (allowed, action_if_exceeded)
        """
        with self._lock:
            # Check agent limit
            if agent_id in self._quotas:
                quota = self._quotas[agent_id]
                if resource_type in quota.limits:
                    limit = quota.limits[resource_type]
                    usage = quota.usage.get(resource_type, ResourceUsage(resource_type))
                    
                    # Check window expiry
                    if limit.window_seconds:
                        elapsed = (datetime.utcnow() - usage.window_start).total_seconds()
                        if elapsed > limit.window_seconds:
                            usage.reset_window()
                    
                    new_value = usage.current_value + amount
                    ratio = new_value / limit.max_value if limit.max_value > 0 else 0
                    
                    # Warning
                    if ratio >= limit.warning_threshold and self._on_warning:
                        self._on_warning(agent_id, resource_type, ratio)
                    
                    # Limit exceeded
                    if new_value > limit.max_value:
                        if self._on_limit_reached:
                            self._on_limit_reached(agent_id, resource_type, limit.action)
                        return False, limit.action
            
            # Check global limit
            if resource_type in self._global_limits:
                limit = self._global_limits[resource_type]
                usage = self._global_usage[resource_type]
                
                if limit.window_seconds:
                    elapsed = (datetime.utcnow() - usage.window_start).total_seconds()
                    if elapsed > limit.window_seconds:
                        usage.reset_window()
                
                if usage.current_value + amount > limit.max_value:
                    if self._on_limit_reached:
                        self._on_limit_reached("global", resource_type, limit.action)
                    return False, limit.action
            
            return True, LimitAction.WARN
    
    def consume(self, agent_id: str, resource_type: ResourceType, amount: float = 1.0) -> bool:
        """Consume resource if within limits."""
        allowed, action = self.check_limit(agent_id, resource_type, amount)
        
        if not allowed and action in (LimitAction.BLOCK, LimitAction.TERMINATE):
            return False
        
        with self._lock:
            # Update agent usage
            if agent_id in self._quotas:
                quota = self._quotas[agent_id]
                if resource_type not in quota.usage:
                    quota.usage[resource_type] = ResourceUsage(resource_type)
                quota.usage[resource_type].add(amount)
            
            # Update global usage
            if resource_type in self._global_usage:
                self._global_usage[resource_type].add(amount)
        
        return True
    
    def get_usage(self, agent_id: str, resource_type: ResourceType) -> float:
        """Get current usage for agent."""
        with self._lock:
            if agent_id in self._quotas:
                quota = self._quotas[agent_id]
                if resource_type in quota.usage:
                    return quota.usage[resource_type].current_value
            return 0.0
    
    def get_remaining(self, agent_id: str, resource_type: ResourceType) -> float:
        """Get remaining quota for agent."""
        with self._lock:
            if agent_id in self._quotas:
                quota = self._quotas[agent_id]
                if resource_type in quota.limits and resource_type in quota.usage:
                    limit = quota.limits[resource_type].max_value
                    used = quota.usage[resource_type].current_value
                    return max(0, limit - used)
            return float('inf')
    
    def reset_usage(self, agent_id: str, resource_type: Optional[ResourceType] = None) -> None:
        """Reset usage for agent."""
        with self._lock:
            if agent_id in self._quotas:
                quota = self._quotas[agent_id]
                if resource_type:
                    if resource_type in quota.usage:
                        quota.usage[resource_type].reset_window()
                else:
                    for usage in quota.usage.values():
                        usage.reset_window()
    
    def get_stats(self, agent_id: Optional[str] = None) -> dict[str, Any]:
        """Get usage statistics."""
        with self._lock:
            if agent_id and agent_id in self._quotas:
                quota = self._quotas[agent_id]
                return {
                    "agent_id": agent_id,
                    "usage": {
                        rt.value: {"current": u.current_value, "ratio": quota.get_usage_ratio(rt)}
                        for rt, u in quota.usage.items()
                    },
                }
            return {
                "total_agents": len(self._quotas),
                "global_usage": {
                    rt.value: u.current_value for rt, u in self._global_usage.items()
                },
            }
    
    def on_limit_reached(self, callback: Callable[[str, ResourceType, LimitAction], None]) -> None:
        self._on_limit_reached = callback
    
    def on_warning(self, callback: Callable[[str, ResourceType, float], None]) -> None:
        self._on_warning = callback
