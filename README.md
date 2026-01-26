<div align="center">

# DMM - Dynamic Markdown Memory

### A Cognitive Memory System for AI Agents

[![Tests](https://img.shields.io/badge/tests-1%2C232%20passing-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()
[![Status](https://img.shields.io/badge/status-Production%20Ready-success)]()

*File-native semantic memory with knowledge graphs and agent orchestration*

[Overview](#overview) • [Architecture](#architecture) • [Quick Start](#quick-start) • [Installation](#installation) • [Usage](#usage) • [Documentation](#documentation)

</div>

---

## Overview

The effectiveness of AI agents is constrained not by model capability, but by **context management**. Monolithic instruction files force agents to load everything into limited context windows, causing information overload, missed constraints, and inconsistent behavior.

**DMM** reframes agent memory as a **semantic, graph-connected knowledge system**. By treating memories as atomic, retrievable units with relationships, DMM enables agents to:

- **Load only relevant context** for each task
- **Maintain persistent knowledge** across sessions
- **Reason over connected information** via knowledge graphs
- **Self-improve** through governed memory creation

This represents the memory architecture used by sophisticated agent systems, formalized into a production-ready framework.

---

## The Problem with Current Approaches

Most agent instruction systems introduce systemic limitations:

| Problem | Description |
|---------|-------------|
| **Context Overflow** | Large instruction files exceed context windows |
| **Irrelevant Loading** | All instructions loaded regardless of task |
| **No Persistence** | Knowledge lost between sessions |
| **Flat Structure** | No relationships between pieces of knowledge |
| **Manual Updates** | Human-only memory management |

DMM eliminates these limitations through semantic retrieval, hierarchical scopes, knowledge graphs, and AI-assisted memory curation.

---

## Architecture

DMM operates as a **layered cognitive system**:
```
Query → Retrieval → Graph Expansion → Context Assembly → Response
```

| Layer | Components | Purpose |
|-------|------------|---------|
| **Storage** | Markdown + SQLite + Kuzu | File-native persistence with vectors and graphs |
| **Memory** | Indexer, Retriever, Write-Back | Semantic storage and retrieval |
| **Intelligence** | Extractors, Inference Engine | Relationship discovery and reasoning |
| **Agent OS** | Skills, Tools, Tasks, Orchestration | Capability composition and execution |
```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              DMM ARCHITECTURE                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│   │   Agent     │    │    Task     │    │   Skills    │    │    Tools    │     │
│   │ Orchestrator│───▶│  Planner    │───▶│  Registry   │───▶│  Registry   │     │
│   └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘     │
│          │                                                                       │
│          ▼                                                                       │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│   │   Hybrid    │    │  Knowledge  │    │  Inference  │    │   Graph     │     │
│   │  Retriever  │◀──▶│    Graph    │◀──▶│   Engine    │───▶│Visualization│     │
│   └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘     │
│          │                                                                       │
│          ▼                                                                       │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│   │  Semantic   │    │  Write-Back │    │  Conflict   │    │  Reviewer   │     │
│   │   Index     │◀──▶│   Engine    │◀──▶│  Detector   │◀──▶│   Agent     │     │
│   └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘     │
│          │                                                                       │
│          ▼                                                                       │
│   ┌───────────────────────────────────────────────────────────────────────┐     │
│   │                          STORAGE LAYER                                 │     │
│   │   Markdown Files (Git)  │  SQLite + Vectors  │  Kuzu Graph Database   │     │
│   └───────────────────────────────────────────────────────────────────────┘     │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Features

### Semantic Memory System
- **Atomic memories** (300-800 tokens) enabling precise retrieval
- **Composite embeddings** combining path, title, tags, and content
- **Two-stage retrieval**: directory filtering then file ranking
- **Token-budgeted assembly** respecting context limits

### Knowledge Graph
- **5 relationship types**: RELATES_TO, SUPPORTS, CONTRADICTS, DEPENDS_ON, SUPERSEDES
- **4 extractors**: Tag similarity, Semantic clustering, Temporal analysis, LLM-based
- **Hybrid retrieval**: Vector search + graph expansion combined
- **Transitive inference**: Discovering implicit knowledge connections

### Agent Operating System
- **Skills Registry**: Composable agent capabilities with dependencies
- **Tools Registry**: External integrations (CLI, API, MCP, functions)
- **Task Orchestration**: Planning, scheduling, execution with recovery
- **Multi-Agent Communication**: Message passing and collaboration patterns

### Quality Control
- **Reviewer Agent**: AI-validated memory creation
- **Conflict Detection**: Semantic contradiction identification
- **Governance Scopes**: baseline > global > agent > project > ephemeral

---

## Quick Start

### For Claude Code (Fastest)

**Step 1:** Copy the bootstrap file to your project:
```bash
cp ~/projects/claude-memory/templates/start.md /path/to/your/project/
```

**Step 2:** Open Claude Code and say:
> "Read and execute start.md"

**Done.** Claude handles installation, initialization, and configuration automatically.

---

## Installation

### Global Installation
```bash
cd ~/projects/claude-memory
./scripts/install.sh
```

This installs DMM to `~/.dmm-system` and adds `dmm` to your PATH.

### Development Installation
```bash
git clone https://github.com/your-org/claude-memory.git
cd claude-memory
poetry install
```

### Requirements
- Python 3.11+
- Poetry for dependency management

---

## Usage

### Initialize a Project
```bash
cd your-project
dmm bootstrap
```

### Memory Operations
```bash
# Query for relevant context
dmm query "How does authentication work?" --budget 1500

# Quick memory creation
dmm remember "We use PostgreSQL with read replicas for scaling"

# Quick memory deprecation
dmm forget mem_2026_01_20_001 --reason "Superseded by new architecture"

# System status
dmm status
```

### Daemon Management
```bash
dmm daemon start
dmm daemon stop
dmm daemon status
```

### Knowledge Graph
```bash
# Extract relationships
dmm graph extract

# Run inference
dmm graph infer

# Visualize
dmm graph viz --format html
```

---

## Memory Structure

### Scopes

| Scope | Priority | Purpose | Retrieval |
|-------|----------|---------|-----------|
| `baseline` | Highest | Core identity, hard constraints | Always included |
| `global` | High | Cross-project standards | When relevant |
| `agent` | Medium | Behavioral rules | When relevant |
| `project` | Medium | Project-specific decisions | When relevant |
| `ephemeral` | Low | Temporary findings | Auto-expires |

### Memory Format
```markdown
---
id: mem_2026_01_20_001
tags: [authentication, security, jwt]
scope: project
priority: 0.8
confidence: stable
status: active
created: 2026-01-20
---

# Authentication Strategy

We use JWT tokens with 15-minute expiry for API authentication.

## Rationale
- Stateless verification reduces database load
- Short expiry limits token theft impact

## Implementation
Tokens are validated via RS256 signatures using rotating keys.
```

---

## Test Coverage

| Module | Tests | Description |
|--------|-------|-------------|
| **Core (Phases 1-4)** | 142 | Indexing, retrieval, write-back, conflicts |
| **Knowledge Graph (Phase 5)** | 135 | Extractors, inference, visualization |
| **Agent OS (Phase 6)** | 917 | Skills, tools, tasks, orchestration |
| **Bootstrap (Phase 7)** | 38 | Auto-setup, quick commands |
| **Total** | **1,232** | Full system coverage |
```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=src/dmm
```

---

## Project Structure
```
claude-memory/
├── src/dmm/
│   ├── cli/                    # Command-line interface
│   │   ├── commands/           # bootstrap, remember, forget
│   │   └── utils/              # DaemonManager
│   ├── core/                   # Constants, exceptions, config
│   ├── models/                 # Memory, Pack, Query, Conflict
│   ├── indexer/                # Embedding, parsing, storage
│   ├── retrieval/              # Router, baseline, assembler
│   ├── writeback/              # Proposals, queue, commit
│   ├── reviewer/               # AI validation
│   ├── conflicts/              # Detection, resolution
│   ├── graph/                  # Knowledge graph
│   │   ├── extractors/         # Tag, semantic, temporal, LLM
│   │   ├── inference/          # Transitive, clustering
│   │   └── visualization/      # HTML, DOT, Mermaid
│   ├── agentos/                # Agent Operating System
│   │   ├── skills/             # Skills registry
│   │   ├── tools/              # Tools registry
│   │   ├── agents/             # Agent definitions
│   │   ├── tasks/              # Task management
│   │   ├── orchestration/      # Execution engine
│   │   └── communication/      # Multi-agent messaging
│   └── daemon/                 # HTTP server, lifecycle
├── scripts/                    # install.sh, uninstall.sh, update.sh
├── templates/                  # start.md, CLAUDE.md.template
└── tests/                      # 1,232 tests
```

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `dmm bootstrap` | Full project initialization |
| `dmm status` | System health check |
| `dmm query "<text>"` | Semantic memory search |
| `dmm remember "<text>"` | Quick memory creation |
| `dmm forget <id>` | Quick memory deprecation |
| `dmm daemon start\|stop\|status` | Daemon management |
| `dmm graph extract\|infer\|viz` | Knowledge graph operations |
| `dmm write propose\|update\|deprecate` | Formal memory proposals |
| `dmm review list\|approve\|reject` | Proposal review |
| `dmm conflicts list\|scan\|resolve` | Conflict management |

---

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | System design overview |
| [Quick Start](docs/QUICKSTART.md) | Getting started guide |
| [API Reference](docs/api/) | Programmatic interfaces |
| [Tutorials](docs/tutorials/) | Step-by-step guides |

---

## Design Principles

DMM draws from principles in:

- **Information Retrieval** — Semantic embeddings, two-stage retrieval
- **Graph Theory** — Knowledge graphs, transitive inference
- **Compiler Design** — Staged pipelines, deterministic processing
- **Distributed Systems** — Agent coordination, message passing
- **Unix Philosophy** — Atomic units, composability, text as interface

---

## Contributing

We welcome contributions that maintain system rigor:

1. All code must have comprehensive tests
2. Memory format constraints must be preserved
3. New features must integrate with existing pipelines
4. Documentation must accompany changes

---

## License

MIT License - See [LICENSE](LICENSE) for details.

---

<div align="center">

**DMM** - *Cognitive memory for AI agents*

Building the memory infrastructure for the next generation of AI systems.

</div>
