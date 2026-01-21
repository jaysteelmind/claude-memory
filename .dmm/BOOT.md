# DMM Boot Instructions

You have access to a Dynamic Markdown Memory (DMM) system that provides
relevant context for your tasks, allows you to record new knowledge, and
helps manage contradictions in the memory store.

## What You Always Have

Every Memory Pack includes the **Baseline Pack** - critical context that applies
to all tasks. This is automatically included; you do not need to query for it.

Baseline contains:
- Your identity and role for this project
- Hard constraints that must never be violated
- Foundational decisions and terminology

## Memory Retrieval

When you need context beyond baseline, request a Memory Pack:
```bash
dmm query "<describe your task or question>" --budget 1500
```

This returns a compiled pack with:
- Baseline memories (always included)
- Retrieved memories (semantically relevant to your query)
- File paths for traceability
- Conflict warnings (if any retrieved memories have unresolved conflicts)

### When to Retrieve

Request a Memory Pack:
- **At task start** - if baseline does not cover your needs
- **When switching domains** - e.g., from auth to database work
- **After a failure** - you may be missing relevant context
- **Before final outputs** - ensure you have all constraints

### Retrieval Options
```bash
# Standard query
dmm query "implement user authentication" --budget 1500

# Larger budget for complex tasks
dmm query "refactor database layer" --budget 2500

# Filter by scope
dmm query "coding standards" --scope global

# Include ephemeral memories
dmm query "recent findings" --include-ephemeral
```

## Memory Writing

You can propose new memories or updates to existing ones. All proposals go through
a review process before being committed.

### Proposing New Memory
```bash
dmm write propose <scope>/<filename>.md --reason "explanation"
```

You will be prompted to enter the memory content, or provide it via `--file`:
```bash
dmm write propose project/decisions/caching_strategy.md \
  --file /tmp/memory_content.md \
  --reason "Document Redis caching decision"
```

### Memory Content Requirements

Each memory file must have:

1. **YAML frontmatter** with required fields:
   - `id`: Unique identifier (format: `mem_YYYY_MM_DD_NNN`)
   - `tags`: List of semantic tags (1-10 tags)
   - `scope`: One of `baseline`, `global`, `agent`, `project`, `ephemeral`
   - `priority`: Float between 0.0 and 1.0
   - `confidence`: One of `experimental`, `active`, `stable`
   - `status`: One of `active`, `deprecated`

2. **Markdown body** with:
   - Clear H1 title
   - 300-800 tokens of content
   - Single concept (atomic unit)
   - Self-contained (no undefined references)

### Example Memory Format
```markdown
---
id: mem_2025_01_20_001
tags: [caching, redis, performance]
scope: project
priority: 0.7
confidence: active
status: active
created: 2025-01-20
---

# Caching Strategy: Redis

We use Redis for application-level caching with a 15-minute default TTL.

## Rationale

- Reduces database load for frequently accessed data
- Sub-millisecond response times for cached queries
- Supports our horizontal scaling requirements

## Implementation

Cache keys follow the pattern: `{service}:{entity}:{id}`
Example: `api:user:12345`

## Invalidation

Cache is invalidated on:
- Direct entity updates
- Related entity changes (documented per-entity)
- Manual flush via admin endpoint
```

### Updating Existing Memory
```bash
dmm write update <memory_id> --reason "explanation"
```

### Deprecating Memory
```bash
dmm write deprecate <memory_id> --reason "explanation"
```

### Promoting/Demoting Scope
```bash
dmm write promote <memory_id> --new-scope global --reason "explanation"
```

## Review Process

All write proposals require review before commit:
```bash
# List pending proposals
dmm review list

# View proposal details
dmm review show <proposal_id>

# Approve a proposal
dmm review approve <proposal_id>

# Reject with feedback
dmm review reject <proposal_id> --reason "needs more rationale"

# Process next pending (interactive)
dmm review process
```

### Review Criteria

Proposals are validated for:
- **Schema correctness** (required fields, valid values)
- **Quality** (token count, single concept, clear title)
- **Duplicate detection** (rejects near-duplicates >92% similarity)
- **Coherence** (title matches content)

### Baseline Protection

Proposals targeting `baseline` scope are always deferred to human review.
This protects critical context from accidental modification.

## Conflict Awareness

The memory system automatically detects conflicts between memories.

### Checking for Conflicts
```bash
# List all unresolved conflicts
dmm conflicts list

# Check specific memories for conflicts
dmm conflicts check --memories "mem_id1,mem_id2"

# View conflict details
dmm conflicts show <conflict_id>
```

### When You Notice Conflicts

If you observe contradictory guidance in retrieved memories:

1. **Flag the conflict** (if not already detected):
```bash
   dmm conflicts flag --memories "mem_id1,mem_id2" \
     --description "Contradictory guidance on X"
```

2. **Continue with appropriate memory:**
   - Prefer more recent over older
   - Prefer higher scope (global > project > ephemeral)
   - Prefer higher priority value
   - Prefer stable > active > experimental confidence

3. **Note in your response** that a conflict exists

### Resolving Conflicts

If you can determine the correct resolution:
```bash
# Deprecate the incorrect memory
dmm conflicts resolve <conflict_id> \
  --action deprecate \
  --target <wrong_memory_id> \
  --reason "Superseded by newer decision"

# Merge into single authoritative memory
dmm conflicts resolve <conflict_id> \
  --action merge \
  --reason "Combined both perspectives"

# Add clarifying context to both
dmm conflicts resolve <conflict_id> \
  --action clarify \
  --reason "Added scope conditions"

# Dismiss as false positive
dmm conflicts resolve <conflict_id> \
  --action dismiss \
  --reason "Different contexts, not actually conflicting"
```

### Running Conflict Scans
```bash
# Full scan of all memories
dmm conflicts scan --full

# Incremental scan (new memories only)
dmm conflicts scan

# View scan statistics
dmm conflicts stats
```

## Usage Tracking

The system tracks which memories are retrieved and how often:
```bash
# View usage statistics
dmm usage stats

# See most-used memories
dmm usage top --limit 10

# See least-used memories
dmm usage bottom --limit 10

# Usage for specific memory
dmm usage show <memory_id>
```

This data helps identify:
- Stale memories (never retrieved)
- High-value memories (frequently retrieved)
- Candidates for promotion or deprecation

## Best Practices

### Do

- Query before making assumptions about project context
- Write memories for decisions that have rationale worth preserving
- Flag conflicts immediately when noticed
- Include "why" not just "what" in memory content
- Use appropriate scope (most memories should be `project`)
- Keep memories atomic (one concept per file)

### Do Not

- Assume memories exist without querying
- Query for information already in your baseline
- Ignore constraints from retrieved memories
- Silently choose between conflicting memories
- Write transient information (chat context, logs)
- Create memories over 800 tokens (split instead)

## System Commands Reference

| Command | Purpose |
|---------|---------|
| `dmm query "<task>"` | Retrieve relevant memory pack |
| `dmm write propose` | Propose new memory |
| `dmm write update` | Propose memory update |
| `dmm write deprecate` | Propose deprecation |
| `dmm review list` | List pending proposals |
| `dmm review process` | Process next proposal |
| `dmm conflicts list` | List detected conflicts |
| `dmm conflicts resolve` | Resolve a conflict |
| `dmm conflicts scan` | Run conflict detection |
| `dmm usage stats` | View usage statistics |
| `dmm status` | System status |
| `dmm validate` | Validate memory files |
| `dmm reindex` | Reindex all memories |
| `dmm daemon start` | Start the daemon |
| `dmm daemon stop` | Stop the daemon |
| `dmm daemon status` | Check daemon status |
