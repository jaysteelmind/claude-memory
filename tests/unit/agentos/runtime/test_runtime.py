"""Unit tests for runtime module (resources, safety, audit)."""

import pytest
from datetime import datetime, timedelta

from dmm.agentos.runtime import (
    # Resources
    ResourceManager, ResourceType, ResourceLimit, LimitAction,
    # Safety
    SafetyManager, SafetyPolicy, SafetyRule, ActionCategory, PermissionLevel, ViolationSeverity,
    # Audit
    AuditLogger, AuditEvent, AuditEventType, AuditLevel, AuditQuery,
)


# =============================================================================
# Resource Manager Tests
# =============================================================================

class TestResourceManager:
    """Tests for ResourceManager."""
    
    @pytest.fixture
    def manager(self):
        return ResourceManager()
    
    def test_create_quota(self, manager):
        quota = manager.create_quota("agent_1")
        assert quota.agent_id == "agent_1"
    
    def test_set_and_check_limit(self, manager):
        manager.set_agent_limit("agent_1", ResourceLimit(
            resource_type=ResourceType.TOKENS,
            max_value=1000,
            action=LimitAction.BLOCK,
        ))
        
        allowed, _ = manager.check_limit("agent_1", ResourceType.TOKENS, 500)
        assert allowed
        
        allowed, action = manager.check_limit("agent_1", ResourceType.TOKENS, 1500)
        assert not allowed
        assert action == LimitAction.BLOCK
    
    def test_consume_resource(self, manager):
        manager.set_agent_limit("agent_1", ResourceLimit(
            resource_type=ResourceType.API_CALLS,
            max_value=10,
        ))
        
        for _ in range(10):
            assert manager.consume("agent_1", ResourceType.API_CALLS)
        
        assert not manager.consume("agent_1", ResourceType.API_CALLS)
    
    def test_get_usage_and_remaining(self, manager):
        manager.set_agent_limit("agent_1", ResourceLimit(
            resource_type=ResourceType.TOKENS,
            max_value=100,
        ))
        manager.consume("agent_1", ResourceType.TOKENS, 30)
        
        assert manager.get_usage("agent_1", ResourceType.TOKENS) == 30
        assert manager.get_remaining("agent_1", ResourceType.TOKENS) == 70
    
    def test_reset_usage(self, manager):
        manager.set_agent_limit("agent_1", ResourceLimit(
            resource_type=ResourceType.TOKENS,
            max_value=100,
        ))
        manager.consume("agent_1", ResourceType.TOKENS, 50)
        manager.reset_usage("agent_1", ResourceType.TOKENS)
        
        assert manager.get_usage("agent_1", ResourceType.TOKENS) == 0
    
    def test_global_limit(self, manager):
        manager.set_global_limit(ResourceLimit(
            resource_type=ResourceType.MEMORY,
            max_value=1000,
        ))
        
        manager.consume("agent_1", ResourceType.MEMORY, 600)
        manager.consume("agent_2", ResourceType.MEMORY, 300)
        
        allowed, _ = manager.check_limit("agent_3", ResourceType.MEMORY, 200)
        assert not allowed
    
    def test_warning_callback(self, manager):
        warnings = []
        manager.on_warning(lambda a, r, ratio: warnings.append((a, r, ratio)))
        
        manager.set_agent_limit("agent_1", ResourceLimit(
            resource_type=ResourceType.TOKENS,
            max_value=100,
            warning_threshold=0.8,
        ))
        manager.consume("agent_1", ResourceType.TOKENS, 85)
        
        assert len(warnings) == 1
        assert warnings[0][2] >= 0.8


# =============================================================================
# Safety Manager Tests
# =============================================================================

class TestSafetyManager:
    """Tests for SafetyManager."""
    
    @pytest.fixture
    def manager(self):
        return SafetyManager()
    
    def test_default_rules_block_system(self, manager):
        allowed, violation = manager.check_action(
            "agent_1",
            ActionCategory.FILE_READ,
            {"path": "/etc/passwd"},
        )
        assert not allowed
        assert violation is not None
    
    def test_path_filtering(self, manager):
        policy = SafetyPolicy(
            name="restricted",
            allowed_paths=["/home/user/projects"],
            denied_paths=["/home/user/projects/secrets"],
        )
        manager.set_policy("agent_1", policy)
        
        assert manager.check_file_access("agent_1", "/home/user/projects/code.py")
        assert not manager.check_file_access("agent_1", "/home/user/projects/secrets/key.pem")
    
    def test_host_filtering(self, manager):
        policy = SafetyPolicy(
            name="network",
            allowed_hosts=["api.example.com", "*.trusted.org"],
            denied_hosts=["malware.com"],
        )
        manager.set_policy("agent_1", policy)
        
        allowed, _ = manager.check_action("agent_1", ActionCategory.NETWORK_ACCESS, {"host": "api.example.com"})
        assert allowed
        
        allowed, _ = manager.check_action("agent_1", ActionCategory.NETWORK_ACCESS, {"host": "malware.com"})
        assert not allowed
    
    def test_custom_rule(self, manager):
        policy = SafetyPolicy(name="custom")
        policy.add_rule(SafetyRule(
            id="no_large_files",
            name="Block Large Files",
            description="Prevent large file writes",
            category=ActionCategory.FILE_WRITE,
            condition=lambda ctx: ctx.get("size", 0) > 1000,
            permission=PermissionLevel.DENY,
        ))
        manager.set_policy("agent_1", policy)
        
        allowed, _ = manager.check_action("agent_1", ActionCategory.FILE_WRITE, {"size": 500})
        assert allowed
        
        allowed, _ = manager.check_action("agent_1", ActionCategory.FILE_WRITE, {"size": 2000})
        assert not allowed
    
    def test_violation_tracking(self, manager):
        manager.check_action("agent_1", ActionCategory.FILE_READ, {"path": "/etc/shadow"})
        manager.check_action("agent_1", ActionCategory.FILE_READ, {"path": "/usr/bin/secret"})
        
        violations = manager.get_violations(agent_id="agent_1")
        assert len(violations) >= 2
    
    def test_violation_callback(self, manager):
        violations = []
        manager.on_violation(lambda v: violations.append(v))
        
        manager.check_action("agent_1", ActionCategory.FILE_READ, {"path": "/etc/passwd"})
        
        assert len(violations) == 1


# =============================================================================
# Audit Logger Tests
# =============================================================================

class TestAuditLogger:
    """Tests for AuditLogger."""
    
    @pytest.fixture
    def logger(self):
        return AuditLogger(level=AuditLevel.DETAILED)
    
    def test_log_event(self, logger):
        event = logger.log(
            AuditEventType.TASK_START,
            action="Starting task",
            agent_id="agent_1",
            task_id="task_123",
        )
        
        assert event is not None
        assert event.event_type == AuditEventType.TASK_START
        assert event.agent_id == "agent_1"
    
    def test_convenience_methods(self, logger):
        logger.log_agent_start("agent_1")
        logger.log_task_start("task_1", "agent_1")
        logger.log_task_complete("task_1", "agent_1", 100.5)
        logger.log_safety_violation("agent_1", "rule_1", "blocked_action")
        
        events = logger.get_recent(10)
        assert len(events) == 4
    
    def test_query_events(self, logger):
        logger.log_task_start("task_1", "agent_1")
        logger.log_task_start("task_2", "agent_2")
        logger.log_task_complete("task_1", "agent_1", 50)
        
        query = AuditQuery(agent_id="agent_1")
        results = logger.query(query)
        
        assert len(results) == 2
        assert all(e.agent_id == "agent_1" for e in results)
    
    def test_query_by_type(self, logger):
        logger.log_agent_start("agent_1")
        logger.log_task_start("task_1", "agent_1")
        logger.log_task_fail("task_1", "agent_1", "error")
        
        query = AuditQuery(event_types=[AuditEventType.TASK_FAIL])
        results = logger.query(query)
        
        assert len(results) == 1
        assert results[0].event_type == AuditEventType.TASK_FAIL
    
    def test_level_filtering(self):
        minimal_logger = AuditLogger(level=AuditLevel.MINIMAL)
        
        # Should log
        event1 = minimal_logger.log(AuditEventType.SAFETY_VIOLATION, "violation")
        assert event1 is not None
        
        # Should not log at minimal level
        event2 = minimal_logger.log(AuditEventType.TASK_START, "start")
        assert event2 is None
    
    def test_get_stats(self, logger):
        logger.log_task_start("t1", "a1")
        logger.log_task_complete("t1", "a1", 100)
        logger.log_task_fail("t2", "a1", "err")
        
        stats = logger.get_stats()
        
        assert stats["total_events"] == 3
        assert "by_type" in stats
        assert "by_outcome" in stats
    
    def test_listener(self, logger):
        events = []
        logger.add_listener(lambda e: events.append(e))
        
        logger.log_agent_start("agent_1")
        
        assert len(events) == 1
    
    def test_export(self, logger):
        logger.log_task_start("task_1", "agent_1")
        
        exported = logger.export()
        
        assert len(exported) == 1
        assert exported[0]["task_id"] == "task_1"


class TestAuditEvent:
    """Tests for AuditEvent."""
    
    def test_to_dict(self):
        event = AuditEvent(
            id="evt_123",
            event_type=AuditEventType.TASK_START,
            timestamp=datetime.utcnow(),
            agent_id="agent_1",
            action="test",
        )
        
        data = event.to_dict()
        assert data["id"] == "evt_123"
        assert data["event_type"] == "task_start"
    
    def test_from_dict(self):
        data = {
            "id": "evt_123",
            "event_type": "task_complete",
            "timestamp": datetime.utcnow().isoformat(),
            "agent_id": "agent_1",
            "outcome": "success",
        }
        
        event = AuditEvent.from_dict(data)
        assert event.id == "evt_123"
        assert event.event_type == AuditEventType.TASK_COMPLETE
