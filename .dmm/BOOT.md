# DMM Boot Instructions

You have access to a Dynamic Markdown Memory (DMM) system that provides
relevant context for your tasks without loading everything into context.

## What You Always Have

Every Memory Pack includes the **Baseline Pack** - critical context that applies
to all tasks. This is automatically included; you do not need to query for it.

Baseline contains:
- Your identity and role for this project
- Hard constraints that must never be violated
- Foundational decisions and terminology

## How to Retrieve Additional Memory

When you need context beyond baseline, request a Memory Pack:
```
dmm query "<describe your task or question>" --budget 1200
```

This returns a compiled pack with:
- Baseline memories (always included)
- Retrieved memories (semantically relevant to your query)
- File paths for traceability

## When to Retrieve

Request a Memory Pack:
- **At task start** - if baseline does not cover your needs
- **When switching domains** - e.g., from auth to database work
- **After a failure** - you may be missing relevant context
- **Before final outputs** - ensure you have all constraints

## What NOT to Do

- Do not assume memories exist without querying
- Do not query for things already in your baseline
- Do not ignore constraints from retrieved memories

## Current Limitations (Phase 1)

In this phase, you can only **read** memories. Writing, updating, and
deprecating memories will be available in Phase 2.

If you discover something that should be remembered:
- Note it in your response to the user
- Suggest it should be added to memory
- The user can manually create the memory file
