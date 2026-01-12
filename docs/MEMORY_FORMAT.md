# Memory File Format Specification

This document defines the format and requirements for DMM memory files.

## Overview

Memory files are Markdown documents with YAML frontmatter. Each file represents
a single atomic unit of knowledge that can be independently retrieved based on
semantic relevance.

## File Structure
```markdown
---
# YAML Frontmatter (required)
id: mem_YYYY_MM_DD_NNN
tags: [tag1, tag2, tag3]
scope: project
priority: 0.8
confidence: active
status: active
---

# Title (H1 heading)

Body content in Markdown format...
```

## Frontmatter Schema

### Required Fields

#### id

Unique identifier for the memory.

- **Type**: string
- **Format**: `mem_YYYY_MM_DD_NNN`
  - `YYYY`: 4-digit year
  - `MM`: 2-digit month
  - `DD`: 2-digit day
  - `NNN`: 3-digit sequence number
```yaml
id: mem_2025_01_15_001
```

#### tags

Semantic tags for retrieval and categorization.

- **Type**: array of strings
- **Minimum**: 1 tag recommended
- **Best Practice**: Use 3-7 specific, descriptive tags
```yaml
tags: [authentication, jwt, security, api]
```

#### scope

The scope determines retrieval behavior and directory location.

- **Type**: enum
- **Values**:
  - `baseline` - Always included in every query
  - `global` - Cross-project stable knowledge
  - `agent` - Agent behavior and style rules
  - `project` - Project-specific context
  - `ephemeral` - Temporary findings (can expire)
```yaml
scope: project
```

#### priority

Influences ranking in retrieval results.

- **Type**: float
- **Range**: 0.0 to 1.0
- **Default**: 0.5
- **Guidelines**:
  - 1.0: Critical, must-see context
  - 0.7-0.9: Important context
  - 0.4-0.6: Normal relevance
  - 0.1-0.3: Background information
```yaml
priority: 0.8
```

#### confidence

Indicates the stability of the information.

- **Type**: enum
- **Values**:
  - `experimental` - Unverified, may change
  - `active` - Current and maintained
  - `stable` - Well-established, rarely changes
  - `deprecated` - Outdated, pending removal
```yaml
confidence: active
```

#### status

Current lifecycle status.

- **Type**: enum
- **Values**:
  - `active` - In use, included in retrieval
  - `deprecated` - Excluded from retrieval by default
```yaml
status: active
```

### Optional Fields

#### created

Creation date of the memory.

- **Type**: date (YYYY-MM-DD)
```yaml
created: 2025-01-15
```

#### last_used

Last time this memory was retrieved.

- **Type**: date or datetime
- **Note**: Populated automatically by usage tracking (Phase 2)
```yaml
last_used: 2025-01-16
```

#### usage_count

Number of times retrieved.

- **Type**: integer
- **Note**: Populated automatically by usage tracking (Phase 2)
```yaml
usage_count: 42
```

#### supersedes

IDs of memories this one replaces.

- **Type**: array of strings
- **Usage**: When updating information, reference the old memory
```yaml
supersedes: [mem_2024_06_01_005, mem_2024_08_15_012]
```

#### related

IDs of related memories.

- **Type**: array of strings
- **Usage**: Link conceptually related memories for conflict detection
```yaml
related: [mem_2025_01_10_003, mem_2025_01_12_007]
```

#### expires

Auto-deprecation date for ephemeral memories.

- **Type**: date (YYYY-MM-DD)
- **Required for**: ephemeral scope (recommended)
```yaml
expires: 2025-02-15
```

## Content Guidelines

### Title

The first H1 heading (`# Title`) becomes the memory title.

- **Required**: Yes (warning if missing)
- **Best Practice**: Clear, descriptive, action-oriented
```markdown
# JWT Authentication Implementation
```

### Body

The body contains the memory content in Markdown format.

#### Token Count

- **Minimum**: 300 tokens (warning if below)
- **Maximum**: 800 tokens (warning if above)
- **Hard Limit**: 2000 tokens (error if exceeded)

#### Single Concept

Each memory should focus on ONE concept:

**Good**:
- "Database Connection Pooling Configuration"
- "API Error Response Format"
- "User Authentication Flow"

**Bad**:
- "Database and API and Authentication" (too broad)
- "Various Project Notes" (unfocused)

#### Self-Contained

Memories should be understandable without external context:

- Include necessary background
- Define project-specific terms
- Reference related memories by ID if needed

### Markdown Features

Supported Markdown features:

- Headings (H1-H6)
- Paragraphs
- Lists (ordered and unordered)
- Code blocks with syntax highlighting
- Inline code
- Bold and italic
- Links
- Tables

## Directory Structure

Memory files must be placed in the appropriate scope directory:
```
.dmm/memory/
  baseline/       <- scope: baseline
  global/         <- scope: global
  agent/          <- scope: agent
  project/        <- scope: project
  ephemeral/      <- scope: ephemeral
  deprecated/     <- archived memories (excluded)
```

Subdirectories within scopes are allowed:
```
.dmm/memory/
  project/
    auth/
      jwt_tokens.md
      session_management.md
    database/
      connection_pool.md
      migrations.md
```

## Composite Embedding

For retrieval, memories are embedded as a composite of:
```
[DIRECTORY] {directory path}
[TITLE] {extracted title}
[TAGS] {comma-separated tags}
[SCOPE] {scope value}
[CONTENT] {body text}
```

This structure enables:
- Directory-level routing (stage 1)
- Content-level ranking (stage 2)
- Tag-based relevance boosting

## Validation Rules

### Errors (Parsing Fails)

1. Missing required frontmatter fields
2. Invalid enum values
3. Token count exceeds 2000
4. Malformed YAML

### Warnings (Parsing Succeeds)

1. Token count below 300
2. Token count above 800
3. Missing H1 title
4. Ephemeral scope without expires field
5. Deprecated confidence but active status
6. Empty tags list

## Examples

### Minimal Valid Memory
```markdown
---
id: mem_2025_01_15_001
tags: [example]
scope: project
priority: 0.5
confidence: active
status: active
---

# Minimal Example

This is a minimal valid memory file with only required fields.
Content should be expanded to meet the 300 token minimum.
```

### Complete Memory
```markdown
---
id: mem_2025_01_15_002
tags: [authentication, security, jwt, api, tokens]
scope: project
priority: 0.9
confidence: stable
status: active
created: 2025-01-15
last_used: 2025-01-16
usage_count: 15
supersedes: [mem_2024_06_01_005]
related: [mem_2025_01_10_003, mem_2025_01_12_007]
---

# JWT Authentication Strategy

Our API uses JSON Web Tokens (JWT) for stateless authentication.
This document describes the implementation details and security
considerations.

## Token Structure

Tokens use the RS256 algorithm with rotating keys. The payload
contains user ID, roles, and expiration time.

## Security Measures

- Tokens expire after 1 hour
- Refresh tokens stored in httpOnly cookies
- Key rotation occurs weekly
- Token revocation via deny list

## Implementation

See the auth module in src/auth/ for implementation details.
The JWT middleware validates tokens on each request.
```

### Ephemeral Memory
```markdown
---
id: mem_2025_01_15_003
tags: [debugging, temporary, session]
scope: ephemeral
priority: 0.3
confidence: experimental
status: active
created: 2025-01-15
expires: 2025-01-22
---

# Current Debugging Session Notes

Temporary notes from debugging the connection timeout issue.
This memory will auto-expire in one week.

## Findings

- Timeouts occur under high load (>1000 req/s)
- Connection pool exhaustion suspected
- Increased pool size from 10 to 50 as test

## Next Steps

Monitor metrics for 24 hours before permanent fix.
```
