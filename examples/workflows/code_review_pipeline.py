"""Code Review Pipeline Workflow.

Demonstrates:
    User Request -> Task Manager -> Code Review Agent -> Report

This workflow shows how multiple agents collaborate to review code.
"""

from pathlib import Path
from typing import Any

from examples.agents.code_review_agent import CodeReviewAgent, CodeReviewAgentConfig
from examples.agents.task_manager_agent import (
    TaskManagerAgent,
    TaskPriority,
    TaskStatus,
)


def run_code_review_pipeline(
    target_path: str | Path,
    recursive: bool = True,
    priority: TaskPriority = TaskPriority.NORMAL,
) -> dict[str, Any]:
    """Run the code review pipeline.
    
    This workflow:
    1. Task Manager creates and decomposes the review task
    2. Code Review Agent analyzes the code
    3. Results are compiled into a report
    
    Args:
        target_path: Path to file or directory to review.
        recursive: Whether to search subdirectories.
        priority: Task priority level.
        
    Returns:
        Dictionary with pipeline results.
    """
    target = Path(target_path)
    
    task_manager = TaskManagerAgent()
    code_reviewer = CodeReviewAgent(CodeReviewAgentConfig(
        max_line_length=100,
        max_function_lines=50,
        check_docstrings=True,
        check_type_hints=True,
    ))
    
    events: list[dict[str, Any]] = []
    
    def on_task_event(task: Any, event: str) -> None:
        events.append({
            "task_id": task.task_id,
            "task_name": task.name,
            "event": event,
            "status": task.status.value,
        })
    
    task_manager.subscribe(on_task_event)
    
    if target.is_file():
        task_description = f"Review Python file: {target.name}"
    else:
        task_description = f"Review Python files in: {target}"
    
    main_task = task_manager.create_task(
        name="Code Review",
        description=task_description,
        priority=priority,
        inputs={"target_path": str(target), "recursive": recursive},
    )
    
    subtasks = task_manager.decompose_task(
        main_task.task_id,
        subtask_definitions=[
            {"name": "Scan files", "description": "Identify Python files to review"},
            {"name": "Analyze code", "description": "Run code analysis on each file"},
            {"name": "Compile results", "description": "Generate review report"},
        ],
    )
    
    task_manager.schedule_tasks()
    
    scan_task = subtasks[0]
    task_manager.start_task(scan_task.task_id)
    
    if target.is_file():
        files_to_review = [target] if target.suffix == ".py" else []
    else:
        pattern = "**/*.py" if recursive else "*.py"
        files_to_review = [
            f for f in target.glob(pattern)
            if "__pycache__" not in str(f)
        ]
    
    task_manager.complete_task(
        scan_task.task_id,
        outputs={"file_count": len(files_to_review), "files": [str(f) for f in files_to_review]},
    )
    
    analyze_task = subtasks[1]
    task_manager.start_task(analyze_task.task_id)
    
    review_results = []
    for i, file_path in enumerate(files_to_review):
        try:
            result = code_reviewer.review_file(file_path)
            review_results.append(result)
            
            progress = (i + 1) / len(files_to_review) if files_to_review else 1.0
            task_manager.update_progress(analyze_task.task_id, progress)
        except (SyntaxError, UnicodeDecodeError) as e:
            review_results.append({
                "file_path": str(file_path),
                "error": str(e),
            })
    
    task_manager.complete_task(
        analyze_task.task_id,
        outputs={"reviews_completed": len(review_results)},
    )
    
    compile_task = subtasks[2]
    task_manager.start_task(compile_task.task_id)
    
    valid_results = [r for r in review_results if hasattr(r, "to_dict")]
    report = code_reviewer.generate_report(valid_results, format="markdown")
    
    task_manager.complete_task(
        compile_task.task_id,
        outputs={"report_length": len(report)},
    )
    
    task_manager.complete_task(
        main_task.task_id,
        outputs={
            "files_reviewed": len(files_to_review),
            "issues_found": sum(len(r.issues) for r in valid_results),
        },
    )
    
    total_issues = sum(len(r.issues) for r in valid_results)
    critical_issues = sum(
        sum(1 for i in r.issues if i.severity == "critical")
        for r in valid_results
    )
    
    return {
        "success": True,
        "task_id": main_task.task_id,
        "files_reviewed": len(files_to_review),
        "total_issues": total_issues,
        "critical_issues": critical_issues,
        "report": report,
        "events": events,
        "status_report": task_manager.get_status_report(),
    }


def main() -> None:
    """Run the code review pipeline on the examples directory."""
    import sys
    
    target = sys.argv[1] if len(sys.argv) > 1 else "examples/agents"
    
    print(f"Running code review pipeline on: {target}")
    print("=" * 60)
    
    result = run_code_review_pipeline(target)
    
    print(f"\nFiles reviewed: {result['files_reviewed']}")
    print(f"Total issues: {result['total_issues']}")
    print(f"Critical issues: {result['critical_issues']}")
    print("\n" + "=" * 60)
    print("\nReport Preview:")
    print(result["report"][:2000])
    
    if result["total_issues"] > 0:
        print("\n... (truncated)")


if __name__ == "__main__":
    main()
