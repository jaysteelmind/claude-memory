"""Integration tests for Claude Code integration.

Tests verify that all required files exist and contain the expected content
for Claude Code to properly discover and utilize the DMM system.
"""

import subprocess
from pathlib import Path

import pytest


class TestClaudeIntegrationFiles:
    """Test Claude Code integration file presence and content."""

    @pytest.fixture
    def project_root(self) -> Path:
        """Get project root directory."""
        return Path(__file__).parent.parent.parent

    @pytest.fixture
    def dmm_root(self, project_root: Path) -> Path:
        """Get .dmm directory."""
        return project_root / ".dmm"

    def test_claude_md_exists(self, project_root: Path) -> None:
        """CLAUDE.md should exist in project root."""
        claude_md = project_root / "CLAUDE.md"
        assert claude_md.exists(), "CLAUDE.md not found in project root"

    def test_claude_md_has_quick_start(self, project_root: Path) -> None:
        """CLAUDE.md should have Quick Start section."""
        claude_md = project_root / "CLAUDE.md"
        content = claude_md.read_text()
        assert "## Quick Start" in content, "Missing Quick Start section"
        assert "dmm daemon status" in content, "Missing daemon status command"
        assert "dmm daemon start" in content, "Missing daemon start command"
        assert "dmm query" in content, "Missing query command"

    def test_claude_md_has_all_commands(self, project_root: Path) -> None:
        """CLAUDE.md should document all command categories."""
        claude_md = project_root / "CLAUDE.md"
        content = claude_md.read_text()

        required_commands = [
            "dmm query",
            "dmm write",
            "dmm review",
            "dmm conflicts",
            "dmm daemon",
            "dmm status",
        ]

        for cmd in required_commands:
            assert cmd in content, f"Missing command documentation: {cmd}"

    def test_claude_md_references_boot(self, project_root: Path) -> None:
        """CLAUDE.md should reference .dmm/BOOT.md."""
        claude_md = project_root / "CLAUDE.md"
        content = claude_md.read_text()
        assert "BOOT.md" in content, "Missing reference to BOOT.md"
        assert "policy.md" in content, "Missing reference to policy.md"

    def test_claude_md_has_troubleshooting(self, project_root: Path) -> None:
        """CLAUDE.md should have troubleshooting section."""
        claude_md = project_root / "CLAUDE.md"
        content = claude_md.read_text()
        assert "## Troubleshooting" in content, "Missing Troubleshooting section"

    def test_claude_md_line_count(self, project_root: Path) -> None:
        """CLAUDE.md should be within expected line count range."""
        claude_md = project_root / "CLAUDE.md"
        line_count = len(claude_md.read_text().splitlines())
        assert 200 <= line_count <= 400, f"CLAUDE.md has {line_count} lines, expected 200-300"

    def test_boot_md_exists(self, dmm_root: Path) -> None:
        """BOOT.md should exist in .dmm directory."""
        boot_md = dmm_root / "BOOT.md"
        assert boot_md.exists(), ".dmm/BOOT.md not found"

    def test_boot_md_updated_no_phase1(self, dmm_root: Path) -> None:
        """BOOT.md should not have Phase 1 limitations content."""
        boot_md = dmm_root / "BOOT.md"
        content = boot_md.read_text()

        # Should NOT have Phase 1 limitations
        assert "Phase 1 Limitations" not in content, "BOOT.md still has Phase 1 Limitations"
        assert "Current Limitations (Phase 1)" not in content, "BOOT.md still has Phase 1 content"

    def test_boot_md_has_write_section(self, dmm_root: Path) -> None:
        """BOOT.md should document memory writing."""
        boot_md = dmm_root / "BOOT.md"
        content = boot_md.read_text()

        assert "## Memory Writing" in content, "Missing Memory Writing section"
        assert "dmm write propose" in content, "Missing write propose command"
        assert "dmm write update" in content, "Missing write update command"
        assert "dmm write deprecate" in content, "Missing write deprecate command"

    def test_boot_md_has_review_section(self, dmm_root: Path) -> None:
        """BOOT.md should document review process."""
        boot_md = dmm_root / "BOOT.md"
        content = boot_md.read_text()

        assert "## Review Process" in content, "Missing Review Process section"
        assert "dmm review list" in content, "Missing review list command"
        assert "dmm review approve" in content, "Missing review approve command"

    def test_boot_md_has_conflict_section(self, dmm_root: Path) -> None:
        """BOOT.md should document conflict handling."""
        boot_md = dmm_root / "BOOT.md"
        content = boot_md.read_text()

        assert "## Conflict Awareness" in content, "Missing Conflict Awareness section"
        assert "dmm conflicts resolve" in content, "Missing conflicts resolve command"
        assert "dmm conflicts list" in content, "Missing conflicts list command"
        assert "dmm conflicts scan" in content, "Missing conflicts scan command"

    def test_boot_md_has_usage_section(self, dmm_root: Path) -> None:
        """BOOT.md should document usage tracking."""
        boot_md = dmm_root / "BOOT.md"
        content = boot_md.read_text()

        assert "## Usage Tracking" in content, "Missing Usage Tracking section"
        assert "dmm usage stats" in content, "Missing usage stats command"

    def test_boot_md_has_command_reference(self, dmm_root: Path) -> None:
        """BOOT.md should have system commands reference table."""
        boot_md = dmm_root / "BOOT.md"
        content = boot_md.read_text()

        assert "## System Commands Reference" in content, "Missing System Commands Reference"

    def test_boot_md_line_count(self, dmm_root: Path) -> None:
        """BOOT.md should be within expected line count range."""
        boot_md = dmm_root / "BOOT.md"
        line_count = len(boot_md.read_text().splitlines())
        assert 300 <= line_count <= 400, f"BOOT.md has {line_count} lines, expected 300-400"

    def test_policy_md_exists(self, dmm_root: Path) -> None:
        """policy.md should exist in .dmm directory."""
        policy_md = dmm_root / "policy.md"
        assert policy_md.exists(), ".dmm/policy.md not found"

    def test_wrapper_script_exists(self, project_root: Path) -> None:
        """Wrapper script should exist."""
        wrapper = project_root / "bin" / "claude-code-dmm"
        assert wrapper.exists(), "Wrapper script not found at bin/claude-code-dmm"

    def test_wrapper_script_executable(self, project_root: Path) -> None:
        """Wrapper script should be executable."""
        wrapper = project_root / "bin" / "claude-code-dmm"
        if wrapper.exists():
            assert wrapper.stat().st_mode & 0o111, "Wrapper script is not executable"

    def test_wrapper_documented_in_claude_md(self, project_root: Path) -> None:
        """CLAUDE.md should document the wrapper script."""
        claude_md = project_root / "CLAUDE.md"
        content = claude_md.read_text()
        assert "claude-code-dmm" in content, "Wrapper script not documented in CLAUDE.md"

    def test_memory_directory_exists(self, dmm_root: Path) -> None:
        """Memory directory should exist."""
        memory_dir = dmm_root / "memory"
        assert memory_dir.exists(), ".dmm/memory/ directory not found"
        assert memory_dir.is_dir(), ".dmm/memory/ is not a directory"


class TestClaudeCLICommand:
    """Test the dmm claude CLI command."""

    @pytest.fixture
    def project_root(self) -> Path:
        """Get project root directory."""
        return Path(__file__).parent.parent.parent

    def test_claude_check_command_exists(self, project_root: Path) -> None:
        """The dmm claude check command should exist."""
        result = subprocess.run(
            ["poetry", "run", "dmm", "claude", "--help"],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"dmm claude --help failed: {result.stderr}"
        assert "integration" in result.stdout.lower(), "Missing integration help text"

    def test_claude_check_runs(self, project_root: Path) -> None:
        """The dmm claude check command should run without error."""
        result = subprocess.run(
            ["poetry", "run", "dmm", "claude", "check"],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        # Command may return 1 if daemon not running, but should not crash
        assert result.returncode in (0, 1), f"dmm claude check crashed: {result.stderr}"
        assert "Integration" in result.stdout or "CLAUDE.md" in result.stdout, \
            f"Unexpected output: {result.stdout}"

    def test_claude_check_json_output(self, project_root: Path) -> None:
        """The dmm claude check --json should output valid JSON."""
        import json

        result = subprocess.run(
            ["poetry", "run", "dmm", "claude", "check", "--json"],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        # Command may return 1 if daemon not running
        assert result.returncode in (0, 1), f"dmm claude check --json crashed: {result.stderr}"

        try:
            data = json.loads(result.stdout)
            assert "ready" in data, "JSON output missing 'ready' field"
            assert "components" in data, "JSON output missing 'components' field"
        except json.JSONDecodeError as e:
            pytest.fail(f"Invalid JSON output: {e}\nOutput: {result.stdout}")


class TestReadmeIntegration:
    """Test README.md has proper documentation."""

    @pytest.fixture
    def project_root(self) -> Path:
        """Get project root directory."""
        return Path(__file__).parent.parent.parent

    def test_readme_has_quick_start(self, project_root: Path) -> None:
        """README.md should have Quick Start section."""
        readme = project_root / "README.md"
        content = readme.read_text()
        assert "## Quick Start" in content, "Missing Quick Start section"

    def test_readme_has_claude_code_instructions(self, project_root: Path) -> None:
        """README.md should document Claude Code setup."""
        readme = project_root / "README.md"
        content = readme.read_text()
        assert "Claude Code" in content, "Missing Claude Code reference"
        assert "start.md" in content, "Missing start.md reference"

    def test_readme_has_installation(self, project_root: Path) -> None:
        """README.md should document installation."""
        readme = project_root / "README.md"
        content = readme.read_text()
        assert "## Installation" in content, "Missing Installation section"
        assert "git clone" in content, "Missing git clone instruction"

    def test_readme_has_usage(self, project_root: Path) -> None:
        """README.md should document basic usage."""
        readme = project_root / "README.md"
        content = readme.read_text()
        assert "dmm bootstrap" in content, "Missing dmm bootstrap documentation"
        assert "dmm status" in content, "Missing dmm status documentation"
