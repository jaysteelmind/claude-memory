"""Reviewer agent for validating write proposals."""

import time
from pathlib import Path

from dmm.core.exceptions import ReviewError
from dmm.indexer.embedder import MemoryEmbedder
from dmm.indexer.store import MemoryStore
from dmm.models.proposal import (
    ProposalStatus,
    ProposalType,
    ReviewDecision,
    ReviewResult,
    WriteProposal,
)
from dmm.reviewer.decisions import DecisionEngine
from dmm.reviewer.validators.duplicate import DuplicateDetector
from dmm.reviewer.validators.quality import QualityChecker
from dmm.reviewer.validators.schema import SchemaValidator
from dmm.writeback.queue import ReviewQueue


class ReviewerAgent:
    """Orchestrates the review process for write proposals."""

    def __init__(
        self,
        queue: ReviewQueue,
        store: MemoryStore,
        embedder: MemoryEmbedder,
        base_path: Path | None = None,
        auto_approve_threshold: float = 0.95,
    ) -> None:
        """Initialize the reviewer agent.
        
        Args:
            queue: The review queue.
            store: The memory store.
            embedder: The memory embedder.
            base_path: Base path for the DMM directory.
            auto_approve_threshold: Confidence threshold for auto-approval.
        """
        self._queue = queue
        self._store = store
        self._embedder = embedder
        self._base_path = base_path or Path.cwd()

        self._schema_validator = SchemaValidator()
        self._quality_checker = QualityChecker()
        self._duplicate_detector = DuplicateDetector(store, embedder)
        self._decision_engine = DecisionEngine(auto_approve_threshold)

    def review(self, proposal: WriteProposal) -> ReviewResult:
        """Review a write proposal.
        
        Args:
            proposal: The proposal to review.
            
        Returns:
            ReviewResult with decision and details.
            
        Raises:
            ReviewError: If review process fails.
        """
        start_time = time.perf_counter()

        try:
            self._queue.update_status(
                proposal.proposal_id,
                ProposalStatus.IN_REVIEW,
            )

            if proposal.type == ProposalType.CREATE:
                result = self._review_create(proposal)
            elif proposal.type == ProposalType.UPDATE:
                result = self._review_update(proposal)
            elif proposal.type == ProposalType.DEPRECATE:
                result = self._review_deprecate(proposal)
            elif proposal.type == ProposalType.PROMOTE:
                result = self._review_promote(proposal)
            else:
                raise ReviewError(
                    f"Unknown proposal type: {proposal.type}",
                    proposal_id=proposal.proposal_id,
                    stage="type_check",
                )

            result.review_duration_ms = (time.perf_counter() - start_time) * 1000

            self._update_proposal_status(proposal, result)

            return result

        except ReviewError:
            raise
        except Exception as e:
            self._queue.update_status(
                proposal.proposal_id,
                ProposalStatus.PENDING,
                notes=f"Review failed: {e}",
            )
            raise ReviewError(
                f"Review failed: {e}",
                proposal_id=proposal.proposal_id,
                stage="unknown",
            ) from e

    def review_pending(self, limit: int = 10) -> list[ReviewResult]:
        """Review all pending proposals.
        
        Args:
            limit: Maximum number of proposals to review.
            
        Returns:
            List of review results.
        """
        pending = self._queue.get_pending(limit)
        results = []

        for proposal in pending:
            try:
                result = self.review(proposal)
                results.append(result)
            except ReviewError:
                continue

        return results

    def _review_create(self, proposal: WriteProposal) -> ReviewResult:
        """Review a CREATE proposal.
        
        Args:
            proposal: The CREATE proposal.
            
        Returns:
            ReviewResult.
        """
        content = proposal.content
        if not content:
            return ReviewResult(
                proposal_id=proposal.proposal_id,
                decision=ReviewDecision.REJECT,
                confidence=1.0,
                schema_valid=False,
                notes="No content provided",
            )

        schema_issues = self._schema_validator.validate(content)

        has_schema_errors = any(i.severity == "error" for i in schema_issues)
        if has_schema_errors:
            return self._decision_engine.decide(
                proposal=proposal,
                schema_issues=schema_issues,
                quality_issues=[],
                duplicate_issues=[],
                duplicate_matches=[],
            )

        quality_issues = self._quality_checker.check(content)

        duplicate_issues, duplicate_matches = self._duplicate_detector.check(
            content=content,
            target_path=proposal.target_path,
            exclude_id=None,
        )

        return self._decision_engine.decide(
            proposal=proposal,
            schema_issues=schema_issues,
            quality_issues=quality_issues,
            duplicate_issues=duplicate_issues,
            duplicate_matches=duplicate_matches,
        )

    def _review_update(self, proposal: WriteProposal) -> ReviewResult:
        """Review an UPDATE proposal.
        
        Args:
            proposal: The UPDATE proposal.
            
        Returns:
            ReviewResult.
        """
        content = proposal.content
        if not content:
            return ReviewResult(
                proposal_id=proposal.proposal_id,
                decision=ReviewDecision.REJECT,
                confidence=1.0,
                schema_valid=False,
                notes="No content provided for update",
            )

        if not proposal.memory_id:
            return ReviewResult(
                proposal_id=proposal.proposal_id,
                decision=ReviewDecision.REJECT,
                confidence=1.0,
                notes="No memory_id specified for update",
            )

        existing = self._store.get_memory(proposal.memory_id)
        if not existing:
            return ReviewResult(
                proposal_id=proposal.proposal_id,
                decision=ReviewDecision.REJECT,
                confidence=1.0,
                notes=f"Memory '{proposal.memory_id}' not found",
            )

        schema_issues = self._schema_validator.validate(content)

        has_schema_errors = any(i.severity == "error" for i in schema_issues)
        if has_schema_errors:
            return self._decision_engine.decide(
                proposal=proposal,
                schema_issues=schema_issues,
                quality_issues=[],
                duplicate_issues=[],
                duplicate_matches=[],
            )

        quality_issues = self._quality_checker.check(content)

        duplicate_issues, duplicate_matches = self._duplicate_detector.check(
            content=content,
            target_path=proposal.target_path,
            exclude_id=proposal.memory_id,
        )

        return self._decision_engine.decide(
            proposal=proposal,
            schema_issues=schema_issues,
            quality_issues=quality_issues,
            duplicate_issues=duplicate_issues,
            duplicate_matches=duplicate_matches,
        )

    def _review_deprecate(self, proposal: WriteProposal) -> ReviewResult:
        """Review a DEPRECATE proposal.
        
        Args:
            proposal: The DEPRECATE proposal.
            
        Returns:
            ReviewResult.
        """
        if not proposal.memory_id:
            return ReviewResult(
                proposal_id=proposal.proposal_id,
                decision=ReviewDecision.REJECT,
                confidence=1.0,
                notes="No memory_id specified for deprecation",
            )

        existing = self._store.get_memory(proposal.memory_id)
        if not existing:
            return ReviewResult(
                proposal_id=proposal.proposal_id,
                decision=ReviewDecision.REJECT,
                confidence=1.0,
                notes=f"Memory '{proposal.memory_id}' not found",
            )

        if existing.status == "deprecated":
            return ReviewResult(
                proposal_id=proposal.proposal_id,
                decision=ReviewDecision.REJECT,
                confidence=1.0,
                notes=f"Memory '{proposal.memory_id}' is already deprecated",
            )

        if existing.scope == "baseline":
            return ReviewResult(
                proposal_id=proposal.proposal_id,
                decision=ReviewDecision.DEFER,
                confidence=1.0,
                notes="Baseline memory deprecation requires human review",
            )

        if not proposal.deprecation_reason or len(proposal.deprecation_reason) < 10:
            return ReviewResult(
                proposal_id=proposal.proposal_id,
                decision=ReviewDecision.REJECT,
                confidence=0.9,
                notes="Deprecation requires a meaningful reason (at least 10 characters)",
            )

        return ReviewResult(
            proposal_id=proposal.proposal_id,
            decision=ReviewDecision.APPROVE,
            confidence=0.95,
            schema_valid=True,
            quality_valid=True,
            duplicate_check_passed=True,
            notes=f"Deprecation approved: {proposal.deprecation_reason}",
        )

    def _review_promote(self, proposal: WriteProposal) -> ReviewResult:
        """Review a PROMOTE proposal.
        
        Args:
            proposal: The PROMOTE proposal.
            
        Returns:
            ReviewResult.
        """
        if not proposal.memory_id:
            return ReviewResult(
                proposal_id=proposal.proposal_id,
                decision=ReviewDecision.REJECT,
                confidence=1.0,
                notes="No memory_id specified for promotion",
            )

        if not proposal.new_scope:
            return ReviewResult(
                proposal_id=proposal.proposal_id,
                decision=ReviewDecision.REJECT,
                confidence=1.0,
                notes="No new_scope specified for promotion",
            )

        existing = self._store.get_memory(proposal.memory_id)
        if not existing:
            return ReviewResult(
                proposal_id=proposal.proposal_id,
                decision=ReviewDecision.REJECT,
                confidence=1.0,
                notes=f"Memory '{proposal.memory_id}' not found",
            )

        if existing.scope == proposal.new_scope:
            return ReviewResult(
                proposal_id=proposal.proposal_id,
                decision=ReviewDecision.REJECT,
                confidence=1.0,
                notes=f"Memory is already in scope '{proposal.new_scope}'",
            )

        if proposal.new_scope == "baseline":
            return ReviewResult(
                proposal_id=proposal.proposal_id,
                decision=ReviewDecision.DEFER,
                confidence=1.0,
                notes="Promotion to baseline requires human review",
            )

        scope_hierarchy = {
            "ephemeral": 0,
            "project": 1,
            "agent": 2,
            "global": 3,
            "baseline": 4,
        }

        current_level = scope_hierarchy.get(existing.scope, 0)
        new_level = scope_hierarchy.get(proposal.new_scope, 0)

        if new_level < current_level:
            return ReviewResult(
                proposal_id=proposal.proposal_id,
                decision=ReviewDecision.DEFER,
                confidence=0.8,
                notes=f"Demotion from '{existing.scope}' to '{proposal.new_scope}' - verify intent",
            )

        return ReviewResult(
            proposal_id=proposal.proposal_id,
            decision=ReviewDecision.APPROVE,
            confidence=0.95,
            schema_valid=True,
            quality_valid=True,
            duplicate_check_passed=True,
            notes=f"Promotion approved: {existing.scope} -> {proposal.new_scope}",
        )

    def _update_proposal_status(
        self,
        proposal: WriteProposal,
        result: ReviewResult,
    ) -> None:
        """Update proposal status based on review result.
        
        Args:
            proposal: The reviewed proposal.
            result: The review result.
        """
        status_map = {
            ReviewDecision.APPROVE: ProposalStatus.APPROVED,
            ReviewDecision.REJECT: ProposalStatus.REJECTED,
            ReviewDecision.MODIFY: ProposalStatus.MODIFIED,
            ReviewDecision.DEFER: ProposalStatus.DEFERRED,
        }

        new_status = status_map.get(result.decision, ProposalStatus.PENDING)
        
        self._queue.update_status(
            proposal.proposal_id,
            new_status,
            notes=result.notes,
        )

    def get_decision_explanation(self, result: ReviewResult) -> str:
        """Get human-readable explanation of a review decision.
        
        Args:
            result: The review result.
            
        Returns:
            Explanation string.
        """
        return self._decision_engine.explain_decision(result)

    def can_auto_commit(self, result: ReviewResult) -> bool:
        """Check if a review result can be auto-committed.
        
        Args:
            result: The review result.
            
        Returns:
            True if can be auto-committed.
        """
        return self._decision_engine.can_auto_approve(result)
