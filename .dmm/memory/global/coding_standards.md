---
id: mem_2025_01_01_010
tags: [coding, standards, conventions, style]
scope: global
priority: 0.7
confidence: stable
status: active
created: 2025-01-01
---

# Coding Standards

This document defines the coding standards that apply across all projects
and codebases. These conventions ensure consistency and maintainability.

## Naming Conventions

Use descriptive names that clearly indicate purpose. Prefer clarity over brevity.
Variable names should be lowercase with underscores for Python, camelCase for
JavaScript and TypeScript.

## Documentation Requirements

All public functions and classes must have docstrings explaining their purpose,
parameters, and return values. Complex logic should have inline comments
explaining the reasoning, not just what the code does.

## Error Handling

Always handle errors explicitly. Never silently swallow exceptions. Log errors
with sufficient context to debug issues. Use custom exception types for
domain-specific errors.

## Code Organization

Keep functions focused on a single responsibility. Limit function length to
improve readability. Group related functionality into modules. Use consistent
file and directory naming patterns.
