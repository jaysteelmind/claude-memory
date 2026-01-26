# DMM Documentation

Welcome to the Dynamic Markdown Memory (DMM) documentation.

## Overview

DMM is a cognitive memory system for AI agents that evolves from simple context retrieval into a full Agent Operating System. It replaces monolithic instruction files with a semantic, hierarchical collection of atomic markdown micro-files.

## Documentation Sections

### Getting Started

- [Quick Start Guide](QUICKSTART.md) - Get up and running in 5 minutes
- [Architecture Overview](ARCHITECTURE.md) - Understand how DMM works

### API Reference

- [Core API](api/core.md) - Memory models, constants, and exceptions
- [Graph API](api/graph.md) - Knowledge graph operations
- [AgentOS API](api/agentos/index.md) - Agent Operating System components
- [CLI Reference](CLI_REFERENCE.md) - Command-line interface

### Tutorials

Step-by-step guides for common tasks:

1. [Basic Memory Operations](tutorials/01-basic-memory.md)
2. [Creating Custom Agents](tutorials/02-creating-agents.md)
3. [Defining Skills](tutorials/03-defining-skills.md)
4. [Task Management](tutorials/04-task-management.md)
5. [Multi-Agent Patterns](tutorials/05-multi-agent.md)
6. [Self-Modification](tutorials/06-self-modification.md)

### Guides

In-depth guides for advanced topics:

- [Deployment Guide](guides/deployment.md)
- [Configuration Guide](guides/configuration.md)
- [Security Guide](guides/security.md)
- [Troubleshooting Guide](TROUBLESHOOTING.md)

### Reference

- [Memory File Format](MEMORY_FORMAT.md)
- [Examples](../examples/README.md)

## System Requirements

- Python 3.11+
- Poetry 1.7+
- SQLite 3.35+ (for JSON and VSS support)

## Quick Links

- [GitHub Repository](https://github.com/anthropic/claude-memory)
- [Issue Tracker](https://github.com/anthropic/claude-memory/issues)
- [Changelog](../CHANGELOG.md)

## Version

This documentation covers DMM v3.0 (Phase 6 Complete).
