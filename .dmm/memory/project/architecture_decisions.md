---
id: mem_2025_01_01_030
tags: [architecture, decisions, design, adr]
scope: project
priority: 0.9
confidence: stable
status: active
created: 2025-01-01
---

# Architecture Decision: Memory Storage

This document records the architectural decision to use SQLite with
custom vector similarity for the memory storage layer.

## Context

The DMM system requires persistent storage for memory embeddings with
efficient similarity search capabilities. Options considered included
dedicated vector databases, PostgreSQL with pgvector, and SQLite.

## Decision

We chose SQLite with a custom cosine similarity implementation for the
following reasons:

1. Zero external dependencies - no separate database server required
2. Single file storage - easy backup, migration, and version control
3. Sufficient performance for expected workloads (< 10,000 memories)
4. Familiar SQL interface for metadata queries

## Consequences

This decision means we handle vector operations in application code
rather than the database. For very large memory collections, we may
need to revisit this decision and consider sqlite-vss or an external
vector database.

## Alternatives Considered

- Qdrant: Excellent performance but adds deployment complexity
- ChromaDB: Good option but less mature ecosystem
- PostgreSQL + pgvector: Overkill for single-user local operation
