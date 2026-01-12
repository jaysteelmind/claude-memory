"""Decision engine for review outcomes."""

from dmm.core.constants import (
    AUTO_APPROVE_CONFIDENCE_THRESHOLD,
    Scope,
)
from dmm.models.proposal import (
    DuplicateMatch,
    ProposalType,
    ReviewDecision,
    ReviewResult,
    ValidationIssue,
    WriteProposal,
)


class DecisionEngine:
    """Makes review decisions based on validation results."""

    def __init__(
        self,
        auto_approve_threshold: float = AUTO_APPROVE_CONFIDENCE_THRESHOLD,
    ) -> None:
        """Initialize the decision engine.
        
        Args:
            auto_approve_threshold: Confidence threshold for auto-approval.
        """
        self._auto_approve_threshold = auto_approve_threshold

    def decide(
        self,
        proposal: WriteProposal,
        schema_issues: list[ValidationIssue],
        quality_issues: list[ValidationIssue],
        duplicate_issues: list[ValidationIssue],
        duplicate_matches: list[DuplicateMatch],
    ) -> ReviewResult:
        """Make a review decision based on validation results.
        
        Args:
            proposal: The write proposal being reviewed.
            schema_issues: Issues from schema validation.
            quality_issues: Issues from quality checking.
            duplicate_issues: Issues from duplicate detection.
            duplicate_matches: Duplicate matches found.
            
        Returns:
            ReviewResult with decision and details.
        """
        all_issues = schema_issues + quality_issues + duplicate_issues

        errors = [i for i in all_issues if i.severity == "error"]
        warnings = [i for i in all_issues if i.severity == "warning"]

        schema_valid = not any(i.severity == "error" for i in schema_issues)
        quality_valid = not any(i.severity == "error" for i in quality_issues)
        duplicate_check_passed = not any(i.severity == "error" for i in duplicate_issues)

        if self._requires_human_review(proposal):
            return ReviewResult(
                proposal_id=proposal.proposal_id,
                decision=ReviewDecision.DEFER,
                confidence=1.0,
                schema_valid=schema_valid,
                quality_valid=quality_valid,
                duplicate_check_passed=duplicate_check_passed,
                issues=all_issues,
                duplicates=duplicate_matches,
                notes="Baseline modifications require human review",
            )

        if errors:
            confidence = self._calculate_rejection_confidence(errors)
            return ReviewResult(
                proposal_id=proposal.proposal_id,
                decision=ReviewDecision.REJECT,
                confidence=confidence,
                schema_valid=schema_valid,
                quality_valid=quality_valid,
                duplicate_check_passed=duplicate_check_passed,
                issues=all_issues,
                duplicates=duplicate_matches,
                notes=self._build_rejection_notes(errors),
            )

        if warnings:
            confidence = self._calculate_approval_confidence(warnings)
            
            if confidence >= self._auto_approve_threshold:
                return ReviewResult(
                    proposal_id=proposal.proposal_id,
                    decision=ReviewDecision.APPROVE,
                    confidence=confidence,
                    schema_valid=schema_valid,
                    quality_valid=quality_valid,
                    duplicate_check_passed=duplicate_check_passed,
                    issues=all_issues,
                    duplicates=duplicate_matches,
                    notes=f"Approved with {len(warnings)} warning(s)",
                )
            else:
                return ReviewResult(
                    proposal_id=proposal.proposal_id,
                    decision=ReviewDecision.DEFER,
                    confidence=confidence,
                    schema_valid=schema_valid,
                    quality_valid=quality_valid,
                    duplicate_check_passed=duplicate_check_passed,
                    issues=all_issues,
                    duplicates=duplicate_matches,
                    notes=f"Deferred due to {len(warnings)} warning(s) - confidence below threshold",
                )

        return ReviewResult(
            proposal_id=proposal.proposal_id,
            decision=ReviewDecision.APPROVE,
            confidence=1.0,
            schema_valid=True,
            quality_valid=True,
            duplicate_check_passed=True,
            issues=all_issues,
            duplicates=duplicate_matches,
            notes="All validations passed",
        )

    def _requires_human_review(self, proposal: WriteProposal) -> bool:
        """Check if proposal requires human review.
        
        Args:
            proposal: The proposal to check.
            
        Returns:
            True if human review required.
        """
        path_parts = proposal.target_path.split("/")
        if path_parts and path_parts[0] == Scope.BASELINE.value:
            return True

        if proposal.type == ProposalType.PROMOTE and proposal.new_scope == Scope.BASELINE.value:
            return True

        return False

    def _calculate_rejection_confidence(
        self,
        errors: list[ValidationIssue],
    ) -> float:
        """Calculate confidence for rejection decision.
        
        Args:
            errors: List of error-level issues.
            
        Returns:
            Confidence score (0.0 to 1.0).
        """
        critical_codes = {
            "duplicate_exact",
            "duplicate_semantic", 
            "missing_required_fields",
            "invalid_yaml",
            "empty_content",
            "token_count_hard_limit",
        }

        critical_count = sum(1 for e in errors if e.code in critical_codes)
        
        if critical_count > 0:
            return 1.0

        base_confidence = 0.8
        confidence = base_confidence + (len(errors) * 0.05)
        return min(confidence, 1.0)

    def _calculate_approval_confidence(
        self,
        warnings: list[ValidationIssue],
    ) -> float:
        """Calculate confidence for approval with warnings.
        
        Args:
            warnings: List of warning-level issues.
            
        Returns:
            Confidence score (0.0 to 1.0).
        """
        base_confidence = 1.0

        minor_warning_codes = {
            "missing_rationale",
            "low_coherence",
            "vague_tag",
            "missing_title",
        }

        for warning in warnings:
            if warning.code in minor_warning_codes:
                base_confidence -= 0.02
            else:
                base_confidence -= 0.05

        return max(base_confidence, 0.5)

    def _build_rejection_notes(self, errors: list[ValidationIssue]) -> str:
        """Build rejection notes from errors.
        
        Args:
            errors: List of error issues.
            
        Returns:
            Formatted rejection notes.
        """
        if len(errors) == 1:
            error = errors[0]
            note = f"Rejected: {error.message}"
            if error.suggestion:
                note += f". Suggestion: {error.suggestion}"
            return note

        notes = [f"Rejected with {len(errors)} error(s):"]
        for i, error in enumerate(errors[:5], 1):
            notes.append(f"  {i}. {error.message}")
        
        if len(errors) > 5:
            notes.append(f"  ... and {len(errors) - 5} more")

        return "\n".join(notes)

    def can_auto_approve(self, result: ReviewResult) -> bool:
        """Check if a review result can be auto-approved.
        
        Args:
            result: The review result to check.
            
        Returns:
            True if can be auto-approved.
        """
        if result.decision != ReviewDecision.APPROVE:
            return False

        return result.confidence >= self._auto_approve_threshold

    def requires_human_decision(self, result: ReviewResult) -> bool:
        """Check if a review result requires human decision.
        
        Args:
            result: The review result to check.
            
        Returns:
            True if human decision required.
        """
        return result.decision == ReviewDecision.DEFER

    def explain_decision(self, result: ReviewResult) -> str:
        """Generate human-readable explanation of decision.
        
        Args:
            result: The review result to explain.
            
        Returns:
            Explanation string.
        """
        lines = [
            f"Decision: {result.decision.value.upper()}",
            f"Confidence: {result.confidence:.1%}",
            "",
            "Validation Summary:",
            f"  - Schema: {'PASS' if result.schema_valid else 'FAIL'}",
            f"  - Quality: {'PASS' if result.quality_valid else 'FAIL'}",
            f"  - Duplicates: {'PASS' if result.duplicate_check_passed else 'FAIL'}",
        ]

        if result.issues:
            error_count = len([i for i in result.issues if i.severity == "error"])
            warning_count = len([i for i in result.issues if i.severity == "warning"])
            info_count = len([i for i in result.issues if i.severity == "info"])
            
            lines.append("")
            lines.append(f"Issues: {error_count} error(s), {warning_count} warning(s), {info_count} info")

            errors = [i for i in result.issues if i.severity == "error"]
            if errors:
                lines.append("")
                lines.append("Errors:")
                for error in errors[:5]:
                    lines.append(f"  - [{error.code}] {error.message}")

        if result.duplicates:
            lines.append("")
            lines.append(f"Duplicate Matches: {len(result.duplicates)}")
            for dup in result.duplicates[:3]:
                lines.append(f"  - {dup.memory_path} ({dup.similarity:.1%} {dup.match_type})")

        if result.notes:
            lines.append("")
            lines.append(f"Notes: {result.notes}")

        return "\n".join(lines)
