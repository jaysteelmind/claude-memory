# Tutorial 2: Creating Custom Agents

Learn how to create agents that leverage DMM's memory and capability systems.

## Prerequisites

- Completed [Tutorial 1: Basic Memory Operations](01-basic-memory.md)
- Understanding of Python dataclasses

## 1. Agent Architecture

An agent in DMM consists of:
```
┌─────────────────────────────────────┐
│              Agent                  │
├─────────────────────────────────────┤
│  Configuration                      │
│  ├─ Identity (id, name, role)       │
│  ├─ Skills (assigned capabilities)  │
│  ├─ Tools (available integrations)  │
│  └─ Behavior (preferences, limits)  │
├─────────────────────────────────────┤
│  State                              │
│  ├─ Current task                    │
│  ├─ Progress                        │
│  └─ History                         │
├─────────────────────────────────────┤
│  Methods                            │
│  ├─ process() - Main entry point    │
│  ├─ plan() - Create execution plan  │
│  └─ execute() - Run operations      │
└─────────────────────────────────────┘
```

## 2. Simple Agent Example

Let's create a basic documentation agent:
```python
"""Documentation Agent - Analyzes and documents code."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class DocAgentConfig:
    """Configuration for DocumentationAgent."""
    
    output_format: str = "markdown"
    include_examples: bool = True
    max_file_size: int = 50000  # bytes


@dataclass
class DocumentationResult:
    """Result of documentation generation."""
    
    file_path: str
    documentation: str
    sections: list[str]
    generated_at: datetime
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "documentation": self.documentation,
            "sections": self.sections,
            "generated_at": self.generated_at.isoformat(),
        }


class DocumentationAgent:
    """Agent that generates documentation for Python code.
    
    This agent demonstrates:
    - Configuration management
    - File processing
    - Output generation
    
    Example:
        agent = DocumentationAgent()
        result = agent.document_file("src/module.py")
        print(result.documentation)
    """
    
    def __init__(self, config: DocAgentConfig | None = None) -> None:
        """Initialize the agent.
        
        Args:
            config: Optional configuration. Uses defaults if not provided.
        """
        self.config = config or DocAgentConfig()
        self._history: list[DocumentationResult] = []
    
    def document_file(self, file_path: str | Path) -> DocumentationResult:
        """Generate documentation for a Python file.
        
        Args:
            file_path: Path to Python file.
            
        Returns:
            DocumentationResult with generated documentation.
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if path.stat().st_size > self.config.max_file_size:
            raise ValueError(f"File too large: {path.stat().st_size} bytes")
        
        content = path.read_text()
        
        # Parse and document
        sections = self._extract_sections(content)
        documentation = self._generate_documentation(path.name, sections)
        
        result = DocumentationResult(
            file_path=str(path),
            documentation=documentation,
            sections=[s["name"] for s in sections],
            generated_at=datetime.now(timezone.utc),
        )
        
        self._history.append(result)
        return result
    
    def _extract_sections(self, content: str) -> list[dict[str, Any]]:
        """Extract documentable sections from code."""
        import ast
        
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []
        
        sections = []
        
        # Module docstring
        module_doc = ast.get_docstring(tree)
        if module_doc:
            sections.append({
                "type": "module",
                "name": "Module",
                "docstring": module_doc,
            })
        
        # Classes and functions
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                sections.append({
                    "type": "class",
                    "name": node.name,
                    "docstring": ast.get_docstring(node) or "No documentation",
                    "methods": [
                        m.name for m in node.body
                        if isinstance(m, ast.FunctionDef)
                    ],
                })
            elif isinstance(node, ast.FunctionDef):
                if not any(
                    isinstance(p, ast.ClassDef) and node in ast.walk(p)
                    for p in ast.walk(tree)
                    if isinstance(p, ast.ClassDef)
                ):
                    sections.append({
                        "type": "function",
                        "name": node.name,
                        "docstring": ast.get_docstring(node) or "No documentation",
                        "args": [a.arg for a in node.args.args],
                    })
        
        return sections
    
    def _generate_documentation(
        self,
        filename: str,
        sections: list[dict[str, Any]],
    ) -> str:
        """Generate markdown documentation."""
        lines = [
            f"# Documentation: {filename}",
            "",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            "",
        ]
        
        for section in sections:
            if section["type"] == "module":
                lines.extend([
                    "## Overview",
                    "",
                    section["docstring"],
                    "",
                ])
            
            elif section["type"] == "class":
                lines.extend([
                    f"## Class: {section['name']}",
                    "",
                    section["docstring"],
                    "",
                ])
                
                if section.get("methods"):
                    lines.append("**Methods:**")
                    for method in section["methods"]:
                        lines.append(f"- `{method}()`")
                    lines.append("")
            
            elif section["type"] == "function":
                lines.extend([
                    f"## Function: {section['name']}",
                    "",
                    section["docstring"],
                    "",
                ])
                
                if section.get("args"):
                    lines.append(f"**Arguments:** `{', '.join(section['args'])}`")
                    lines.append("")
        
        return "\n".join(lines)
    
    def get_history(self) -> list[DocumentationResult]:
        """Get documentation generation history."""
        return self._history.copy()
```

## 3. Agent with Memory Integration

Enhance the agent to use DMM memories:
```python
"""Memory-Aware Documentation Agent."""

from pathlib import Path
from dmm.retrieval import MemoryRetriever
from dmm.indexer.store import MemoryStore


class MemoryAwareDocAgent:
    """Documentation agent that uses DMM memories for context."""
    
    def __init__(
        self,
        config: DocAgentConfig | None = None,
        memory_store: MemoryStore | None = None,
    ) -> None:
        self.config = config or DocAgentConfig()
        self._store = memory_store
        self._retriever = None
        
        if self._store:
            self._retriever = MemoryRetriever(self._store)
    
    def document_with_context(
        self,
        file_path: str | Path,
        query: str | None = None,
    ) -> DocumentationResult:
        """Generate documentation with memory context.
        
        Args:
            file_path: Path to file.
            query: Optional query for relevant memories.
        """
        path = Path(file_path)
        content = path.read_text()
        
        # Get relevant memories for context
        context = ""
        if self._retriever and query:
            pack = self._retriever.retrieve(query, budget=1000)
            if pack.entries:
                context = self._format_context(pack)
        
        # Generate documentation with context
        sections = self._extract_sections(content)
        documentation = self._generate_documentation(
            path.name,
            sections,
            context=context,
        )
        
        return DocumentationResult(
            file_path=str(path),
            documentation=documentation,
            sections=[s["name"] for s in sections],
            generated_at=datetime.now(timezone.utc),
        )
    
    def _format_context(self, pack) -> str:
        """Format memory pack as context."""
        lines = ["## Project Context", ""]
        
        for entry in pack.entries[:3]:
            lines.append(f"### {entry.title}")
            lines.append(entry.content[:500])
            lines.append("")
        
        return "\n".join(lines)
    
    def _generate_documentation(
        self,
        filename: str,
        sections: list,
        context: str = "",
    ) -> str:
        """Generate documentation with optional context."""
        lines = [
            f"# Documentation: {filename}",
            "",
        ]
        
        if context:
            lines.extend([context, "---", ""])
        
        # ... rest of generation logic
        for section in sections:
            lines.append(f"## {section.get('name', 'Unknown')}")
            lines.append(section.get("docstring", ""))
            lines.append("")
        
        return "\n".join(lines)
```

## 4. Agent with Task Integration

Connect the agent to the task system:
```python
"""Task-Integrated Documentation Agent."""

from examples.agents.task_manager_agent import (
    TaskManagerAgent,
    TaskPriority,
    TaskStatus,
)


class TaskAwareDocAgent:
    """Documentation agent integrated with task management."""
    
    def __init__(self) -> None:
        self.doc_agent = DocumentationAgent()
        self.task_manager = TaskManagerAgent()
        
        # Subscribe to task events
        self.task_manager.subscribe(self._on_task_event)
    
    def _on_task_event(self, task, event: str) -> None:
        """Handle task events."""
        print(f"[{event}] {task.name}: {task.status.value}")
    
    def document_directory(
        self,
        directory: str | Path,
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> dict:
        """Document all Python files in a directory.
        
        Creates tasks for each file and tracks progress.
        """
        path = Path(directory)
        files = list(path.glob("**/*.py"))
        
        # Create main task
        main_task = self.task_manager.create_task(
            name=f"Document {path.name}",
            description=f"Generate documentation for {len(files)} files",
            priority=priority,
        )
        
        # Create subtasks
        subtasks = []
        for file in files:
            subtask = self.task_manager.create_task(
                name=f"Document {file.name}",
                description=f"Generate docs for {file}",
                priority=priority,
                parent_id=main_task.task_id,
            )
            subtasks.append((subtask, file))
        
        # Execute
        results = []
        for subtask, file in subtasks:
            self.task_manager.start_task(subtask.task_id)
            
            try:
                result = self.doc_agent.document_file(file)
                results.append(result)
                self.task_manager.complete_task(
                    subtask.task_id,
                    outputs={"sections": len(result.sections)},
                )
            except Exception as e:
                self.task_manager.fail_task(subtask.task_id, str(e))
        
        # Complete main task
        self.task_manager.complete_task(
            main_task.task_id,
            outputs={
                "files_documented": len(results),
                "total_sections": sum(len(r.sections) for r in results),
            },
        )
        
        return {
            "task_id": main_task.task_id,
            "results": results,
            "report": self.task_manager.get_status_report(),
        }
```

## 5. Agent YAML Definition

Define agent capabilities in YAML:
```yaml
# .dmm/agents/documentation_agent.agent.yaml

id: agent_documentation
name: Documentation Agent
version: "1.0.0"
description: |
  Generates and maintains documentation for Python codebases.
  Uses memory context for project-specific documentation style.

role: documentation

skills:
  - skill_code_analysis
  - skill_report_generation

tools:
  - tool_filesystem
  - tool_git

behavior:
  temperature: 0.3
  max_retries: 2
  timeout_seconds: 300
  
  preferences:
    output_format: markdown
    include_examples: true
    verbose_logging: false

constraints:
  max_files_per_run: 50
  max_file_size_bytes: 100000
  allowed_extensions:
    - .py
    - .md

memory_access:
  scopes:
    - project
    - global
  tags_filter:
    - documentation
    - coding-standards
  max_tokens: 2000
```

## 6. Loading Agent from YAML
```python
from pathlib import Path
from dmm.agentos import AgentRegistry, SkillRegistry, ToolRegistry

# Initialize registries
skill_registry = SkillRegistry(Path(".dmm/skills"))
tool_registry = ToolRegistry(Path(".dmm/tools"))
agent_registry = AgentRegistry(
    Path(".dmm/agents"),
    skill_registry,
    tool_registry,
)

# Load all
skill_registry.load_all()
tool_registry.load_all()
agents = agent_registry.load_all()

# Get specific agent
doc_agent = agent_registry.find_by_id("agent_documentation")
if doc_agent:
    print(f"Agent: {doc_agent.name}")
    print(f"Skills: {doc_agent.skills}")
    print(f"Tools: {doc_agent.tools}")
```

## 7. Agent Matching

Find the best agent for a task:
```python
from dmm.agentos import AgentMatcher

matcher = AgentMatcher(agent_registry, skill_registry, tool_registry)

# Find by task description
agent = matcher.get_best_agent("Generate documentation for the auth module")
print(f"Best agent: {agent.name}")

# Find by required skills
agents = matcher.find_by_skills(["skill_code_analysis"])
print(f"Matching agents: {[a.name for a in agents]}")

# Find by available tools
agents = matcher.find_by_tools(["tool_git"])
print(f"Agents with git: {[a.name for a in agents]}")
```

## 8. Complete Agent Template
```python
"""Template for creating custom agents."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


@dataclass
class AgentConfig:
    """Base configuration for agents."""
    
    name: str = "CustomAgent"
    max_retries: int = 2
    timeout_seconds: int = 300


@dataclass
class AgentResult:
    """Base result from agent operations."""
    
    success: bool
    data: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "errors": self.errors,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class BaseAgent:
    """Base class for custom agents.
    
    Provides:
    - Configuration management
    - Event subscription
    - Error handling
    - History tracking
    """
    
    def __init__(self, config: AgentConfig | None = None) -> None:
        self.config = config or AgentConfig()
        self._history: list[AgentResult] = []
        self._subscribers: list[Callable[[str, Any], None]] = []
    
    def process(self, input_data: Any) -> AgentResult:
        """Main entry point for agent processing.
        
        Override this method in subclasses.
        """
        raise NotImplementedError("Subclasses must implement process()")
    
    def subscribe(self, callback: Callable[[str, Any], None]) -> None:
        """Subscribe to agent events."""
        self._subscribers.append(callback)
    
    def _emit(self, event: str, data: Any) -> None:
        """Emit an event to subscribers."""
        for callback in self._subscribers:
            try:
                callback(event, data)
            except Exception:
                pass
    
    def _record_result(self, result: AgentResult) -> None:
        """Record result in history."""
        result.completed_at = datetime.now(timezone.utc)
        self._history.append(result)
        self._emit("completed", result)
    
    def get_history(self) -> list[AgentResult]:
        """Get processing history."""
        return self._history.copy()
    
    def clear_history(self) -> None:
        """Clear processing history."""
        self._history.clear()


class MyCustomAgent(BaseAgent):
    """Example custom agent implementation."""
    
    def process(self, input_data: Any) -> AgentResult:
        """Process input data."""
        self._emit("started", input_data)
        
        try:
            # Your processing logic here
            output = self._do_work(input_data)
            
            result = AgentResult(
                success=True,
                data={"output": output},
            )
        except Exception as e:
            result = AgentResult(
                success=False,
                data={},
                errors=[str(e)],
            )
        
        self._record_result(result)
        return result
    
    def _do_work(self, input_data: Any) -> Any:
        """Implement your agent's core logic."""
        return f"Processed: {input_data}"
```

## Exercises

1. **Create a Linting Agent**: Build an agent that runs code linting
2. **Add Memory Context**: Enhance your agent to use project memories
3. **Task Integration**: Connect your agent to the task system
4. **Multi-File Processing**: Handle directories with progress tracking

## Next Steps

- [Tutorial 3: Defining Skills](03-defining-skills.md)
- [Tutorial 4: Task Management](04-task-management.md)
- [Agents API Reference](../api/agentos/agents.md)
