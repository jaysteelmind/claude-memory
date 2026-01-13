"""Unit tests for conflict models."""

import pytest
from datetime import datetime

from dmm.models.conflict import (
    Conflict,
    ConflictCandidate,
    ConflictMemory,
    ConflictStats,
    ConflictStatus,
    ConflictType,
    DetectionMethod,
    MergeResult,
    ResolutionAction,
    ResolutionRequest,
    ResolutionResult,
    ScanRequest,
    ScanResult,
)


class TestConflictMemory:
    """Tests for ConflictMemory dataclass."""

    def test_create_conflict_memory(self):
        """Test creating a ConflictMemory."""
        mem = ConflictMemory(
            memory_id="mem_001",
            path="project/test.md",
            title="Test Memory",
            summary="A test memory",
            scope="project",
            priority=0.7,
            role="primary",
        )
        
        assert mem.memory_id == "mem_001"
        assert mem.path == "project/test.md"
        assert mem.title == "Test Memory"
        assert mem.role == "primary"

    def test_to_dict(self):
        """Test serialization to dict."""
        mem = ConflictMemory(
            memory_id="mem_001",
            path="test.md",
            title="Test",
            summary="Summary",
            scope="global",
            priority=0.5,
            role="secondary",
            key_claims=["claim1", "claim2"],
        )
        
        d = mem.to_dict()
        assert d["memory_id"] == "mem_001"
        assert d["key_claims"] == ["claim1", "claim2"]

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "memory_id": "mem_002",
            "path": "agent/rules.md",
            "title": "Rules",
            "summary": "Agent rules",
            "scope": "agent",
            "priority": 0.9,
            "role": "primary",
            "key_claims": ["rule1"],
            "last_modified": "2025-01-01T00:00:00",
        }
        
        mem = ConflictMemory.from_dict(data)
        assert mem.memory_id == "mem_002"
        assert mem.scope == "agent"
        assert mem.key_claims == ["rule1"]


class TestConflict:
    """Tests for Conflict dataclass."""

    def test_create_conflict(self):
        """Test creating a Conflict."""
        conflict = Conflict(
            conflict_id="conflict_20250101_abc123",
            memories=[
                ConflictMemory(
                    memory_id="mem_001",
                    path="a.md",
                    title="A",
                    summary="",
                    scope="global",
                    priority=0.5,
                    role="primary",
                ),
                ConflictMemory(
                    memory_id="mem_002",
                    path="b.md",
                    title="B",
                    summary="",
                    scope="global",
                    priority=0.5,
                    role="secondary",
                ),
            ],
            conflict_type=ConflictType.CONTRADICTORY,
            detection_method=DetectionMethod.TAG_OVERLAP,
            confidence=0.85,
            description="Test conflict",
            evidence="{'test': 'data'}",
            status=ConflictStatus.UNRESOLVED,
        )
        
        assert conflict.conflict_id == "conflict_20250101_abc123"
        assert conflict.conflict_type == ConflictType.CONTRADICTORY
        assert conflict.confidence == 0.85
        assert len(conflict.memories) == 2

    def test_memory_ids_property(self):
        """Test memory_ids property."""
        conflict = Conflict(
            conflict_id="test",
            memories=[
                ConflictMemory(
                    memory_id="mem_001", path="", title="", summary="",
                    scope="global", priority=0.5, role="primary"
                ),
                ConflictMemory(
                    memory_id="mem_002", path="", title="", summary="",
                    scope="global", priority=0.5, role="secondary"
                ),
            ],
            conflict_type=ConflictType.DUPLICATE,
            detection_method=DetectionMethod.SEMANTIC_SIMILARITY,
            confidence=0.9,
            description="",
            evidence="",
            status=ConflictStatus.UNRESOLVED,
        )
        
        assert conflict.memory_ids == ["mem_001", "mem_002"]

    def test_is_resolved_property(self):
        """Test is_resolved property."""
        conflict = Conflict(
            conflict_id="test",
            memories=[],
            conflict_type=ConflictType.CONTRADICTORY,
            detection_method=DetectionMethod.MANUAL,
            confidence=1.0,
            description="",
            evidence="",
            status=ConflictStatus.UNRESOLVED,
        )
        
        assert not conflict.is_resolved
        
        conflict.status = ConflictStatus.RESOLVED
        assert conflict.is_resolved
        
        conflict.status = ConflictStatus.DISMISSED
        assert conflict.is_resolved

    def test_memory_pair_hash(self):
        """Test memory_pair_hash is consistent."""
        conflict = Conflict(
            conflict_id="test",
            memories=[
                ConflictMemory(
                    memory_id="mem_002", path="", title="", summary="",
                    scope="global", priority=0.5, role="primary"
                ),
                ConflictMemory(
                    memory_id="mem_001", path="", title="", summary="",
                    scope="global", priority=0.5, role="secondary"
                ),
            ],
            conflict_type=ConflictType.CONTRADICTORY,
            detection_method=DetectionMethod.TAG_OVERLAP,
            confidence=0.8,
            description="",
            evidence="",
            status=ConflictStatus.UNRESOLVED,
        )
        
        # Hash should be consistent regardless of order
        expected_hash = "mem_001|mem_002"
        assert conflict.memory_pair_hash == expected_hash


class TestConflictCandidate:
    """Tests for ConflictCandidate dataclass."""

    def test_pair_key_sorted(self):
        """Test pair_key is always sorted."""
        candidate = ConflictCandidate(
            memory_ids=("mem_002", "mem_001"),
            detection_method=DetectionMethod.TAG_OVERLAP,
            raw_score=0.7,
            evidence={"test": True},
        )
        
        assert candidate.pair_key == ("mem_001", "mem_002")

    def test_to_dict(self):
        """Test serialization."""
        candidate = ConflictCandidate(
            memory_ids=("mem_001", "mem_002"),
            detection_method=DetectionMethod.SEMANTIC_SIMILARITY,
            raw_score=0.85,
            evidence={"similarity": 0.85},
        )
        
        d = candidate.to_dict()
        assert d["memory_ids"] == ["mem_001", "mem_002"]
        assert d["detection_method"] == "semantic_similarity"
        assert d["raw_score"] == 0.85


class TestScanRequest:
    """Tests for ScanRequest dataclass."""

    def test_default_methods(self):
        """Test default detection methods."""
        request = ScanRequest(scan_type="full")
        
        assert DetectionMethod.TAG_OVERLAP in request.methods
        assert DetectionMethod.SEMANTIC_SIMILARITY in request.methods
        assert DetectionMethod.SUPERSESSION_CHAIN in request.methods
        assert not request.include_rule_extraction


class TestScanResult:
    """Tests for ScanResult dataclass."""

    def test_success_property(self):
        """Test success property."""
        result = ScanResult(
            scan_id="scan_001",
            scan_type="full",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_ms=100,
            memories_scanned=50,
            methods_used=["tag_overlap"],
            conflicts_detected=5,
            conflicts_new=3,
            conflicts_existing=2,
        )
        
        assert result.success
        
        result.errors = ["Some error"]
        assert not result.success


class TestResolutionRequest:
    """Tests for ResolutionRequest dataclass."""

    def test_deprecate_request(self):
        """Test deprecate resolution request."""
        request = ResolutionRequest(
            conflict_id="conflict_001",
            action=ResolutionAction.DEPRECATE,
            target_memory_id="mem_002",
            reason="Outdated information",
            resolved_by="user",
        )
        
        assert request.action == ResolutionAction.DEPRECATE
        assert request.target_memory_id == "mem_002"

    def test_dismiss_request(self):
        """Test dismiss resolution request."""
        request = ResolutionRequest(
            conflict_id="conflict_001",
            action=ResolutionAction.DISMISS,
            dismiss_reason="False positive",
            resolved_by="system",
        )
        
        assert request.action == ResolutionAction.DISMISS
        assert request.dismiss_reason == "False positive"


class TestResolutionResult:
    """Tests for ResolutionResult dataclass."""

    def test_successful_result(self):
        """Test successful resolution result."""
        result = ResolutionResult(
            success=True,
            conflict_id="conflict_001",
            action_taken=ResolutionAction.DEPRECATE,
            memories_deprecated=["mem_002"],
        )
        
        assert result.success
        assert result.memories_deprecated == ["mem_002"]

    def test_failed_result(self):
        """Test failed resolution result."""
        result = ResolutionResult(
            success=False,
            conflict_id="conflict_001",
            action_taken=ResolutionAction.MERGE,
            error="Missing merged content",
        )
        
        assert not result.success
        assert "Missing" in result.error


class TestConflictStats:
    """Tests for ConflictStats dataclass."""

    def test_stats_to_dict(self):
        """Test stats serialization."""
        stats = ConflictStats(
            total=100,
            unresolved=50,
            in_progress=10,
            resolved=30,
            dismissed=10,
            by_type={"contradictory": 60, "duplicate": 40},
            by_method={"tag_overlap": 70, "semantic_similarity": 30},
            avg_confidence=0.75,
        )
        
        d = stats.to_dict()
        assert d["total"] == 100
        assert d["unresolved"] == 50
        assert d["by_type"]["contradictory"] == 60


class TestMergeResult:
    """Tests for MergeResult dataclass."""

    def test_merge_result(self):
        """Test merge result."""
        result = MergeResult(
            total_candidates=10,
            unique_pairs=8,
            new_conflicts=5,
            existing_conflicts=3,
            conflicts=[],
        )
        
        assert result.total_candidates == 10
        assert result.new_conflicts == 5
