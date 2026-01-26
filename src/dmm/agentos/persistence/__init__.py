"""AgentOS persistence layer.

This module provides SQLite-based persistence for AgentOS components:
- Agent runtime state
- Message history
- Self-modification audit log
- Session management

The registries (Skills, Tools, Agents) continue to use YAML filesystem
storage for human-readable configuration, while this module handles
runtime state that needs database persistence.
"""

from dmm.agentos.persistence.store import (
    AgentOSStore,
    AgentOSStoreError,
)
from dmm.agentos.persistence.models import (
    AgentState,
    MessageRecord,
    ModificationRecord,
    SessionRecord,
)

__all__ = [
    # Store
    "AgentOSStore",
    "AgentOSStoreError",
    # Models
    "AgentState",
    "MessageRecord", 
    "ModificationRecord",
    "SessionRecord",
]
