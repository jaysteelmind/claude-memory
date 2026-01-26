# Tutorial 3: Defining Skills

Learn how to define and register skills that agents can use.

## Prerequisites

- Completed [Tutorial 2: Creating Custom Agents](02-creating-agents.md)

## 1. What Are Skills?

Skills are declarative definitions of agent capabilities:
```
┌─────────────────────────────────────┐
│              Skill                  │
├─────────────────────────────────────┤
│  Identity                           │
│  ├─ id: unique identifier           │
│  ├─ name: human-readable            │
│  └─ version: semantic version       │
├─────────────────────────────────────┤
│  Interface                          │
│  ├─ inputs: required parameters     │
│  └─ outputs: produced results       │
├─────────────────────────────────────┤
│  Requirements                       │
│  ├─ dependencies: other skills      │
│  ├─ tools: required tools           │
│  └─ memories: context needs         │
├─────────────────────────────────────┤
│  Execution                          │
│  ├─ timeout                         │
│  ├─ retry policy                    │
│  └─ parallelization                 │
└─────────────────────────────────────┘
```

## 2. Skill YAML Structure

Create a skill file in `.dmm/skills/`:
```yaml
# .dmm/skills/custom/code_lint.skill.yaml

# Identity
id: skill_code_lint
name: Code Linting
version: "1.0.0"
description: |
  Runs static analysis on Python code using ruff.
  Reports style issues, potential bugs, and complexity warnings.

# Classification  
category: analysis
tags:
  - code
  - linting
  - quality
  - python

# Enable/disable
enabled: true

# Input parameters
inputs:
  - name: file_path
    type: string
    required: true
    description: Path to Python file or directory
  
  - name: fix
    type: boolean
    required: false
    default: false
    description: Whether to auto-fix issues
  
  - name: rules
    type: array
    required: false
    default: ["E", "F", "W"]
    description: Rule categories to enable

# Output parameters
outputs:
  - name: issues
    type: array
    description: List of detected issues
  
  - name: fixed_count
    type: integer
    description: Number of auto-fixed issues
  
  - name: summary
    type: string
    description: Human-readable summary

# Dependencies
dependencies:
  skills: []  # No prerequisite skills
  tools:
    - tool_ruff  # Requires ruff CLI tool

# Memory context
memory_requirements:
  - scope: project
    tags:
      - coding-standards
      - linting-config
    required: false  # Nice to have, not mandatory

# Execution settings
execution:
  timeout_seconds: 60
  retry_count: 1
  retry_delay_seconds: 2
  parallel_safe: true  # Can run multiple instances
```

## 3. Input Types

Skills support these input types:

| Type | YAML | Python | Example |
|------|------|--------|---------|
| string | `type: string` | `str` | `"src/main.py"` |
| integer | `type: integer` | `int` | `100` |
| number | `type: number` | `float` | `0.75` |
| boolean | `type: boolean` | `bool` | `true` |
| array | `type: array` | `list` | `["a", "b"]` |
| object | `type: object` | `dict` | `{key: value}` |

### Input Validation
```yaml
inputs:
  - name: threshold
    type: number
    required: true
    description: Confidence threshold
    # Validation (optional)
    minimum: 0.0
    maximum: 1.0
    
  - name: format
    type: string
    required: false
    default: "json"
    description: Output format
    # Enum constraint
    enum: ["json", "text", "html"]
```

## 4. Skill Categories

Organize skills by category:

| Category | Purpose | Examples |
|----------|---------|----------|
| analysis | Inspect and analyze | code_lint, complexity_check |
| generation | Create content | doc_generate, code_generate |
| retrieval | Find information | memory_search, web_search |
| transformation | Convert data | format_convert, refactor |
| review | Evaluate quality | code_review, security_scan |
| planning | Create plans | task_decompose, roadmap |
| communication | Send messages | notify, report |
| maintenance | System upkeep | cleanup, optimize |

## 5. Skill Dependencies

### Skill-to-Skill Dependencies
```yaml
id: skill_full_review
name: Full Code Review

dependencies:
  skills:
    - skill_code_lint      # Run linting first
    - skill_complexity     # Then complexity analysis
    - skill_security_scan  # Then security scan
```

The system executes skills in dependency order.

### Tool Dependencies
```yaml
dependencies:
  tools:
    - tool_git        # Requires git CLI
    - tool_python     # Requires Python runtime
```

## 6. Memory Requirements

Skills can request memory context:
```yaml
memory_requirements:
  # Required memory
  - scope: project
    tags:
      - coding-standards
    required: true  # Fail if not found
  
  # Optional memory
  - scope: global
    tags:
      - python-best-practices
    required: false  # Continue without
  
  # Agent-specific
  - scope: agent
    tags:
      - review-preferences
    required: false
```

## 7. Execution Configuration
```yaml
execution:
  # Time limit
  timeout_seconds: 120
  
  # Retry policy
  retry_count: 3
  retry_delay_seconds: 5
  
  # Parallelization
  parallel_safe: true
  
  # Resource hints (optional)
  resource_hints:
    memory_mb: 512
    cpu_intensive: false
```

## 8. Loading and Using Skills

### Load Skills
```python
from pathlib import Path
from dmm.agentos import SkillRegistry

registry = SkillRegistry(Path(".dmm/skills"))
skills = registry.load_all()

print(f"Loaded {len(skills)} skills")
for skill in skills:
    print(f"  - {skill.id}: {skill.name}")
```

### Find Skills
```python
# By ID
lint_skill = registry.find_by_id("skill_code_lint")

# By tags
analysis_skills = registry.find_by_tags(["analysis", "code"])

# By category
review_skills = registry.find_by_category("review")

# Search
matching = registry.search("security")
```

### Check Dependencies
```python
# Check if skill can run
check = registry.check_dependencies(
    skill_id="skill_full_review",
    available_tools=["tool_git", "tool_python"],
)

if check.satisfied:
    print("All dependencies met!")
else:
    print(f"Missing skills: {check.missing_skills}")
    print(f"Missing tools: {check.missing_tools}")
```

### Get Execution Order
```python
# Get dependency-ordered list
order = registry.get_execution_order([
    "skill_full_review",
    "skill_report_generation",
])

for skill in order:
    print(f"Execute: {skill.name}")
```

## 9. Complex Skill Example

A comprehensive skill definition:
```yaml
# .dmm/skills/custom/security_audit.skill.yaml

id: skill_security_audit
name: Security Audit
version: "2.1.0"
description: |
  Comprehensive security audit for Python applications.
  
  Checks for:
  - Dependency vulnerabilities (using safety)
  - Code security issues (using bandit)
  - Secrets in code
  - Insecure configurations

category: review
tags:
  - security
  - audit
  - vulnerabilities
  - compliance

enabled: true

inputs:
  - name: project_path
    type: string
    required: true
    description: Root path of the project
  
  - name: scan_dependencies
    type: boolean
    required: false
    default: true
    description: Scan dependencies for vulnerabilities
  
  - name: scan_code
    type: boolean
    required: false
    default: true
    description: Scan code for security issues
  
  - name: scan_secrets
    type: boolean
    required: false
    default: true
    description: Scan for hardcoded secrets
  
  - name: severity_threshold
    type: string
    required: false
    default: "medium"
    description: Minimum severity to report
    enum: ["low", "medium", "high", "critical"]
  
  - name: output_format
    type: string
    required: false
    default: "json"
    description: Report format
    enum: ["json", "html", "markdown"]

outputs:
  - name: vulnerabilities
    type: array
    description: List of found vulnerabilities
  
  - name: code_issues
    type: array
    description: Security issues in code
  
  - name: secrets_found
    type: array
    description: Potential secrets detected
  
  - name: risk_score
    type: number
    description: Overall risk score (0-100)
  
  - name: report
    type: string
    description: Formatted security report
  
  - name: recommendations
    type: array
    description: Prioritized fix recommendations

dependencies:
  skills:
    - skill_code_analysis  # Need code structure first
  tools:
    - tool_bandit
    - tool_safety
    - tool_detect_secrets

memory_requirements:
  - scope: project
    tags:
      - security-policy
      - allowed-packages
    required: false
  
  - scope: global
    tags:
      - security-best-practices
      - owasp-guidelines
    required: false

execution:
  timeout_seconds: 300
  retry_count: 2
  retry_delay_seconds: 10
  parallel_safe: false  # Modifies files during scan
  
  resource_hints:
    memory_mb: 1024
    cpu_intensive: true
```

## 10. Skill Validation

Validate skill definitions:
```python
from dmm.agentos.skills import SkillValidator

validator = SkillValidator()

# Validate single skill
errors = validator.validate_file(Path("skills/my_skill.skill.yaml"))
if errors:
    for error in errors:
        print(f"Error: {error}")
else:
    print("Skill is valid!")

# Validate all skills
all_errors = validator.validate_directory(Path(".dmm/skills"))
```

### Common Validation Errors

| Error | Cause | Fix |
|-------|-------|-----|
| Missing required field | `id` or `name` not set | Add required fields |
| Invalid input type | Unknown type value | Use supported type |
| Circular dependency | Skill depends on itself | Remove circular ref |
| Unknown tool | Tool not registered | Register tool first |

## 11. Skill Best Practices

### Naming Conventions
```yaml
# Good
id: skill_code_review
id: skill_dependency_scan
id: skill_report_generate

# Bad
id: CodeReview        # Should be snake_case
id: review            # Too generic
id: my_skill_v2       # Version in ID
```

### Input Design
```yaml
# Good - clear, typed, documented
inputs:
  - name: file_path
    type: string
    required: true
    description: Absolute or relative path to Python file

# Bad - vague, untyped
inputs:
  - name: input
    type: object
    description: Input data
```

### Output Design
```yaml
# Good - specific, actionable
outputs:
  - name: issues
    type: array
    description: |
      List of issues, each with:
      - severity: critical|high|medium|low
      - line: line number
      - message: description
      - suggestion: fix recommendation

# Bad - vague
outputs:
  - name: result
    type: object
```

## Exercises

1. **Create a Formatting Skill**: Define a skill for code formatting
2. **Add Dependencies**: Create a skill that depends on two others
3. **Memory Integration**: Add memory requirements to your skill
4. **Validation**: Write a skill with comprehensive input validation

## Next Steps

- [Tutorial 4: Task Management](04-task-management.md)
- [Skills API Reference](../api/agentos/skills.md)
- [Tools API Reference](../api/agentos/tools.md)
