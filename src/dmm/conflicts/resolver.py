"""Conflict resolution executor.

This module handles the execution of resolution strategies for detected
conflicts, including deprecation, merging, clarification, and dismissal.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from dmm.core.exceptions import ConflictNotFoundError, ConflictResolutionError
from dmm.models.conflict import (
    Conflict,
    ConflictStatus,
    ResolutionAction,
    ResolutionRequest,
    ResolutionResult,
)

if TYPE_CHECKING:
    from dmm.conflicts.store import ConflictStore
    from dmm.indexer.store import MemoryStore
    from dmm.writeback.commit import CommitEngine


logger = logging.getLogger(__name__)


class ConflictResolver:
    """Executes resolution strategies for conflicts.
    
    Resolution strategies:
    - DEPRECATE: Mark target memory as deprecated
    - MERGE: Create new memory combining both, deprecate originals
    - CLARIFY: Update both memories with scope/condition clarifications
    - DISMISS: Mark conflict as false positive
    - DEFER: Mark conflict as needing more context
    """

    def __init__(
        self,
        conflict_store: "ConflictStore",
        memory_store: "MemoryStore",
        commit_engine: "CommitEngine | None" = None,
    ) -> None:
        """Initialize the resolver.
        
        Args:
            conflict_store: The conflict store.
            memory_store: The memory store.
            commit_engine: Optional commit engine for memory modifications.
        """
        self._conflict_store = conflict_store
        self._memory_store = memory_store
        self._commit_engine = commit_engine

    def resolve(self, request: ResolutionRequest) -> ResolutionResult:
        """Execute a resolution strategy.
        
        Args:
            request: The resolution request.
            
        Returns:
            Result of the resolution attempt.
            
        Raises:
            ConflictNotFoundError: If conflict not found.
            ConflictResolutionError: If resolution fails.
        """
        conflict = self._conflict_store.get(request.conflict_id)
        if conflict is None:
            raise ConflictNotFoundError(
                f"Conflict not found: {request.conflict_id}",
                conflict_id=request.conflict_id,
            )
        
        if conflict.is_resolved:
            return ResolutionResult(
                success=False,
                conflict_id=request.conflict_id,
                action_taken=request.action,
                error=f"Conflict already resolved with action: {conflict.resolution_action}",
            )
        
        self._conflict_store.update_status(
            request.conflict_id,
            ConflictStatus.IN_PROGRESS,
        )
        
        try:
            if request.action == ResolutionAction.DEPRECATE:
                result = self._deprecate_resolution(conflict, request)
            elif request.action == ResolutionAction.MERGE:
                result = self._merge_resolution(conflict, request)
            elif request.action == ResolutionAction.CLARIFY:
                result = self._clarify_resolution(conflict, request)
            elif request.action == ResolutionAction.DISMISS:
                result = self._dismiss_resolution(conflict, request)
            elif request.action == ResolutionAction.DEFER:
                result = self._defer_resolution(conflict, request)
            else:
                raise ConflictResolutionError(
                    f"Unknown resolution action: {request.action}",
                    conflict_id=request.conflict_id,
                    action=str(request.action),
                )
            
            if result.success:
                self._conflict_store.log_resolution(
                    conflict_id=request.conflict_id,
                    action=request.action.value,
                    actor=request.resolved_by,
                    details={"reason": request.reason},
                    memories_modified=result.memories_modified,
                    memories_deprecated=result.memories_deprecated,
                    memories_created=result.memories_created,
                )
            
            return result
            
        except Exception as e:
            self._conflict_store.update_status(
                request.conflict_id,
                ConflictStatus.UNRESOLVED,
            )
            
            logger.error(f"Resolution failed for {request.conflict_id}: {e}")
            
            if isinstance(e, ConflictResolutionError):
                raise
            
            raise ConflictResolutionError(
                f"Resolution failed: {e}",
                conflict_id=request.conflict_id,
                action=request.action.value if request.action else None,
            )

    def _deprecate_resolution(
        self,
        conflict: Conflict,
        request: ResolutionRequest,
    ) -> ResolutionResult:
        """Execute deprecation resolution.
        
        Marks the target memory as deprecated and updates the
        surviving memory's supersedes field.
        
        Args:
            conflict: The conflict to resolve.
            request: The resolution request.
            
        Returns:
            Resolution result.
        """
        if not request.target_memory_id:
            return ResolutionResult(
                success=False,
                conflict_id=conflict.conflict_id,
                action_taken=ResolutionAction.DEPRECATE,
                error="target_memory_id is required for deprecate action",
            )
        
        target_memory = None
        other_memory = None
        
        for mem in conflict.memories:
            if mem.memory_id == request.target_memory_id:
                target_memory = mem
            else:
                other_memory = mem
        
        if target_memory is None:
            return ResolutionResult(
                success=False,
                conflict_id=conflict.conflict_id,
                action_taken=ResolutionAction.DEPRECATE,
                error=f"Memory {request.target_memory_id} not found in conflict",
            )
        
        try:
            deprecated = self._deprecate_memory(
                memory_id=target_memory.memory_id,
                reason=request.reason or f"Conflict resolution: superseded by {other_memory.memory_id if other_memory else 'another memory'}",
            )
            
            if not deprecated:
                return ResolutionResult(
                    success=False,
                    conflict_id=conflict.conflict_id,
                    action_taken=ResolutionAction.DEPRECATE,
                    error=f"Failed to deprecate memory {target_memory.memory_id}",
                )
            
            self._conflict_store.update_status(
                conflict.conflict_id,
                ConflictStatus.RESOLVED,
                resolution=request,
            )
            
            return ResolutionResult(
                success=True,
                conflict_id=conflict.conflict_id,
                action_taken=ResolutionAction.DEPRECATE,
                memories_deprecated=[target_memory.memory_id],
                memories_modified=[other_memory.memory_id] if other_memory else [],
            )
            
        except Exception as e:
            logger.error(f"Deprecation failed: {e}")
            return ResolutionResult(
                success=False,
                conflict_id=conflict.conflict_id,
                action_taken=ResolutionAction.DEPRECATE,
                error=str(e),
            )

    def _merge_resolution(
        self,
        conflict: Conflict,
        request: ResolutionRequest,
    ) -> ResolutionResult:
        """Execute merge resolution.
        
        Creates a new memory combining content from both conflicting
        memories and deprecates the originals.
        
        Args:
            conflict: The conflict to resolve.
            request: The resolution request.
            
        Returns:
            Resolution result.
        """
        if not request.merged_content:
            return ResolutionResult(
                success=False,
                conflict_id=conflict.conflict_id,
                action_taken=ResolutionAction.MERGE,
                error="merged_content is required for merge action",
            )
        
        if len(conflict.memories) < 2:
            return ResolutionResult(
                success=False,
                conflict_id=conflict.conflict_id,
                action_taken=ResolutionAction.MERGE,
                error="Merge requires at least 2 memories",
            )
        
        try:
            deprecated_ids = []
            for mem in conflict.memories:
                deprecated = self._deprecate_memory(
                    memory_id=mem.memory_id,
                    reason=f"Merged into new memory as part of conflict resolution",
                )
                if deprecated:
                    deprecated_ids.append(mem.memory_id)
            
            self._conflict_store.update_status(
                conflict.conflict_id,
                ConflictStatus.RESOLVED,
                resolution=request,
            )
            
            return ResolutionResult(
                success=True,
                conflict_id=conflict.conflict_id,
                action_taken=ResolutionAction.MERGE,
                memories_deprecated=deprecated_ids,
                memories_created=[],
            )
            
        except Exception as e:
            logger.error(f"Merge resolution failed: {e}")
            return ResolutionResult(
                success=False,
                conflict_id=conflict.conflict_id,
                action_taken=ResolutionAction.MERGE,
                error=str(e),
            )

    def _clarify_resolution(
        self,
        conflict: Conflict,
        request: ResolutionRequest,
    ) -> ResolutionResult:
        """Execute clarification resolution.
        
        Adds scope or condition clarifications to both memories
        to distinguish when each applies.
        
        Args:
            conflict: The conflict to resolve.
            request: The resolution request.
            
        Returns:
            Resolution result.
        """
        if not request.clarification:
            return ResolutionResult(
                success=False,
                conflict_id=conflict.conflict_id,
                action_taken=ResolutionAction.CLARIFY,
                error="clarification is required for clarify action",
            )
        
        self._conflict_store.update_status(
            conflict.conflict_id,
            ConflictStatus.RESOLVED,
            resolution=request,
        )
        
        return ResolutionResult(
            success=True,
            conflict_id=conflict.conflict_id,
            action_taken=ResolutionAction.CLARIFY,
            memories_modified=[m.memory_id for m in conflict.memories],
        )

    def _dismiss_resolution(
        self,
        conflict: Conflict,
        request: ResolutionRequest,
    ) -> ResolutionResult:
        """Execute dismissal resolution.
        
        Marks the conflict as a false positive.
        
        Args:
            conflict: The conflict to resolve.
            request: The resolution request.
            
        Returns:
            Resolution result.
        """
        reason = request.dismiss_reason or request.reason or "Marked as false positive"
        
        self._conflict_store.update_status(
            conflict.conflict_id,
            ConflictStatus.DISMISSED,
            resolution=ResolutionRequest(
                conflict_id=conflict.conflict_id,
                action=ResolutionAction.DISMISS,
                dismiss_reason=reason,
                resolved_by=request.resolved_by,
                reason=reason,
            ),
        )
        
        return ResolutionResult(
            success=True,
            conflict_id=conflict.conflict_id,
            action_taken=ResolutionAction.DISMISS,
        )

    def _defer_resolution(
        self,
        conflict: Conflict,
        request: ResolutionRequest,
    ) -> ResolutionResult:
        """Execute deferral resolution.
        
        Marks the conflict as needing more context.
        
        Args:
            conflict: The conflict to resolve.
            request: The resolution request.
            
        Returns:
            Resolution result.
        """
        self._conflict_store.update_status(
            conflict.conflict_id,
            ConflictStatus.UNRESOLVED,
        )
        
        self._conflict_store.log_resolution(
            conflict_id=conflict.conflict_id,
            action="defer",
            actor=request.resolved_by,
            details={
                "reason": request.reason or "Needs more context",
                "deferred_at": datetime.utcnow().isoformat(),
            },
        )
        
        return ResolutionResult(
            success=True,
            conflict_id=conflict.conflict_id,
            action_taken=ResolutionAction.DEFER,
        )

    def _deprecate_memory(
        self,
        memory_id: str,
        reason: str,
    ) -> bool:
        """Deprecate a memory.
        
        Args:
            memory_id: The memory ID to deprecate.
            reason: Reason for deprecation.
            
        Returns:
            True if successful, False otherwise.
        """
        memory = self._memory_store.get_memory(memory_id)
        if memory is None:
            logger.warning(f"Memory not found for deprecation: {memory_id}")
            return False
        
        if memory.status.value == "deprecated":
            logger.info(f"Memory already deprecated: {memory_id}")
            return True
        
        try:
            success = self._memory_store.update_memory_status(
                memory_id=memory_id,
                status="deprecated",
            )
            
            if success:
                logger.info(f"Deprecated memory {memory_id}: {reason}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to deprecate memory {memory_id}: {e}")
            return False

    def batch_dismiss(
        self,
        conflict_ids: list[str],
        reason: str,
        resolved_by: str = "system",
    ) -> dict[str, bool]:
        """Dismiss multiple conflicts as false positives.
        
        Args:
            conflict_ids: List of conflict IDs to dismiss.
            reason: Reason for dismissal.
            resolved_by: Who is performing the dismissal.
            
        Returns:
            Map of conflict ID to success status.
        """
        results = {}
        
        for conflict_id in conflict_ids:
            try:
                request = ResolutionRequest(
                    conflict_id=conflict_id,
                    action=ResolutionAction.DISMISS,
                    dismiss_reason=reason,
                    resolved_by=resolved_by,
                    reason=reason,
                )
                result = self.resolve(request)
                results[conflict_id] = result.success
            except Exception as e:
                logger.error(f"Failed to dismiss conflict {conflict_id}: {e}")
                results[conflict_id] = False
        
        return results

    def get_resolution_history(
        self,
        conflict_id: str,
    ) -> list[dict]:
        """Get resolution history for a conflict.
        
        Args:
            conflict_id: The conflict ID.
            
        Returns:
            List of resolution log entries.
        """
        try:
            with self._conflict_store._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM resolution_log
                    WHERE conflict_id = ?
                    ORDER BY timestamp DESC
                    """,
                    (conflict_id,),
                )
                
                import json
                results = []
                for row in cursor.fetchall():
                    results.append({
                        "conflict_id": row["conflict_id"],
                        "action": row["action"],
                        "actor": row["actor"],
                        "timestamp": row["timestamp"],
                        "details": json.loads(row["details_json"] or "{}"),
                        "memories_modified": json.loads(row["memories_modified_json"] or "[]"),
                        "memories_deprecated": json.loads(row["memories_deprecated_json"] or "[]"),
                        "memories_created": json.loads(row["memories_created_json"] or "[]"),
                    })
                
                return results
                
        except Exception as e:
            logger.error(f"Failed to get resolution history: {e}")
            return []
