"""DMM configuration loading and validation."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

from dmm.core.constants import (
    DEFAULT_BASELINE_BUDGET,
    DEFAULT_DEBOUNCE_MS,
    DEFAULT_DIVERSITY_THRESHOLD,
    DEFAULT_GRACEFUL_SHUTDOWN_TIMEOUT,
    DEFAULT_HOST,
    DEFAULT_MAX_CANDIDATES,
    DEFAULT_PORT,
    DEFAULT_TOP_K_DIRECTORIES,
    DEFAULT_TOTAL_BUDGET,
    DEFAULT_WATCH_INTERVAL_MS,
    EMBEDDING_MODEL,
    MAX_MEMORY_TOKENS,
    MIN_MEMORY_TOKENS,
    get_dmm_root,
)
from dmm.core.exceptions import ConfigurationError


@dataclass(frozen=True)
class DaemonConfig:
    """Daemon server configuration."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    auto_start: bool = True
    graceful_shutdown_timeout_ms: int = int(DEFAULT_GRACEFUL_SHUTDOWN_TIMEOUT * 1000)
    log_level: str = "info"

    @property
    def graceful_shutdown_timeout(self) -> float:
        """Get timeout in seconds."""
        return self.graceful_shutdown_timeout_ms / 1000.0


@dataclass(frozen=True)
class IndexerConfig:
    """Indexer configuration."""

    watch_interval_ms: int = DEFAULT_WATCH_INTERVAL_MS
    debounce_ms: int = DEFAULT_DEBOUNCE_MS
    embedding_model: str = EMBEDDING_MODEL
    batch_size: int = 50


@dataclass(frozen=True)
class RetrievalConfig:
    """Retrieval configuration."""

    top_k_directories: int = DEFAULT_TOP_K_DIRECTORIES
    max_candidates: int = DEFAULT_MAX_CANDIDATES
    diversity_threshold: float = DEFAULT_DIVERSITY_THRESHOLD
    default_budget: int = DEFAULT_TOTAL_BUDGET
    baseline_budget: int = DEFAULT_BASELINE_BUDGET


@dataclass(frozen=True)
class StorageConfig:
    """Storage paths configuration."""

    embeddings_db: str = "index/embeddings.db"
    stats_db: str = "index/stats.db"


@dataclass(frozen=True)
class ValidationConfig:
    """Memory validation configuration."""

    min_tokens: int = MIN_MEMORY_TOKENS
    max_tokens: int = MAX_MEMORY_TOKENS
    warn_on_missing_optional: bool = True


@dataclass(frozen=True)
class DMMConfig:
    """Complete DMM configuration."""

    version: str = "1.0"
    daemon: DaemonConfig = field(default_factory=DaemonConfig)
    indexer: IndexerConfig = field(default_factory=IndexerConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create config from dictionary."""
        return cls(
            version=data.get("version", "1.0"),
            daemon=DaemonConfig(**data.get("daemon", {})),
            indexer=IndexerConfig(**data.get("indexer", {})),
            retrieval=RetrievalConfig(**data.get("retrieval", {})),
            storage=StorageConfig(**data.get("storage", {})),
            validation=ValidationConfig(**data.get("validation", {})),
        )

    @classmethod
    def load(cls, base_path: Path | None = None) -> Self:
        """Load configuration from file or use defaults."""
        config_path = get_dmm_root(base_path) / "daemon.config.json"

        if not config_path.exists():
            return cls()

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except json.JSONDecodeError as e:
            raise ConfigurationError(
                f"Invalid JSON in config file: {e}",
                details={"path": str(config_path)},
            ) from e
        except (TypeError, ValueError) as e:
            raise ConfigurationError(
                f"Invalid configuration values: {e}",
                details={"path": str(config_path)},
            ) from e

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "version": self.version,
            "daemon": {
                "host": self.daemon.host,
                "port": self.daemon.port,
                "auto_start": self.daemon.auto_start,
                "graceful_shutdown_timeout_ms": self.daemon.graceful_shutdown_timeout_ms,
                "log_level": self.daemon.log_level,
            },
            "indexer": {
                "watch_interval_ms": self.indexer.watch_interval_ms,
                "debounce_ms": self.indexer.debounce_ms,
                "embedding_model": self.indexer.embedding_model,
                "batch_size": self.indexer.batch_size,
            },
            "retrieval": {
                "top_k_directories": self.retrieval.top_k_directories,
                "max_candidates": self.retrieval.max_candidates,
                "diversity_threshold": self.retrieval.diversity_threshold,
                "default_budget": self.retrieval.default_budget,
                "baseline_budget": self.retrieval.baseline_budget,
            },
            "storage": {
                "embeddings_db": self.storage.embeddings_db,
                "stats_db": self.storage.stats_db,
            },
            "validation": {
                "min_tokens": self.validation.min_tokens,
                "max_tokens": self.validation.max_tokens,
                "warn_on_missing_optional": self.validation.warn_on_missing_optional,
            },
        }

    def save(self, base_path: Path | None = None) -> None:
        """Save configuration to file."""
        config_path = get_dmm_root(base_path) / "daemon.config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
