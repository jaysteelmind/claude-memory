# Architecture Overview

DMM (Dynamic Markdown Memory) is a layered system that evolves from simple memory retrieval into a full Agent Operating System.

## System Evolution
```
Phase 1-4: Memory System     "What does the agent know?"
           ↓
Phase 5: Knowledge Graph     "How does knowledge connect?"
           ↓
Phase 6: Agent Operating System     "What can the agent do?"
```

## Layered Architecture
```
┌────────────────────────────────────────────────────────────────┐
│                   APPLICATION LAYER                            │
│         CLI │ HTTP API │ Claude Code │ MCP Server              │
├────────────────────────────────────────────────────────────────┤
│                   AGENT OS LAYER (Phase 6)                     │
│    Tasks │ Orchestration │ Communication │ Self-Mod │ Runtime  │
├────────────────────────────────────────────────────────────────┤
│                   CAPABILITY LAYER (Phase 6)                   │
│         Skills Registry │ Tools Registry │ Agents Pool         │
├────────────────────────────────────────────────────────────────┤
│                   INTELLIGENCE LAYER (Phase 5)                 │
│    Extractors │ Hybrid Retriever │ Inference │ Visualization   │
├────────────────────────────────────────────────────────────────┤
│                   MEMORY LAYER (Phases 1-4)                    │
│        Indexer │ Retriever │ Write-Back │ Conflicts            │
├────────────────────────────────────────────────────────────────┤
│                   STORAGE LAYER                                │
│      SQLite (vectors) │ Kuzu (graph) │ Markdown (files)        │
└────────────────────────────────────────────────────────────────┘
```

## Core Components

### Storage Layer

| Component | Technology | Purpose |
|-----------|------------|---------|
| Vector Store | SQLite + sqlite-vss | Embedding storage and similarity search |
| Graph Store | Kuzu | Relationship storage and traversal |
| File Store | Markdown files | Human-readable memory storage |

### Memory Layer (Phases 1-4)

#### Indexer
Parses markdown files and generates composite embeddings:
```
[DIRECTORY] memory/project/constraints
[TITLE] Constraint: No Background Jobs
[TAGS] build, constraints, async
[SCOPE] project
[CONTENT] We do not use asynchronous background execution...
```

#### Two-Stage Retrieval Router

**Stage 1: Directory Selection**
- Embed the query
- Rank directories by relevance
- Select top-K directories (default: 3)

**Stage 2: File Selection**
```
Score = 0.6 × similarity + 0.25 × priority + 0.15 × confidence_score
```

#### Baseline Pack
Critical context always included in every query:
- Identity and role definitions
- Hard constraints
- Core principles

#### Write-Back Engine
Quality-controlled memory creation:
1. Propose → 2. Validate → 3. Review → 4. Commit

#### Conflict Detector
Identifies contradictions using:
- Tag overlap analysis
- Semantic similarity clustering
- Supersession chain validation

### Intelligence Layer (Phase 5)

#### Relationship Extractors

| Extractor | Algorithm | Edge Types |
|-----------|-----------|------------|
| Tag | Jaccard similarity | RELATES_TO |
| Semantic | Cosine ≥0.75 | RELATES_TO, SUPPORTS |
| Temporal | Version regex | SUPERSEDES |
| LLM | Prompt-based | All types |

#### Hybrid Retrieval
Combines vector and graph search:
```
S(m) = α × V(m) + (1-α) × G(m)

where:
  α = 0.6 (vector weight)
  V(m) = vector similarity score
  G(m) = graph expansion score
```

#### Inference Engine
- **Transitive Inference**: Discovers implicit relationships
- **Cluster Detection**: Finds groups of related memories

### Capability Layer (Phase 6)

#### Skills Registry
Agent capabilities defined in YAML:
```yaml
id: skill_code_review
name: Code Review
inputs:
  - name: file_path
    type: string
outputs:
  - name: issues
    type: array
```

#### Tools Registry
External tool integrations:
- CLI tools
- API endpoints
- MCP servers
- Python functions

#### Agents Registry
Agent personas with:
- Assigned skills
- Available tools
- Behavioral configuration
- Resource constraints

### Agent OS Layer (Phase 6)

#### Task System
```
pending → scheduled → running → completed/failed
```

#### Execution Engine
- Context building
- Skill/tool execution
- Error handling with retry/fallback/escalate

#### Communication Layer
Multi-agent messaging:
- REQUEST/RESPONSE
- DELEGATE/ASSIST
- BROADCAST

#### Self-Modification Framework

| Level | Description | Approval |
|-------|-------------|----------|
| 1 | Memory updates | Automatic |
| 2 | Skill changes | Logged |
| 3 | Behavior changes | Human required |
| 4 | Goal changes | Human required |

## Data Flow

### Query Flow
```
User Query
    ↓
┌─────────────────┐
│  Embed Query    │
└────────┬────────┘
         ↓
┌─────────────────┐
│ Directory       │ ← Stage 1
│ Selection       │
└────────┬────────┘
         ↓
┌─────────────────┐
│ Memory Ranking  │ ← Stage 2
│ + Graph Expand  │
└────────┬────────┘
         ↓
┌─────────────────┐
│ Budget Filter   │
│ + Baseline      │
└────────┬────────┘
         ↓
    Memory Pack
```

### Write Flow
```
Memory Proposal
    ↓
┌─────────────────┐
│ Schema          │
│ Validation      │
└────────┬────────┘
         ↓
┌─────────────────┐
│ Quality Checks  │
│ (tokens, etc)   │
└────────┬────────┘
         ↓
┌─────────────────┐
│ Duplicate       │
│ Detection       │
└────────┬────────┘
         ↓
┌─────────────────┐
│ Reviewer Agent  │
│ Decision        │
└────────┬────────┘
         ↓
   APPROVED / REJECTED / MODIFIED
```

## Directory Structure
```
.dmm/
├── BOOT.md                      # Agent boot instructions
├── policy.md                    # Write-back policies
├── daemon.config.json           # Daemon configuration
│
├── memory/                      # Memory storage
│   ├── baseline/                # Always included
│   ├── global/                  # Cross-project
│   ├── agent/                   # Agent behavior
│   ├── project/                 # Project-specific
│   ├── ephemeral/               # Temporary
│   └── deprecated/              # Archived
│
├── skills/                      # Skill definitions
│   ├── core/
│   └── custom/
│
├── tools/                       # Tool definitions
│   ├── cli/
│   ├── api/
│   ├── mcp/
│   └── function/
│
├── agents/                      # Agent definitions
│
├── tasks/                       # Task queue
│   ├── active/
│   ├── completed/
│   └── failed/
│
├── index/                       # Databases
│   ├── embeddings.db            # Vector store
│   ├── knowledge.kuzu/          # Graph database
│   ├── stats.db                 # Usage statistics
│   ├── conflicts.db             # Conflict records
│   └── tasks.db                 # Task state
│
└── packs/
    ├── last_pack.md             # Last compiled pack
    └── baseline_pack.md         # Pre-compiled baseline
```

## Performance Characteristics

### Complexity Analysis

| Operation | Complexity | Notes |
|-----------|------------|-------|
| Directory search | O(D) | D = directories |
| Memory search | O(M log M) | M = memories |
| Overall retrieval | O(D + kM log M) | ≈ O(n log n) |
| Transitive inference | O(V(V+E)) | BFS-based |
| Cluster detection | O(V+E) | DFS-based |

### Performance Targets

| Operation | Target |
|-----------|--------|
| Simple query | <150ms |
| Complex query | <1s |
| Index per file | <200ms |
| Skill execution | <5s |
| Task orchestration | <10s |

## Design Principles

1. **File-Native**: All data as human-readable files
2. **Atomic Units**: Small, focused memory units (300-800 tokens)
3. **Semantic Retrieval**: Meaning-based, not keyword
4. **Hierarchical Scopes**: Layered context priority
5. **Quality Gates**: AI-assisted validation
6. **Graph-Aware**: Relationships are first-class
7. **Composable**: Skills combine into capabilities
8. **Safe Self-Modification**: Agent can improve with guardrails

## Further Reading

- [API Reference](api/index.md)
- [Memory Format Specification](MEMORY_FORMAT.md)
- [Tutorials](tutorials/01-basic-memory.md)
