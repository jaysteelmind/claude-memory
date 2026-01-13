"""Unit tests for ConflictResolver."""

import pytest
from unittest.mock import MagicMock
from datetime import datetime

from dmm.conflicts.resolver import ConflictResolver
from dmm.models.conflict import (
    Conflict,
    ConflictMemory,
    ConflictStatus,
    ConflictType,
    DetectionMethod,
    ResolutionAction,
    ResolutionRequest,
)
from dmm.core.exceptions import ConflictNotFoundError


@pytest.fixture
def mock_conflict_store():
    """Create a mock conflict store."""
    store = MagicMock()
    return store


@pytest.fixture
def mock_memory_store():
    """Create a mock memory store."""
    store = MagicMock()
    store.update_memory_status.return_value = True
    return store


@pytest.fixture
def sample_conflict():
    """Create a sample conflict."""
    return Conflict(
        conflict_id="conflict_test_001",
        memories=[
            ConflictMemory(
                memory_id="mem_001",
                path="project/old.md",
                title="Old Config",
                summary="Old configuration",
                scope="project",
                priority=0.5,
                role="primary",
            ),
            ConflictMemory(
                memory_id="mem_002",
                path="project/new.md",
                title="New Config",
                summary="New configuration",
                scope="project",
                priority=0.7,
                role="secondary",
            ),
        ],
        conflict_type=ConflictType.CONTRADICTORY,
        detection_method=DetectionMethod.TAG_OVERLAP,
        confidence=0.85,
        description="Conflicting configs",
        evidence="{}",
        status=ConflictStatus.UNRESOLVED,
        detected_at=datetime.utcnow(),
    )


class TestConflictResolver:
    """Tests for ConflictResolver."""

    def test_init(self, mock_conflict_store, mock_memory_store):
        """Test initialization."""
        resolver = ConflictResolver(mock_conflict_store, mock_memory_store)
        assert resolver is not None

    def test_resolve_not_found(self, mock_conflict_store, mock_memory_store):
        """Test resolving non-existent conflict."""
        mock_conflict_store.get.return_value = None
        resolver = ConflictResolver(mock_conflict_store, mock_memory_store)
        
        request = ResolutionRequest(
            conflict_id="nonexistent",
            action=ResolutionAction.DISMISS,
        )
        
        with pytest.raises(ConflictNotFoundError):
            resolver.resolve(request)

    def test_resolve_already_resolved(self, mock_conflict_store, mock_memory_store, sample_conflict):
        """Test resolving already resolved conflict."""
        sample_conflict.status = ConflictStatus.RESOLVED
        sample_conflict.resolution_action = ResolutionAction.DEPRECATE
        mock_conflict_store.get.return_value = sample_conflict
        
        resolver = ConflictResolver(mock_conflict_store, mock_memory_store)
        
        request = ResolutionRequest(
            conflict_id=sample_conflict.conflict_id,
            action=ResolutionAction.DISMISS,
        )
        
        result = resolver.resolve(request)
        
        assert not result.success
        assert "already resolved" in result.error.lower()

    def test_resolve_deprecate(self, mock_conflict_store, mock_memory_store, sample_conflict):
        """Test deprecate resolution."""
        mock_conflict_store.get.return_value = sample_conflict
        resolver = ConflictResolver(mock_conflict_store, mock_memory_store)
        
        request = ResolutionRequest(
            conflict_id=sample_conflict.conflict_id,
            action=ResolutionAction.DEPRECATE,
            target_memory_id="mem_001",
            reason="Outdated",
            resolved_by="test_user",
        )
        
        result = resolver.resolve(request)
        
        assert result.success
        assert result.action_taken == ResolutionAction.DEPRECATE
        assert "mem_001" in result.memories_deprecated
        mock_memory_store.update_memory_status.assert_called_with(
            memory_id="mem_001",
            status="deprecated",
        )

    def test_resolve_deprecate_missing_target(self, mock_conflict_store, mock_memory_store, sample_conflict):
        """Test deprecate without target memory."""
        mock_conflict_store.get.return_value = sample_conflict
        resolver = ConflictResolver(mock_conflict_store, mock_memory_store)
        
        request = ResolutionRequest(
            conflict_id=sample_conflict.conflict_id,
            action=ResolutionAction.DEPRECATE,
            # No target_memory_id
        )
        
        result = resolver.resolve(request)
        
        assert not result.success
        assert "target_memory_id" in result.error.lower()

    def test_resolve_deprecate_target_not_in_conflict(self, mock_conflict_store, mock_memory_store, sample_conflict):
        """Test deprecate with invalid target."""
        mock_conflict_store.get.return_value = sample_conflict
        resolver = ConflictResolver(mock_conflict_store, mock_memory_store)
        
        request = ResolutionRequest(
            conflict_id=sample_conflict.conflict_id,
            action=ResolutionAction.DEPRECATE,
            target_memory_id="mem_999",  # Not in conflict
        )
        
        result = resolver.resolve(request)
        
        assert not result.success
        assert "not found in conflict" in result.error.lower()

    def test_resolve_dismiss(self, mock_conflict_store, mock_memory_store, sample_conflict):
        """Test dismiss resolution."""
        mock_conflict_store.get.return_value = sample_conflict
        resolver = ConflictResolver(mock_conflict_store, mock_memory_store)
        
        request = ResolutionRequest(
            conflict_id=sample_conflict.conflict_id,
            action=ResolutionAction.DISMISS,
            dismiss_reason="False positive - different contexts",
            resolved_by="test_user",
        )
        
        result = resolver.resolve(request)
        
        assert result.success
        assert result.action_taken == ResolutionAction.DISMISS
        mock_conflict_store.update_status.assert_called()

    def test_resolve_merge_missing_content(self, mock_conflict_store, mock_memory_store, sample_conflict):
        """Test merge without content."""
        mock_conflict_store.get.return_value = sample_conflict
        resolver = ConflictResolver(mock_conflict_store, mock_memory_store)
        
        request = ResolutionRequest(
            conflict_id=sample_conflict.conflict_id,
            action=ResolutionAction.MERGE,
            # No merged_content
        )
        
        result = resolver.resolve(request)
        
        assert not result.success
        assert "merged_content" in result.error.lower()

    def test_resolve_clarify_missing_clarification(self, mock_conflict_store, mock_memory_store, sample_conflict):
        """Test clarify without clarification text."""
        mock_conflict_store.get.return_value = sample_conflict
        resolver = ConflictResolver(mock_conflict_store, mock_memory_store)
        
        request = ResolutionRequest(
            conflict_id=sample_conflict.conflict_id,
            action=ResolutionAction.CLARIFY,
            # No clarification
        )
        
        result = resolver.resolve(request)
        
        assert not result.success
        assert "clarification" in result.error.lower()

    def test_resolve_clarify_success(self, mock_conflict_store, mock_memory_store, sample_conflict):
        """Test successful clarify resolution."""
        mock_conflict_store.get.return_value = sample_conflict
        resolver = ConflictResolver(mock_conflict_store, mock_memory_store)
        
        request = ResolutionRequest(
            conflict_id=sample_conflict.conflict_id,
            action=ResolutionAction.CLARIFY,
            clarification="mem_001 applies to development, mem_002 applies to production",
            resolved_by="test_user",
        )
        
        result = resolver.resolve(request)
        
        assert result.success
        assert result.action_taken == ResolutionAction.CLARIFY
        assert len(result.memories_modified) == 2

    def test_resolve_defer(self, mock_conflict_store, mock_memory_store, sample_conflict):
        """Test defer resolution."""
        mock_conflict_store.get.return_value = sample_conflict
        resolver = ConflictResolver(mock_conflict_store, mock_memory_store)
        
        request = ResolutionRequest(
            conflict_id=sample_conflict.conflict_id,
            action=ResolutionAction.DEFER,
            reason="Need more context from team",
            resolved_by="test_user",
        )
        
        result = resolver.resolve(request)
        
        assert result.success
        assert result.action_taken == ResolutionAction.DEFER

    def test_resolve_logs_resolution(self, mock_conflict_store, mock_memory_store, sample_conflict):
        """Test that resolution is logged."""
        mock_conflict_store.get.return_value = sample_conflict
        resolver = ConflictResolver(mock_conflict_store, mock_memory_store)
        
        request = ResolutionRequest(
            conflict_id=sample_conflict.conflict_id,
            action=ResolutionAction.DISMISS,
            resolved_by="test_user",
            reason="False positive",
        )
        
        result = resolver.resolve(request)
        
        assert result.success
        mock_conflict_store.log_resolution.assert_called()

    def test_batch_dismiss(self, mock_conflict_store, mock_memory_store, sample_conflict):
        """Test batch dismissal."""
        mock_conflict_store.get.return_value = sample_conflict
        resolver = ConflictResolver(mock_conflict_store, mock_memory_store)
        
        results = resolver.batch_dismiss(
            conflict_ids=["conflict_001", "conflict_002"],
            reason="Bulk cleanup",
            resolved_by="admin",
        )
        
        assert "conflict_001" in results
        assert "conflict_002" in results

    def test_resolve_handles_deprecation_error(self, mock_conflict_store, mock_memory_store, sample_conflict):
        """Test that deprecation errors are handled gracefully."""
        mock_conflict_store.get.return_value = sample_conflict
        mock_memory_store.update_memory_status.side_effect = Exception("DB error")
        
        resolver = ConflictResolver(mock_conflict_store, mock_memory_store)
        
        request = ResolutionRequest(
            conflict_id=sample_conflict.conflict_id,
            action=ResolutionAction.DEPRECATE,
            target_memory_id="mem_001",
        )
        
        result = resolver.resolve(request)
        
        # Resolution should fail gracefully
        assert not result.success
        assert result.error is not None
