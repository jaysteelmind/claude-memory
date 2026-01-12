"""System prompts for the reviewer agent."""

REVIEWER_SYSTEM_PROMPT = """You are a Memory Reviewer Agent for the Dynamic Markdown Memory (DMM) system.

Your role is to review proposed memory files and ensure they meet quality standards.

## Memory File Requirements

1. **Frontmatter**: Must include id, tags, scope, priority, confidence, status
2. **Single Concept**: Each memory should focus on one main topic
3. **Token Count**: Should be 300-800 tokens (soft limits)
4. **Self-Contained**: Must be understandable without external context
5. **Actionable**: Should provide clear, usable information
6. **Justified**: Should include rationale for decisions/constraints

## Scope Hierarchy

- baseline: Critical context, always loaded (most restrictive)
- global: Stable truths, long-lived conventions
- agent: Behavioral rules, tone, workflows
- project: Project-specific decisions, constraints
- ephemeral: Short-lived findings (least restrictive)

## Your Task

Review the proposed memory and provide:
1. Whether it passes quality checks
2. Any issues found (errors, warnings, suggestions)
3. Your confidence in the assessment (0.0 to 1.0)
4. Recommendation: APPROVE, REJECT, MODIFY, or DEFER

Be thorough but not overly strict. The goal is to maintain quality while allowing useful memories to be added.
"""

QUALITY_ASSESSMENT_PROMPT = """Assess the quality of this proposed memory:
```markdown
{content}
```

Target path: {target_path}
Proposal reason: {reason}

Evaluate:
1. Is the content focused on a single concept?
2. Is the title descriptive and accurate?
3. Are the tags relevant and specific?
4. Is there sufficient context/rationale?
5. Is the scope appropriate for the content?
6. Is the priority reasonable?

Respond with a JSON object:
{{
    "passes_quality": true/false,
    "confidence": 0.0-1.0,
    "issues": [
        {{"code": "string", "message": "string", "severity": "error|warning|info"}}
    ],
    "suggestions": ["string"],
    "recommendation": "APPROVE|REJECT|MODIFY|DEFER"
}}
"""

COHERENCE_CHECK_PROMPT = """Check if the title, tags, and content of this memory are coherent:

Title: {title}
Tags: {tags}
Scope: {scope}

Content:
```
{body}
```

Questions:
1. Does the title accurately describe the content?
2. Do the tags reflect the main topics in the content?
3. Is the scope appropriate for this type of information?
4. Is there any mismatch between what the title promises and what the content delivers?

Respond with a JSON object:
{{
    "is_coherent": true/false,
    "title_accuracy": 0.0-1.0,
    "tag_relevance": 0.0-1.0,
    "scope_appropriateness": 0.0-1.0,
    "issues": ["string"],
    "suggestions": ["string"]
}}
"""

SINGLE_CONCEPT_CHECK_PROMPT = """Analyze if this memory focuses on a single concept or tries to cover multiple topics:
```markdown
{content}
```

A memory should be atomic - covering one concept thoroughly rather than multiple concepts superficially.

Signs of multiple concepts:
- Multiple H1 headings
- Unrelated sections
- Topic shifts within the content
- Content that could be split into independent memories

Respond with a JSON object:
{{
    "is_single_concept": true/false,
    "detected_concepts": ["string"],
    "concept_count": number,
    "can_be_split": true/false,
    "split_suggestions": ["string"]
}}
"""

DUPLICATE_ASSESSMENT_PROMPT = """Compare the proposed memory with this existing memory to assess if they are duplicates:

Proposed Memory:
```markdown
{proposed_content}
```

Existing Memory ({existing_path}):
```markdown
{existing_content}
```

Embedding Similarity: {similarity:.2%}

Determine:
1. Are these semantically the same information?
2. Does the proposed memory add new information?
3. Should the existing memory be updated instead?
4. Are they complementary (both should exist)?

Respond with a JSON object:
{{
    "is_duplicate": true/false,
    "duplicate_type": "exact|semantic|complementary|unrelated",
    "overlap_assessment": "string",
    "recommendation": "REJECT|UPDATE_EXISTING|KEEP_BOTH",
    "reasoning": "string"
}}
"""


def format_quality_prompt(content: str, target_path: str, reason: str) -> str:
    """Format the quality assessment prompt.
    
    Args:
        content: The proposed memory content.
        target_path: The target path for the memory.
        reason: The reason for the proposal.
        
    Returns:
        Formatted prompt string.
    """
    return QUALITY_ASSESSMENT_PROMPT.format(
        content=content,
        target_path=target_path,
        reason=reason,
    )


def format_coherence_prompt(
    title: str,
    tags: list[str],
    scope: str,
    body: str,
) -> str:
    """Format the coherence check prompt.
    
    Args:
        title: The memory title.
        tags: List of tags.
        scope: The memory scope.
        body: The memory body content.
        
    Returns:
        Formatted prompt string.
    """
    return COHERENCE_CHECK_PROMPT.format(
        title=title,
        tags=", ".join(tags),
        scope=scope,
        body=body,
    )


def format_single_concept_prompt(content: str) -> str:
    """Format the single concept check prompt.
    
    Args:
        content: The memory content.
        
    Returns:
        Formatted prompt string.
    """
    return SINGLE_CONCEPT_CHECK_PROMPT.format(content=content)


def format_duplicate_prompt(
    proposed_content: str,
    existing_path: str,
    existing_content: str,
    similarity: float,
) -> str:
    """Format the duplicate assessment prompt.
    
    Args:
        proposed_content: The proposed memory content.
        existing_path: Path of the existing memory.
        existing_content: Content of the existing memory.
        similarity: Embedding similarity score.
        
    Returns:
        Formatted prompt string.
    """
    return DUPLICATE_ASSESSMENT_PROMPT.format(
        proposed_content=proposed_content,
        existing_path=existing_path,
        existing_content=existing_content,
        similarity=similarity,
    )
