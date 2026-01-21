#!/bin/bash
# test_claude_integration.sh
# Verifies Claude Code integration is properly configured
#
# Usage: ./tests/test_claude_integration.sh
# Returns: 0 if all tests pass, 1 otherwise

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

echo "=== DMM Claude Code Integration Test ==="
echo "Project root: ${PROJECT_ROOT}"
echo ""

# Test function
run_test() {
    local test_name="$1"
    local test_cmd="$2"
    TESTS_RUN=$((TESTS_RUN + 1))
    
    echo -n "[${TESTS_RUN}] ${test_name}... "
    
    if eval "${test_cmd}" > /dev/null 2>&1; then
        echo -e "${GREEN}PASS${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        echo -e "${RED}FAIL${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

# Test with expected failure
run_test_expect_content() {
    local test_name="$1"
    local file="$2"
    local pattern="$3"
    TESTS_RUN=$((TESTS_RUN + 1))
    
    echo -n "[${TESTS_RUN}] ${test_name}... "
    
    if [ -f "${file}" ] && grep -q "${pattern}" "${file}"; then
        echo -e "${GREEN}PASS${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        echo -e "${RED}FAIL${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

# Test for absence of content
run_test_expect_no_content() {
    local test_name="$1"
    local file="$2"
    local pattern="$3"
    TESTS_RUN=$((TESTS_RUN + 1))
    
    echo -n "[${TESTS_RUN}] ${test_name}... "
    
    if [ -f "${file}" ] && ! grep -q "${pattern}" "${file}"; then
        echo -e "${GREEN}PASS${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        echo -e "${RED}FAIL${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

echo "--- File Existence Tests ---"

# Test 1: CLAUDE.md exists
run_test "CLAUDE.md exists" "[ -f CLAUDE.md ]"

# Test 2: BOOT.md exists
run_test ".dmm/BOOT.md exists" "[ -f .dmm/BOOT.md ]"

# Test 3: policy.md exists
run_test ".dmm/policy.md exists" "[ -f .dmm/policy.md ]"

# Test 4: Memory directory exists
run_test ".dmm/memory/ directory exists" "[ -d .dmm/memory ]"

# Test 5: Wrapper script exists
run_test "bin/claude-code-dmm exists" "[ -f bin/claude-code-dmm ]"

# Test 6: CLI module exists
run_test "src/dmm/cli/claude.py exists" "[ -f src/dmm/cli/claude.py ]"

echo ""
echo "--- CLAUDE.md Content Tests ---"

# Test 7: CLAUDE.md has Quick Start
run_test_expect_content "CLAUDE.md has Quick Start section" "CLAUDE.md" "## Quick Start"

# Test 8: CLAUDE.md has Essential Commands
run_test_expect_content "CLAUDE.md has Essential Commands" "CLAUDE.md" "## Essential Commands"

# Test 9: CLAUDE.md has dmm query
run_test_expect_content "CLAUDE.md documents dmm query" "CLAUDE.md" "dmm query"

# Test 10: CLAUDE.md has dmm write
run_test_expect_content "CLAUDE.md documents dmm write" "CLAUDE.md" "dmm write"

# Test 11: CLAUDE.md has dmm conflicts
run_test_expect_content "CLAUDE.md documents dmm conflicts" "CLAUDE.md" "dmm conflicts"

# Test 12: CLAUDE.md references BOOT.md
run_test_expect_content "CLAUDE.md references BOOT.md" "CLAUDE.md" "BOOT.md"

# Test 13: CLAUDE.md has Troubleshooting
run_test_expect_content "CLAUDE.md has Troubleshooting" "CLAUDE.md" "## Troubleshooting"

# Test 14: CLAUDE.md documents wrapper
run_test_expect_content "CLAUDE.md documents wrapper script" "CLAUDE.md" "claude-code-dmm"

echo ""
echo "--- BOOT.md Content Tests ---"

# Test 15: BOOT.md has no Phase 1 Limitations
run_test_expect_no_content "BOOT.md has no Phase 1 Limitations" ".dmm/BOOT.md" "Phase 1 Limitations"

# Test 16: BOOT.md has no Current Limitations (Phase 1)
run_test_expect_no_content "BOOT.md has no Phase 1 content" ".dmm/BOOT.md" "Current Limitations (Phase 1)"

# Test 17: BOOT.md has Memory Writing section
run_test_expect_content "BOOT.md has Memory Writing section" ".dmm/BOOT.md" "## Memory Writing"

# Test 18: BOOT.md has Review Process section
run_test_expect_content "BOOT.md has Review Process section" ".dmm/BOOT.md" "## Review Process"

# Test 19: BOOT.md has Conflict Awareness section
run_test_expect_content "BOOT.md has Conflict Awareness section" ".dmm/BOOT.md" "## Conflict Awareness"

# Test 20: BOOT.md has Usage Tracking section
run_test_expect_content "BOOT.md has Usage Tracking section" ".dmm/BOOT.md" "## Usage Tracking"

# Test 21: BOOT.md has dmm conflicts resolve
run_test_expect_content "BOOT.md documents dmm conflicts resolve" ".dmm/BOOT.md" "dmm conflicts resolve"

# Test 22: BOOT.md has System Commands Reference
run_test_expect_content "BOOT.md has System Commands Reference" ".dmm/BOOT.md" "## System Commands Reference"

echo ""
echo "--- README.md Content Tests ---"

# Test 23: README has Claude Code Integration section
run_test_expect_content "README.md has Claude Code Integration" "README.md" "## Claude Code Integration"

# Test 24: README has Automatic Setup
run_test_expect_content "README.md has Automatic Setup" "README.md" "### Automatic Setup"

# Test 25: README has Manual Setup
run_test_expect_content "README.md has Manual Setup" "README.md" "### Manual Setup"

# Test 26: README has Verifying Integration
run_test_expect_content "README.md has Verifying Integration" "README.md" "### Verifying Integration"

# Test 27: README documents dmm claude check
run_test_expect_content "README.md documents dmm claude check" "README.md" "dmm claude check"

echo ""
echo "--- CLI Command Tests ---"

# Test 28: dmm claude --help works
TESTS_RUN=$((TESTS_RUN + 1))
echo -n "[${TESTS_RUN}] dmm claude --help works... "
if poetry run dmm claude --help > /dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${RED}FAIL${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Test 29: dmm claude check runs (may return 1 if daemon not running)
TESTS_RUN=$((TESTS_RUN + 1))
echo -n "[${TESTS_RUN}] dmm claude check runs... "
OUTPUT=$(poetry run dmm claude check 2>&1) || true
if echo "${OUTPUT}" | grep -q "Integration\|CLAUDE.md"; then
    echo -e "${GREEN}PASS${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${RED}FAIL${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Test 30: dmm claude check --json outputs valid JSON
TESTS_RUN=$((TESTS_RUN + 1))
echo -n "[${TESTS_RUN}] dmm claude check --json outputs JSON... "
JSON_OUTPUT=$(poetry run dmm claude check --json 2>&1) || true
if echo "${JSON_OUTPUT}" | python3 -c "import sys, json; json.load(sys.stdin)" 2>/dev/null; then
    echo -e "${GREEN}PASS${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${RED}FAIL${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

echo ""
echo "--- Line Count Tests ---"

# Test 31: CLAUDE.md line count (200-300)
TESTS_RUN=$((TESTS_RUN + 1))
echo -n "[${TESTS_RUN}] CLAUDE.md line count (200-300)... "
CLAUDE_LINES=$(wc -l < CLAUDE.md)
if [ "${CLAUDE_LINES}" -ge 200 ] && [ "${CLAUDE_LINES}" -le 300 ]; then
    echo -e "${GREEN}PASS${NC} (${CLAUDE_LINES} lines)"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${RED}FAIL${NC} (${CLAUDE_LINES} lines)"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Test 32: BOOT.md line count (300-400)
TESTS_RUN=$((TESTS_RUN + 1))
echo -n "[${TESTS_RUN}] BOOT.md line count (300-400)... "
BOOT_LINES=$(wc -l < .dmm/BOOT.md)
if [ "${BOOT_LINES}" -ge 300 ] && [ "${BOOT_LINES}" -le 400 ]; then
    echo -e "${GREEN}PASS${NC} (${BOOT_LINES} lines)"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${RED}FAIL${NC} (${BOOT_LINES} lines)"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

echo ""
echo "=========================================="
echo "Results: ${TESTS_PASSED}/${TESTS_RUN} tests passed"

if [ "${TESTS_FAILED}" -gt 0 ]; then
    echo -e "${RED}${TESTS_FAILED} tests failed${NC}"
    exit 1
else
    echo -e "${GREEN}All tests passed${NC}"
    exit 0
fi
