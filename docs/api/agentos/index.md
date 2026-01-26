# AgentOS API Reference

The AgentOS module transforms DMM from a memory system into a full Agent Operating System.

## Overview
```
┌─────────────────────────────────────────────────────────┐
│                    AgentOS Layer                        │
├─────────────┬─────────────┬─────────────┬──────────────┤
│   Skills    │    Tools    │   Agents    │    Tasks     │
├─────────────┴─────────────┴─────────────┴──────────────┤
│                   Orchestration                         │
├─────────────┬─────────────┬─────────────┬──────────────┤
│Communication│  Self-Mod   │   Runtime   │    Safety    │
└─────────────┴─────────────┴─────────────┴──────────────┘
```

## Modules

### [Skills](skills.md)
Agent capabilities defined in YAML.
```python
from dmm.agentos import SkillRegistry

registry = SkillRegistry(Path(".dmm/skills"))
skills = registry.load_all()
skill = registry.find_by_id("skill_code_review")
```

### [Tools](tools.md)
External tool integrations (CLI, API, MCP, Functions).
```python
from dmm.agentos import ToolRegistry, ToolExecutor

registry = ToolRegistry(Path(".dmm/tools"))
executor = ToolExecutor(registry)
result = await executor.execute("tool_git", {"command": "status"})
```

### [Agents](agents.md)
Agent personas with skills, tools, and behavior.
```python
from dmm.agentos import AgentRegistry, AgentMatcher

registry = AgentRegistry(Path(".dmm/agents"), skill_registry, tool_registry)
matcher = AgentMatcher(registry, skill_registry, tool_registry)
best_agent = matcher.get_best_agent("review my Python code")
```

### [Tasks](tasks.md)
Task lifecycle management.
```python
from dmm.agentos.tasks import Task, TaskStore, TaskPlanner, TaskScheduler

store = TaskStore()
planner = TaskPlanner(store)
scheduler = TaskScheduler(store)

task = Task(name="Review code", description="...")
subtasks = planner.decompose(task)
scheduled = scheduler.schedule()
```

### [Orchestration](orchestration.md)
Task execution engine.
```python
from dmm.agentos.orchestration import TaskOrchestrator

orchestrator = TaskOrchestrator(skill_registry, tool_registry)
result = await orchestrator.execute_task(task)
```

### [Communication](communication.md)
Multi-agent messaging.
```python
from dmm.agentos.communication import MessageBus, Message, MessageType

bus = MessageBus()
bus.register_agent("agent_1")

message = Message(
    sender="agent_1",
    recipient="agent_2",
    message_type=MessageType.REQUEST,
    content={"task": "help needed"},
)
bus.send(message)
```

### [Self-Modification](selfmod.md)
Safe code analysis and generation.
```python
from dmm.agentos.selfmod import CodeAnalyzer, CodeGenerator, ProposalManager

analyzer = CodeAnalyzer()
analysis = analyzer.analyze_file("src/module.py")

generator = CodeGenerator()
code = generator.generate_function(spec)

manager = ProposalManager()
proposal = manager.create_proposal(modification)
```

### [Runtime](runtime.md)
Safety, resources, and audit logging.
```python
from dmm.agentos.runtime import ResourceManager, SafetyManager, AuditLogger

resources = ResourceManager()
resources.set_quota("agent_1", "tokens", 10000)

safety = SafetyManager()
safety.add_path_rule("allow", "/home/user/project/**")

audit = AuditLogger()
audit.log("task_started", {"task_id": "task_123"})
```

## Quick Start

### Basic Agent Setup
```python
from pathlib import Path
from dmm.agentos import (
    SkillRegistry,
    ToolRegistry, 
    AgentRegistry,
    AgentMatcher,
)
from dmm.agentos.tasks import TaskStore, TaskPlanner
from dmm.agentos.orchestration import TaskOrchestrator

# Initialize registries
skill_registry = SkillRegistry(Path(".dmm/skills"))
tool_registry = ToolRegistry(Path(".dmm/tools"))
agent_registry = AgentRegistry(
    Path(".dmm/agents"),
    skill_registry,
    tool_registry,
)

# Load all definitions
skill_registry.load_all()
tool_registry.load_all()
agent_registry.load_all()

# Find best agent for a task
matcher = AgentMatcher(agent_registry, skill_registry, tool_registry)
agent = matcher.get_best_agent("analyze this Python file")

# Create and execute task
store = TaskStore()
orchestrator = TaskOrchestrator(skill_registry, tool_registry)

task = store.create_task(
    name="Code Analysis",
    description="Analyze src/main.py",
    assigned_agent=agent.id,
)

result = await orchestrator.execute_task(task)
```

### Multi-Agent Collaboration
```python
from dmm.agentos.communication import MessageBus, Message, MessageType

bus = MessageBus()

# Register agents
bus.register_agent("coordinator")
bus.register_agent("reviewer")
bus.register_agent("writer")

# Coordinator delegates task
delegation = Message(
    sender="coordinator",
    recipient="reviewer",
    message_type=MessageType.DELEGATE,
    content={
        "task": "Review the authentication module",
        "priority": "high",
    },
)
bus.send(delegation)

# Reviewer requests assistance
assist_request = Message(
    sender="reviewer",
    recipient="writer",
    message_type=MessageType.ASSIST,
    content={
        "need": "Documentation for auth flow",
    },
)
bus.send(assist_request)
```

## Module Summary

| Module | Purpose | Key Classes |
|--------|---------|-------------|
| skills | Agent capabilities | SkillRegistry, Skill, SkillDiscovery |
| tools | External integrations | ToolRegistry, ToolExecutor, Tool |
| agents | Agent personas | AgentRegistry, AgentMatcher, Agent |
| tasks | Task management | TaskStore, TaskPlanner, TaskScheduler |
| orchestration | Execution engine | TaskOrchestrator, ExecutionContext |
| communication | Messaging | MessageBus, Message, CollaborationPatterns |
| selfmod | Code modification | CodeAnalyzer, CodeGenerator, ProposalManager |
| runtime | Safety & resources | ResourceManager, SafetyManager, AuditLogger |

## See Also

- [Core API](../core.md) - Memory models
- [Graph API](../graph.md) - Knowledge graph
- [Examples](../../examples/README.md) - Working examples
- [Tutorials](../../tutorials/02-creating-agents.md) - Step-by-step guides
