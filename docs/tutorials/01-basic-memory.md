# Tutorial 1: Basic Memory Operations

Learn the fundamentals of creating, querying, and managing memories in DMM.

## Prerequisites

- DMM installed (`poetry install`)
- DMM initialized (`dmm init`)

## 1. Understanding Memory Structure

Memories are markdown files with YAML frontmatter:
```markdown
---
id: mem_2026_01_25_001
tags: [python, best-practices, errors]
scope: project
priority: 0.7
confidence: active
status: active
created: 2026-01-25
---

# Error Handling Best Practices

Always use specific exception types instead of bare except clauses.

## Guidelines

1. Catch specific exceptions
2. Log errors with context
3. Re-raise when appropriate
```

### Frontmatter Fields

| Field | Required | Description |
|-------|----------|-------------|
| id | Yes | Unique identifier (mem_YYYY_MM_DD_NNN) |
| tags | Yes | 1-10 semantic tags |
| scope | Yes | baseline, global, agent, project, ephemeral |
| priority | Yes | 0.0-1.0 retrieval priority |
| confidence | Yes | experimental, active, stable, deprecated |
| status | Yes | active, deprecated |
| created | No | Creation date |
| last_used | No | Last retrieval date |
| supersedes | No | IDs of replaced memories |
| related | No | IDs of related memories |
| expires | No | Expiration date |

## 2. Creating Memories

### Manual Creation

Create a memory file directly:
```bash
cat > .dmm/memory/project/authentication.md << 'MEMORY'
---
id: mem_2026_01_25_002
tags: [authentication, security, jwt]
scope: project
priority: 0.8
confidence: active
status: active
created: 2026-01-25
---

# Authentication Architecture

This project uses JWT tokens for authentication.

## Token Flow

1. User submits credentials
2. Server validates and issues JWT
3. Client stores token securely
4. Client includes token in Authorization header

## Security Notes

- Tokens expire after 1 hour
- Refresh tokens last 7 days
- Always use HTTPS
MEMORY
```

### Using the CLI

Propose a memory through the write-back system:
```bash
dmm write propose \
  --path .dmm/memory/project/caching.md \
  --reason "Document caching strategy"
```

This creates a proposal that goes through quality checks.

### Programmatic Creation
```python
from pathlib import Path
from datetime import datetime
from dmm.models.memory import MemoryFile
from dmm.core.constants import Scope, Confidence, Status
from dmm.indexer import MemoryIndexer

# Create memory object
memory = MemoryFile(
    id="mem_2026_01_25_003",
    path="project/database_config.md",
    title="Database Configuration",
    body="""# Database Configuration

Use PostgreSQL for production with connection pooling.

## Settings
- Pool size: 20
- Max overflow: 10
- Pool timeout: 30s
""",
    token_count=50,
    tags=["database", "configuration", "postgresql"],
    scope=Scope.PROJECT,
    priority=0.7,
    confidence=Confidence.ACTIVE,
    status=Status.ACTIVE,
    created=datetime.now(),
)

# Write to file
memory_root = Path(".dmm/memory")
file_path = memory_root / memory.path
file_path.parent.mkdir(parents=True, exist_ok=True)

# Format as markdown with frontmatter
content = f"""---
id: {memory.id}
tags: {memory.tags}
scope: {memory.scope.value}
priority: {memory.priority}
confidence: {memory.confidence.value}
status: {memory.status.value}
created: {memory.created.date().isoformat()}
---

{memory.body}
"""
file_path.write_text(content)
print(f"Created: {file_path}")
```

## 3. Indexing Memories

After creating memories, index them for retrieval:
```bash
# Index all memories
dmm reindex

# Index specific scope
dmm reindex --scope project

# Full reindex (clear and rebuild)
dmm reindex --full
```

### Programmatic Indexing
```python
from pathlib import Path
from dmm.indexer import MemoryIndexer
from dmm.indexer.store import MemoryStore

# Initialize store
store = MemoryStore(Path(".dmm/index/embeddings.db"))
store.initialize()

# Create indexer
indexer = MemoryIndexer(
    memory_root=Path(".dmm/memory"),
    store=store,
)

# Index all memories
result = indexer.index_all()
print(f"Indexed {result.indexed} memories")
print(f"Skipped {result.skipped} (unchanged)")
print(f"Errors: {result.errors}")
```

## 4. Querying Memories

### Basic Query
```bash
# Simple query
dmm query "How do I handle authentication?"

# With token budget
dmm query "error handling" --budget 1500

# Filter by scope
dmm query "configuration" --scope project

# Filter by tags
dmm query "database" --tags postgresql,config
```

### Programmatic Query
```python
from pathlib import Path
from dmm.retrieval import MemoryRetriever
from dmm.indexer.store import MemoryStore

# Initialize
store = MemoryStore(Path(".dmm/index/embeddings.db"))
store.initialize()

retriever = MemoryRetriever(store)

# Simple query
pack = retriever.retrieve(
    query="How does authentication work?",
    budget=2000,
)

print(f"Retrieved {len(pack.entries)} memories")
print(f"Total tokens: {pack.total_tokens}")

# Inspect entries
for entry in pack.entries:
    print(f"\n--- {entry.title} ---")
    print(f"Score: {entry.relevance_score:.3f}")
    print(f"Source: {entry.source}")
    print(entry.content[:200] + "...")
```

### Filtered Query
```python
from dmm.models.query import SearchFilters
from dmm.core.constants import Scope, Confidence

filters = SearchFilters(
    scopes=[Scope.PROJECT, Scope.GLOBAL],
    tags=["security"],
    min_priority=0.5,
    min_confidence=Confidence.ACTIVE,
    exclude_deprecated=True,
)

pack = retriever.retrieve(
    query="security best practices",
    budget=2000,
    filters=filters,
)
```

## 5. Memory Pack Output

The retriever returns a `MemoryPack`:
```python
from dmm.models.pack import MemoryPack

# Get as markdown (for context injection)
context = pack.to_markdown()
print(context)
```

Output:
```markdown
# Retrieved Memories

## Authentication Architecture
*Score: 0.892 | Source: retrieved*

This project uses JWT tokens for authentication...

## Error Handling Best Practices
*Score: 0.756 | Source: retrieved*

Always use specific exception types...
```

## 6. Updating Memories

### Update Content

Edit the file directly, then reindex:
```bash
# Edit the file
nano .dmm/memory/project/authentication.md

# Reindex to pick up changes
dmm reindex
```

### Update Metadata
```python
from dmm.indexer.store import MemoryStore

store = MemoryStore(Path(".dmm/index/embeddings.db"))
store.initialize()

# Update last_used timestamp
store.update_usage("mem_2026_01_25_002")

# Update priority
memory = store.get_memory("mem_2026_01_25_002")
if memory:
    memory.priority = 0.9
    embedding = store.get_embedding(memory.id)
    store.upsert_memory(memory, embedding)
```

## 7. Deprecating Memories

When a memory is outdated, deprecate it:
```bash
# Via CLI
dmm memory deprecate mem_2026_01_25_001 --reason "Replaced by new guidelines"
```
```python
# Programmatically
from dmm.core.constants import Status, Confidence

memory = store.get_memory("mem_2026_01_25_001")
if memory:
    memory.status = Status.DEPRECATED
    memory.confidence = Confidence.DEPRECATED
    
    # Update in store
    embedding = store.get_embedding(memory.id)
    store.upsert_memory(memory, embedding)
    
    # Move file to deprecated folder
    old_path = Path(".dmm/memory") / memory.path
    new_path = Path(".dmm/memory/deprecated") / memory.path
    new_path.parent.mkdir(parents=True, exist_ok=True)
    old_path.rename(new_path)
```

## 8. Memory Scopes

### Scope Hierarchy

| Scope | Priority | Always Loaded | Use Case |
|-------|----------|---------------|----------|
| baseline | Highest | Yes | Core identity, constraints |
| global | High | No | Cross-project knowledge |
| agent | Medium | No | Agent behavior rules |
| project | Medium | No | Project-specific info |
| ephemeral | Low | No | Temporary findings |

### Baseline Pack

Baseline memories are always included:
```bash
# Check baseline size
dmm status | grep baseline

# Compile baseline
dmm assemble --baseline-only
```

Keep baseline under 800 tokens.

## 9. Best Practices

### Memory Size

- Target: 300-800 tokens
- Too small: Lacks context
- Too large: Wastes budget

### Tags

- Use 3-7 tags per memory
- Be specific but not overly narrow
- Include category and topic tags

### Priorities

| Priority | Use For |
|----------|---------|
| 0.9-1.0 | Critical constraints, identity |
| 0.7-0.8 | Important guidelines |
| 0.5-0.6 | General knowledge |
| 0.3-0.4 | Background information |
| 0.1-0.2 | Nice to have |

### Versioning

When updating a memory significantly:
```yaml
---
id: mem_2026_01_26_001
supersedes: [mem_2026_01_25_001]
# ...
---

# Updated Error Handling (v2)

This supersedes the previous error handling guidelines...
```

## Exercises

1. **Create a Memory**: Write a memory about your project's coding standards
2. **Query and Inspect**: Query for the memory and examine the relevance score
3. **Update Priority**: Increase the priority and see how it affects retrieval
4. **Create Related Memories**: Create 3 related memories and see how they cluster

## Next Steps

- [Tutorial 2: Creating Custom Agents](02-creating-agents.md)
- [Memory Format Reference](../MEMORY_FORMAT.md)
- [Troubleshooting Guide](../TROUBLESHOOTING.md)
