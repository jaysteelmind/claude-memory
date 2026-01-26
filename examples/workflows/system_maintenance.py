"""System Maintenance Workflow.

Demonstrates:
    Scheduled Trigger -> Memory Curator -> Task Manager -> Cleanup Tasks

This workflow shows automated system maintenance using agents.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from examples.agents.memory_curator_agent import (
    MemoryCuratorAgent,
    MemoryCuratorConfig,
    MemoryHealthStatus,
)
from examples.agents.task_manager_agent import (
    TaskManagerAgent,
    TaskPriority,
)


def run_system_maintenance(
    memory_dir: Path | None = None,
    auto_fix: bool = False,
) -> dict[str, Any]:
    """Run the system maintenance workflow.
    
    This workflow:
    1. Memory Curator checks system health
    2. Identifies issues and creates maintenance tasks
    3. Task Manager schedules and tracks cleanup
    4. Generates maintenance report
    
    Args:
        memory_dir: Optional path to memory directory.
        auto_fix: Whether to automatically apply fixes.
        
    Returns:
        Dictionary with maintenance results.
    """
    memory_curator = MemoryCuratorAgent(
        memory_dir=memory_dir,
        config=MemoryCuratorConfig(
            stale_threshold_days=30,
            conflict_confidence_threshold=0.7,
            enable_auto_cleanup=auto_fix,
        ),
    )
    task_manager = TaskManagerAgent()
    
    events: list[dict[str, Any]] = []
    actions_taken: list[dict[str, Any]] = []
    
    def on_task_event(task: Any, event: str) -> None:
        events.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": task.task_id,
            "task_name": task.name,
            "event": event,
        })
    
    task_manager.subscribe(on_task_event)
    
    main_task = task_manager.create_task(
        name="System Maintenance",
        description="Perform routine system maintenance",
        priority=TaskPriority.NORMAL,
    )
    
    health_task = task_manager.create_task(
        name="Health Check",
        description="Check memory system health",
        priority=TaskPriority.HIGH,
        parent_id=main_task.task_id,
    )
    
    task_manager.start_task(health_task.task_id)
    
    memory_count = memory_curator.scan_memories()
    stats = memory_curator.get_stats()
    health_status, health_issues = memory_curator.check_health()
    
    task_manager.complete_task(
        health_task.task_id,
        outputs={
            "health_status": health_status.value,
            "issue_count": len(health_issues),
            "memory_count": memory_count,
        },
    )
    
    maintenance_tasks = []
    
    conflicts = memory_curator.find_potential_conflicts()
    if conflicts:
        conflict_task = task_manager.create_task(
            name="Resolve Conflicts",
            description=f"Review and resolve {len(conflicts)} potential conflicts",
            priority=TaskPriority.HIGH,
            parent_id=main_task.task_id,
            inputs={"conflict_count": len(conflicts)},
        )
        maintenance_tasks.append(("conflicts", conflict_task, conflicts))
    
    stale_memories = memory_curator.get_stale_memories()
    if stale_memories:
        stale_task = task_manager.create_task(
            name="Review Stale Memories",
            description=f"Review {len(stale_memories)} stale memories",
            priority=TaskPriority.NORMAL,
            parent_id=main_task.task_id,
            inputs={"stale_count": len(stale_memories)},
        )
        maintenance_tasks.append(("stale", stale_task, stale_memories))
    
    consolidation = memory_curator.suggest_consolidation()
    if consolidation:
        consolidate_task = task_manager.create_task(
            name="Consolidate Memories",
            description=f"Review {len(consolidation)} consolidation suggestions",
            priority=TaskPriority.LOW,
            parent_id=main_task.task_id,
            inputs={"suggestion_count": len(consolidation)},
        )
        maintenance_tasks.append(("consolidation", consolidate_task, consolidation))
    
    for task_type, task, items in maintenance_tasks:
        task_manager.start_task(task.task_id)
        
        if auto_fix:
            if task_type == "conflicts":
                for conflict in items:
                    actions_taken.append({
                        "type": "conflict_flagged",
                        "conflict_id": conflict.conflict_id,
                        "memory_ids": conflict.memory_ids,
                        "action": "flagged_for_review",
                    })
            
            elif task_type == "stale":
                for memory in items[:10]:
                    actions_taken.append({
                        "type": "stale_flagged",
                        "memory_id": memory.get("id"),
                        "days_stale": memory.get("days_since_used", "unknown"),
                        "action": "flagged_for_review",
                    })
            
            elif task_type == "consolidation":
                for suggestion in items:
                    actions_taken.append({
                        "type": "consolidation_suggested",
                        "tag": suggestion.get("tag"),
                        "memory_count": suggestion.get("memory_count"),
                        "action": "suggested",
                    })
        
        task_manager.complete_task(
            task.task_id,
            outputs={
                "items_processed": len(items),
                "auto_fix": auto_fix,
            },
        )
    
    task_manager.complete_task(
        main_task.task_id,
        outputs={
            "health_status": health_status.value,
            "tasks_completed": len(maintenance_tasks) + 1,
            "actions_taken": len(actions_taken),
        },
    )
    
    health_report = memory_curator.generate_health_report()
    
    report_lines = [
        "# System Maintenance Report",
        "",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        f"**Auto-fix enabled:** {auto_fix}",
        "",
        "## Summary",
        "",
        f"- Health Status: **{health_status.value.upper()}**",
        f"- Total Memories: {stats.total_memories}",
        f"- Conflicts Found: {len(conflicts)}",
        f"- Stale Memories: {len(stale_memories)}",
        f"- Consolidation Suggestions: {len(consolidation)}",
        "",
        "## Tasks Executed",
        "",
    ]
    
    for task_type, task, items in [("health", health_task, [])] + maintenance_tasks:
        status = task.status.value
        report_lines.append(f"- **{task.name}**: {status}")
    
    if actions_taken:
        report_lines.extend([
            "",
            "## Actions Taken",
            "",
        ])
        for action in actions_taken[:20]:
            report_lines.append(f"- [{action['type']}] {action.get('action', 'processed')}")
    
    if health_issues:
        report_lines.extend([
            "",
            "## Health Issues",
            "",
        ])
        for issue in health_issues:
            report_lines.append(f"- {issue}")
    
    report_lines.extend([
        "",
        "---",
        "",
        "## Detailed Health Report",
        "",
        health_report,
    ])
    
    maintenance_report = "\n".join(report_lines)
    
    return {
        "success": True,
        "task_id": main_task.task_id,
        "health_status": health_status.value,
        "stats": stats.to_dict(),
        "issues": {
            "health_issues": health_issues,
            "conflicts": len(conflicts),
            "stale_memories": len(stale_memories),
            "consolidation_suggestions": len(consolidation),
        },
        "actions_taken": actions_taken,
        "events": events,
        "report": maintenance_report,
        "recommendations": _generate_recommendations(
            health_status, conflicts, stale_memories, consolidation
        ),
    }


def _generate_recommendations(
    health_status: MemoryHealthStatus,
    conflicts: list,
    stale_memories: list,
    consolidation: list,
) -> list[str]:
    """Generate maintenance recommendations."""
    recommendations = []
    
    if health_status == MemoryHealthStatus.CRITICAL:
        recommendations.append(
            "URGENT: System health is critical. Immediate attention required."
        )
    
    if conflicts:
        recommendations.append(
            f"Review {len(conflicts)} potential conflicts to ensure consistency."
        )
    
    if len(stale_memories) > 10:
        recommendations.append(
            f"Consider archiving or updating {len(stale_memories)} stale memories."
        )
    
    if consolidation:
        recommendations.append(
            f"Review {len(consolidation)} consolidation opportunities to reduce redundancy."
        )
    
    if not recommendations:
        recommendations.append("System is healthy. No immediate actions required.")
    
    return recommendations


def main() -> None:
    """Run the system maintenance workflow."""
    import sys
    
    auto_fix = "--auto-fix" in sys.argv
    
    print("Running system maintenance workflow")
    print(f"Auto-fix: {auto_fix}")
    print("=" * 60)
    
    result = run_system_maintenance(auto_fix=auto_fix)
    
    print(f"\nHealth Status: {result['health_status']}")
    print(f"Total Memories: {result['stats']['total_memories']}")
    print(f"\nIssues Found:")
    for issue_type, count in result["issues"].items():
        if isinstance(count, int) and count > 0:
            print(f"  - {issue_type}: {count}")
        elif isinstance(count, list) and count:
            print(f"  - {issue_type}: {len(count)}")
    
    print(f"\nActions Taken: {len(result['actions_taken'])}")
    
    print("\nRecommendations:")
    for rec in result["recommendations"]:
        print(f"  - {rec}")
    
    print("\n" + "=" * 60)
    print("\nMaintenance Report Preview:")
    print(result["report"][:2000])
    
    if len(result["report"]) > 2000:
        print("\n... (truncated)")


if __name__ == "__main__":
    main()
