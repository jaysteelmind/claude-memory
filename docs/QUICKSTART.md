# Quick Start Guide

Get DMM up and running in 5 minutes.

## Prerequisites

- Python 3.11 or higher
- Poetry 1.7 or higher
- Git

## Installation

### 1. Clone the Repository
```bash
git clone https://github.com/anthropic/claude-memory.git
cd claude-memory
```

### 2. Install Dependencies
```bash
poetry install
```

### 3. Initialize DMM
```bash
poetry run dmm init
```

This creates the `.dmm/` directory structure:
```
.dmm/
├── BOOT.md              # Agent boot instructions
├── policy.md            # Write-back policies
├── memory/
│   ├── baseline/        # Always-loaded context
│   ├── global/          # Cross-project knowledge
│   ├── agent/           # Agent behavior rules
│   ├── project/         # Project-specific memories
│   └── ephemeral/       # Temporary findings
└── index/
    └── embeddings.db    # Vector database
```

## Basic Usage

### Start the Daemon
```bash
poetry run dmm daemon start
```

### Query Memories
```bash
# Simple query
poetry run dmm query "How do I handle errors?"

# With token budget
poetry run dmm query "authentication flow" --budget 2000

# Filter by scope
poetry run dmm query "coding standards" --scope project
```

### Create a Memory
```bash
# Create a new memory file
cat > .dmm/memory/project/error_handling.md << 'MEMORY'
---
id: mem_2026_01_25_001
tags: [errors, exceptions, handling]
scope: project
priority: 0.7
confidence: active
status: active
created: 2026-01-25
---

# Error Handling Guidelines

Always use specific exception types rather than bare except clauses.

## Best Practices

- Catch specific exceptions
- Log errors with context
- Re-raise when appropriate
MEMORY

# Reindex to pick up the new memory
poetry run dmm reindex
```

### Propose a Memory (AI-Reviewed)
```bash
poetry run dmm write propose \
  --path .dmm/memory/project/new_memory.md \
  --reason "Document caching strategy"
```

### Check for Conflicts
```bash
# Scan for conflicts
poetry run dmm conflicts scan

# List detected conflicts
poetry run dmm conflicts list
```

## Claude Code Integration

If using Claude Code, DMM integrates automatically:

### Automatic Setup

1. Open your project in Claude Code
2. DMM detects the `.dmm/` directory
3. Reads `CLAUDE.md` for instructions
4. Starts the daemon automatically

### Manual Setup
```bash
# Initialize if needed
poetry run dmm init

# Start daemon
poetry run dmm daemon start

# Verify integration
poetry run dmm claude check
```

## Common Commands

| Command | Description |
|---------|-------------|
| `dmm status` | Show system status |
| `dmm daemon start` | Start the daemon |
| `dmm daemon stop` | Stop the daemon |
| `dmm query "<text>"` | Query for relevant memories |
| `dmm reindex` | Reindex all memories |
| `dmm write propose` | Propose a new memory |
| `dmm review list` | List pending proposals |
| `dmm conflicts scan` | Scan for conflicts |
| `dmm graph status` | Show knowledge graph stats |

## Next Steps

- Read the [Architecture Overview](ARCHITECTURE.md)
- Follow the [Basic Memory Tutorial](tutorials/01-basic-memory.md)
- Explore the [API Reference](api/index.md)
- Check out the [Examples](../examples/README.md)

## Troubleshooting

### Daemon Won't Start
```bash
# Check if already running
poetry run dmm daemon status

# Force restart
poetry run dmm daemon restart

# Check logs
tail -f /tmp/dmm.log
```

### Query Returns No Results
```bash
# Verify memories exist
ls -la .dmm/memory/*/

# Check index status
poetry run dmm status

# Force reindex
poetry run dmm reindex --full
```

### Memory Not Being Retrieved

- Verify the memory file has valid YAML frontmatter
- Check that `status: active` (not deprecated)
- Ensure token count is 300-800 tokens
- Run `dmm validate` to check for errors

See [Troubleshooting Guide](TROUBLESHOOTING.md) for more solutions.
