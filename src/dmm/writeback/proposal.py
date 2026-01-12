"""Proposal handler for validating and processing write proposals."""

import re
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dmm.core.constants import (
    MAX_MEMORY_TOKENS_HARD,
    MIN_MEMORY_TOKENS,
    Scope,
    get_memory_root,
)
from dmm.core.exceptions import ProposalError
from dmm.indexer.store import MemoryStore
from dmm.models.proposal import (
    ProposalStatus,
    ProposalType,
    ValidationIssue,
    WriteProposal,
)
from dmm.writeback.queue import ReviewQueue


def generate_proposal_id() -> str:
    """Generate a unique proposal ID.
    
    Format: prop_{timestamp}_{random}
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    random_suffix = secrets.token_hex(4)
    return f"prop_{timestamp}_{random_suffix}"


class ProposalHandler:
    """Handles creation and validation of write proposals."""

    VALID_SCOPES = {s.value for s in Scope}
    
    PATH_PATTERN = re.compile(
        r"^[a-zA-Z0-9_\-]+(/[a-zA-Z0-9_\-]+)*\.md$"
    )

    def __init__(
        self,
        queue: ReviewQueue,
        store: MemoryStore,
        base_path: Path | None = None,
    ) -> None:
        """Initialize the proposal handler.
        
        Args:
            queue: The review queue for persisting proposals.
            store: The memory store for duplicate checks.
            base_path: Base path for the DMM directory.
        """
        self._queue = queue
        self._store = store
        self._base_path = base_path or Path.cwd()
        self._memory_root = get_memory_root(self._base_path)

    def propose_create(
        self,
        target_path: str,
        content: str,
        reason: str,
        proposed_by: str = "agent",
    ) -> WriteProposal:
        """Create a proposal to add a new memory.
        
        Args:
            target_path: Path relative to memory root (e.g., "project/constraints/no_async.md")
            content: Full markdown content including frontmatter.
            reason: Explanation for why this memory should be created.
            proposed_by: Identifier of the proposer.
            
        Returns:
            The created proposal.
            
        Raises:
            ProposalError: If the proposal is invalid.
        """
        issues = self._precheck_create(target_path, content)
        if issues:
            error_issues = [i for i in issues if i.severity == "error"]
            if error_issues:
                raise ProposalError(
                    f"Proposal precheck failed: {error_issues[0].message}",
                    reason=error_issues[0].code,
                    details={"issues": [i.to_dict() for i in issues]},
                )
        
        proposal = WriteProposal(
            proposal_id=generate_proposal_id(),
            type=ProposalType.CREATE,
            target_path=target_path,
            reason=reason,
            content=content,
            proposed_by=proposed_by,
            status=ProposalStatus.PENDING,
        )
        
        self._queue.enqueue(proposal)
        return proposal

    def propose_update(
        self,
        memory_id: str,
        content: str,
        reason: str,
        proposed_by: str = "agent",
    ) -> WriteProposal:
        """Create a proposal to update an existing memory.
        
        Args:
            memory_id: ID of the memory to update.
            content: New full markdown content including frontmatter.
            reason: Explanation for the update.
            proposed_by: Identifier of the proposer.
            
        Returns:
            The created proposal.
            
        Raises:
            ProposalError: If the proposal is invalid.
        """
        existing = self._store.get_memory(memory_id)
        if not existing:
            raise ProposalError(
                f"Memory '{memory_id}' not found",
                reason="memory_not_found",
                details={"memory_id": memory_id},
            )
        
        issues = self._precheck_update(existing.path, content, memory_id)
        if issues:
            error_issues = [i for i in issues if i.severity == "error"]
            if error_issues:
                raise ProposalError(
                    f"Proposal precheck failed: {error_issues[0].message}",
                    reason=error_issues[0].code,
                    details={"issues": [i.to_dict() for i in issues]},
                )
        
        proposal = WriteProposal(
            proposal_id=generate_proposal_id(),
            type=ProposalType.UPDATE,
            target_path=existing.path,
            reason=reason,
            content=content,
            proposed_by=proposed_by,
            status=ProposalStatus.PENDING,
            memory_id=memory_id,
        )
        
        self._queue.enqueue(proposal)
        return proposal

    def propose_deprecate(
        self,
        memory_id: str,
        reason: str,
        proposed_by: str = "agent",
    ) -> WriteProposal:
        """Create a proposal to deprecate an existing memory.
        
        Args:
            memory_id: ID of the memory to deprecate.
            reason: Explanation for the deprecation.
            proposed_by: Identifier of the proposer.
            
        Returns:
            The created proposal.
            
        Raises:
            ProposalError: If the proposal is invalid.
        """
        existing = self._store.get_memory(memory_id)
        if not existing:
            raise ProposalError(
                f"Memory '{memory_id}' not found",
                reason="memory_not_found",
                details={"memory_id": memory_id},
            )
        
        if existing.status == "deprecated":
            raise ProposalError(
                f"Memory '{memory_id}' is already deprecated",
                reason="already_deprecated",
                details={"memory_id": memory_id},
            )
        
        if self._queue.has_pending_for_path(existing.path):
            raise ProposalError(
                f"Pending proposal already exists for path '{existing.path}'",
                reason="pending_exists",
                details={"path": existing.path},
            )
        
        proposal = WriteProposal(
            proposal_id=generate_proposal_id(),
            type=ProposalType.DEPRECATE,
            target_path=existing.path,
            reason=reason,
            proposed_by=proposed_by,
            status=ProposalStatus.PENDING,
            memory_id=memory_id,
            deprecation_reason=reason,
        )
        
        self._queue.enqueue(proposal)
        return proposal

    def propose_promote(
        self,
        memory_id: str,
        new_scope: str,
        reason: str,
        proposed_by: str = "agent",
    ) -> WriteProposal:
        """Create a proposal to promote a memory to a different scope.
        
        Args:
            memory_id: ID of the memory to promote.
            new_scope: The new scope (e.g., "global", "project").
            reason: Explanation for the promotion.
            proposed_by: Identifier of the proposer.
            
        Returns:
            The created proposal.
            
        Raises:
            ProposalError: If the proposal is invalid.
        """
        existing = self._store.get_memory(memory_id)
        if not existing:
            raise ProposalError(
                f"Memory '{memory_id}' not found",
                reason="memory_not_found",
                details={"memory_id": memory_id},
            )
        
        if new_scope not in self.VALID_SCOPES:
            raise ProposalError(
                f"Invalid scope '{new_scope}'",
                reason="invalid_scope",
                details={"valid_scopes": list(self.VALID_SCOPES)},
            )
        
        if existing.scope == new_scope:
            raise ProposalError(
                f"Memory '{memory_id}' is already in scope '{new_scope}'",
                reason="same_scope",
                details={"current_scope": existing.scope},
            )
        
        if new_scope == "baseline":
            pass
        
        if self._queue.has_pending_for_path(existing.path):
            raise ProposalError(
                f"Pending proposal already exists for path '{existing.path}'",
                reason="pending_exists",
                details={"path": existing.path},
            )
        
        proposal = WriteProposal(
            proposal_id=generate_proposal_id(),
            type=ProposalType.PROMOTE,
            target_path=existing.path,
            reason=reason,
            proposed_by=proposed_by,
            status=ProposalStatus.PENDING,
            memory_id=memory_id,
            new_scope=new_scope,
            source_scope=existing.scope,
        )
        
        self._queue.enqueue(proposal)
        return proposal

    def _precheck_create(
        self,
        target_path: str,
        content: str,
    ) -> list[ValidationIssue]:
        """Run prechecks for a CREATE proposal.
        
        Args:
            target_path: The target path for the new memory.
            content: The proposed content.
            
        Returns:
            List of validation issues found.
        """
        issues: list[ValidationIssue] = []
        
        issues.extend(self._validate_path(target_path))
        
        full_path = self._memory_root / target_path
        if full_path.exists():
            issues.append(ValidationIssue(
                code="path_exists",
                message=f"File already exists at path '{target_path}'",
                severity="error",
                field="target_path",
                suggestion="Use propose_update to modify existing memories",
            ))
        
        existing = self._store.get_memory_by_path(target_path)
        if existing:
            issues.append(ValidationIssue(
                code="memory_exists",
                message=f"Memory already indexed at path '{target_path}'",
                severity="error",
                field="target_path",
            ))
        
        if self._queue.has_pending_for_path(target_path):
            issues.append(ValidationIssue(
                code="pending_exists",
                message=f"Pending proposal already exists for path '{target_path}'",
                severity="error",
                field="target_path",
            ))
        
        issues.extend(self._validate_content_basic(content))
        
        return issues

    def _precheck_update(
        self,
        target_path: str,
        content: str,
        memory_id: str,
    ) -> list[ValidationIssue]:
        """Run prechecks for an UPDATE proposal.
        
        Args:
            target_path: The target path.
            content: The proposed new content.
            memory_id: The ID of the memory being updated.
            
        Returns:
            List of validation issues found.
        """
        issues: list[ValidationIssue] = []
        
        if self._queue.has_pending_for_path(target_path):
            issues.append(ValidationIssue(
                code="pending_exists",
                message=f"Pending proposal already exists for path '{target_path}'",
                severity="error",
                field="target_path",
            ))
        
        issues.extend(self._validate_content_basic(content))
        
        return issues

    def _validate_path(self, target_path: str) -> list[ValidationIssue]:
        """Validate the target path format.
        
        Args:
            target_path: The path to validate.
            
        Returns:
            List of validation issues.
        """
        issues: list[ValidationIssue] = []
        
        if not target_path:
            issues.append(ValidationIssue(
                code="empty_path",
                message="Target path cannot be empty",
                severity="error",
                field="target_path",
            ))
            return issues
        
        if not target_path.endswith(".md"):
            issues.append(ValidationIssue(
                code="invalid_extension",
                message="Target path must end with .md",
                severity="error",
                field="target_path",
                suggestion="Add .md extension to the filename",
            ))
        
        if target_path.startswith("/") or target_path.startswith("\\"):
            issues.append(ValidationIssue(
                code="absolute_path",
                message="Target path must be relative",
                severity="error",
                field="target_path",
            ))
        
        if ".." in target_path:
            issues.append(ValidationIssue(
                code="path_traversal",
                message="Target path cannot contain '..'",
                severity="error",
                field="target_path",
            ))
        
        parts = target_path.replace("\\", "/").split("/")
        if len(parts) < 2:
            issues.append(ValidationIssue(
                code="missing_scope_dir",
                message="Target path must include scope directory (e.g., 'project/file.md')",
                severity="error",
                field="target_path",
                suggestion="Include a scope directory like 'baseline/', 'global/', 'project/', etc.",
            ))
        else:
            scope_dir = parts[0]
            if scope_dir not in self.VALID_SCOPES:
                issues.append(ValidationIssue(
                    code="invalid_scope_dir",
                    message=f"Invalid scope directory '{scope_dir}'",
                    severity="error",
                    field="target_path",
                    suggestion=f"Use one of: {', '.join(sorted(self.VALID_SCOPES))}",
                ))
        
        return issues

    def _validate_content_basic(self, content: str) -> list[ValidationIssue]:
        """Run basic content validation.
        
        Args:
            content: The content to validate.
            
        Returns:
            List of validation issues.
        """
        issues: list[ValidationIssue] = []
        
        if not content or not content.strip():
            issues.append(ValidationIssue(
                code="empty_content",
                message="Content cannot be empty",
                severity="error",
                field="content",
            ))
            return issues
        
        if not content.strip().startswith("---"):
            issues.append(ValidationIssue(
                code="missing_frontmatter",
                message="Content must start with YAML frontmatter (---)",
                severity="error",
                field="content",
                suggestion="Add frontmatter with required fields: id, tags, scope, priority, confidence, status",
            ))
        
        frontmatter_count = content.count("---")
        if frontmatter_count < 2:
            issues.append(ValidationIssue(
                code="incomplete_frontmatter",
                message="Frontmatter must be closed with ---",
                severity="error",
                field="content",
            ))
        
        return issues

    def get_proposal(self, proposal_id: str) -> WriteProposal | None:
        """Get a proposal by ID.
        
        Args:
            proposal_id: The proposal ID.
            
        Returns:
            The proposal if found, None otherwise.
        """
        return self._queue.get(proposal_id)

    def get_pending_proposals(self, limit: int = 100) -> list[WriteProposal]:
        """Get all pending proposals.
        
        Args:
            limit: Maximum number to return.
            
        Returns:
            List of pending proposals.
        """
        return self._queue.get_pending(limit)

    def cancel_proposal(self, proposal_id: str) -> bool:
        """Cancel a pending proposal.
        
        Args:
            proposal_id: The proposal ID to cancel.
            
        Returns:
            True if cancelled, False if not found or not cancellable.
        """
        proposal = self._queue.get(proposal_id)
        if not proposal:
            return False
        
        if proposal.status not in (ProposalStatus.PENDING, ProposalStatus.DEFERRED):
            return False
        
        return self._queue.delete(proposal_id)

    def get_stats(self) -> dict[str, Any]:
        """Get handler statistics.
        
        Returns:
            Dictionary with statistics.
        """
        return self._queue.get_stats()
