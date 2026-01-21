# Project Instructions for Claude

This project uses **DMM (Dynamic Markdown Memory)** - a file-native cognitive memory
system that provides relevant context for your tasks without loading everything
into the context window.

## Quick Start

### 1. Check if DMM daemon is running
```bash
dmm daemon status
```

### 2. Start the daemon if needed
```bash
dmm daemon start
```

### 3. Query for relevant context
```bash
dmm query "your task description" --budget 1500
```

## DMM Overview

DMM stores knowledge as atomic markdown files (300-800 tokens each) organized by scope:

| Scope | Purpose | Retrieval |
|-------|---------|-----------|
| baseline | Critical context (identity, constraints) | Always included |
| global | Cross-project standards | When relevant |
| agent | Your behavioral rules | When relevant |
| project | Project-specific decisions | When relevant |
| ephemeral | Temporary findings | When relevant, may expire |

## Essential Commands

### Memory Retrieval
```bash
# Basic query
dmm query "implement authentication"

# With custom token budget
dmm query "database schema design" --budget 2000

# Filter by scope
dmm query "API patterns" --scope project
```

### Memory Writing
```bash
# Propose new memory
dmm write propose project/decisions/api_versioning.md \
  --reason "Document API versioning strategy"

# Propose update to existing memory
dmm write update <memory_id> --reason "Update with new findings"

# Propose deprecation
dmm write deprecate <memory_id> --reason "Superseded by newer decision"

# Propose scope promotion
dmm write promote <memory_id> --new-scope global --reason "Applies globally"
```

### Review Process
```bash
# List pending proposals
dmm review list

# Show proposal details
dmm review show <proposal_id>

# Approve a proposal
dmm review approve <proposal_id>

# Reject with feedback
dmm review reject <proposal_id> --reason "Needs more rationale"

# Process next pending (interactive)
dmm review process
```

### Conflict Management
```bash
# List unresolved conflicts
dmm conflicts list

# Show conflict details
dmm conflicts show <conflict_id>

# Run conflict scan
dmm conflicts scan

# Resolve a conflict
dmm conflicts resolve <conflict_id> --action deprecate --target <memory_id>
```

### System Management
```bash
# Check system status
dmm status

# Reindex all memories
dmm reindex

# Validate memory files
dmm validate

# View usage statistics
dmm usage stats

# Check daemon status
dmm daemon status

# Start daemon
dmm daemon start

# Stop daemon
dmm daemon stop
```

## Operational Guidelines

For detailed operational rules, read:

- `.dmm/BOOT.md` - Complete instructions for memory operations
- `.dmm/policy.md` - Policies for retrieval, writing, and conflict handling

## When to Use DMM

### DO Query Memory When:

- Starting a new task (beyond baseline context)
- Switching to a different domain or subsystem
- Encountering unexpected behavior or failures
- Before producing final deliverables
- Unsure about project conventions or constraints

### DO Write Memory When:

- Making architectural decisions with rationale
- Discovering patterns that should be reused
- Establishing new constraints or conventions
- Finding information that will be needed again

### DO NOT:

- Assume memories exist without querying
- Query for information already in baseline
- Ignore constraints from retrieved memories
- Silently choose between conflicting memories (flag them instead)

## Token Budget Guidelines

| Task Type | Recommended Budget |
|-----------|-------------------|
| Quick question | 1000 |
| Standard task | 1500 |
| Complex task | 2000 |
| Multi-domain work | 2500 |

Baseline always uses ~800 tokens (reserved).

## Wrapper Script

For automatic daemon lifecycle management:
```bash
# Add to PATH
export PATH="/path/to/project/bin:$PATH"

# Run Claude Code with automatic DMM daemon management
claude-code-dmm
```

This wrapper:
1. Starts DMM daemon before Claude Code
2. Waits for health check
3. Stops daemon when Claude Code exits

## Troubleshooting

### Daemon won't start
```bash
# Check if port is in use
lsof -i :7433

# Check for stale PID file
cat /tmp/dmm.pid
rm /tmp/dmm.pid  # if stale

# Start with verbose output
dmm daemon start --foreground
```

### Query returns no results
```bash
# Verify memories are indexed
dmm status

# Force reindex
dmm reindex

# Check memory directory
ls -la .dmm/memory/
```

### Conflicts detected
```bash
# View conflict details
dmm conflicts show <conflict_id>

# See all unresolved
dmm conflicts list --status unresolved
```

## File Locations

| File | Purpose |
|------|---------|
| `.dmm/BOOT.md` | Detailed operational instructions |
| `.dmm/policy.md` | Memory policies and guidelines |
| `.dmm/daemon.config.json` | Daemon configuration |
| `.dmm/memory/` | Memory file storage |
| `.dmm/index/` | Embeddings and metadata databases |
