"""
Safety constraints for runtime protection.

Defines and enforces safety rules, permissions, and boundaries for agent actions.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Callable
from enum import Enum
from pathlib import Path
import re


class PermissionLevel(str, Enum):
    """Permission levels for actions."""
    DENY = "deny"
    ASK = "ask"  # Requires confirmation
    ALLOW = "allow"
    ADMIN = "admin"  # Full access


class ActionCategory(str, Enum):
    """Categories of actions."""
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    CODE_EXECUTE = "code_execute"
    CODE_MODIFY = "code_modify"
    NETWORK_ACCESS = "network_access"
    MEMORY_WRITE = "memory_write"
    MEMORY_DELETE = "memory_delete"
    AGENT_CREATE = "agent_create"
    AGENT_MODIFY = "agent_modify"
    SYSTEM_CONFIG = "system_config"


class ViolationSeverity(str, Enum):
    """Severity of safety violations."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class SafetyRule:
    """A safety rule definition."""
    id: str
    name: str
    description: str
    category: ActionCategory
    condition: Callable[[dict[str, Any]], bool]  # Returns True if rule applies
    permission: PermissionLevel = PermissionLevel.DENY
    severity: ViolationSeverity = ViolationSeverity.WARNING
    enabled: bool = True
    
    def check(self, context: dict[str, Any]) -> bool:
        """Check if rule applies to context."""
        if not self.enabled:
            return False
        try:
            return self.condition(context)
        except Exception:
            return False


@dataclass
class SafetyViolation:
    """Record of a safety violation."""
    rule_id: str
    rule_name: str
    severity: ViolationSeverity
    agent_id: str
    action: str
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    blocked: bool = True
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "severity": self.severity.value,
            "agent_id": self.agent_id,
            "action": self.action,
            "timestamp": self.timestamp.isoformat(),
            "blocked": self.blocked,
        }


@dataclass
class SafetyPolicy:
    """A collection of safety rules for an agent or scope."""
    name: str
    rules: list[SafetyRule] = field(default_factory=list)
    default_permission: PermissionLevel = PermissionLevel.ASK
    allowed_paths: list[str] = field(default_factory=list)
    denied_paths: list[str] = field(default_factory=list)
    allowed_hosts: list[str] = field(default_factory=list)
    denied_hosts: list[str] = field(default_factory=list)
    max_file_size_bytes: int = 10 * 1024 * 1024  # 10MB
    
    def add_rule(self, rule: SafetyRule) -> None:
        self.rules.append(rule)
    
    def is_path_allowed(self, path: str) -> bool:
        """Check if file path is allowed."""
        path_obj = Path(path).resolve()
        path_str = str(path_obj)
        
        # Check denied first
        for pattern in self.denied_paths:
            if re.match(pattern, path_str) or pattern in path_str:
                return False
        
        # If allowed list is empty, allow all (except denied)
        if not self.allowed_paths:
            return True
        
        # Check allowed
        for pattern in self.allowed_paths:
            if re.match(pattern, path_str) or pattern in path_str:
                return True
        
        return False
    
    def is_host_allowed(self, host: str) -> bool:
        """Check if network host is allowed."""
        # Check denied first
        for pattern in self.denied_hosts:
            if re.match(pattern, host) or pattern == host:
                return False
        
        if not self.allowed_hosts:
            return True
        
        for pattern in self.allowed_hosts:
            if re.match(pattern, host) or pattern == host:
                return True
        
        return False


class SafetyManager:
    """
    Manages safety constraints and enforcement.
    
    Features:
    - Rule-based safety checks
    - Path/host filtering
    - Violation tracking
    - Policy management
    """
    
    def __init__(self, default_policy: Optional[SafetyPolicy] = None) -> None:
        self._default_policy = default_policy or SafetyPolicy(name="default")
        self._agent_policies: dict[str, SafetyPolicy] = {}
        self._violations: list[SafetyViolation] = []
        self._on_violation: Optional[Callable[[SafetyViolation], None]] = None
        self._confirmation_handler: Optional[Callable[[str, dict], bool]] = None
        
        # Add default rules
        self._setup_default_rules()
    
    def _setup_default_rules(self) -> None:
        """Setup default safety rules."""
        # Prevent system file access
        self._default_policy.add_rule(SafetyRule(
            id="no_system_files",
            name="Block System Files",
            description="Prevent access to system directories",
            category=ActionCategory.FILE_READ,
            condition=lambda ctx: any(
                p in ctx.get("path", "") 
                for p in ["/etc", "/usr", "/bin", "/sbin", "/boot", "/root"]
            ),
            permission=PermissionLevel.DENY,
            severity=ViolationSeverity.ERROR,
        ))
        
        # Prevent code execution of untrusted sources
        self._default_policy.add_rule(SafetyRule(
            id="no_untrusted_exec",
            name="Block Untrusted Execution",
            description="Prevent execution of untrusted code",
            category=ActionCategory.CODE_EXECUTE,
            condition=lambda ctx: not ctx.get("trusted", False),
            permission=PermissionLevel.ASK,
            severity=ViolationSeverity.WARNING,
        ))
        
        # Limit file sizes
        self._default_policy.add_rule(SafetyRule(
            id="file_size_limit",
            name="File Size Limit",
            description="Limit file operation sizes",
            category=ActionCategory.FILE_WRITE,
            condition=lambda ctx: ctx.get("size", 0) > 10 * 1024 * 1024,
            permission=PermissionLevel.DENY,
            severity=ViolationSeverity.WARNING,
        ))
    
    def set_policy(self, agent_id: str, policy: SafetyPolicy) -> None:
        """Set policy for specific agent."""
        self._agent_policies[agent_id] = policy
    
    def get_policy(self, agent_id: str) -> SafetyPolicy:
        """Get policy for agent."""
        return self._agent_policies.get(agent_id, self._default_policy)
    
    def check_action(
        self,
        agent_id: str,
        action: ActionCategory,
        context: dict[str, Any],
    ) -> tuple[bool, Optional[SafetyViolation]]:
        """
        Check if action is allowed.
        
        Returns: (allowed, violation if blocked)
        """
        policy = self.get_policy(agent_id)
        context["action"] = action.value
        context["agent_id"] = agent_id
        
        # Check path-based rules
        if action in (ActionCategory.FILE_READ, ActionCategory.FILE_WRITE, ActionCategory.FILE_DELETE):
            path = context.get("path", "")
            if path and not policy.is_path_allowed(path):
                violation = SafetyViolation(
                    rule_id="path_denied",
                    rule_name="Path Access Denied",
                    severity=ViolationSeverity.ERROR,
                    agent_id=agent_id,
                    action=action.value,
                    context=context,
                )
                self._record_violation(violation)
                return False, violation
        
        # Check host-based rules
        if action == ActionCategory.NETWORK_ACCESS:
            host = context.get("host", "")
            if host and not policy.is_host_allowed(host):
                violation = SafetyViolation(
                    rule_id="host_denied",
                    rule_name="Host Access Denied",
                    severity=ViolationSeverity.ERROR,
                    agent_id=agent_id,
                    action=action.value,
                    context=context,
                )
                self._record_violation(violation)
                return False, violation
        
        # Check custom rules
        for rule in policy.rules:
            if rule.category == action and rule.check(context):
                if rule.permission == PermissionLevel.DENY:
                    violation = SafetyViolation(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        agent_id=agent_id,
                        action=action.value,
                        context=context,
                    )
                    self._record_violation(violation)
                    return False, violation
                
                elif rule.permission == PermissionLevel.ASK:
                    if self._confirmation_handler:
                        allowed = self._confirmation_handler(
                            f"Action requires confirmation: {rule.name}",
                            context,
                        )
                        if not allowed:
                            violation = SafetyViolation(
                                rule_id=rule.id,
                                rule_name=rule.name,
                                severity=rule.severity,
                                agent_id=agent_id,
                                action=action.value,
                                context=context,
                            )
                            self._record_violation(violation)
                            return False, violation
                    else:
                        # No handler, deny by default
                        return False, None
        
        return True, None
    
    def check_file_access(self, agent_id: str, path: str, write: bool = False) -> bool:
        """Convenience method for file access checks."""
        action = ActionCategory.FILE_WRITE if write else ActionCategory.FILE_READ
        allowed, _ = self.check_action(agent_id, action, {"path": path})
        return allowed
    
    def check_code_execution(self, agent_id: str, code: str, trusted: bool = False) -> bool:
        """Convenience method for code execution checks."""
        allowed, _ = self.check_action(
            agent_id, 
            ActionCategory.CODE_EXECUTE,
            {"code": code[:500], "trusted": trusted},
        )
        return allowed
    
    def _record_violation(self, violation: SafetyViolation) -> None:
        """Record a safety violation."""
        self._violations.append(violation)
        if self._on_violation:
            self._on_violation(violation)
        # Keep bounded
        if len(self._violations) > 10000:
            self._violations = self._violations[-5000:]
    
    def get_violations(
        self,
        agent_id: Optional[str] = None,
        severity: Optional[ViolationSeverity] = None,
        limit: int = 100,
    ) -> list[SafetyViolation]:
        """Get recorded violations."""
        violations = self._violations
        if agent_id:
            violations = [v for v in violations if v.agent_id == agent_id]
        if severity:
            violations = [v for v in violations if v.severity == severity]
        return violations[-limit:]
    
    def get_violation_count(self, agent_id: Optional[str] = None) -> dict[str, int]:
        """Get violation counts by severity."""
        violations = self._violations
        if agent_id:
            violations = [v for v in violations if v.agent_id == agent_id]
        
        counts = {s.value: 0 for s in ViolationSeverity}
        for v in violations:
            counts[v.severity.value] += 1
        return counts
    
    def clear_violations(self, agent_id: Optional[str] = None) -> int:
        """Clear violations."""
        if agent_id:
            original = len(self._violations)
            self._violations = [v for v in self._violations if v.agent_id != agent_id]
            return original - len(self._violations)
        else:
            count = len(self._violations)
            self._violations.clear()
            return count
    
    def on_violation(self, callback: Callable[[SafetyViolation], None]) -> None:
        """Set violation callback."""
        self._on_violation = callback
    
    def set_confirmation_handler(self, handler: Callable[[str, dict], bool]) -> None:
        """Set handler for ASK permission level."""
        self._confirmation_handler = handler
