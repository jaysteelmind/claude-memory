"""Tests for the memory file parser."""

from pathlib import Path

import pytest

from dmm.core.constants import Confidence, Scope, Status
from dmm.indexer.parser import MemoryParser, TokenCounter, ValidationWarning


class TestTokenCounter:
    """Tests for TokenCounter."""

    def test_count_empty_string(self, token_counter: TokenCounter) -> None:
        """Empty string should have zero tokens."""
        assert token_counter.count("") == 0

    def test_count_simple_text(self, token_counter: TokenCounter) -> None:
        """Simple text should have expected token count."""
        text = "Hello, world!"
        count = token_counter.count(text)
        assert count > 0
        assert count < 10

    def test_count_longer_text(self, token_counter: TokenCounter) -> None:
        """Longer text should have proportionally more tokens."""
        short = "Hello"
        long = "Hello " * 100
        short_count = token_counter.count(short)
        long_count = token_counter.count(long)
        assert long_count > short_count

    def test_count_with_overhead(self, token_counter: TokenCounter) -> None:
        """Count with overhead should add extra tokens."""
        text = "Hello, world!"
        base_count = token_counter.count(text)
        overhead_count = token_counter.count_with_overhead(text, overhead=10)
        assert overhead_count == base_count + 10


class TestMemoryParser:
    """Tests for MemoryParser."""

    def test_parse_valid_file(
        self, parser: MemoryParser, sample_memory_file: Path
    ) -> None:
        """Valid memory file should parse successfully."""
        result = parser.parse(sample_memory_file)

        assert result.success
        assert result.error is None
        assert result.memory is not None
        assert result.memory.id == "mem_2025_01_15_001"
        assert result.memory.scope == Scope.PROJECT
        assert result.memory.priority == 0.8
        assert result.memory.confidence == Confidence.ACTIVE
        assert result.memory.status == Status.ACTIVE
        assert "testing" in result.memory.tags
        assert result.memory.token_count > 0

    def test_parse_extracts_title(
        self, parser: MemoryParser, sample_memory_file: Path
    ) -> None:
        """Parser should extract H1 title from content."""
        result = parser.parse(sample_memory_file)

        assert result.success
        assert result.memory is not None
        assert result.memory.title == "Sample Memory for Testing"

    def test_parse_baseline_file(
        self, parser: MemoryParser, sample_baseline_file: Path
    ) -> None:
        """Baseline memory file should parse with correct scope."""
        result = parser.parse(sample_baseline_file)

        assert result.success
        assert result.memory is not None
        assert result.memory.scope == Scope.BASELINE
        assert result.memory.is_baseline

    def test_parse_missing_file(self, parser: MemoryParser, temp_dir: Path) -> None:
        """Missing file should return error."""
        result = parser.parse(temp_dir / "nonexistent.md")

        assert not result.success
        assert result.error is not None
        assert result.error.error_type == "io"

    def test_parse_missing_required_fields(
        self,
        parser: MemoryParser,
        memory_root: Path,
        invalid_memory_content_missing_fields: str,
    ) -> None:
        """Missing required fields should return schema error."""
        file_path = memory_root / "project" / "invalid.md"
        file_path.write_text(invalid_memory_content_missing_fields)

        result = parser.parse(file_path)

        assert not result.success
        assert result.error is not None
        assert "missing" in result.error.message.lower() or result.error.missing_fields

    def test_parse_invalid_field_values(
        self,
        parser: MemoryParser,
        memory_root: Path,
        invalid_memory_content_bad_values: str,
    ) -> None:
        """Invalid field values should return schema error."""
        file_path = memory_root / "project" / "invalid.md"
        file_path.write_text(invalid_memory_content_bad_values)

        result = parser.parse(file_path)

        assert not result.success
        assert result.error is not None

    def test_parse_warns_on_low_token_count(
        self, parser: MemoryParser, memory_root: Path
    ) -> None:
        """Low token count should generate warning."""
        content = """---
id: mem_2025_01_15_004
tags: [short]
scope: project
priority: 0.5
confidence: active
status: active
---

# Short Memory

Too short.
"""
        file_path = memory_root / "project" / "short.md"
        file_path.write_text(content)

        result = parser.parse(file_path)

        assert result.success
        assert any(w.warning_type == "low_token_count" for w in result.warnings)

    def test_parse_warns_on_missing_title(
        self, parser: MemoryParser, memory_root: Path
    ) -> None:
        """Missing H1 title should generate warning."""
        content = """---
id: mem_2025_01_15_005
tags: [notitle]
scope: project
priority: 0.5
confidence: active
status: active
---

No heading here, just regular text that goes on for a while to meet
the token requirements. This content lacks a proper H1 heading which
should trigger a warning during parsing. The system should still parse
successfully but note the missing title.

More content here to pad out the token count and ensure we meet the
minimum requirements for the file to be considered valid in terms of
length even though it is missing the title.
"""
        file_path = memory_root / "project" / "notitle.md"
        file_path.write_text(content)

        result = parser.parse(file_path)

        assert result.success
        assert any(w.warning_type == "missing_title" for w in result.warnings)

    def test_parse_extracts_directory(
        self, parser: MemoryParser, sample_memory_file: Path
    ) -> None:
        """Parser should extract directory from path."""
        result = parser.parse(sample_memory_file)

        assert result.success
        assert result.memory is not None
        assert result.memory.directory == "project"

    def test_validate_memory(
        self, parser: MemoryParser, sample_memory_file: Path
    ) -> None:
        """Validate should check memory constraints."""
        result = parser.parse(sample_memory_file)
        assert result.memory is not None

        warnings = parser.validate(result.memory)
        # Sample memory should be valid
        assert isinstance(warnings, list)

    def test_compute_file_hash(
        self, parser: MemoryParser, sample_memory_file: Path
    ) -> None:
        """File hash should be consistent."""
        hash1 = parser.compute_file_hash(sample_memory_file)
        hash2 = parser.compute_file_hash(sample_memory_file)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length

    def test_file_hash_changes_with_content(
        self, parser: MemoryParser, sample_memory_file: Path
    ) -> None:
        """File hash should change when content changes."""
        hash1 = parser.compute_file_hash(sample_memory_file)

        # Modify file
        content = sample_memory_file.read_text()
        sample_memory_file.write_text(content + "\nAdditional content.")

        hash2 = parser.compute_file_hash(sample_memory_file)

        assert hash1 != hash2

    def test_parse_with_optional_fields(
        self, parser: MemoryParser, memory_root: Path
    ) -> None:
        """Optional fields should be parsed when present."""
        content = """---
id: mem_2025_01_15_006
tags: [complete]
scope: project
priority: 0.7
confidence: stable
status: active
created: 2025-01-15
last_used: 2025-01-16
usage_count: 5
supersedes: [mem_2024_01_01_001]
related: [mem_2025_01_01_002]
---

# Complete Memory

This memory has all optional fields populated for testing purposes.
It includes creation date, last used date, usage count, and relations
to other memories. This helps verify that optional field parsing works
correctly throughout the system.

Additional content to meet token requirements and ensure the file is
considered valid by the parser validation logic.
"""
        file_path = memory_root / "project" / "complete.md"
        file_path.write_text(content)

        result = parser.parse(file_path)

        assert result.success
        assert result.memory is not None
        assert result.memory.created is not None
        assert result.memory.last_used is not None
        assert result.memory.usage_count == 5
        assert "mem_2024_01_01_001" in result.memory.supersedes
        assert "mem_2025_01_01_002" in result.memory.related
