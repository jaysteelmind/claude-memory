# Skills API Reference

Skills represent agent capabilities defined in YAML files.

## Module: dmm.agentos.skills

### Skill

Data model for an agent skill.
```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class Skill:
    id: str                    # Unique identifier (skill_*)
    name: str                  # Human-readable name
    version: str               # Semantic version
    description: str           # Detailed description
    category: str              # Category (analysis, generation, etc.)
    tags: list[str]            # Semantic tags
    enabled: bool              # Whether skill is active
    inputs: list[SkillInput]   # Input parameters
    outputs: list[SkillOutput] # Output parameters
    dependencies: SkillDependencies
    memory_requirements: list[MemoryRequirement]
    execution: SkillExecution
```

### SkillInput
```python
@dataclass
class SkillInput:
    name: str
    type: str          # string, integer, boolean, array, object
    required: bool
    default: Any = None
    description: str = ""
```

### SkillOutput
```python
@dataclass
class SkillOutput:
    name: str
    type: str
    description: str = ""
```

### SkillDependencies
```python
@dataclass
class SkillDependencies:
    skills: list[str] = field(default_factory=list)  # Required skill IDs
    tools: list[str] = field(default_factory=list)   # Required tool IDs
```

### MemoryRequirement
```python
@dataclass
class MemoryRequirement:
    scope: str              # baseline, global, agent, project, ephemeral
    tags: list[str]         # Required tags
    required: bool = False  # Whether memory is mandatory
```

### SkillExecution
```python
@dataclass
class SkillExecution:
    timeout_seconds: int = 60
    retry_count: int = 0
    retry_delay_seconds: int = 1
    parallel_safe: bool = True
```

## SkillRegistry

Central registry for skill management.
```python
from pathlib import Path
from dmm.agentos import SkillRegistry

registry = SkillRegistry(Path(".dmm/skills"))
```

### Methods
```python
def load_all(self) -> list[Skill]:
    """Load all skills from the skills directory.
    
    Searches for *.skill.yaml files in:
    - .dmm/skills/core/
    - .dmm/skills/custom/
    
    Returns:
        List of loaded Skill objects.
    """

def reload(self) -> list[Skill]:
    """Reload all skills, clearing cache."""

def find_by_id(self, skill_id: str) -> Skill | None:
    """Find a skill by its ID.
    
    Args:
        skill_id: Skill identifier.
        
    Returns:
        Skill or None if not found.
    """

def find_by_tags(
    self,
    tags: list[str],
    match_all: bool = False,
) -> list[Skill]:
    """Find skills by tags.
    
    Args:
        tags: Tags to search for.
        match_all: If True, skill must have all tags.
        
    Returns:
        List of matching skills.
    """

def find_by_category(self, category: str) -> list[Skill]:
    """Find skills in a category."""

def search(self, query: str) -> list[Skill]:
    """Search skills by name, description, or tags."""

def get_dependencies(
    self,
    skill_id: str,
    transitive: bool = True,
) -> list[Skill]:
    """Get skill dependencies.
    
    Args:
        skill_id: Skill to get dependencies for.
        transitive: Include transitive dependencies.
        
    Returns:
        List of dependency skills.
    """

def get_execution_order(self, skill_ids: list[str]) -> list[Skill]:
    """Get skills in dependency-respecting order.
    
    Uses topological sort to order skills so dependencies
    are executed before dependents.
    """

def check_dependencies(
    self,
    skill_id: str,
    available_tools: list[str],
) -> DependencyCheck:
    """Check if skill dependencies are satisfied.
    
    Returns:
        DependencyCheck with satisfied flag and missing items.
    """

def sync_to_graph(self) -> SyncResult:
    """Sync skills to knowledge graph."""
```

### Usage Example
```python
from pathlib import Path
from dmm.agentos import SkillRegistry

# Initialize registry
registry = SkillRegistry(Path(".dmm/skills"))

# Load all skills
skills = registry.load_all()
print(f"Loaded {len(skills)} skills")

# Find specific skill
code_review = registry.find_by_id("skill_code_review")
if code_review:
    print(f"Found: {code_review.name} v{code_review.version}")
    print(f"Inputs: {[i.name for i in code_review.inputs]}")

# Search by tags
analysis_skills = registry.find_by_tags(["analysis", "code"])
print(f"Analysis skills: {[s.name for s in analysis_skills]}")

# Get execution order
order = registry.get_execution_order([
    "skill_code_analysis",
    "skill_report_generation",
])
for skill in order:
    print(f"Execute: {skill.name}")
```

## SkillDiscovery

Discovers skills matching specific criteria.
```python
from dmm.agentos.skills import SkillDiscovery

discovery = SkillDiscovery(registry)
```

### Methods
```python
def find_for_task(self, task_description: str) -> list[Skill]:
    """Find skills suitable for a task description."""

def find_by_output(self, output_type: str) -> list[Skill]:
    """Find skills that produce a specific output type."""

def find_compatible(self, skill_id: str) -> list[Skill]:
    """Find skills compatible with another skill."""
```

## Skill YAML Format

Skills are defined in YAML files with `.skill.yaml` extension.
```yaml
# .dmm/skills/custom/my_skill.skill.yaml

id: skill_my_custom
name: My Custom Skill
version: "1.0.0"
description: |
  Detailed description of what this skill does.
  Can span multiple lines.

category: analysis  # analysis, generation, retrieval, planning, etc.
tags:
  - custom
  - example

enabled: true

inputs:
  - name: file_path
    type: string
    required: true
    description: Path to the file to process
  
  - name: options
    type: object
    required: false
    default: {}
    description: Additional options

outputs:
  - name: result
    type: object
    description: Processing result
  
  - name: status
    type: string
    description: Success or error status

dependencies:
  skills:
    - skill_prerequisite  # Must run first
  tools:
    - tool_required       # Must be available

memory_requirements:
  - scope: project
    tags:
      - configuration
    required: false

execution:
  timeout_seconds: 60
  retry_count: 2
  retry_delay_seconds: 5
  parallel_safe: true
```

## Built-in Categories

| Category | Description |
|----------|-------------|
| analysis | Code analysis, data inspection |
| generation | Content creation, code generation |
| retrieval | Information retrieval, search |
| planning | Task planning, decomposition |
| review | Code review, quality checks |
| transformation | Data transformation, conversion |
| communication | Messaging, notifications |
| maintenance | Cleanup, optimization |

## See Also

- [Tools API](tools.md) - External tool integrations
- [Agents API](agents.md) - Agent configuration
- [Tutorial: Defining Skills](../../tutorials/03-defining-skills.md)
