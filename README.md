<div align="center">

# DMM - Dynamic Markdown Memory

### A File-Native Cognitive Memory System for AI Agents

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()
[![Phases](https://img.shields.io/badge/phases%201--4-complete-success)]()

*Persistent, semantic memory that gives AI agents context without overwhelming token budgets*

**Created By: Jerome Naidoo**

[Overview](#overview) • [Architecture](#architecture) • [Key Features](#key-features) • [Installation](#installation) • [Usage](#usage) • [Documentation](#documentation)

</div>

---

## Overview

Large language models operate within fixed context windows, forcing a constant tradeoff between **comprehensive context** and **token efficiency**. Current approaches either dump everything into the prompt (wasting tokens) or rely on fragile keyword matching (missing relevant context).

**DMM** reframes AI memory as a **semantic retrieval problem** rather than a context stuffing exercise. By treating memories as atomic, typed markdown files with vector embeddings, DMM provides:

- **Relevant** — semantic search retrieves only what matters for the current task
- **Efficient** — token budgets are respected, not exceeded
- **Persistent** — memories survive across sessions and machines
- **Governed** — baseline context is guaranteed, scopes control visibility
- **Automatic** — no manual approval needed, memories commit instantly

This represents production-grade memory infrastructure for AI coding assistants, formalized into a deployable system.

---

## The Problem with Current Approaches

Most AI memory systems introduce friction or fail silently:

| Problem | Description |
|---------|-------------|
| **Context Overflow** | Dumping all context exhausts token budgets |
| **Keyword Fragility** | Simple matching misses semantically related content |
| **Session Amnesia** | Knowledge lost between conversations |
| **Manual Overhead** | Requiring human approval for every memory |
| **No Guarantees** | Critical context may be omitted randomly |

DMM eliminates these problems through semantic embeddings, guaranteed baseline inclusion, and automatic memory commits.

---

## Architecture

DMM operates as a **daemon-based retrieval system** with a two-stage semantic pipeline:
```
Query → Embed → Stage 1 (Directory Routing) → Stage 2 (Memory Ranking) → Pack Assembly → Response
```

| Component | Purpose | Output |
|-----------|---------|--------|
| **Daemon** | FastAPI server with hot-reload indexing | HTTP API on port 7433 |
| **Indexer** | Parses markdown, generates 384-dim embeddings | SQLite vector store |
| **Retriever** | Two-stage semantic search with budget packing | Ranked memory list |
| **Writer** | Proposes and auto-commits new memories | Atomic file creation |
| **Reviewer** | Validates memory quality and conflicts | Quality gates |
```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              DMM ARCHITECTURE                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │
│   │   Memory    │    │   Vector    │    │  Retrieval  │    │    Pack     │    │
│   │   Files     │───▶│   Index     │───▶│   Pipeline  │───▶│  Assembly   │    │
│   │             │    │             │    │             │    │             │    │
│   │  .dmm/      │    │  SQLite +   │    │  2-Stage    │    │  Budget-    │    │
│   │  memory/    │    │  Embeddings │    │  Semantic   │    │  Aware      │    │
│   │             │    │             │    │  Search     │    │  Packing    │    │
│   └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    │
│         │                  │                  │                  │             │
│         │                  │                  │                  │             │
│         ▼                  ▼                  ▼                  ▼             │
│   Markdown with      384-dim vectors     Directory →        Baseline +        │
│   YAML frontmatter   (MiniLM-L6-v2)      Memory routing     Retrieved context │
│                                                                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   Memory Scopes:                                                                │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│   │ baseline │ │  global  │ │  agent   │ │ project  │ │ephemeral │           │
│   │ ALWAYS   │ │ Cross-   │ │ Behavior │ │ Project- │ │ Temporary│           │
│   │ included │ │ project  │ │ rules    │ │ specific │ │ expires  │           │
│   └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Features

### Semantic Retrieval
- **384-dimensional embeddings** using sentence-transformers (all-MiniLM-L6-v2)
- **Two-stage search**: Directory routing → Memory ranking
- **Cosine similarity** with priority and confidence weighting
- **Budget-aware packing**: Never exceeds specified token limits

### Memory Scopes
| Scope | Purpose | Retrieval |
|-------|---------|-----------|
| `baseline` | Critical identity and constraints | **Always included** |
| `global` | Cross-project standards | When relevant |
| `agent` | Behavioral rules and style | When relevant |
| `project` | Project-specific knowledge | When relevant |
| `ephemeral` | Temporary context with expiration | When relevant, auto-expires |

### Automatic Commits
- **No manual approval** — memories commit instantly by default
- **Quality validation** — frontmatter and content checks
- **Conflict detection** — semantic similarity and tag overlap analysis
- **Atomic writes** — all-or-nothing file creation with rollback

### Claude Code Integration
- **CLAUDE.md** — Project instructions Claude reads automatically
- **Bootstrap script** — One-command installation on new machines
- **Wrapper script** — `claudex` starts daemon and launches Claude
- **Live memory** — Query and write during conversations

---

## What Makes This Different

<table>
<tr>
<th>Feature</th>
<th>Typical AI Memory</th>
<th>DMM</th>
</tr>
<tr>
<td><b>Retrieval</b></td>
<td>Keyword matching or full dump</td>
<td>Semantic vector search</td>
</tr>
<tr>
<td><b>Persistence</b></td>
<td>Session-only or cloud-dependent</td>
<td>Local markdown files (git-trackable)</td>
</tr>
<tr>
<td><b>Token Budget</b></td>
<td>Often exceeded or ignored</td>
<td>Strictly enforced with packing</td>
</tr>
<tr>
<td><b>Baseline Guarantee</b></td>
<td>None</td>
<td>Always included, never dropped</td>
</tr>
<tr>
<td><b>Approval Workflow</b></td>
<td>Manual or none</td>
<td>Automatic with quality gates</td>
</tr>
<tr>
<td><b>Multi-Machine</b></td>
<td>Cloud sync required</td>
<td>Git-based, works offline</td>
</tr>
</table>

---

## Installation

### New Machine (Full Install)
```bash
# Clone repository
git clone https://github.com/jaysteelmind/claude-memory.git ~/projects/claude-memory

# Run installer
cd ~/projects/claude-memory && ./start.sh

# Use from anywhere
claudex
```

### Requirements
- Python 3.11+
- Poetry (auto-installed by bootstrap)
- ~90MB disk for embedding model (downloaded once)
- Claude Code (for `claudex` wrapper)

### What `start.sh` Does
1. Runs `bin/dmm-bootstrap` (installs Poetry, dependencies, `dmm` command)
2. Installs `claudex` to `/usr/local/bin/`
3. Verifies installation

---

## Usage

### Start Claude Code with DMM
```bash
# From anywhere on your machine
claudex
```

This:
1. Starts the DMM daemon
2. Launches Claude Code in the project directory
3. Stops daemon when Claude exits

### CLI Commands
```bash
# Check system status
dmm daemon status
dmm claude check

# Query for relevant context
dmm query "implement authentication" --budget 1500

# Save a new memory (auto-commits)
echo '---
id: mem_2026_01_21_001
tags: [api, authentication]
scope: project
priority: 0.8
confidence: active
status: active
---
# Authentication Pattern
Use JWT tokens with 24-hour expiration...' | dmm write propose project/auth-pattern.md --reason "Document auth approach"

# Reindex after manual file changes
dmm reindex

# Check for conflicts
dmm conflicts scan
```

### Memory File Format
```markdown
---
id: mem_YYYY_MM_DD_NNN
tags: [tag1, tag2]
scope: project          # baseline|global|agent|project|ephemeral
priority: 0.7           # 0.0-1.0, higher = more important
confidence: active      # experimental|active|stable|deprecated
status: active          # active|deprecated
created: 2026-01-21
expires: 2026-02-21     # optional, for ephemeral scope
---
# Memory Title

Content goes here. Keep memories atomic (300-800 tokens).
Single concept per file. No undefined references.
```

### Programmatic Access
```python
from dmm.retriever.pack_builder import PackBuilder
from dmm.indexer.store import MemoryStore
from dmm.core.config import DMMConfig

# Load configuration
config = DMMConfig.load(Path.cwd())
store = MemoryStore(config.index_path / "embeddings.db")

# Build a memory pack
builder = PackBuilder(store, config)
pack = builder.build(
    query="implement user authentication",
    token_budget=1500,
)

print(f"Retrieved: {len(pack.memories)} memories")
print(f"Tokens used: {pack.total_tokens}")
```

---

## Project Structure
```
claude-memory/
├── CLAUDE.md                    # Instructions for Claude Code
├── start.sh                     # One-command installer
├── bin/
│   ├── dmm-bootstrap            # Dependency installer
│   └── claude-code-dmm          # Native wrapper script
├── .dmm/
│   ├── BOOT.md                  # Detailed operational instructions
│   ├── policy.md                # Memory governance policies
│   ├── daemon.config.json       # Daemon configuration
│   ├── memory/                  # Memory files by scope
│   │   ├── baseline/
│   │   ├── global/
│   │   ├── agent/
│   │   ├── project/
│   │   └── ephemeral/
│   └── index/                   # SQLite databases
│       ├── embeddings.db        # Vector store
│       ├── usage.db             # Usage tracking
│       └── conflicts.db         # Conflict records
├── src/dmm/
│   ├── cli/                     # Command-line interface
│   │   ├── main.py              # CLI entry point
│   │   ├── query.py             # Query commands
│   │   ├── write.py             # Write commands
│   │   ├── review.py            # Review commands
│   │   ├── conflicts.py         # Conflict commands
│   │   └── claude.py            # Integration check
│   ├── core/                    # Core utilities
│   │   ├── config.py            # Configuration loading
│   │   ├── constants.py         # System constants
│   │   └── exceptions.py        # Custom exceptions
│   ├── daemon/                  # FastAPI daemon
│   │   └── server.py
│   ├── indexer/                 # Indexing pipeline
│   │   ├── indexer.py           # Main indexer
│   │   ├── embedder.py          # Embedding generation
│   │   ├── parser.py            # Markdown parsing
│   │   └── store.py             # SQLite storage
│   ├── retriever/               # Retrieval pipeline
│   │   ├── retriever.py         # Two-stage search
│   │   └── pack_builder.py      # Budget-aware packing
│   ├── writeback/               # Write operations
│   │   ├── proposal.py          # Proposal handling
│   │   ├── commit.py            # Atomic commits
│   │   └── queue.py             # Review queue
│   ├── reviewer/                # Quality validation
│   │   └── agent.py             # Review agent
│   └── conflicts/               # Conflict detection
│       ├── detector.py          # Conflict scanner
│       └── resolver.py          # Resolution strategies
└── tests/                       # Test suites
    ├── test_integration/
    └── test_claude_integration.py
```

---

## Configuration

### Daemon Configuration (`.dmm/daemon.config.json`)
```json
{
  "host": "127.0.0.1",
  "port": 7433,
  "auto_reload": true,
  "log_level": "info"
}
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DMM_PORT` | `7433` | Daemon port |
| `DMM_HOST` | `127.0.0.1` | Daemon host |
| `DMM_LOG_LEVEL` | `info` | Logging verbosity |

---

## Development Phases

| Phase | Description | Status |
|-------|-------------|--------|
| **Phase 1** | Core retrieval, daemon, CLI | Complete |
| **Phase 2** | Write-back engine, review agent | Complete |
| **Phase 3** | Conflict detection and resolution | Complete |
| **Phase 4** | Claude Code integration | Complete |
| **Phase 5** | Docker deployment | Skipped |

---

## API Reference

### Daemon Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/status` | GET | Daemon status and stats |
| `/query` | POST | Semantic memory query |
| `/reindex` | POST | Trigger reindexing |

### Query Request
```json
{
  "query": "implement user authentication",
  "budget": 1500,
  "scopes": ["baseline", "project"],
  "min_relevance": 0.3
}
```

### Query Response
```json
{
  "pack": "# DMM Memory Pack\n...",
  "stats": {
    "baseline_tokens": 160,
    "retrieved_tokens": 593,
    "total_tokens": 753,
    "memories_included": 4,
    "memories_excluded": 2
  }
}
```

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `dmm: command not found` | Not installed globally | Run `./bin/dmm-bootstrap` |
| Daemon won't start | Port in use | `lsof -i :7433` and kill process |
| Empty query results | Not indexed | Run `dmm reindex` |
| Slow first query | Model loading | Normal, ~5s first time |
| Permission denied | Wrapper not executable | `chmod +x /usr/local/bin/claudex` |

### Debug Commands
```bash
# Check daemon logs
dmm daemon status

# Verify integration
dmm claude check -v

# Test query pipeline
dmm query "test" --budget 500

# Reindex all memories
dmm reindex
```

---

## Contributing

Contributions are welcome:

1. All code must have tests
2. Memory format must be preserved
3. Token budgets must be respected
4. Documentation must accompany new features

---

## License

MIT License — See [LICENSE](LICENSE) for details.

---

<div align="center">

**DMM** — *Semantic memory infrastructure for AI agents*

**Jerome Naidoo**

Building persistent, intelligent context for the next generation of AI assistants.

</div>
