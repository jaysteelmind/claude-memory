"""Pytest configuration and fixtures for DMM tests."""

import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Generator

import pytest

from dmm.core.config import DMMConfig
from dmm.core.constants import Confidence, Scope, Status
from dmm.indexer.parser import MemoryParser, TokenCounter
from dmm.indexer.store import MemoryStore
from dmm.models.memory import MemoryFile


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests."""
    tmp = Path(tempfile.mkdtemp())
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def dmm_root(temp_dir: Path) -> Path:
    """Create a .dmm directory structure."""
    dmm = temp_dir / ".dmm"
    (dmm / "index").mkdir(parents=True)
    (dmm / "memory" / "baseline").mkdir(parents=True)
    (dmm / "memory" / "global").mkdir(parents=True)
    (dmm / "memory" / "agent").mkdir(parents=True)
    (dmm / "memory" / "project").mkdir(parents=True)
    (dmm / "memory" / "ephemeral").mkdir(parents=True)
    (dmm / "memory" / "deprecated").mkdir(parents=True)
    (dmm / "packs").mkdir(parents=True)
    return dmm


@pytest.fixture
def memory_root(dmm_root: Path) -> Path:
    """Get memory root path."""
    return dmm_root / "memory"


@pytest.fixture
def config() -> DMMConfig:
    """Create default configuration."""
    return DMMConfig()


@pytest.fixture
def token_counter() -> TokenCounter:
    """Create token counter instance."""
    return TokenCounter()


@pytest.fixture
def parser(token_counter: TokenCounter) -> MemoryParser:
    """Create parser instance."""
    return MemoryParser(token_counter=token_counter)


@pytest.fixture
def store(dmm_root: Path) -> Generator[MemoryStore, None, None]:
    """Create and initialize memory store."""
    db_path = dmm_root / "index" / "embeddings.db"
    store = MemoryStore(db_path)
    store.initialize()
    yield store
    store.close()


@pytest.fixture
def sample_memory_content() -> str:
    """Sample memory file content."""
    return """---
id: mem_2025_01_15_001
tags: [testing, sample, fixtures]
scope: project
priority: 0.8
confidence: active
status: active
created: 2025-01-15
---

# Sample Memory for Testing

This is a sample memory file used for testing the DMM system.
It contains enough content to meet the minimum token requirements
while demonstrating the expected structure and format.

## Purpose

This memory serves as a test fixture to validate:
- Frontmatter parsing
- Content extraction
- Token counting
- Embedding generation

## Additional Context

The memory system requires files to be self-contained and focused
on a single concept. This sample demonstrates that pattern by
focusing solely on testing requirements.
"""


@pytest.fixture
def sample_memory_file(memory_root: Path, sample_memory_content: str) -> Path:
    """Create a sample memory file."""
    file_path = memory_root / "project" / "sample_test.md"
    file_path.write_text(sample_memory_content)
    return file_path


@pytest.fixture
def sample_baseline_content() -> str:
    """Sample baseline memory content."""
    return """---
id: mem_2025_01_01_001
tags: [identity, core]
scope: baseline
priority: 1.0
confidence: stable
status: active
created: 2025-01-01
---

# Test Identity

This is a baseline identity memory for testing purposes.
It establishes the core identity and role for test scenarios.

## Role Definition

The test agent is responsible for validating the DMM system
components and ensuring correct behavior across all operations.
"""


@pytest.fixture
def sample_baseline_file(memory_root: Path, sample_baseline_content: str) -> Path:
    """Create a sample baseline file."""
    file_path = memory_root / "baseline" / "identity.md"
    file_path.write_text(sample_baseline_content)
    return file_path


@pytest.fixture
def sample_memory() -> MemoryFile:
    """Create a sample MemoryFile object."""
    return MemoryFile(
        id="mem_2025_01_15_001",
        path="project/sample_test.md",
        title="Sample Memory for Testing",
        body="This is a sample memory file used for testing.",
        token_count=150,
        tags=["testing", "sample"],
        scope=Scope.PROJECT,
        priority=0.8,
        confidence=Confidence.ACTIVE,
        status=Status.ACTIVE,
        created=datetime(2025, 1, 15),
    )


@pytest.fixture
def invalid_memory_content_missing_fields() -> str:
    """Memory content with missing required fields."""
    return """---
id: mem_2025_01_15_002
tags: [invalid]
---

# Invalid Memory

This memory is missing required frontmatter fields.
"""


@pytest.fixture
def invalid_memory_content_bad_values() -> str:
    """Memory content with invalid field values."""
    return """---
id: mem_2025_01_15_003
tags: [invalid]
scope: not_a_valid_scope
priority: 2.5
confidence: active
status: active
---

# Invalid Memory

This memory has invalid field values.
"""


def create_memory_file(
    memory_root: Path,
    scope: str,
    filename: str,
    memory_id: str,
    title: str,
    content: str,
    tags: list[str] | None = None,
    priority: float = 0.5,
    confidence: str = "active",
) -> Path:
    """Helper to create memory files for testing."""
    tags = tags or ["test"]
    tags_str = ", ".join(tags)

    file_content = f"""---
id: {memory_id}
tags: [{tags_str}]
scope: {scope}
priority: {priority}
confidence: {confidence}
status: active
created: 2025-01-15
---

# {title}

{content}
"""
    file_path = memory_root / scope / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(file_content)
    return file_path
