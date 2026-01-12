# DMM Policy

## Memory Retrieval Policy

### Retrieval Triggers
Retrieve a Memory Pack when:
1. Starting a new task (if baseline is insufficient)
2. Switching to a different domain or subsystem
3. Encountering unexpected behavior or failures
4. Before producing final deliverables

### Retrieval Guidelines
- Query with clear, specific descriptions of your task
- Include relevant technical terms in your query
- Request larger budgets for complex, multi-domain tasks
- Request smaller budgets for focused, single-domain tasks

## Token Budget Guidelines

| Task Type | Recommended Budget |
|-----------|-------------------|
| Quick question | 1000 |
| Standard task | 1500 |
| Complex task | 2000 |
| Multi-domain | 2500 |

Baseline always uses 800 tokens (reserved).

## Scope Meanings

| Scope | Meaning | Retrieval Behavior |
|-------|---------|-------------------|
| baseline | Critical, always-relevant | Always included |
| global | Stable, cross-project truths | Retrieved when relevant |
| agent | Behavioral rules for the agent | Retrieved when relevant |
| project | Project-specific context | Retrieved when relevant |
| ephemeral | Temporary findings | Retrieved when relevant; may expire |
| deprecated | Outdated memories | Never retrieved (archived) |

## Memory File Requirements

Each memory file must:
- Be 300-800 tokens in length
- Contain exactly ONE concept
- Include valid YAML frontmatter
- Have a clear H1 title

### Required Frontmatter Fields
- id: Unique identifier (mem_YYYY_MM_DD_NNN)
- tags: List of semantic tags
- scope: One of baseline, global, agent, project, ephemeral
- priority: Float between 0.0 and 1.0
- confidence: One of experimental, active, stable, deprecated
- status: One of active, deprecated

## Phase 1 Limitations

Write operations are not available in Phase 1. If you need to record
new information, instruct the user to:

1. Create a new file in .dmm/memory/{appropriate_scope}/
2. Use the required frontmatter schema
3. Keep content between 300-800 tokens
4. One concept per file
