"""
DMM Runtime Module.

Provides runtime safety, resource management, and audit logging for Agent OS.

Public API:
-----------

Resources:
    ResourceManager - Manages resource limits and quotas
    ResourceType - Types of resources
    ResourceLimit - Limit configuration
    ResourceQuota - Agent quota
    LimitAction - Action when limit reached

Safety:
    SafetyManager - Enforces safety constraints
    SafetyPolicy - Collection of safety rules
    SafetyRule - Individual safety rule
    SafetyViolation - Violation record
    ActionCategory - Categories of actions
    PermissionLevel - Permission levels
    ViolationSeverity - Violation severity levels

Audit:
    AuditLogger - Comprehensive audit logging
    AuditEvent - Audit log event
    AuditEventType - Types of events
    AuditLevel - Logging verbosity
    AuditQuery - Query parameters
"""

from dmm.agentos.runtime.resources import (
    ResourceManager,
    ResourceType,
    ResourceLimit,
    ResourceUsage,
    ResourceQuota,
    LimitAction,
)

from dmm.agentos.runtime.safety import (
    SafetyManager,
    SafetyPolicy,
    SafetyRule,
    SafetyViolation,
    ActionCategory,
    PermissionLevel,
    ViolationSeverity,
)

from dmm.agentos.runtime.audit import (
    AuditLogger,
    AuditEvent,
    AuditEventType,
    AuditLevel,
    AuditQuery,
)

__all__ = [
    # Resources
    "ResourceManager",
    "ResourceType",
    "ResourceLimit",
    "ResourceUsage",
    "ResourceQuota",
    "LimitAction",
    # Safety
    "SafetyManager",
    "SafetyPolicy",
    "SafetyRule",
    "SafetyViolation",
    "ActionCategory",
    "PermissionLevel",
    "ViolationSeverity",
    # Audit
    "AuditLogger",
    "AuditEvent",
    "AuditEventType",
    "AuditLevel",
    "AuditQuery",
]
