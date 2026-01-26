# DMM Example Agents and Workflows

This directory contains example implementations demonstrating the DMM AgentOS capabilities.

## Overview

These examples show how to build agents that leverage the DMM memory system for:
- Code analysis and review
- Task management and orchestration
- Memory curation and maintenance
- Research and information gathering

## Directory Structure
```
examples/
├── agents/                    # Agent implementations
│   ├── __init__.py
│   ├── code_review_agent.py   # Analyzes code for issues
│   ├── task_manager_agent.py  # Manages and coordinates tasks
│   ├── memory_curator_agent.py # Curates the memory system
│   └── research_assistant_agent.py # Assists with research
├── skills/                    # Skill definitions (YAML)
│   ├── code_analysis.yaml     # Code analysis skill
│   ├── task_planning.yaml     # Task planning skill
│   ├── memory_search.yaml     # Memory search skill
│   └── report_generation.yaml # Report generation skill
├── workflows/                 # Multi-agent workflows
│   ├── __init__.py
│   ├── code_review_pipeline.py    # Code review workflow
│   ├── research_task.py           # Research workflow
│   └── system_maintenance.py      # Maintenance workflow
└── README.md                  # This file
```

## Agents

### Code Review Agent

Analyzes Python code for quality and best practices.
```python
from examples.agents import CodeReviewAgent

agent = CodeReviewAgent()
result = agent.review_file("src/module.py")
print(result.summary)

# Review entire directory
results = agent.review_directory("src/", recursive=True)
report = agent.generate_report(results, format="markdown")
```

**Capabilities:**
- AST-based code analysis
- Cyclomatic complexity calculation
- Style and convention checking
- Issue detection with severity levels
- Markdown report generation

### Task Manager Agent

Manages and coordinates tasks with dependency tracking.
```python
from examples.agents import TaskManagerAgent, TaskPriority

agent = TaskManagerAgent()

# Create a task
task = agent.create_task(
    name="Review codebase",
    description="Review all Python files for quality",
    priority=TaskPriority.HIGH,
)

# Decompose into subtasks
subtasks = agent.decompose_task(task.task_id)

# Schedule and execute
agent.schedule_tasks()
agent.start_task(subtasks[0].task_id)
agent.complete_task(subtasks[0].task_id, outputs={"result": "done"})

# Get status report
print(agent.get_status_report())
```

**Capabilities:**
- Task creation and decomposition
- Priority-based scheduling
- Dependency management
- Progress tracking
- Event subscriptions

### Memory Curator Agent

Manages and organizes the DMM memory system.
```python
from examples.agents import MemoryCuratorAgent
from pathlib import Path

agent = MemoryCuratorAgent(memory_dir=Path(".dmm/memory"))

# Check system health
health_status, issues = agent.check_health()
print(f"Health: {health_status.value}")

# Search memories
results = agent.search_memories(query="error handling", scope="project")

# Find conflicts
conflicts = agent.find_potential_conflicts()

# Generate health report
report = agent.generate_health_report()
```

**Capabilities:**
- Memory scanning and caching
- Health monitoring
- Conflict detection
- Stale memory identification
- Consolidation suggestions

### Research Assistant Agent

Assists with research and information gathering.
```python
from examples.agents import ResearchAssistantAgent, ResearchDepth

agent = ResearchAssistantAgent()

# Conduct research
report = agent.research(
    query="What are best practices for error handling?",
    depth=ResearchDepth.COMPREHENSIVE,
)

# Generate markdown report
markdown = agent.generate_report_markdown(report)
print(markdown)
```

**Capabilities:**
- Question decomposition
- Memory-based information retrieval
- Finding synthesis
- Multi-depth research levels
- Structured report generation

## Skills

Skills are defined in YAML format and describe agent capabilities:

### code_analysis.yaml
```yaml
id: skill_code_analysis
name: Code Analysis
category: analysis
inputs:
  - name: file_path
    type: string
    required: true
outputs:
  - name: structure
    type: object
  - name: metrics
    type: object
  - name: issues
    type: array
```

### task_planning.yaml
```yaml
id: skill_task_planning
name: Task Planning
category: planning
inputs:
  - name: task_description
    type: string
    required: true
outputs:
  - name: subtasks
    type: array
  - name: execution_order
    type: array
```

## Workflows

Workflows demonstrate multi-agent collaboration patterns.

### Code Review Pipeline
```
User Request -> Task Manager -> Code Review Agent -> Report
```
```python
from examples.workflows import run_code_review_pipeline

result = run_code_review_pipeline("src/", recursive=True)
print(result["report"])
```

### Research Task
```
User Request -> Task Manager -> Research Assistant -> Memory Curator -> Report
```
```python
from examples.workflows import run_research_task
from examples.agents import ResearchDepth

result = run_research_task(
    query="How to implement caching?",
    depth=ResearchDepth.STANDARD,
)
print(result["report"])
```

### System Maintenance
```
Scheduled Trigger -> Memory Curator -> Task Manager -> Cleanup Tasks
```
```python
from examples.workflows import run_system_maintenance

result = run_system_maintenance(auto_fix=False)
print(result["recommendations"])
```

## Running Examples

### From Command Line
```bash
# Code review pipeline
cd ~/projects/claude-memory
python -m examples.workflows.code_review_pipeline src/dmm/

# Research task
python -m examples.workflows.research_task "What is semantic retrieval?"

# System maintenance
python -m examples.workflows.system_maintenance
python -m examples.workflows.system_maintenance --auto-fix
```

### From Python
```python
import sys
sys.path.insert(0, "/path/to/claude-memory")

from examples.agents import CodeReviewAgent
from examples.workflows import run_code_review_pipeline

# Use agents directly
agent = CodeReviewAgent()
result = agent.review_file("myfile.py")

# Or use workflows
pipeline_result = run_code_review_pipeline("src/")
```

## Extending

### Creating Custom Agents
```python
from dataclasses import dataclass
from typing import Any

@dataclass
class MyAgentConfig:
    setting: str = "default"

class MyAgent:
    def __init__(self, config: MyAgentConfig | None = None):
        self.config = config or MyAgentConfig()
    
    def process(self, input_data: Any) -> Any:
        # Implementation
        pass
```

### Creating Custom Skills
```yaml
id: skill_my_custom
name: My Custom Skill
version: "1.0.0"
description: Description of what this skill does
category: custom
tags: [custom, example]

inputs:
  - name: input_param
    type: string
    required: true

outputs:
  - name: result
    type: object

execution:
  timeout_seconds: 30
  parallel_safe: true
```

### Creating Custom Workflows
```python
def run_my_workflow(param: str) -> dict:
    task_manager = TaskManagerAgent()
    my_agent = MyAgent()
    
    # Create tasks
    main_task = task_manager.create_task(
        name="My Workflow",
        description=f"Process: {param}",
    )
    
    # Execute
    result = my_agent.process(param)
    
    # Complete
    task_manager.complete_task(main_task.task_id, outputs=result)
    
    return {"success": True, "result": result}
```

## Testing

Run the example tests:
```bash
cd ~/projects/claude-memory
poetry run pytest tests/test_examples/ -v
```

## License

These examples are part of the DMM project and are provided under the same license.
