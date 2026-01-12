"""Commit engine for atomically applying approved proposals."""

import asyncio
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import frontmatter

from dmm.core.constants import (
    Confidence,
    Scope,
    Status,
    get_memory_root,
)
from dmm.core.exceptions import CommitError
from dmm.models.proposal import (
    CommitResult,
    ProposalStatus,
    ProposalType,
    WriteProposal,
)
from dmm.writeback.queue import ReviewQueue

if TYPE_CHECKING:
    from dmm.indexer.indexer import Indexer


class CommitEngine:
    """Handles atomic commits of approved write proposals."""

    def __init__(
        self,
        queue: ReviewQueue,
        indexer: "Indexer",
        base_path: Path | None = None,
        backup_enabled: bool = True,
    ) -> None:
        """Initialize the commit engine.
        
        Args:
            queue: The review queue.
            indexer: The memory indexer for reindexing.
            base_path: Base path for the DMM directory.
            backup_enabled: Whether to create backups before modifications.
        """
        self._queue = queue
        self._indexer = indexer
        self._base_path = base_path or Path.cwd()
        self._memory_root = get_memory_root(self._base_path)
        self._backup_enabled = backup_enabled
        self._backup_dir = self._memory_root.parent / "backups"

    def commit(self, proposal: WriteProposal) -> CommitResult:
        """Commit an approved proposal.
        
        Args:
            proposal: The approved proposal to commit.
            
        Returns:
            CommitResult with success/failure details.
            
        Raises:
            CommitError: If the commit fails and rollback also fails.
        """
        if proposal.status not in (ProposalStatus.APPROVED, ProposalStatus.MODIFIED):
            return CommitResult(
                proposal_id=proposal.proposal_id,
                success=False,
                error=f"Cannot commit proposal with status '{proposal.status.value}'",
            )

        start_time = time.perf_counter()
        
        backup_path: Path | None = None
        target_path = self._memory_root / proposal.target_path

        try:
            if proposal.type == ProposalType.CREATE:
                result = self._commit_create(proposal, target_path)
            elif proposal.type == ProposalType.UPDATE:
                backup_path = self._create_backup(target_path) if self._backup_enabled else None
                result = self._commit_update(proposal, target_path)
            elif proposal.type == ProposalType.DEPRECATE:
                backup_path = self._create_backup(target_path) if self._backup_enabled else None
                result = self._commit_deprecate(proposal, target_path)
            elif proposal.type == ProposalType.PROMOTE:
                backup_path = self._create_backup(target_path) if self._backup_enabled else None
                result = self._commit_promote(proposal, target_path)
            else:
                return CommitResult(
                    proposal_id=proposal.proposal_id,
                    success=False,
                    error=f"Unknown proposal type: {proposal.type}",
                )

            if result.success:
                reindex_start = time.perf_counter()
                self._reindex_memory(target_path, proposal)
                result.reindex_duration_ms = (time.perf_counter() - reindex_start) * 1000

                self._queue.update_status(
                    proposal.proposal_id,
                    ProposalStatus.COMMITTED,
                    notes="Successfully committed",
                )

                if backup_path and backup_path.exists():
                    backup_path.unlink()

            result.commit_duration_ms = (time.perf_counter() - start_time) * 1000
            return result

        except Exception as e:
            rollback_success = False
            if backup_path and backup_path.exists():
                rollback_success = self._rollback(backup_path, target_path)

            self._queue.set_commit_error(proposal.proposal_id, str(e))

            if not rollback_success and backup_path:
                raise CommitError(
                    f"Commit failed and rollback failed: {e}",
                    proposal_id=proposal.proposal_id,
                    path=str(target_path),
                    rollback_success=False,
                ) from e

            return CommitResult(
                proposal_id=proposal.proposal_id,
                success=False,
                error=str(e),
                rollback_performed=backup_path is not None,
                rollback_success=rollback_success,
                commit_duration_ms=(time.perf_counter() - start_time) * 1000,
            )

    def _commit_create(
        self,
        proposal: WriteProposal,
        target_path: Path,
    ) -> CommitResult:
        """Commit a CREATE proposal.
        
        Args:
            proposal: The proposal.
            target_path: Full path to the target file.
            
        Returns:
            CommitResult.
        """
        if target_path.exists():
            return CommitResult(
                proposal_id=proposal.proposal_id,
                success=False,
                error=f"File already exists: {target_path}",
            )

        target_path.parent.mkdir(parents=True, exist_ok=True)

        content = proposal.content
        if not content:
            return CommitResult(
                proposal_id=proposal.proposal_id,
                success=False,
                error="No content provided for CREATE proposal",
            )

        target_path.write_text(content, encoding="utf-8")

        memory_id = self._extract_memory_id(content)

        return CommitResult(
            proposal_id=proposal.proposal_id,
            success=True,
            memory_id=memory_id,
            memory_path=proposal.target_path,
        )

    def _commit_update(
        self,
        proposal: WriteProposal,
        target_path: Path,
    ) -> CommitResult:
        """Commit an UPDATE proposal.
        
        Args:
            proposal: The proposal.
            target_path: Full path to the target file.
            
        Returns:
            CommitResult.
        """
        if not target_path.exists():
            return CommitResult(
                proposal_id=proposal.proposal_id,
                success=False,
                error=f"File does not exist: {target_path}",
            )

        content = proposal.content
        if not content:
            return CommitResult(
                proposal_id=proposal.proposal_id,
                success=False,
                error="No content provided for UPDATE proposal",
            )

        target_path.write_text(content, encoding="utf-8")

        return CommitResult(
            proposal_id=proposal.proposal_id,
            success=True,
            memory_id=proposal.memory_id,
            memory_path=proposal.target_path,
        )

    def _commit_deprecate(
        self,
        proposal: WriteProposal,
        target_path: Path,
    ) -> CommitResult:
        """Commit a DEPRECATE proposal.
        
        Updates the memory's status and confidence to deprecated.
        
        Args:
            proposal: The proposal.
            target_path: Full path to the target file.
            
        Returns:
            CommitResult.
        """
        if not target_path.exists():
            return CommitResult(
                proposal_id=proposal.proposal_id,
                success=False,
                error=f"File does not exist: {target_path}",
            )

        try:
            content = target_path.read_text(encoding="utf-8")
            post = frontmatter.loads(content)

            post.metadata["status"] = Status.DEPRECATED.value
            post.metadata["confidence"] = Confidence.DEPRECATED.value
            post.metadata["deprecated_at"] = datetime.now().isoformat()
            post.metadata["deprecation_reason"] = proposal.deprecation_reason

            new_content = frontmatter.dumps(post)
            target_path.write_text(new_content, encoding="utf-8")

            deprecated_dir = self._memory_root / "deprecated"
            deprecated_dir.mkdir(parents=True, exist_ok=True)
            
            new_filename = target_path.name
            deprecated_path = deprecated_dir / new_filename
            
            counter = 1
            while deprecated_path.exists():
                stem = target_path.stem
                deprecated_path = deprecated_dir / f"{stem}_{counter}.md"
                counter += 1

            shutil.move(str(target_path), str(deprecated_path))

            return CommitResult(
                proposal_id=proposal.proposal_id,
                success=True,
                memory_id=proposal.memory_id,
                memory_path=str(deprecated_path.relative_to(self._memory_root)),
            )

        except Exception as e:
            return CommitResult(
                proposal_id=proposal.proposal_id,
                success=False,
                error=f"Failed to deprecate memory: {e}",
            )

    def _commit_promote(
        self,
        proposal: WriteProposal,
        target_path: Path,
    ) -> CommitResult:
        """Commit a PROMOTE proposal.
        
        Moves the memory to a new scope directory and updates its scope.
        
        Args:
            proposal: The proposal.
            target_path: Full path to the target file.
            
        Returns:
            CommitResult.
        """
        if not target_path.exists():
            return CommitResult(
                proposal_id=proposal.proposal_id,
                success=False,
                error=f"File does not exist: {target_path}",
            )

        if not proposal.new_scope:
            return CommitResult(
                proposal_id=proposal.proposal_id,
                success=False,
                error="No new_scope specified for PROMOTE proposal",
            )

        try:
            content = target_path.read_text(encoding="utf-8")
            post = frontmatter.loads(content)

            post.metadata["scope"] = proposal.new_scope
            post.metadata["promoted_at"] = datetime.now().isoformat()
            post.metadata["promoted_from"] = proposal.source_scope

            new_content = frontmatter.dumps(post)

            new_scope_dir = self._memory_root / proposal.new_scope
            new_scope_dir.mkdir(parents=True, exist_ok=True)

            relative_path_parts = proposal.target_path.split("/")
            if len(relative_path_parts) > 1:
                new_filename = "/".join(relative_path_parts[1:])
            else:
                new_filename = relative_path_parts[0]

            new_path = new_scope_dir / new_filename
            new_path.parent.mkdir(parents=True, exist_ok=True)

            counter = 1
            original_new_path = new_path
            while new_path.exists():
                stem = original_new_path.stem
                new_path = original_new_path.parent / f"{stem}_{counter}.md"
                counter += 1

            new_path.write_text(new_content, encoding="utf-8")
            target_path.unlink()

            return CommitResult(
                proposal_id=proposal.proposal_id,
                success=True,
                memory_id=proposal.memory_id,
                memory_path=str(new_path.relative_to(self._memory_root)),
            )

        except Exception as e:
            return CommitResult(
                proposal_id=proposal.proposal_id,
                success=False,
                error=f"Failed to promote memory: {e}",
            )

    def _create_backup(self, target_path: Path) -> Path | None:
        """Create a backup of a file before modification.
        
        Args:
            target_path: Path to the file to backup.
            
        Returns:
            Path to the backup file, or None if file doesn't exist.
        """
        if not target_path.exists():
            return None

        self._backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_name = f"{target_path.stem}_{timestamp}.md.bak"
        backup_path = self._backup_dir / backup_name

        shutil.copy2(target_path, backup_path)
        return backup_path

    def _rollback(self, backup_path: Path, target_path: Path) -> bool:
        """Rollback a modification using backup.
        
        Args:
            backup_path: Path to the backup file.
            target_path: Path to restore to.
            
        Returns:
            True if rollback successful, False otherwise.
        """
        try:
            if backup_path.exists():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_path, target_path)
                backup_path.unlink()
                return True
            return False
        except Exception:
            return False

    def _reindex_memory(self, target_path: Path, proposal: WriteProposal) -> None:
        """Reindex a memory after commit.
        
        Args:
            target_path: Path to the memory file.
            proposal: The committed proposal.
        """
        if proposal.type == ProposalType.DEPRECATE:
            if proposal.memory_id:
                self._indexer.store.delete_memory(proposal.memory_id)
        else:
            if target_path.exists():
                # index_file is async, run it synchronously
                try:
                    asyncio.run(self._indexer.index_file(target_path))
                except RuntimeError:
                    # Already in async context - use nest_asyncio pattern
                    # or just skip reindexing (will be picked up on next reindex)
                    pass

    def _extract_memory_id(self, content: str) -> str | None:
        """Extract memory ID from content frontmatter.
        
        Args:
            content: The markdown content.
            
        Returns:
            The memory ID if found, None otherwise.
        """
        try:
            post = frontmatter.loads(content)
            return post.metadata.get("id")
        except Exception:
            return None

    def cleanup_old_backups(self, max_age_hours: int = 24) -> int:
        """Clean up old backup files.
        
        Args:
            max_age_hours: Maximum age in hours for backups.
            
        Returns:
            Number of backups deleted.
        """
        if not self._backup_dir.exists():
            return 0

        deleted = 0
        cutoff = datetime.now().timestamp() - (max_age_hours * 3600)

        for backup_file in self._backup_dir.glob("*.md.bak"):
            if backup_file.stat().st_mtime < cutoff:
                backup_file.unlink()
                deleted += 1

        return deleted
