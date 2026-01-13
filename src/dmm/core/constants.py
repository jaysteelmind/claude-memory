"""DMM system constants and default values."""

from enum import Enum
from pathlib import Path
from typing import Final


class Scope(str, Enum):
    """Memory scope categories with semantic meaning."""
    
    BASELINE = "baseline"
    GLOBAL = "global"
    AGENT = "agent"
    PROJECT = "project"
    EPHEMERAL = "ephemeral"


class Confidence(str, Enum):
    """Memory confidence levels indicating stability."""
    
    EXPERIMENTAL = "experimental"
    ACTIVE = "active"
    STABLE = "stable"
    DEPRECATED = "deprecated"


class Status(str, Enum):
    """Memory status for lifecycle management."""
    
    ACTIVE = "active"
    DEPRECATED = "deprecated"


# Directory structure
DMM_ROOT_DIR: Final[str] = ".dmm"
MEMORY_DIR: Final[str] = "memory"
INDEX_DIR: Final[str] = "index"
PACKS_DIR: Final[str] = "packs"

# Database files
EMBEDDINGS_DB: Final[str] = "embeddings.db"
STATS_DB: Final[str] = "stats.db"

# Pack files
BASELINE_PACK_FILE: Final[str] = "baseline_pack.md"
LAST_PACK_FILE: Final[str] = "last_pack.md"

# Token budgets
DEFAULT_TOTAL_BUDGET: Final[int] = 2000
DEFAULT_BASELINE_BUDGET: Final[int] = 800
MIN_MEMORY_TOKENS: Final[int] = 300
MAX_MEMORY_TOKENS: Final[int] = 800
MAX_MEMORY_TOKENS_HARD: Final[int] = 2000

# Retrieval settings
DEFAULT_TOP_K_DIRECTORIES: Final[int] = 3
DEFAULT_MAX_CANDIDATES: Final[int] = 50
DEFAULT_DIVERSITY_THRESHOLD: Final[float] = 0.9

# Ranking weights
SIMILARITY_WEIGHT: Final[float] = 0.6
PRIORITY_WEIGHT: Final[float] = 0.25
CONFIDENCE_WEIGHT: Final[float] = 0.15

# Confidence scores for ranking
CONFIDENCE_SCORES: Final[dict[Confidence, float]] = {
    Confidence.STABLE: 1.0,
    Confidence.ACTIVE: 0.8,
    Confidence.EXPERIMENTAL: 0.5,
    Confidence.DEPRECATED: 0.0,
}

# Embedding model
EMBEDDING_MODEL: Final[str] = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSION: Final[int] = 384

# Daemon settings
DEFAULT_HOST: Final[str] = "127.0.0.1"
DEFAULT_PORT: Final[int] = 7433
DEFAULT_GRACEFUL_SHUTDOWN_TIMEOUT: Final[float] = 5.0

# File watcher settings
DEFAULT_DEBOUNCE_MS: Final[int] = 100
DEFAULT_WATCH_INTERVAL_MS: Final[int] = 1000

# Memory file settings
MEMORY_FILE_EXTENSION: Final[str] = ".md"
MEMORY_ID_PREFIX: Final[str] = "mem"
MEMORY_ID_FORMAT: Final[str] = "mem_{date}_{sequence:03d}"

# Required frontmatter fields
REQUIRED_FRONTMATTER_FIELDS: Final[tuple[str, ...]] = (
    "id",
    "tags",
    "scope",
    "priority",
    "confidence",
    "status",
)

# Optional frontmatter fields
OPTIONAL_FRONTMATTER_FIELDS: Final[tuple[str, ...]] = (
    "created",
    "last_used",
    "usage_count",
    "supersedes",
    "related",
    "expires",
)

# Baseline file ordering (priority files first)
BASELINE_PRIORITY_FILES: Final[tuple[str, ...]] = (
    "identity.md",
    "hard_constraints.md",
)


def get_dmm_root(base_path: Path | None = None) -> Path:
    """Get the .dmm root directory path."""
    if base_path is None:
        base_path = Path.cwd()
    return base_path / DMM_ROOT_DIR


def get_memory_root(base_path: Path | None = None) -> Path:
    """Get the memory directory path."""
    return get_dmm_root(base_path) / MEMORY_DIR


def get_index_root(base_path: Path | None = None) -> Path:
    """Get the index directory path."""
    return get_dmm_root(base_path) / INDEX_DIR


def get_embeddings_db_path(base_path: Path | None = None) -> Path:
    """Get the embeddings database path."""
    return get_index_root(base_path) / EMBEDDINGS_DB


def get_stats_db_path(base_path: Path | None = None) -> Path:
    """Get the stats database path."""
    return get_index_root(base_path) / STATS_DB


# =============================================================================
# Phase 2: Write-Back Engine Constants
# =============================================================================

# Proposal settings
PROPOSAL_ID_PREFIX: Final[str] = "prop"
PROPOSAL_ID_FORMAT: Final[str] = "prop_{timestamp}_{random}"

# Review queue database
REVIEW_QUEUE_DB: Final[str] = "review_queue.db"

# Usage tracking database  
USAGE_DB: Final[str] = "usage.db"

# Duplicate detection thresholds
DUPLICATE_EXACT_THRESHOLD: Final[float] = 0.99
DUPLICATE_SEMANTIC_THRESHOLD: Final[float] = 0.85
DUPLICATE_WARNING_THRESHOLD: Final[float] = 0.70

# Review settings
AUTO_APPROVE_CONFIDENCE_THRESHOLD: Final[float] = 0.95
REVIEW_TIMEOUT_SECONDS: Final[int] = 30
MAX_REVIEW_RETRIES: Final[int] = 3

# Quality check settings
QUALITY_MIN_TAGS: Final[int] = 1
QUALITY_MAX_TAGS: Final[int] = 10
QUALITY_MIN_BODY_LENGTH: Final[int] = 50
QUALITY_MAX_TITLE_LENGTH: Final[int] = 100

# Commit settings
COMMIT_BACKUP_ENABLED: Final[bool] = True
COMMIT_REINDEX_TIMEOUT_SECONDS: Final[int] = 30

# Usage tracking settings
USAGE_BATCH_SIZE: Final[int] = 100
USAGE_FLUSH_INTERVAL_SECONDS: Final[int] = 60


def get_review_queue_db_path(base_path: Path | None = None) -> Path:
    """Get the review queue database path."""
    return get_index_root(base_path) / REVIEW_QUEUE_DB


def get_usage_db_path(base_path: Path | None = None) -> Path:
    """Get the usage tracking database path."""
    return get_index_root(base_path) / USAGE_DB


# =============================================================================
# Phase 3: Conflict Detection Constants
# =============================================================================

# Conflicts database
CONFLICTS_DB: Final[str] = "conflicts.db"

# Conflict ID format
CONFLICT_ID_PREFIX: Final[str] = "conflict"
CONFLICT_ID_FORMAT: Final[str] = "conflict_{timestamp}_{random}"

# Scan ID format
SCAN_ID_PREFIX: Final[str] = "scan"
SCAN_ID_FORMAT: Final[str] = "scan_{timestamp}_{random}"

# Tag overlap detection settings
TAG_OVERLAP_MIN_SHARED_TAGS: Final[int] = 2
TAG_OVERLAP_CONTRADICTION_SCORE_INCREMENT: Final[float] = 0.3

# Semantic similarity detection settings
SEMANTIC_SIMILARITY_THRESHOLD: Final[float] = 0.80
SEMANTIC_DIVERGENCE_THRESHOLD: Final[float] = 0.30
SEMANTIC_MAX_PAIRS_TO_CHECK: Final[int] = 1000

# Supersession chain detection settings
SUPERSESSION_ORPHAN_SCORE: Final[float] = 0.90
SUPERSESSION_CONTESTED_SCORE: Final[float] = 0.85
SUPERSESSION_CIRCULAR_SCORE: Final[float] = 1.0

# Rule extraction (LLM) settings
RULE_EXTRACTION_ENABLED: Final[bool] = False
RULE_EXTRACTION_TIMEOUT_SECONDS: Final[int] = 30

# Conflict confidence thresholds
CONFLICT_HIGH_CONFIDENCE_THRESHOLD: Final[float] = 0.80
CONFLICT_LOW_CONFIDENCE_THRESHOLD: Final[float] = 0.50

# Multi-method detection boost
CONFLICT_MULTI_METHOD_BOOST: Final[float] = 0.10
CONFLICT_MULTI_METHOD_MAX_BOOST: Final[float] = 0.30

# Scan settings
PERIODIC_SCAN_ENABLED: Final[bool] = True
PERIODIC_SCAN_INTERVAL_HOURS: Final[int] = 24
SCAN_AT_STARTUP: Final[bool] = False
INCREMENTAL_SCAN_ON_COMMIT: Final[bool] = True
MAX_CANDIDATES_PER_METHOD: Final[int] = 100

# Conflict filtering
IGNORE_DEPRECATED_IN_SCAN: Final[bool] = True
IGNORE_EPHEMERAL_VS_EPHEMERAL: Final[bool] = True

# Resolution settings
RESOLUTION_BACKUP_ENABLED: Final[bool] = True

# Divergence detection keywords
DIVERGENCE_KEYWORDS: Final[tuple[str, ...]] = (
    "not",
    "never",
    "avoid",
    "don't",
    "shouldn't",
    "instead",
    "rather",
    "but",
    "however",
    "although",
    "except",
    "unless",
)

# Contradiction pattern pairs for tag overlap analysis
CONTRADICTION_PATTERNS: Final[tuple[tuple[str, str], ...]] = (
    (r"\balways\b", r"\bnever\b"),
    (r"\bmust\b", r"\bmust not\b"),
    (r"\brequired\b", r"\bforbidden\b"),
    (r"\buse\b", r"\bavoid\b"),
    (r"\benable\b", r"\bdisable\b"),
    (r"\ballow\b", r"\bprohibit\b"),
    (r"\bsync\b", r"\basync\b"),
    (r"\btabs\b", r"\bspaces\b"),
    (r"\bSQL\b", r"\bORM\b"),
    (r"\byes\b", r"\bno\b"),
    (r"\btrue\b", r"\bfalse\b"),
    (r"\binclude\b", r"\bexclude\b"),
    (r"\baccept\b", r"\breject\b"),
)


def get_conflicts_db_path(base_path: Path | None = None) -> Path:
    """Get the conflicts database path."""
    return get_index_root(base_path) / CONFLICTS_DB


# =============================================================================
