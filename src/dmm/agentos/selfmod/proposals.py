"""
Modification proposals for self-modification framework.

This module handles proposing, reviewing, and applying code modifications
with safety checks and approval workflows.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional
from pathlib import Path
from enum import Enum
import difflib
import hashlib
import uuid


from dmm.agentos.selfmod.analyzer import CodeAnalyzer, AnalysisResult, CodeElement
from dmm.agentos.selfmod.generator import CodeGenerator, GenerationResult


# =============================================================================
# Proposal Types
# =============================================================================

class ModificationType(str, Enum):
    """Types of code modifications."""
    
    ADD_FUNCTION = "add_function"
    ADD_METHOD = "add_method"
    ADD_CLASS = "add_class"
    MODIFY_FUNCTION = "modify_function"
    MODIFY_METHOD = "modify_method"
    MODIFY_CLASS = "modify_class"
    DELETE_FUNCTION = "delete_function"
    DELETE_METHOD = "delete_method"
    DELETE_CLASS = "delete_class"
    ADD_IMPORT = "add_import"
    REFACTOR = "refactor"
    FIX_BUG = "fix_bug"
    ADD_DOCSTRING = "add_docstring"
    ADD_TESTS = "add_tests"
    OPTIMIZE = "optimize"


class ProposalStatus(str, Enum):
    """Status of a modification proposal."""
    
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    REVERTED = "reverted"
    EXPIRED = "expired"


class RiskLevel(str, Enum):
    """Risk level of a modification."""
    
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# =============================================================================
# Proposal Models
# =============================================================================

def generate_proposal_id() -> str:
    """Generate unique proposal ID."""
    return f"prop_{uuid.uuid4().hex[:12]}"


@dataclass
class CodeChange:
    """A specific code change."""
    
    file_path: str
    original_code: str
    modified_code: str
    line_start: int = 0
    line_end: int = 0
    change_type: ModificationType = ModificationType.MODIFY_FUNCTION
    element_name: Optional[str] = None
    
    @property
    def diff(self) -> str:
        """Generate unified diff."""
        original_lines = self.original_code.splitlines(keepends=True)
        modified_lines = self.modified_code.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=f"a/{self.file_path}",
            tofile=f"b/{self.file_path}",
            lineterm="",
        )
        return "".join(diff)
    
    @property
    def lines_added(self) -> int:
        """Count lines added."""
        return len(self.modified_code.splitlines()) - len(self.original_code.splitlines())
    
    @property
    def lines_removed(self) -> int:
        """Count lines removed."""
        return max(0, -self.lines_added)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "change_type": self.change_type.value,
            "element_name": self.element_name,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "lines_added": self.lines_added,
            "lines_removed": self.lines_removed,
            "diff": self.diff,
        }


@dataclass
class ReviewComment:
    """A review comment on a proposal."""
    
    reviewer: str
    comment: str
    line_number: Optional[int] = None
    file_path: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    is_blocking: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "reviewer": self.reviewer,
            "comment": self.comment,
            "line_number": self.line_number,
            "file_path": self.file_path,
            "created_at": self.created_at.isoformat(),
            "is_blocking": self.is_blocking,
        }


@dataclass
class ReviewResult:
    """Result of a proposal review."""
    
    reviewer: str
    approved: bool
    comments: list[ReviewComment] = field(default_factory=list)
    risk_assessment: RiskLevel = RiskLevel.LOW
    reviewed_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "reviewer": self.reviewer,
            "approved": self.approved,
            "comments": [c.to_dict() for c in self.comments],
            "risk_assessment": self.risk_assessment.value,
            "reviewed_at": self.reviewed_at.isoformat(),
        }


@dataclass
class ModificationProposal:
    """
    A proposal for code modification.
    
    Proposals go through a workflow:
    1. Creation (DRAFT)
    2. Submission (PENDING_REVIEW)
    3. Review (UNDER_REVIEW)
    4. Approval/Rejection
    5. Application (APPLIED)
    """
    
    # Identity
    id: str = field(default_factory=generate_proposal_id)
    title: str = ""
    description: str = ""
    
    # Author
    author: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    # Changes
    changes: list[CodeChange] = field(default_factory=list)
    modification_type: ModificationType = ModificationType.MODIFY_FUNCTION
    
    # Status
    status: ProposalStatus = ProposalStatus.DRAFT
    submitted_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None
    
    # Review
    reviews: list[ReviewResult] = field(default_factory=list)
    required_approvals: int = 1
    
    # Risk
    risk_level: RiskLevel = RiskLevel.LOW
    risk_factors: list[str] = field(default_factory=list)
    
    # Metadata
    tags: list[str] = field(default_factory=list)
    related_issues: list[str] = field(default_factory=list)
    
    # Backup for revert
    _original_files: dict[str, str] = field(default_factory=dict)
    
    # -------------------------------------------------------------------------
    # Status Checks
    # -------------------------------------------------------------------------
    
    @property
    def is_approved(self) -> bool:
        """Check if proposal has required approvals."""
        approvals = sum(1 for r in self.reviews if r.approved)
        return approvals >= self.required_approvals
    
    @property
    def has_blocking_comments(self) -> bool:
        """Check if there are blocking review comments."""
        for review in self.reviews:
            if any(c.is_blocking for c in review.comments):
                return True
        return False
    
    @property
    def can_apply(self) -> bool:
        """Check if proposal can be applied."""
        return (
            self.status == ProposalStatus.APPROVED and
            self.is_approved and
            not self.has_blocking_comments
        )
    
    @property
    def total_lines_changed(self) -> int:
        """Total lines changed across all files."""
        return sum(
            abs(c.lines_added) + c.lines_removed
            for c in self.changes
        )
    
    # -------------------------------------------------------------------------
    # Workflow
    # -------------------------------------------------------------------------
    
    def submit(self) -> bool:
        """Submit proposal for review."""
        if self.status != ProposalStatus.DRAFT:
            return False
        
        self.status = ProposalStatus.PENDING_REVIEW
        self.submitted_at = datetime.utcnow()
        return True
    
    def start_review(self) -> bool:
        """Mark proposal as under review."""
        if self.status != ProposalStatus.PENDING_REVIEW:
            return False
        
        self.status = ProposalStatus.UNDER_REVIEW
        return True
    
    def add_review(self, review: ReviewResult) -> None:
        """Add a review result."""
        self.reviews.append(review)
        
        # Update status based on reviews
        if self.is_approved and not self.has_blocking_comments:
            self.status = ProposalStatus.APPROVED
            self.approved_at = datetime.utcnow()
        elif any(not r.approved for r in self.reviews):
            # Any rejection rejects the proposal
            rejections = [r for r in self.reviews if not r.approved]
            if len(rejections) > 0:
                self.status = ProposalStatus.REJECTED
    
    def mark_applied(self) -> None:
        """Mark proposal as applied."""
        self.status = ProposalStatus.APPLIED
        self.applied_at = datetime.utcnow()
    
    def mark_reverted(self) -> None:
        """Mark proposal as reverted."""
        self.status = ProposalStatus.REVERTED
    
    # -------------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------------
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "author": self.author,
            "created_at": self.created_at.isoformat(),
            "changes": [c.to_dict() for c in self.changes],
            "modification_type": self.modification_type.value,
            "status": self.status.value,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "reviews": [r.to_dict() for r in self.reviews],
            "required_approvals": self.required_approvals,
            "risk_level": self.risk_level.value,
            "risk_factors": self.risk_factors,
            "tags": self.tags,
            "total_lines_changed": self.total_lines_changed,
            "is_approved": self.is_approved,
            "can_apply": self.can_apply,
        }


# =============================================================================
# Proposal Manager
# =============================================================================

class ProposalManager:
    """
    Manages modification proposals through their lifecycle.
    
    Handles:
    - Proposal creation
    - Risk assessment
    - Review workflow
    - Application and revert
    """
    
    def __init__(
        self,
        analyzer: Optional[CodeAnalyzer] = None,
        generator: Optional[CodeGenerator] = None,
        auto_approve_low_risk: bool = False,
        require_tests: bool = True,
    ) -> None:
        """
        Initialize proposal manager.
        
        Args:
            analyzer: Code analyzer for impact analysis
            generator: Code generator for validation
            auto_approve_low_risk: Auto-approve low risk changes
            require_tests: Require test coverage for changes
        """
        self._analyzer = analyzer or CodeAnalyzer()
        self._generator = generator or CodeGenerator()
        self._auto_approve_low_risk = auto_approve_low_risk
        self._require_tests = require_tests
        
        # Storage
        self._proposals: dict[str, ModificationProposal] = {}
        
        # Callbacks
        self._on_submit: Optional[Callable[[ModificationProposal], None]] = None
        self._on_approve: Optional[Callable[[ModificationProposal], None]] = None
        self._on_apply: Optional[Callable[[ModificationProposal], None]] = None
    
    # -------------------------------------------------------------------------
    # Proposal Creation
    # -------------------------------------------------------------------------
    
    def create_proposal(
        self,
        title: str,
        description: str,
        author: str,
        changes: list[CodeChange],
        modification_type: ModificationType = ModificationType.MODIFY_FUNCTION,
        tags: Optional[list[str]] = None,
    ) -> ModificationProposal:
        """
        Create a new modification proposal.
        
        Args:
            title: Proposal title
            description: Detailed description
            author: Author identifier
            changes: List of code changes
            modification_type: Type of modification
            tags: Optional tags
            
        Returns:
            ModificationProposal
        """
        proposal = ModificationProposal(
            title=title,
            description=description,
            author=author,
            changes=changes,
            modification_type=modification_type,
            tags=tags or [],
        )
        
        # Assess risk
        proposal.risk_level, proposal.risk_factors = self._assess_risk(proposal)
        
        # Store
        self._proposals[proposal.id] = proposal
        
        return proposal
    
    def create_function_addition(
        self,
        file_path: str,
        original_source: str,
        function_code: str,
        author: str,
        description: str = "",
    ) -> ModificationProposal:
        """Create proposal to add a function."""
        # Append function to source
        modified_source = original_source.rstrip() + "\n\n\n" + function_code + "\n"
        
        change = CodeChange(
            file_path=file_path,
            original_code=original_source,
            modified_code=modified_source,
            change_type=ModificationType.ADD_FUNCTION,
        )
        
        return self.create_proposal(
            title=f"Add function to {Path(file_path).name}",
            description=description,
            author=author,
            changes=[change],
            modification_type=ModificationType.ADD_FUNCTION,
        )
    
    def create_refactoring(
        self,
        file_path: str,
        original_source: str,
        refactored_source: str,
        author: str,
        description: str,
    ) -> ModificationProposal:
        """Create proposal for refactoring."""
        change = CodeChange(
            file_path=file_path,
            original_code=original_source,
            modified_code=refactored_source,
            change_type=ModificationType.REFACTOR,
        )
        
        return self.create_proposal(
            title=f"Refactor {Path(file_path).name}",
            description=description,
            author=author,
            changes=[change],
            modification_type=ModificationType.REFACTOR,
        )
    
    # -------------------------------------------------------------------------
    # Risk Assessment
    # -------------------------------------------------------------------------
    
    def _assess_risk(self, proposal: ModificationProposal) -> tuple[RiskLevel, list[str]]:
        """Assess risk level of a proposal."""
        factors = []
        risk_score = 0
        
        for change in proposal.changes:
            # Validate modified code
            result = self._generator.validate_code(change.modified_code)
            if not result.success:
                factors.append("Code validation failed")
                risk_score += 30
            
            # Analyze impact
            analysis = self._analyzer.analyze_source(change.modified_code)
            
            # High complexity
            if analysis.metrics.complexity_level.value in ("high", "very_high"):
                factors.append("High code complexity")
                risk_score += 20
            
            # Many lines changed
            if abs(change.lines_added) > 100:
                factors.append("Large number of lines changed")
                risk_score += 15
            
            # Core module changes
            if any(p in change.file_path for p in ["core", "base", "main", "__init__"]):
                factors.append("Changes to core module")
                risk_score += 25
            
            # Modification type risk
            if change.change_type in (ModificationType.DELETE_CLASS, ModificationType.DELETE_FUNCTION):
                factors.append("Deletion of code")
                risk_score += 20
            
            # Check for test coverage
            if self._require_tests and "test" not in change.file_path.lower():
                has_test_change = any(
                    "test" in c.file_path.lower() for c in proposal.changes
                )
                if not has_test_change:
                    factors.append("No test changes included")
                    risk_score += 10
        
        # Determine risk level
        if risk_score >= 50:
            level = RiskLevel.CRITICAL
        elif risk_score >= 30:
            level = RiskLevel.HIGH
        elif risk_score >= 15:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW
        
        return level, factors
    
    # -------------------------------------------------------------------------
    # Review Workflow
    # -------------------------------------------------------------------------
    
    def submit_proposal(self, proposal_id: str) -> bool:
        """Submit a proposal for review."""
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            return False
        
        if proposal.submit():
            if self._on_submit:
                self._on_submit(proposal)
            
            # Auto-approve if low risk and enabled
            if self._auto_approve_low_risk and proposal.risk_level == RiskLevel.LOW:
                self.add_review(
                    proposal_id,
                    ReviewResult(
                        reviewer="auto_review",
                        approved=True,
                        risk_assessment=RiskLevel.LOW,
                    )
                )
            
            return True
        return False
    
    def add_review(self, proposal_id: str, review: ReviewResult) -> bool:
        """Add a review to a proposal."""
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            return False
        
        if proposal.status == ProposalStatus.PENDING_REVIEW:
            proposal.start_review()
        
        proposal.add_review(review)
        
        if proposal.status == ProposalStatus.APPROVED and self._on_approve:
            self._on_approve(proposal)
        
        return True
    
    # -------------------------------------------------------------------------
    # Application
    # -------------------------------------------------------------------------
    
    def apply_proposal(self, proposal_id: str) -> tuple[bool, str]:
        """
        Apply a proposal's changes.
        
        Args:
            proposal_id: Proposal ID
            
        Returns:
            (success, message) tuple
        """
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            return False, "Proposal not found"
        
        if not proposal.can_apply:
            return False, f"Proposal cannot be applied (status: {proposal.status.value})"
        
        # Store originals for revert
        for change in proposal.changes:
            proposal._original_files[change.file_path] = change.original_code
        
        # Apply changes
        try:
            for change in proposal.changes:
                path = Path(change.file_path)
                if path.exists():
                    path.write_text(change.modified_code, encoding="utf-8")
            
            proposal.mark_applied()
            
            if self._on_apply:
                self._on_apply(proposal)
            
            return True, "Proposal applied successfully"
            
        except Exception as e:
            # Attempt revert on failure
            self._revert_changes(proposal)
            return False, f"Failed to apply: {e}"
    
    def revert_proposal(self, proposal_id: str) -> tuple[bool, str]:
        """
        Revert a proposal's changes.
        
        Args:
            proposal_id: Proposal ID
            
        Returns:
            (success, message) tuple
        """
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            return False, "Proposal not found"
        
        if proposal.status != ProposalStatus.APPLIED:
            return False, "Proposal has not been applied"
        
        success = self._revert_changes(proposal)
        if success:
            proposal.mark_reverted()
            return True, "Proposal reverted successfully"
        return False, "Failed to revert changes"
    
    def _revert_changes(self, proposal: ModificationProposal) -> bool:
        """Revert changes from original files."""
        try:
            for file_path, original_code in proposal._original_files.items():
                path = Path(file_path)
                path.write_text(original_code, encoding="utf-8")
            return True
        except Exception:
            return False
    
    # -------------------------------------------------------------------------
    # Proposal Management
    # -------------------------------------------------------------------------
    
    def get_proposal(self, proposal_id: str) -> Optional[ModificationProposal]:
        """Get a proposal by ID."""
        return self._proposals.get(proposal_id)
    
    def get_proposals_by_status(self, status: ProposalStatus) -> list[ModificationProposal]:
        """Get proposals by status."""
        return [p for p in self._proposals.values() if p.status == status]
    
    def get_proposals_by_author(self, author: str) -> list[ModificationProposal]:
        """Get proposals by author."""
        return [p for p in self._proposals.values() if p.author == author]
    
    def get_pending_reviews(self) -> list[ModificationProposal]:
        """Get proposals pending review."""
        return self.get_proposals_by_status(ProposalStatus.PENDING_REVIEW)
    
    def delete_proposal(self, proposal_id: str) -> bool:
        """Delete a draft proposal."""
        proposal = self._proposals.get(proposal_id)
        if proposal and proposal.status == ProposalStatus.DRAFT:
            del self._proposals[proposal_id]
            return True
        return False
    
    # -------------------------------------------------------------------------
    # Callbacks
    # -------------------------------------------------------------------------
    
    def on_submit(self, callback: Callable[[ModificationProposal], None]) -> None:
        """Set callback for proposal submission."""
        self._on_submit = callback
    
    def on_approve(self, callback: Callable[[ModificationProposal], None]) -> None:
        """Set callback for proposal approval."""
        self._on_approve = callback
    
    def on_apply(self, callback: Callable[[ModificationProposal], None]) -> None:
        """Set callback for proposal application."""
        self._on_apply = callback
    
    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------
    
    def get_stats(self) -> dict[str, Any]:
        """Get proposal statistics."""
        proposals = list(self._proposals.values())
        
        return {
            "total_proposals": len(proposals),
            "by_status": {
                status.value: len([p for p in proposals if p.status == status])
                for status in ProposalStatus
            },
            "by_risk": {
                risk.value: len([p for p in proposals if p.risk_level == risk])
                for risk in RiskLevel
            },
            "total_lines_changed": sum(p.total_lines_changed for p in proposals),
        }
