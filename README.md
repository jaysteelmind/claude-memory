# DMM - Dynamic Markdown Memory

A file-native cognitive memory system for AI agents that replaces monolithic instruction files with a semantic, hierarchical collection of atomic markdown micro-files.

## Features

- **Semantic Retrieval**: Two-stage retrieval using composite embeddings
- **Token Budgeting**: Respects context window limits with configurable budgets
- **Baseline Guarantee**: Critical context always included in every query
- **File-Native**: All memories stored as auditable markdown files with Git support
- **Hot Reloading**: File watcher automatically indexes changes

## Quick Start

### Installation
```bash
# Clone the repository
git clone https://github.com/your-org/claude-memory.git
cd claude-memory

# Install with Poetry
poetry install

# Verify installation
poetry run dmm --help
```

### Initialize a Project
```bash
# Initialize DMM in your project directory
cd /path/to/your/project
dmm init

# This creates:
# .dmm/
#   BOOT.md              - Agent boot instructions
#   policy.md            - Memory policies
#   daemon.config.json   - Configuration
#   memory/
#     baseline/          - Always-included memories
#     global/            - Cross-project knowledge
#     agent/             - Agent behavior rules
#     project/           - Project-specific context
#     ephemeral/         - Temporary findings
```

### Start the Daemon
```bash
# Start in background
dmm daemon start

# Or run in foreground for debugging
dmm daemon start --foreground

# Check status
dmm daemon status
```

### Query for Context
```bash
# Basic query
dmm query "implement user authentication"

# With custom budget
dmm query "debug database connection" --budget 1500

# Filter by scope
dmm query "API design" --scope project

# Save to file
dmm query "system architecture" --output context.md
```

### Validate Memory Files
```bash
# Validate all memory files
dmm validate

# Validate specific file
dmm validate --path .dmm/memory/project/my_memory.md
```

## Memory File Format

Each memory file is a Markdown document with YAML frontmatter:
```markdown
---
id: mem_2025_01_15_001
tags: [authentication, security, api]
scope: project
priority: 0.8
confidence: active
status: active
created: 2025-01-15
---

# Authentication Strategy

We use JWT tokens for API authentication with a 1-hour expiry.
Refresh tokens are stored in httpOnly cookies.

## Implementation Details

- Tokens signed with RS256 algorithm
- Public key available at /.well-known/jwks.json
- Token refresh happens automatically on 401 responses
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| id | string | Unique identifier (format: `mem_YYYY_MM_DD_NNN`) |
| tags | list | Semantic tags for retrieval |
| scope | enum | One of: baseline, global, agent, project, ephemeral |
| priority | float | 0.0 to 1.0, influences ranking |
| confidence | enum | One of: experimental, active, stable, deprecated |
| status | enum | One of: active, deprecated |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| created | date | Creation date |
| last_used | date | Last retrieval date |
| usage_count | int | Times retrieved |
| supersedes | list | IDs of replaced memories |
| related | list | IDs of related memories |
| expires | date | Auto-deprecation date (for ephemeral) |

## Scopes

| Scope | Description | Retrieval Behavior |
|-------|-------------|-------------------|
| baseline | Critical, always-relevant context | Always included |
| global | Stable, cross-project truths | Retrieved when relevant |
| agent | Behavioral rules for the agent | Retrieved when relevant |
| project | Project-specific decisions | Retrieved when relevant |
| ephemeral | Temporary findings | Auto-expires; retrieved when relevant |

## Configuration

Edit `.dmm/daemon.config.json`:
```json
{
  "daemon": {
    "host": "127.0.0.1",
    "port": 7433
  },
  "retrieval": {
    "default_budget": 2000,
    "baseline_budget": 800,
    "top_k_directories": 3,
    "max_candidates": 50
  },
  "validation": {
    "min_tokens": 300,
    "max_tokens": 800
  }
}
```

## Claude Code Integration

Use the wrapper script to automatically start/stop the daemon:
```bash
# Add to your PATH
export PATH="/path/to/claude-memory/bin:$PATH"

# Run Claude Code with DMM
claude-code-dmm
```

## Development
```bash
# Run tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=dmm

# Type checking
poetry run mypy src/

# Linting
poetry run ruff check src/
```

## Architecture
```
DMM Core System
+------------------+     +------------------+     +------------------+
|   File Watcher   | --> |     Indexer      | --> |  Embedding Store |
|                  |     |                  |     |    (SQLite)      |
+------------------+     +------------------+     +------------------+
                                                          |
                                                          v
+------------------+     +------------------+     +------------------+
|  Baseline Pack   | --> | Retrieval Router | --> | Context Assembler|
|     Cache        |     | (2-stage search) |     |                  |
+------------------+     +------------------+     +------------------+
                                                          |
                                                          v
+------------------+     +------------------+     +------------------+
| Daemon Manager   | <-> |    HTTP API      | <-> |  CLI Interface   |
|                  |     |   (FastAPI)      |     |    (Typer)       |
+------------------+     +------------------+     +------------------+
```

## License

MIT License - See LICENSE file for details.
