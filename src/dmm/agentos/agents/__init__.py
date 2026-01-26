"""Agents module for the Agent OS.

This module provides agent management capabilities including:
- Agent data models (Agent, SkillsConfig, ToolsConfig, etc.)
- Agent file loading from YAML
- Agent registry for management and caching
- Agent-task matching
"""

from dmm.agentos.agents.models import (
    AGENT_CATEGORIES,
    BEHAVIOR_TONES,
    VERBOSITY_LEVELS,
    Agent,
    AgentConstraints,
    BehaviorConfig,
    MemoryConfig,
    SkillsConfig,
    ToolsConfig,
)
from dmm.agentos.agents.loader import (
    AgentLoader,
    AgentLoadError,
    AgentValidationError,
)
from dmm.agentos.agents.registry import (
    AgentRegistry,
    AgentRegistryStats,
    SyncResult,
    ValidationResult,
)
from dmm.agentos.agents.matcher import (
    AgentMatch,
    AgentMatcher,
)

__all__ = [
    # Constants
    "AGENT_CATEGORIES",
    "BEHAVIOR_TONES",
    "VERBOSITY_LEVELS",
    # Models
    "Agent",
    "AgentConstraints",
    "BehaviorConfig",
    "MemoryConfig",
    "SkillsConfig",
    "ToolsConfig",
    # Loader
    "AgentLoader",
    "AgentLoadError",
    "AgentValidationError",
    # Registry
    "AgentRegistry",
    "AgentRegistryStats",
    "SyncResult",
    "ValidationResult",
    # Matcher
    "AgentMatch",
    "AgentMatcher",
]
