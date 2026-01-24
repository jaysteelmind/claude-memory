# DMM - Dynamic Markdown Memory

> **Cognitive Memory System for AI Agents**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-135%20passing-brightgreen.svg)](#testing)

DMM (Dynamic Markdown Memory) is a file-native memory system that gives AI agents persistent, semantic, and graph-connected knowledge. It evolves from simple context retrieval into a full **Agent Operating System**.

---

## Vision

```
Traditional Agent:  [Prompt] + [Static Instructions] → [Response]

DMM Agent:          [Prompt] + [Retrieved Context] + [Graph Relationships] → [Response]
                                       │                      │
                                       ▼                      ▼
                               Semantic Match         Connected Knowledge
```

**DMM transforms how AI agents access knowledge:**
- From static prompts → dynamic, relevant context
- From flat files → interconnected knowledge graph
- From manual updates → self-improving memory

---

## Project Status

### Completed Phases

| Phase | Name | Status | Description |
|-------|------|--------|-------------|
| 1 | Core Foundation | Complete | File-native storage, indexing, basic retrieval |
| 2 | Write-Back System | Complete | AI-reviewed memory creation, quality gates |
| 3 | Conflict Detection | Complete | Semantic conflict detection, resolution |
| 4 | Claude Code Integration | Complete | CLAUDE.md, boot sequence, daemon |
| 5.1 | Graph Foundation | Complete | Kuzu database, nodes, edges, schema |
| 5.2 | Graph Intelligence | Complete | Extractors, hybrid retrieval, inference |

### In Development

| Phase | Name | Status | Description |
|-------|------|--------|-------------|
| 6.1 | Agent OS Foundation |  Planned | Skills, Tools, Agents registries |
| 6.2 | Agent OS Advanced |  Planned | Task orchestration, multi-agent, self-modification |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AGENT OPERATING SYSTEM                       │
│                              (Phase 6)                               │
│                                                                      │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐ │
│   │   Skills    │  │    Tools    │  │   Agents    │  │   Tasks   │ │
│   │  Registry   │  │  Registry   │  │  Registry   │  │ Orchestr. │ │
│   └─────────────┘  └─────────────┘  └─────────────┘  └───────────┘ │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                         INTELLIGENCE LAYER                           │
│                              (Phase 5)                             │
│                                                                      │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐ │
│   │ Relationship│  │   Hybrid    │  │  Inference  │  │   Graph   │ │
│   │ Extractors  │  │  Retrieval  │  │   Engine    │  │    Viz    │ │
│   └─────────────┘  └─────────────┘  └─────────────┘  └───────────┘ │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                          KNOWLEDGE LAYER                             │
│                           (Phases 1-4)                             │
│                                                                      │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐ │
│   │   Memory    │  │  Write-Back │  │  Conflicts  │  │  Claude   │ │
│   │   System    │  │   Engine    │  │  Detector   │  │   Code    │ │
│   └─────────────┘  └─────────────┘  └─────────────┘  └───────────┘ │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                          STORAGE LAYER                               │
│                                                                      │
│   ┌───────────────────┐  ┌───────────────────┐  ┌─────────────────┐ │
│   │  Markdown Files   │  │  SQLite + Vector  │  │   Kuzu Graph    │ │
│   │   (Git-friendly)  │  │   (Embeddings)    │  │  (Relationships)│ │
│   └───────────────────┘  └───────────────────┘  └─────────────────┘ │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/claude-memory.git
cd claude-memory

# Install with Poetry
poetry install

# Or with pip
pip install -e .
```

### Initialize a Project

```bash
# Initialize DMM in your project
cd your-project
dmm init

# This creates:
# .dmm/
# ├── memory/
# │   ├── baseline/
# │   ├── global/
# │   ├── project/
# │   └── ephemeral/
# ├── index/
# └── BOOT.md
```

### Basic Usage

```bash
# Index all memories
dmm index

# Query memories
dmm query "How does authentication work?"

# Assemble context pack
dmm assemble --tokens 4000

# Boot sequence (for Claude Code)
dmm boot
```

---

## Memory Structure

### Scopes

Memories are organized into hierarchical scopes:

| Scope | Priority | Purpose | Persistence |
|-------|----------|---------|-------------|
| `baseline` | Highest | Core identity, principles | Permanent |
| `global` | High | Cross-project knowledge | Long-term |
| `agent` | Medium | Agent-specific context | Session |
| `project` | Medium | Project-specific | Project lifetime |
| `ephemeral` | Low | Temporary context | Short-term |

### Memory Format

```markdown
---
id: mem_abc123
title: Authentication Best Practices
scope: global
tags: [security, authentication, best-practices]
priority: 0.8
created: 2026-01-15
updated: 2026-01-23
---

# Authentication Best Practices

## Overview
This document outlines security best practices for authentication...

## Key Principles
1. Always use secure password hashing (bcrypt, argon2)
2. Implement rate limiting on login attempts
3. Use HTTPS for all authentication endpoints
```

---

## 🕸️ Knowledge Graph (Phase 5)

### Overview

Phase 5 transforms flat memories into an interconnected knowledge structure using [Kuzu](https://kuzudb.com/), an embedded graph database.

### Relationship Types

| Relationship | Description | Example |
|--------------|-------------|---------|
| `RELATES_TO` | Topical connection | "API Design" ↔ "REST Patterns" |
| `SUPPORTS` | Evidence/reinforcement | "Test Results" → "Design Decision" |
| `CONTRADICTS` | Conflicting information | "Old Policy" ↔ "New Policy" |
| `DEPENDS_ON` | Prerequisite knowledge | "OAuth Flow" → "HTTP Basics" |
| `SUPERSEDES` | Version replacement | "API v2 Guide" → "API v1 Guide" |

### Relationship Extraction

DMM automatically discovers relationships using multiple extractors:

```bash
# Run extraction
dmm graph extract

# With specific extractors
dmm graph extract --extractors tag,semantic,temporal

# Dry run
dmm graph extract --dry-run
```

**Extractors:**

| Extractor | Method | Complexity |
|-----------|--------|------------|
| **Tag** | Jaccard similarity on tags | O(n × t) |
| **Semantic** | Cosine similarity on embeddings | O(n² × d) |
| **Temporal** | Version detection, time proximity | O(n) |
| **LLM** | Deep semantic analysis | O(API calls) |

### Hybrid Retrieval

Combines vector similarity with graph traversal:

```python
# Retrieval formula
combined_score = α × vector_score + (1-α) × graph_score
# where α = 0.6 (configurable)
```

```bash
# Query with graph expansion
dmm query "authentication" --graph-expand

# Assemble with relationships
dmm assemble --include-relationships
```

### Inference Engine

Discovers implicit knowledge:

```bash
# Run all inference
dmm graph infer

# Transitive relationships (A→B→C implies A→C)
dmm graph infer --mode transitive --apply

# Detect clusters
dmm graph infer --mode clusters

# Find knowledge gaps
dmm graph infer --mode gaps
```

### Visualization

```bash
# Interactive HTML (D3.js)
dmm graph viz --output graph.html

# Mermaid for documentation
dmm graph viz --format mermaid --output docs/graph.md

# Filter by scope
dmm graph viz --scope global,project

# Highlight clusters
dmm graph viz --clusters
```

### Graph CLI Commands

```bash
# Status and statistics
dmm graph status
dmm graph extract-stats

# Extraction
dmm graph extract [--extractors tag,semantic,temporal,llm]
                  [--memory <id>]
                  [--dry-run]
                  [--min-weight 0.3]

# Inference
dmm graph infer [--mode transitive|clusters|gaps|all]
                [--apply]
                [--min-confidence 0.5]

# Visualization
dmm graph viz [--output <path>]
              [--format html|json|dot|mermaid]
              [--scope <scopes>]
              [--clusters]
```

---

## 🤖 Agent OS (Phase 6) - Coming Soon

Phase 6 transforms DMM from a memory system into a complete **Agent Operating System**.

### Phase 6.1: Foundation (Planned)

**Skills Registry** - Reusable agent capabilities:
```yaml
# .dmm/skills/core/code_review.skill.yaml
id: skill_code_review
name: Code Review
inputs:
  - name: code
    type: string
outputs:
  - name: issues
    type: array
dependencies:
  skills: [skill_syntax_check]
  tools: [tool_eslint]
```

**Tools Registry** - External tool integration:
```yaml
# .dmm/tools/cli/eslint.tool.yaml
id: tool_eslint
name: ESLint
type: cli
command:
  template: "npx eslint {files} --format json"
```

**Agents Registry** - Specialized personas:
```yaml
# .dmm/agents/reviewer.agent.yaml
id: agent_reviewer
name: Code Reviewer
skills:
  primary: [skill_code_review, skill_security_scan]
behavior:
  tone: professional
  focus_areas: [code_quality, security]
```

### Phase 6.2: Advanced (Planned)

**Task Orchestration:**
```
Task: "Review authentication module"
         │
         ▼
   ┌─────────────┐
   │   Planner   │ → Decompose into subtasks
   └─────────────┘
         │
         ▼
   ┌─────────────┐
   │  Scheduler  │ → Prioritize, assign agents
   └─────────────┘
         │
         ▼
   ┌─────────────┐
   │  Executor   │ → Run skills, invoke tools
   └─────────────┘
         │
         ▼
      Results
```

**Multi-Agent Communication:**
```yaml
message:
  type: DELEGATE
  sender: agent_researcher
  recipient: agent_implementer
  body:
    task_id: task_implement_patterns
    context: {...}
```

**Self-Modification Framework:**

| Level | Type | Approval |
|-------|------|----------|
| 1 | Memory | Automatic |
| 2 | Skill | Logged |
| 3 | Behavior | AI Review |
| 4 | Goal | Human Required |

---

## Testing

### Run Tests

```bash
# All tests
poetry run pytest

# Specific phase
poetry run pytest tests/unit/graph/

# With coverage
poetry run pytest --cov=src/dmm --cov-report=html
```

### Test Coverage

| Phase | Tests | Status |
|-------|-------|--------|
| Phases 1-4 | 67 | Passing |
| Phase 5.1 (Graph Foundation) | 67 | Passing |
| Phase 5.2 (Graph Intelligence) | 68 | Passing |
| **Total** | **135** | **All Passing** |

---

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | System design and data flow |
| [PRD Phase 5.1](docs/prd-phase5-part1.md) | Graph foundation specification |
| [PRD Phase 5.2](docs/prd-phase5-part2-completion.md) | Graph intelligence implementation |
| [PRD Phase 6.1](docs/prd-phase6-part1.md) | Agent OS foundation |
| [PRD Phase 6.2](docs/prd-phase6-part2.md) | Agent OS advanced features |

---

## 🛠️ CLI Reference

### Core Commands

| Command | Description |
|---------|-------------|
| `dmm init` | Initialize DMM in a project |
| `dmm index` | Index all memory files |
| `dmm query <text>` | Semantic search for memories |
| `dmm assemble` | Assemble context pack |
| `dmm boot` | Run boot sequence |

### Write-Back Commands

| Command | Description |
|---------|-------------|
| `dmm write propose` | Propose new memory |
| `dmm write review` | Review pending proposals |
| `dmm write commit` | Commit approved proposals |

### Graph Commands (Phase 5)

| Command | Description |
|---------|-------------|
| `dmm graph status` | Show graph statistics |
| `dmm graph extract` | Extract relationships |
| `dmm graph infer` | Run inference engine |
| `dmm graph viz` | Generate visualization |
| `dmm graph extract-stats` | Show extraction stats |

### Agent OS Commands (Phase 6 - Planned)

| Command | Description |
|---------|-------------|
| `dmm skill list\|show\|enable` | Manage skills |
| `dmm tool list\|show\|check` | Manage tools |
| `dmm agent list\|show\|match` | Manage agents |
| `dmm task create\|run\|status` | Manage tasks |

---

## Configuration

### Project Configuration

```json
// .dmm/config.json
{
  "embedding_model": "text-embedding-3-small",
  "default_scope": "project",
  "token_budget": 8000,
  "graph": {
    "auto_extract": true,
    "extractors": ["tag", "temporal"],
    "min_edge_weight": 0.3
  }
}
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DMM_HOME` | Global DMM directory | `~/.dmm` |
| `DMM_EMBEDDING_MODEL` | Embedding model | `text-embedding-3-small` |
| `ANTHROPIC_API_KEY` | API key for LLM features | Required for write-back |

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Development Setup

```bash
# Clone and install
git clone https://github.com/your-org/claude-memory.git
cd claude-memory
poetry install --with dev

# Run tests
poetry run pytest

# Type checking
poetry run mypy src/

# Linting
poetry run ruff check src/
```

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Acknowledgments

- [Kuzu](https://kuzudb.com/) - Embedded graph database
- [Anthropic](https://anthropic.com/) - Claude AI
- [LangChain](https://langchain.com/) - LLM tooling inspiration

---

## Roadmap

```
2025 Q4                    2026 Q1                    2026 Q2
   │                          │                          │
   ▼                          ▼                          ▼
┌──────────┐             ┌──────────┐             ┌──────────┐
│ Phase    │             │ Phase 5  │             │ Phase 6  │
│  1-4     │────────────▶│ Graph    │────────────▶│ Agent OS │
│ Core     │             │ Intel.   │             │          │
└──────────┘             └──────────┘             └──────────┘
                                                  

Future:
├── Federated learning between DMM instances
├── Active research - autonomous investigation
├── Skill marketplace - community contributions
├── Memory inheritance - project templates
└── Real-time collaboration
```

---

<p align="center">
  <b>DMM - Making AI agents remember, reason, and improve.</b>
</p>
