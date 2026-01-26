"""
Unit tests for modification proposals.

Tests cover:
- Proposal creation
- Risk assessment
- Review workflow
- Application and revert
"""

import pytest
from pathlib import Path
import tempfile

from dmm.agentos.selfmod import (
    ProposalManager,
    ModificationProposal,
    ModificationType,
    ProposalStatus,
    RiskLevel,
    CodeChange,
    ReviewResult,
    ReviewComment,
    generate_proposal_id,
)


@pytest.fixture
def manager():
    """Create proposal manager."""
    return ProposalManager(auto_approve_low_risk=False)


@pytest.fixture
def auto_approve_manager():
    """Create manager with auto-approve enabled."""
    return ProposalManager(auto_approve_low_risk=True, require_tests=False)


@pytest.fixture
def sample_change():
    """Create sample code change."""
    return CodeChange(
        file_path="src/module.py",
        original_code="def old():\n    pass\n",
        modified_code="def new():\n    return 1\n",
        change_type=ModificationType.MODIFY_FUNCTION,
        element_name="old",
    )


class TestProposalId:
    """Tests for proposal ID generation."""
    
    def test_generate_id(self):
        """Test ID generation."""
        prop_id = generate_proposal_id()
        
        assert prop_id.startswith("prop_")
        assert len(prop_id) == 17  # prop_ + 12 hex chars
    
    def test_ids_unique(self):
        """Test IDs are unique."""
        ids = [generate_proposal_id() for _ in range(100)]
        assert len(set(ids)) == 100


class TestCodeChange:
    """Tests for CodeChange."""
    
    def test_create_change(self, sample_change):
        """Test creating code change."""
        assert sample_change.file_path == "src/module.py"
        assert sample_change.change_type == ModificationType.MODIFY_FUNCTION
    
    def test_diff_generation(self, sample_change):
        """Test diff generation."""
        diff = sample_change.diff
        
        assert "---" in diff
        assert "+++" in diff
        assert "-def old():" in diff
        assert "+def new():" in diff
    
    def test_lines_added(self):
        """Test lines added calculation."""
        change = CodeChange(
            file_path="test.py",
            original_code="a\n",
            modified_code="a\nb\nc\n",
        )
        
        assert change.lines_added == 2
    
    def test_lines_removed(self):
        """Test lines removed calculation."""
        change = CodeChange(
            file_path="test.py",
            original_code="a\nb\nc\n",
            modified_code="a\n",
        )
        
        assert change.lines_removed == 2
    
    def test_to_dict(self, sample_change):
        """Test serialization."""
        data = sample_change.to_dict()
        
        assert data["file_path"] == "src/module.py"
        assert "diff" in data


class TestReviewComment:
    """Tests for ReviewComment."""
    
    def test_create_comment(self):
        """Test creating review comment."""
        comment = ReviewComment(
            reviewer="agent_1",
            comment="Looks good",
        )
        
        assert comment.reviewer == "agent_1"
        assert not comment.is_blocking
    
    def test_blocking_comment(self):
        """Test blocking comment."""
        comment = ReviewComment(
            reviewer="agent_1",
            comment="Critical issue",
            is_blocking=True,
        )
        
        assert comment.is_blocking


class TestReviewResult:
    """Tests for ReviewResult."""
    
    def test_create_approval(self):
        """Test creating approval."""
        review = ReviewResult(
            reviewer="agent_1",
            approved=True,
            risk_assessment=RiskLevel.LOW,
        )
        
        assert review.approved
        assert review.risk_assessment == RiskLevel.LOW
    
    def test_create_rejection(self):
        """Test creating rejection."""
        review = ReviewResult(
            reviewer="agent_1",
            approved=False,
            comments=[
                ReviewComment(
                    reviewer="agent_1",
                    comment="Missing tests",
                    is_blocking=True,
                )
            ],
        )
        
        assert not review.approved
        assert len(review.comments) == 1


class TestModificationProposal:
    """Tests for ModificationProposal."""
    
    def test_create_proposal(self, sample_change):
        """Test creating proposal."""
        proposal = ModificationProposal(
            title="Update function",
            description="Improve old function",
            author="agent_1",
            changes=[sample_change],
        )
        
        assert proposal.id.startswith("prop_")
        assert proposal.status == ProposalStatus.DRAFT
        assert len(proposal.changes) == 1
    
    def test_submit_proposal(self, sample_change):
        """Test submitting proposal."""
        proposal = ModificationProposal(
            title="Test",
            changes=[sample_change],
        )
        
        assert proposal.submit()
        assert proposal.status == ProposalStatus.PENDING_REVIEW
        assert proposal.submitted_at is not None
    
    def test_cannot_resubmit(self, sample_change):
        """Test cannot submit twice."""
        proposal = ModificationProposal(changes=[sample_change])
        proposal.submit()
        
        assert not proposal.submit()
    
    def test_add_review_approval(self, sample_change):
        """Test adding approval review."""
        proposal = ModificationProposal(changes=[sample_change])
        proposal.submit()
        proposal.start_review()
        
        review = ReviewResult(reviewer="agent_1", approved=True)
        proposal.add_review(review)
        
        assert proposal.status == ProposalStatus.APPROVED
    
    def test_add_review_rejection(self, sample_change):
        """Test adding rejection review."""
        proposal = ModificationProposal(changes=[sample_change])
        proposal.submit()
        proposal.start_review()
        
        review = ReviewResult(reviewer="agent_1", approved=False)
        proposal.add_review(review)
        
        assert proposal.status == ProposalStatus.REJECTED
    
    def test_is_approved(self, sample_change):
        """Test approval check."""
        proposal = ModificationProposal(
            changes=[sample_change],
            required_approvals=2,
        )
        
        proposal.reviews = [
            ReviewResult(reviewer="a", approved=True),
        ]
        assert not proposal.is_approved
        
        proposal.reviews.append(
            ReviewResult(reviewer="b", approved=True)
        )
        assert proposal.is_approved
    
    def test_has_blocking_comments(self, sample_change):
        """Test blocking comments check."""
        proposal = ModificationProposal(changes=[sample_change])
        
        assert not proposal.has_blocking_comments
        
        proposal.reviews = [
            ReviewResult(
                reviewer="a",
                approved=True,
                comments=[
                    ReviewComment(reviewer="a", comment="Issue", is_blocking=True)
                ],
            )
        ]
        
        assert proposal.has_blocking_comments
    
    def test_can_apply(self, sample_change):
        """Test can_apply check."""
        proposal = ModificationProposal(changes=[sample_change])
        
        # Draft cannot apply
        assert not proposal.can_apply
        
        # Approved can apply
        proposal.status = ProposalStatus.APPROVED
        proposal.reviews = [ReviewResult(reviewer="a", approved=True)]
        
        assert proposal.can_apply
    
    def test_total_lines_changed(self):
        """Test total lines calculation."""
        proposal = ModificationProposal(
            changes=[
                CodeChange(
                    file_path="a.py",
                    original_code="1\n",
                    modified_code="1\n2\n3\n",
                ),
                CodeChange(
                    file_path="b.py",
                    original_code="1\n2\n",
                    modified_code="1\n",
                ),
            ]
        )
        
        # Change 1: +2 lines, Change 2: -1 line (abs) + 1 removed = 4
        assert proposal.total_lines_changed == 4
    
    def test_to_dict(self, sample_change):
        """Test serialization."""
        proposal = ModificationProposal(
            title="Test",
            author="agent_1",
            changes=[sample_change],
        )
        
        data = proposal.to_dict()
        
        assert data["title"] == "Test"
        assert data["author"] == "agent_1"
        assert len(data["changes"]) == 1


class TestProposalManager:
    """Tests for ProposalManager."""
    
    def test_create_manager(self):
        """Test creating manager."""
        manager = ProposalManager()
        assert manager is not None
    
    def test_create_proposal(self, manager, sample_change):
        """Test creating proposal through manager."""
        proposal = manager.create_proposal(
            title="Update function",
            description="Improve performance",
            author="agent_1",
            changes=[sample_change],
        )
        
        assert proposal is not None
        assert proposal.risk_level is not None
    
    def test_submit_proposal(self, manager, sample_change):
        """Test submitting proposal."""
        proposal = manager.create_proposal(
            title="Test",
            description="Test",
            author="agent_1",
            changes=[sample_change],
        )
        
        assert manager.submit_proposal(proposal.id)
        assert proposal.status == ProposalStatus.PENDING_REVIEW
    
    def test_add_review(self, manager, sample_change):
        """Test adding review."""
        proposal = manager.create_proposal(
            title="Test",
            description="Test",
            author="agent_1",
            changes=[sample_change],
        )
        manager.submit_proposal(proposal.id)
        
        review = ReviewResult(reviewer="reviewer_1", approved=True)
        assert manager.add_review(proposal.id, review)
    
    def test_get_proposal(self, manager, sample_change):
        """Test getting proposal."""
        proposal = manager.create_proposal(
            title="Test",
            description="Test",
            author="agent_1",
            changes=[sample_change],
        )
        
        retrieved = manager.get_proposal(proposal.id)
        assert retrieved is proposal
    
    def test_get_proposals_by_status(self, manager, sample_change):
        """Test filtering by status."""
        p1 = manager.create_proposal(
            title="Draft",
            description="",
            author="a",
            changes=[sample_change],
        )
        p2 = manager.create_proposal(
            title="Submitted",
            description="",
            author="a",
            changes=[sample_change],
        )
        manager.submit_proposal(p2.id)
        
        drafts = manager.get_proposals_by_status(ProposalStatus.DRAFT)
        pending = manager.get_proposals_by_status(ProposalStatus.PENDING_REVIEW)
        
        assert len(drafts) == 1
        assert len(pending) == 1
    
    def test_delete_draft(self, manager, sample_change):
        """Test deleting draft proposal."""
        proposal = manager.create_proposal(
            title="Test",
            description="",
            author="a",
            changes=[sample_change],
        )
        
        assert manager.delete_proposal(proposal.id)
        assert manager.get_proposal(proposal.id) is None
    
    def test_cannot_delete_submitted(self, manager, sample_change):
        """Test cannot delete submitted proposal."""
        proposal = manager.create_proposal(
            title="Test",
            description="",
            author="a",
            changes=[sample_change],
        )
        manager.submit_proposal(proposal.id)
        
        assert not manager.delete_proposal(proposal.id)


class TestRiskAssessment:
    """Tests for risk assessment."""
    
    def test_low_risk_simple_change(self, manager):
        """Test low risk for simple changes."""
        change = CodeChange(
            file_path="src/utils.py",
            original_code="def a():\n    pass\n",
            modified_code="def a():\n    return 1\n",
        )
        
        proposal = manager.create_proposal(
            title="Small fix",
            description="",
            author="a",
            changes=[change],
        )
        
        assert proposal.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)
    
    def test_high_risk_core_module(self, manager):
        """Test high risk for core module changes."""
        change = CodeChange(
            file_path="src/core/__init__.py",
            original_code="x = 1\n" * 50,
            modified_code="y = 2\n" * 100,
        )
        
        proposal = manager.create_proposal(
            title="Core change",
            description="",
            author="a",
            changes=[change],
        )
        
        # Core module changes should increase risk
        assert proposal.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL)


class TestAutoApproval:
    """Tests for auto-approval."""
    
    def test_auto_approve_low_risk(self, auto_approve_manager):
        """Test auto-approval for low risk."""
        change = CodeChange(
            file_path="src/utils.py",
            original_code="def a():\n    pass\n",
            modified_code="def a():\n    return 1\n",
        )
        
        proposal = auto_approve_manager.create_proposal(
            title="Simple fix",
            description="",
            author="a",
            changes=[change],
        )
        
        # Force low risk for test
        proposal.risk_level = RiskLevel.LOW
        
        auto_approve_manager.submit_proposal(proposal.id)
        
        # Should be auto-approved
        assert proposal.status == ProposalStatus.APPROVED


class TestApplyAndRevert:
    """Tests for applying and reverting proposals."""
    
    def test_apply_proposal(self, manager):
        """Test applying proposal to files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("old = 1\n")
            
            change = CodeChange(
                file_path=str(test_file),
                original_code="old = 1\n",
                modified_code="new = 2\n",
            )
            
            proposal = manager.create_proposal(
                title="Test",
                description="",
                author="a",
                changes=[change],
            )
            
            # Approve
            manager.submit_proposal(proposal.id)
            manager.add_review(
                proposal.id,
                ReviewResult(reviewer="r", approved=True)
            )
            
            # Apply
            success, msg = manager.apply_proposal(proposal.id)
            
            assert success
            assert test_file.read_text() == "new = 2\n"
            assert proposal.status == ProposalStatus.APPLIED
    
    def test_revert_proposal(self, manager):
        """Test reverting applied proposal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("old = 1\n")
            
            change = CodeChange(
                file_path=str(test_file),
                original_code="old = 1\n",
                modified_code="new = 2\n",
            )
            
            proposal = manager.create_proposal(
                title="Test",
                description="",
                author="a",
                changes=[change],
            )
            
            manager.submit_proposal(proposal.id)
            manager.add_review(
                proposal.id,
                ReviewResult(reviewer="r", approved=True)
            )
            manager.apply_proposal(proposal.id)
            
            # Revert
            success, msg = manager.revert_proposal(proposal.id)
            
            assert success
            assert test_file.read_text() == "old = 1\n"
            assert proposal.status == ProposalStatus.REVERTED


class TestCallbacks:
    """Tests for proposal callbacks."""
    
    def test_on_submit_callback(self, manager, sample_change):
        """Test submit callback."""
        submitted = []
        manager.on_submit(lambda p: submitted.append(p))
        
        proposal = manager.create_proposal(
            title="Test",
            description="",
            author="a",
            changes=[sample_change],
        )
        manager.submit_proposal(proposal.id)
        
        assert len(submitted) == 1
    
    def test_on_approve_callback(self, manager, sample_change):
        """Test approve callback."""
        approved = []
        manager.on_approve(lambda p: approved.append(p))
        
        proposal = manager.create_proposal(
            title="Test",
            description="",
            author="a",
            changes=[sample_change],
        )
        manager.submit_proposal(proposal.id)
        manager.add_review(
            proposal.id,
            ReviewResult(reviewer="r", approved=True)
        )
        
        assert len(approved) == 1


class TestStatistics:
    """Tests for proposal statistics."""
    
    def test_get_stats(self, manager, sample_change):
        """Test getting statistics."""
        manager.create_proposal(
            title="A",
            description="",
            author="a",
            changes=[sample_change],
        )
        p2 = manager.create_proposal(
            title="B",
            description="",
            author="a",
            changes=[sample_change],
        )
        manager.submit_proposal(p2.id)
        
        stats = manager.get_stats()
        
        assert stats["total_proposals"] == 2
        assert stats["by_status"]["draft"] == 1
        assert stats["by_status"]["pending_review"] == 1
