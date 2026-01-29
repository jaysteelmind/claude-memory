"""
DMM Memory Proposal Prompt - Template for identifying learnings worth remembering.

This prompt guides Claude to extract memorable information from conversations
and propose appropriate memories for future context.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

MEMORY_WORTHY_PATTERNS: dict[str, dict[str, Any]] = {
    "decision": {
        "indicators": [
            "we decided", "decision is", "agreed to", "going with",
            "chosen approach", "selected", "will use", "opted for",
            "final choice", "determined that",
        ],
        "scope": "project",
        "priority": 0.7,
        "description": "Project decisions and choices",
    },
    "constraint": {
        "indicators": [
            "must not", "cannot", "forbidden", "not allowed", "never",
            "always must", "required to", "mandatory", "restricted",
            "limitation", "constraint", "rule is",
        ],
        "scope": "project",
        "priority": 0.8,
        "description": "Constraints and restrictions",
    },
    "architecture": {
        "indicators": [
            "architecture", "design pattern", "structure is", "organized as",
            "component", "module", "layer", "system design", "data flow",
            "integration", "interface",
        ],
        "scope": "project",
        "priority": 0.7,
        "description": "Architectural decisions and patterns",
    },
    "convention": {
        "indicators": [
            "convention", "standard", "naming", "format", "style guide",
            "best practice", "we follow", "pattern we use", "our approach",
            "coding standard", "guideline",
        ],
        "scope": "global",
        "priority": 0.6,
        "description": "Conventions and standards",
    },
    "preference": {
        "indicators": [
            "i prefer", "i like", "please always", "please never",
            "my preference", "i want", "style preference", "tone",
            "format preference", "communication style",
        ],
        "scope": "agent",
        "priority": 0.6,
        "description": "User preferences and style",
    },
    "solution": {
        "indicators": [
            "solution is", "fix is", "resolved by", "workaround",
            "the answer", "how to fix", "solved by", "approach that works",
            "implementation", "technique",
        ],
        "scope": "project",
        "priority": 0.6,
        "description": "Solutions and implementations",
    },
    "finding": {
        "indicators": [
            "discovered", "found that", "turns out", "learned that",
            "realized", "noticed", "observed", "investigation showed",
            "analysis revealed", "testing showed",
        ],
        "scope": "ephemeral",
        "priority": 0.5,
        "description": "Temporary findings and observations",
    },
    "external": {
        "indicators": [
            "api endpoint", "third party", "external service", "dependency",
            "library", "package", "integration with", "credential",
            "environment variable", "configuration for",
        ],
        "scope": "project",
        "priority": 0.7,
        "description": "External dependencies and integrations",
    },
}

NOT_MEMORY_WORTHY: list[str] = [
    "temporary", "just for now", "quick fix", "hack", "placeholder",
    "todo", "fixme", "will change", "not final", "draft",
    "testing only", "debug", "experiment", "trying",
]


def generate_memory_proposal(conversation_summary: str) -> str:
    """
    Generate a memory proposal prompt for the given conversation.

    This prompt instructs Claude to:
    1. Analyze the conversation for memorable information
    2. Categorize potential memories by type
    3. Propose appropriate memories with metadata

    Args:
        conversation_summary: Summary of the conversation so far

    Returns:
        Formatted prompt template as string
    """
    if not conversation_summary or not conversation_summary.strip():
        return _generate_generic_proposal_prompt()

    conversation_summary = conversation_summary.strip()
    detected_patterns = _detect_memory_patterns(conversation_summary)
    
    return _build_proposal_prompt(conversation_summary, detected_patterns)


def _detect_memory_patterns(text: str) -> list[dict[str, Any]]:
    """Detect potential memory-worthy patterns in text."""
    text_lower = text.lower()
    detected: list[dict[str, Any]] = []

    for pattern_name, pattern_info in MEMORY_WORTHY_PATTERNS.items():
        indicators = pattern_info["indicators"]
        matches = [ind for ind in indicators if ind in text_lower]

        if matches:
            detected.append({
                "type": pattern_name,
                "scope": pattern_info["scope"],
                "priority": pattern_info["priority"],
                "description": pattern_info["description"],
                "matched_indicators": matches[:3],
            })

    exclusions = [ex for ex in NOT_MEMORY_WORTHY if ex in text_lower]
    if exclusions:
        for item in detected:
            item["caution"] = f"Contains exclusion terms: {', '.join(exclusions[:3])}"

    return detected


def _build_proposal_prompt(
    conversation_summary: str,
    detected_patterns: list[dict[str, Any]],
) -> str:
    """Build the complete memory proposal prompt."""
    patterns_section = _format_detected_patterns(detected_patterns)
    
    summary_preview = conversation_summary[:500]
    if len(conversation_summary) > 500:
        summary_preview += "..."

    return f"""## Memory Proposal Analysis

### Conversation Summary
{summary_preview}

### Detected Patterns
{patterns_section}

### Instructions

Analyze this conversation and identify information worth remembering for future sessions.

**Step 1: Identify Memory Candidates**

Look for:
- Decisions made during this conversation
- Constraints or requirements discovered
- Architectural patterns established
- User preferences expressed
- Solutions to problems found
- Important findings or observations

**Step 2: Evaluate Each Candidate**

For each potential memory, assess:
- Is this information stable (not temporary)?
- Will this be useful in future conversations?
- Is this specific enough to be actionable?
- Does this duplicate existing memories?

**Step 3: Propose Memories**

For each worthy candidate, use `dmm_remember()` with:
```
dmm_remember(
    content="<clear, self-contained description>",
    scope="<appropriate scope>",
    tags=["<relevant>", "<tags>"],
    priority=<0.0-1.0>
)
```

**Scope Selection Guide:**
- `baseline`: Critical constraints that must NEVER be violated
- `global`: Stable truths that rarely change
- `agent`: User preferences and communication style
- `project`: Project-specific decisions and patterns
- `ephemeral`: Temporary findings (auto-expire)

**Priority Guide:**
- 0.8-1.0: Critical, affects many decisions
- 0.6-0.7: Important, frequently relevant
- 0.4-0.5: Useful, occasionally relevant
- 0.1-0.3: Minor, rarely needed

### Do NOT Remember

- Temporary workarounds or hacks
- Information marked as "draft" or "not final"
- Debug-only configurations
- Personally identifiable information
- Secrets, passwords, or API keys
- Information already in existing memories

### Output Format

After analysis, either:
1. Call `dmm_remember()` for each worthy memory
2. State "No new memories needed" if nothing qualifies

Briefly inform the user what was remembered (without details):
"I have noted that for future reference." """


def _format_detected_patterns(patterns: list[dict[str, Any]]) -> str:
    """Format detected patterns for display."""
    if not patterns:
        return "*No specific patterns detected. Manual analysis required.*"

    lines: list[str] = []
    for pattern in patterns:
        pattern_type = pattern["type"].replace("_", " ").title()
        scope = pattern["scope"]
        priority = pattern["priority"]
        description = pattern["description"]
        indicators = ", ".join(pattern["matched_indicators"])

        lines.append(f"**{pattern_type}** (suggested scope: {scope}, priority: {priority})")
        lines.append(f"  - {description}")
        lines.append(f"  - Matched: {indicators}")

        if "caution" in pattern:
            lines.append(f"  - Caution: {pattern['caution']}")

        lines.append("")

    return "\n".join(lines)


def _generate_generic_proposal_prompt() -> str:
    """Generate a generic prompt when no conversation is provided."""
    return """## Memory Proposal Guidelines

### When to Create Memories

Create memories when you encounter:

1. **Decisions** - Choices made about approach, technology, or design
2. **Constraints** - Rules, limitations, or requirements
3. **Patterns** - Recurring solutions or architectural choices
4. **Preferences** - User's style, format, or communication preferences
5. **Solutions** - Fixes to problems that may recur
6. **Integrations** - External services, APIs, or dependencies

### Memory Creation Template
```
dmm_remember(
    content="<what to remember>",
    scope="project",  # or baseline/global/agent/ephemeral
    tags=["tag1", "tag2"],
    priority=0.6  # 0.0 to 1.0
)
```

### Scope Selection

| Scope | Use For | Examples |
|-------|---------|----------|
| baseline | Non-negotiable constraints | "No eval() in code" |
| global | Stable conventions | "Use snake_case for Python" |
| agent | User preferences | "Prefer concise responses" |
| project | Project decisions | "Using PostgreSQL for DB" |
| ephemeral | Temporary findings | "Bug in v2.3.1 of library" |

### Do NOT Create Memories For

- Temporary or draft information
- Information likely to change soon
- Debug or testing configurations
- Secrets or sensitive data
- Duplicates of existing memories

### Best Practices

- Keep memories atomic (one concept each)
- Make content self-contained
- Use descriptive tags for retrieval
- Set appropriate priority levels
- Inform user briefly: "I have noted that for future reference." """
