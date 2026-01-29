"""
DMM Context Injection Prompt - Template for automatic context retrieval.

This prompt guides Claude to query memories and incorporate them
before responding to user requests, ensuring consistent context awareness.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

TASK_CATEGORIES: dict[str, list[str]] = {
    "code_implementation": [
        "implement", "create", "build", "write", "develop", "code",
        "function", "class", "module", "component", "feature",
    ],
    "code_review": [
        "review", "check", "analyze", "audit", "inspect", "examine",
        "refactor", "improve", "optimize",
    ],
    "debugging": [
        "debug", "fix", "error", "bug", "issue", "problem", "broken",
        "failing", "crash", "exception",
    ],
    "architecture": [
        "architecture", "design", "structure", "pattern", "organize",
        "system", "layout", "schema", "model",
    ],
    "documentation": [
        "document", "docs", "readme", "explain", "describe", "comment",
        "tutorial", "guide", "specification",
    ],
    "testing": [
        "test", "spec", "coverage", "unittest", "pytest", "mock",
        "fixture", "assertion", "verify",
    ],
    "configuration": [
        "config", "configure", "setup", "install", "environment",
        "settings", "options", "parameters",
    ],
    "database": [
        "database", "sql", "query", "migration", "schema", "table",
        "index", "transaction", "orm",
    ],
    "api": [
        "api", "endpoint", "rest", "graphql", "request", "response",
        "http", "route", "handler",
    ],
    "security": [
        "security", "auth", "authentication", "authorization", "permission",
        "encrypt", "token", "credential", "password",
    ],
    "deployment": [
        "deploy", "release", "production", "staging", "ci", "cd",
        "pipeline", "container", "server",
    ],
    "general": [],
}


def generate_context_injection(task: str) -> str:
    """
    Generate a context injection prompt for the given task.

    This prompt instructs Claude to:
    1. Query relevant memories before responding
    2. Incorporate retrieved context into the response
    3. Note any conflicts or gaps in knowledge

    Args:
        task: Description of the current task or user request

    Returns:
        Formatted prompt template as string
    """
    if not task or not task.strip():
        return _generate_generic_prompt()

    task = task.strip()
    category = _categorize_task(task)
    keywords = _extract_keywords(task)
    query_suggestions = _generate_query_suggestions(task, category, keywords)

    return _build_prompt(task, category, query_suggestions)


def _categorize_task(task: str) -> str:
    """Categorize the task based on keywords."""
    task_lower = task.lower()

    category_scores: dict[str, int] = {}

    for category, keywords in TASK_CATEGORIES.items():
        if not keywords:
            continue

        score = sum(1 for kw in keywords if kw in task_lower)
        if score > 0:
            category_scores[category] = score

    if not category_scores:
        return "general"

    return max(category_scores, key=category_scores.get)


def _extract_keywords(task: str) -> list[str]:
    """Extract significant keywords from the task description."""
    stop_words = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "must", "shall", "can", "need", "dare",
        "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by",
        "from", "as", "into", "through", "during", "before", "after", "above",
        "below", "between", "under", "again", "further", "then", "once", "here",
        "there", "when", "where", "why", "how", "all", "each", "few", "more",
        "most", "other", "some", "such", "no", "nor", "not", "only", "own",
        "same", "so", "than", "too", "very", "just", "and", "but", "if", "or",
        "because", "until", "while", "this", "that", "these", "those", "i",
        "me", "my", "myself", "we", "our", "you", "your", "he", "him", "she",
        "her", "it", "its", "they", "them", "what", "which", "who", "whom",
        "please", "help", "want", "like", "make", "get", "put", "see", "know",
    }

    words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", task.lower())

    keywords = [w for w in words if w not in stop_words and len(w) > 2]

    seen: set[str] = set()
    unique_keywords: list[str] = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_keywords.append(kw)

    return unique_keywords[:10]


def _generate_query_suggestions(
    task: str,
    category: str,
    keywords: list[str],
) -> list[str]:
    """Generate suggested queries based on task analysis."""
    suggestions: list[str] = []

    if keywords:
        primary_query = " ".join(keywords[:4])
        suggestions.append(primary_query)

    category_queries = {
        "code_implementation": "coding standards conventions patterns",
        "code_review": "code review guidelines best practices",
        "debugging": "error handling debugging patterns",
        "architecture": "architecture design decisions patterns",
        "documentation": "documentation standards templates",
        "testing": "testing requirements coverage standards",
        "configuration": "configuration environment setup",
        "database": "database schema conventions queries",
        "api": "api design endpoints conventions",
        "security": "security requirements authentication",
        "deployment": "deployment process requirements",
    }

    if category in category_queries:
        suggestions.append(category_queries[category])

    if len(task) <= 50:
        suggestions.insert(0, task)

    return suggestions[:3]


def _build_prompt(
    task: str,
    category: str,
    query_suggestions: list[str],
) -> str:
    """Build the complete context injection prompt."""
    suggestions_text = "\n".join(f"  - `{q}`" for q in query_suggestions)

    return f"""## Context Injection for Task

**Task:** {task}
**Category:** {category}

### Instructions

Before responding to this task, retrieve relevant context from DMM:

1. **Query for relevant memories:**
{suggestions_text}

2. **Review the retrieved context for:**
   - Project-specific constraints or requirements
   - Established patterns or conventions
   - Previous decisions related to this task
   - Known issues or considerations

3. **Incorporate context into your response:**
   - Follow established patterns and conventions
   - Respect documented constraints
   - Reference relevant prior decisions
   - Flag any conflicts with retrieved information

4. **After completing the task:**
   - If you learned something new worth remembering, use `dmm_remember()`
   - If you found outdated information, use `dmm_forget()`
   - If you detected conflicts, report them to the user

### Context Integration Guidelines

- **Baseline memories** are non-negotiable constraints
- **Project memories** contain project-specific decisions
- **Agent memories** define behavioral preferences
- **Ephemeral memories** are temporary findings

Do not mention to the user that you queried memory unless:
- They explicitly ask about project context
- There is a relevant conflict to report
- The retrieved context significantly affects your response

Proceed with the task using the retrieved context."""


def _generate_generic_prompt() -> str:
    """Generate a generic prompt when no task is provided."""
    return """## Context Injection

### Instructions

Before responding to user requests, retrieve relevant context from DMM:

1. **Identify the topic or task** from the user's message
2. **Query DMM** with relevant keywords: `dmm_query("<topic>")`
3. **Review retrieved memories** for constraints, patterns, and decisions
4. **Incorporate context** into your response silently
5. **Capture new learnings** with `dmm_remember()` when appropriate

### Memory Priority

1. **Baseline**: Always applies, non-negotiable
2. **Global**: Stable truths and conventions
3. **Agent**: Behavioral preferences
4. **Project**: Project-specific decisions
5. **Ephemeral**: Temporary findings

### Best Practices

- Query at the start of complex tasks
- Do not announce memory operations to users
- Respect baseline constraints absolutely
- Report conflicts when detected
- Remember significant learnings for future sessions"""
