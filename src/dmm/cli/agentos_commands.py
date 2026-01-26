"""
CLI commands for AgentOS using Typer.

Provides commands for managing agents, tasks, skills, and system operations.
"""

import typer
from typing import Optional
from rich.console import Console
from rich.table import Table
from datetime import datetime
import json

console = Console()
err_console = Console(stderr=True)

# Create AgentOS app
agentos_app = typer.Typer(
    name="agentos",
    help="AgentOS management commands",
    no_args_is_help=True,
)

# Sub-apps
agent_app = typer.Typer(help="Manage agents")
task_app = typer.Typer(help="Manage tasks")
skill_app = typer.Typer(help="Manage skills")
system_app = typer.Typer(help="System management")

agentos_app.add_typer(agent_app, name="agent")
agentos_app.add_typer(task_app, name="task")
agentos_app.add_typer(skill_app, name="skill")
agentos_app.add_typer(system_app, name="system")


# =============================================================================
# Agent Commands
# =============================================================================

@agent_app.command("list")
def agent_list(
    status: str = typer.Option("all", help="Filter by status: active, idle, all"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List registered agents."""
    try:
        from dmm.agentos.agents import AgentRegistry
        registry = AgentRegistry()
        agents = registry.list_agents()
        
        if status != "all":
            agents = [a for a in agents if a.get("status") == status]
        
        if output_json:
            console.print_json(json.dumps(agents, default=str))
        else:
            if not agents:
                console.print("[yellow]No agents registered.[/yellow]")
                return
            
            table = Table(title="Registered Agents")
            table.add_column("ID", style="cyan")
            table.add_column("Name")
            table.add_column("Status")
            table.add_column("Capabilities")
            
            for a in agents:
                caps = ", ".join(a.get("capabilities", [])[:3])
                table.add_row(a["id"], a.get("name", "N/A"), a.get("status", "unknown"), caps)
            
            console.print(table)
    except Exception as e:
        err_console.print(f"[red]Error: {e}[/red]")


@agent_app.command("info")
def agent_info(agent_id: str = typer.Argument(..., help="Agent ID")):
    """Show agent details."""
    try:
        from dmm.agentos.agents import AgentRegistry
        registry = AgentRegistry()
        agent = registry.get(agent_id)
        
        if not agent:
            err_console.print(f"[red]Agent not found: {agent_id}[/red]")
            raise typer.Exit(1)
        
        console.print(f"[bold]Agent:[/bold] {agent.id}")
        console.print(f"  Name: {agent.name}")
        console.print(f"  Description: {agent.description}")
        console.print(f"  Capabilities: {', '.join(agent.capabilities)}")
    except typer.Exit:
        raise
    except Exception as e:
        err_console.print(f"[red]Error: {e}[/red]")


# =============================================================================
# Task Commands
# =============================================================================

@task_app.command("list")
def task_list(
    status: str = typer.Option("all", help="Filter: pending, running, completed, failed, all"),
    limit: int = typer.Option(20, help="Maximum tasks to show"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List tasks."""
    try:
        from dmm.agentos.tasks import TaskStore, TaskStatus
        store = TaskStore()
        
        if status == "all":
            tasks = store.list_tasks(limit=limit)
        else:
            task_status = TaskStatus(status)
            tasks = store.get_tasks_by_status(task_status)[:limit]
        
        if output_json:
            console.print_json(json.dumps([t.to_dict() for t in tasks], default=str))
        else:
            if not tasks:
                console.print("[yellow]No tasks found.[/yellow]")
                return
            
            table = Table(title="Tasks")
            table.add_column("ID", style="cyan")
            table.add_column("Name")
            table.add_column("Status")
            table.add_column("Priority")
            
            for t in tasks:
                table.add_row(t.id, t.name[:30], t.status.value, t.priority.value)
            
            console.print(table)
    except Exception as e:
        err_console.print(f"[red]Error: {e}[/red]")


@task_app.command("show")
def task_show(task_id: str = typer.Argument(..., help="Task ID")):
    """Show task details."""
    try:
        from dmm.agentos.tasks import TaskStore
        store = TaskStore()
        task = store.get_task(task_id)
        
        if not task:
            err_console.print(f"[red]Task not found: {task_id}[/red]")
            raise typer.Exit(1)
        
        console.print(f"[bold]Task:[/bold] {task.id}")
        console.print(f"  Name: {task.name}")
        console.print(f"  Status: {task.status.value}")
        console.print(f"  Priority: {task.priority.value}")
        console.print(f"  Description: {task.description[:100]}...")
        if task.assigned_agent:
            console.print(f"  Assigned to: {task.assigned_agent}")
    except typer.Exit:
        raise
    except Exception as e:
        err_console.print(f"[red]Error: {e}[/red]")


@task_app.command("create")
def task_create(
    name: str = typer.Option(..., "--name", "-n", help="Task name"),
    description: str = typer.Option("", "--desc", "-d", help="Description"),
    priority: str = typer.Option("normal", help="Priority: low, normal, high, critical"),
    assign: Optional[str] = typer.Option(None, "--assign", "-a", help="Agent to assign"),
):
    """Create a new task."""
    try:
        from dmm.agentos.tasks import TaskStore, Task, TaskPriority
        store = TaskStore()
        
        task = Task(
            name=name,
            description=description,
            priority=TaskPriority(priority),
            assigned_agent=assign,
        )
        store.save_task(task)
        
        console.print(f"[green]Created task:[/green] {task.id}")
    except Exception as e:
        err_console.print(f"[red]Error: {e}[/red]")


# =============================================================================
# Skill Commands
# =============================================================================

@skill_app.command("list")
def skill_list(output_json: bool = typer.Option(False, "--json", help="Output as JSON")):
    """List available skills."""
    try:
        from dmm.agentos.skills import SkillRegistry
        registry = SkillRegistry()
        skills = registry.list_skills()
        
        if output_json:
            console.print_json(json.dumps(skills, default=str))
        else:
            if not skills:
                console.print("[yellow]No skills registered.[/yellow]")
                return
            
            table = Table(title="Skills")
            table.add_column("ID", style="cyan")
            table.add_column("Name")
            table.add_column("Version")
            
            for s in skills:
                table.add_row(s["id"], s.get("name", "N/A"), s.get("version", "1.0"))
            
            console.print(table)
    except Exception as e:
        err_console.print(f"[red]Error: {e}[/red]")


# =============================================================================
# System Commands
# =============================================================================

@system_app.command("status")
def system_status():
    """Show system status."""
    console.print("[bold]AgentOS Status[/bold]")
    console.print("-" * 40)
    
    try:
        from dmm.agentos.agents import AgentRegistry
        from dmm.agentos.tasks import TaskStore
        from dmm.agentos.skills import SkillRegistry
        
        console.print(f"  Agents: {len(AgentRegistry().list_agents())}")
        console.print(f"  Tasks: {len(TaskStore().list_tasks())}")
        console.print(f"  Skills: {len(SkillRegistry().list_skills())}")
        console.print(f"  Status: [green]Running[/green]")
    except Exception as e:
        console.print(f"  Status: [red]Error - {e}[/red]")


@system_app.command("stats")
def system_stats():
    """Show system statistics."""
    console.print("[bold]AgentOS Statistics[/bold]")
    console.print("-" * 40)
    console.print(f"  Timestamp: {datetime.utcnow().isoformat()}")
    
    try:
        from dmm.agentos.runtime import AuditLogger
        stats = AuditLogger().get_stats()
        console.print(f"  Total Events: {stats.get('total_events', 0)}")
    except Exception:
        pass


@system_app.command("audit")
def system_audit(
    limit: int = typer.Option(20, help="Number of events"),
    agent: Optional[str] = typer.Option(None, help="Filter by agent"),
):
    """Show recent audit events."""
    try:
        from dmm.agentos.runtime import AuditLogger, AuditLevel
        logger = AuditLogger(level=AuditLevel.DETAILED)
        events = logger.get_events(agent_id=agent, limit=limit)
        
        if not events:
            console.print("[yellow]No audit events.[/yellow]")
            return
        
        table = Table(title="Audit Events")
        table.add_column("Time")
        table.add_column("Type")
        table.add_column("Agent")
        table.add_column("Outcome")
        
        for e in events:
            table.add_row(
                e.timestamp.strftime("%H:%M:%S"),
                e.event_type.value,
                e.agent_id or "N/A",
                e.outcome,
            )
        
        console.print(table)
    except Exception as e:
        err_console.print(f"[red]Error: {e}[/red]")
