"""Tests for the review queue."""

import pytest
from datetime import datetime
from pathlib import Path

from dmm.models.proposal import (
    ProposalStatus,
    ProposalType,
    WriteProposal,
)
from dmm.writeback.queue import ReviewQueue


@pytest.fixture
def temp_queue(tmp_path: Path) -> ReviewQueue:
    """Create a temporary review queue."""
    queue = ReviewQueue(tmp_path)
    queue.initialize()
    yield queue
    queue.close()


@pytest.fixture
def sample_proposal() -> WriteProposal:
    """Create a sample write proposal."""
    return WriteProposal(
        proposal_id="prop_20250111_120000_abcd1234",
        type=ProposalType.CREATE,
        target_path="project/test_memory.md",
        reason="Test memory creation",
        content="""---
id: mem_2025_01_11_001
tags: [test, example]
scope: project
priority: 0.8
confidence: active
status: active
---

# Test Memory

This is a test memory for unit testing.
""",
        proposed_by="test",
    )


class TestReviewQueueInitialization:
    """Tests for queue initialization."""

    def test_initialize_creates_tables(self, tmp_path: Path) -> None:
        """Test that initialize creates required tables."""
        queue = ReviewQueue(tmp_path)
        queue.initialize()
        
        stats = queue.get_stats()
        assert "total" in stats
        assert stats["total"] == 0
        
        queue.close()

    def test_initialize_is_idempotent(self, tmp_path: Path) -> None:
        """Test that initialize can be called multiple times."""
        queue = ReviewQueue(tmp_path)
        queue.initialize()
        queue.initialize()
        
        stats = queue.get_stats()
        assert stats["total"] == 0
        
        queue.close()


class TestReviewQueueEnqueue:
    """Tests for enqueue operations."""

    def test_enqueue_proposal(
        self,
        temp_queue: ReviewQueue,
        sample_proposal: WriteProposal,
    ) -> None:
        """Test enqueuing a proposal."""
        temp_queue.enqueue(sample_proposal)
        
        retrieved = temp_queue.get(sample_proposal.proposal_id)
        assert retrieved is not None
        assert retrieved.proposal_id == sample_proposal.proposal_id
        assert retrieved.type == ProposalType.CREATE
        assert retrieved.target_path == "project/test_memory.md"
        assert retrieved.status == ProposalStatus.PENDING

    def test_enqueue_duplicate_fails(
        self,
        temp_queue: ReviewQueue,
        sample_proposal: WriteProposal,
    ) -> None:
        """Test that enqueuing duplicate proposal fails."""
        temp_queue.enqueue(sample_proposal)
        
        from dmm.core.exceptions import QueueError
        with pytest.raises(QueueError):
            temp_queue.enqueue(sample_proposal)

    def test_enqueue_records_history(
        self,
        temp_queue: ReviewQueue,
        sample_proposal: WriteProposal,
    ) -> None:
        """Test that enqueue creates history entry."""
        temp_queue.enqueue(sample_proposal)
        
        history = temp_queue.get_history(sample_proposal.proposal_id)
        assert len(history) == 1
        assert history[0]["action"] == "enqueue"


class TestReviewQueueRetrieval:
    """Tests for retrieval operations."""

    def test_get_nonexistent_returns_none(self, temp_queue: ReviewQueue) -> None:
        """Test that getting nonexistent proposal returns None."""
        result = temp_queue.get("nonexistent_id")
        assert result is None

    def test_get_by_path(
        self,
        temp_queue: ReviewQueue,
        sample_proposal: WriteProposal,
    ) -> None:
        """Test retrieving proposals by path."""
        temp_queue.enqueue(sample_proposal)
        
        proposals = temp_queue.get_by_path(sample_proposal.target_path)
        assert len(proposals) == 1
        assert proposals[0].proposal_id == sample_proposal.proposal_id

    def test_get_pending(
        self,
        temp_queue: ReviewQueue,
        sample_proposal: WriteProposal,
    ) -> None:
        """Test retrieving pending proposals."""
        temp_queue.enqueue(sample_proposal)
        
        pending = temp_queue.get_pending()
        assert len(pending) == 1
        assert pending[0].status == ProposalStatus.PENDING

    def test_get_by_status(
        self,
        temp_queue: ReviewQueue,
        sample_proposal: WriteProposal,
    ) -> None:
        """Test retrieving proposals by status."""
        temp_queue.enqueue(sample_proposal)
        temp_queue.update_status(
            sample_proposal.proposal_id,
            ProposalStatus.APPROVED,
        )
        
        pending = temp_queue.get_by_status(ProposalStatus.PENDING)
        assert len(pending) == 0
        
        approved = temp_queue.get_by_status(ProposalStatus.APPROVED)
        assert len(approved) == 1


class TestReviewQueueStatusUpdates:
    """Tests for status update operations."""

    def test_update_status(
        self,
        temp_queue: ReviewQueue,
        sample_proposal: WriteProposal,
    ) -> None:
        """Test updating proposal status."""
        temp_queue.enqueue(sample_proposal)
        
        result = temp_queue.update_status(
            sample_proposal.proposal_id,
            ProposalStatus.APPROVED,
            notes="Approved by reviewer",
        )
        assert result is True
        
        proposal = temp_queue.get(sample_proposal.proposal_id)
        assert proposal is not None
        assert proposal.status == ProposalStatus.APPROVED
        assert proposal.reviewer_notes == "Approved by reviewer"

    def test_update_status_nonexistent(self, temp_queue: ReviewQueue) -> None:
        """Test updating nonexistent proposal returns False."""
        result = temp_queue.update_status(
            "nonexistent",
            ProposalStatus.APPROVED,
        )
        assert result is False

    def test_update_status_records_history(
        self,
        temp_queue: ReviewQueue,
        sample_proposal: WriteProposal,
    ) -> None:
        """Test that status updates create history entries."""
        temp_queue.enqueue(sample_proposal)
        temp_queue.update_status(
            sample_proposal.proposal_id,
            ProposalStatus.IN_REVIEW,
        )
        temp_queue.update_status(
            sample_proposal.proposal_id,
            ProposalStatus.APPROVED,
        )
        
        history = temp_queue.get_history(sample_proposal.proposal_id)
        assert len(history) == 3


class TestReviewQueueDelete:
    """Tests for delete operations."""

    def test_delete_proposal(
        self,
        temp_queue: ReviewQueue,
        sample_proposal: WriteProposal,
    ) -> None:
        """Test deleting a proposal."""
        temp_queue.enqueue(sample_proposal)
        
        result = temp_queue.delete(sample_proposal.proposal_id)
        assert result is True
        
        retrieved = temp_queue.get(sample_proposal.proposal_id)
        assert retrieved is None

    def test_delete_nonexistent(self, temp_queue: ReviewQueue) -> None:
        """Test deleting nonexistent proposal returns False."""
        result = temp_queue.delete("nonexistent")
        assert result is False


class TestReviewQueueStats:
    """Tests for statistics."""

    def test_get_stats_empty(self, temp_queue: ReviewQueue) -> None:
        """Test stats on empty queue."""
        stats = temp_queue.get_stats()
        assert stats["total"] == 0

    def test_get_stats_with_proposals(
        self,
        temp_queue: ReviewQueue,
    ) -> None:
        """Test stats with multiple proposals."""
        for i in range(3):
            proposal = WriteProposal(
                proposal_id=f"prop_{i}",
                type=ProposalType.CREATE,
                target_path=f"project/memory_{i}.md",
                reason=f"Test {i}",
                content="test",
            )
            temp_queue.enqueue(proposal)
        
        temp_queue.update_status("prop_0", ProposalStatus.APPROVED)
        temp_queue.update_status("prop_1", ProposalStatus.REJECTED)
        
        stats = temp_queue.get_stats()
        assert stats["total"] == 3
        assert stats["by_status"].get("approved", 0) == 1
        assert stats["by_status"].get("rejected", 0) == 1
        assert stats["by_status"].get("pending", 0) == 1


class TestReviewQueueHelpers:
    """Tests for helper methods."""

    def test_has_pending_for_path(
        self,
        temp_queue: ReviewQueue,
        sample_proposal: WriteProposal,
    ) -> None:
        """Test checking for pending proposals by path."""
        assert temp_queue.has_pending_for_path(sample_proposal.target_path) is False
        
        temp_queue.enqueue(sample_proposal)
        assert temp_queue.has_pending_for_path(sample_proposal.target_path) is True
        
        temp_queue.update_status(sample_proposal.proposal_id, ProposalStatus.REJECTED)
        assert temp_queue.has_pending_for_path(sample_proposal.target_path) is False

    def test_increment_retry(
        self,
        temp_queue: ReviewQueue,
        sample_proposal: WriteProposal,
    ) -> None:
        """Test incrementing retry count."""
        temp_queue.enqueue(sample_proposal)
        
        count = temp_queue.increment_retry(sample_proposal.proposal_id)
        assert count == 1
        
        count = temp_queue.increment_retry(sample_proposal.proposal_id)
        assert count == 2

    def test_set_commit_error(
        self,
        temp_queue: ReviewQueue,
        sample_proposal: WriteProposal,
    ) -> None:
        """Test setting commit error."""
        temp_queue.enqueue(sample_proposal)
        temp_queue.set_commit_error(sample_proposal.proposal_id, "Test error")
        
        proposal = temp_queue.get(sample_proposal.proposal_id)
        assert proposal is not None
        assert proposal.status == ProposalStatus.FAILED
        assert proposal.commit_error == "Test error"
