"""DMM Conflict Detection System - Phase 3.

This module provides proactive conflict detection between memories,
including tag overlap analysis, semantic similarity clustering,
supersession chain validation, and optional LLM-based rule extraction.
"""

from dmm.conflicts.store import ConflictStore
from dmm.conflicts.merger import ConflictMerger
from dmm.conflicts.resolver import ConflictResolver
from dmm.conflicts.scanner import ConflictScanner
from dmm.conflicts.detector import ConflictDetector

__all__ = [
    "ConflictStore",
    "ConflictMerger",
    "ConflictResolver",
    "ConflictScanner",
    "ConflictDetector",
]
