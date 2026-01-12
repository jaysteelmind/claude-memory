"""Write-back engine for memory modifications.

This module provides:
- ProposalHandler: Creates and validates write proposals
- ReviewQueue: Persists proposals for review
- CommitEngine: Atomically commits approved proposals
- UsageTracker: Tracks memory retrieval usage
- ConflictsDB: Conflict database (Phase 3 preparation)
"""

from dmm.writeback.commit import CommitEngine
from dmm.writeback.conflicts import ConflictsDB, initialize_conflicts_db
from dmm.writeback.proposal import ProposalHandler
from dmm.writeback.queue import ReviewQueue
from dmm.writeback.usage import UsageTracker

__all__ = [
    "ProposalHandler",
    "ReviewQueue",
    "CommitEngine",
    "UsageTracker",
    "ConflictsDB",
    "initialize_conflicts_db",
]
