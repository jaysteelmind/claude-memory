"""Research Task Workflow.

Demonstrates:
    User Request -> Task Manager -> Research Assistant -> Memory Curator -> Report

This workflow shows how agents collaborate to research a topic.
"""

from pathlib import Path
from typing import Any

from examples.agents.memory_curator_agent import MemoryCuratorAgent
from examples.agents.research_assistant_agent import (
    ResearchAssistantAgent,
    ResearchDepth,
)
from examples.agents.task_manager_agent import (
    TaskManagerAgent,
    TaskPriority,
)


def run_research_task(
    query: str,
    depth: ResearchDepth = ResearchDepth.STANDARD,
    memory_dir: Path | None = None,
) -> dict[str, Any]:
    """Run the research task workflow.
    
    This workflow:
    1. Task Manager creates and manages the research task
    2. Memory Curator provides relevant memories
    3. Research Assistant conducts research and generates report
    
    Args:
        query: Research query or question.
        depth: Research depth level.
        memory_dir: Optional path to memory directory.
        
    Returns:
        Dictionary with workflow results.
    """
    task_manager = TaskManagerAgent()
    memory_curator = MemoryCuratorAgent(memory_dir=memory_dir)
    
    def memory_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search memories using the curator."""
        results = memory_curator.search_memories(query=query)
        return results[:limit]
    
    research_assistant = ResearchAssistantAgent(
        memory_search_func=memory_search,
    )
    
    events: list[dict[str, Any]] = []
    
    def on_task_event(task: Any, event: str) -> None:
        events.append({
            "task_id": task.task_id,
            "task_name": task.name,
            "event": event,
        })
    
    task_manager.subscribe(on_task_event)
    
    main_task = task_manager.create_task(
        name="Research Task",
        description=f"Research: {query}",
        priority=TaskPriority.NORMAL,
        inputs={"query": query, "depth": depth.value},
    )
    
    subtasks = task_manager.decompose_task(
        main_task.task_id,
        subtask_definitions=[
            {"name": "Scan memories", "description": "Search for relevant memories"},
            {"name": "Decompose question", "description": "Break down research question"},
            {"name": "Gather information", "description": "Collect relevant information"},
            {"name": "Synthesize findings", "description": "Analyze and synthesize results"},
            {"name": "Generate report", "description": "Create research report"},
        ],
    )
    
    task_manager.schedule_tasks()
    
    scan_task = subtasks[0]
    task_manager.start_task(scan_task.task_id)
    
    memory_count = memory_curator.scan_memories()
    relevant_memories = memory_curator.search_memories(query=query)
    
    task_manager.complete_task(
        scan_task.task_id,
        outputs={
            "total_memories": memory_count,
            "relevant_memories": len(relevant_memories),
        },
    )
    
    decompose_task = subtasks[1]
    task_manager.start_task(decompose_task.task_id)
    
    questions = research_assistant.decompose_question(query, depth)
    
    task_manager.complete_task(
        decompose_task.task_id,
        outputs={"question_count": len(questions)},
    )
    
    gather_task = subtasks[2]
    task_manager.start_task(gather_task.task_id)
    
    report = research_assistant.research(query, depth)
    
    task_manager.update_progress(gather_task.task_id, 0.5)
    
    task_manager.complete_task(
        gather_task.task_id,
        outputs={"finding_count": len(report.findings)},
    )
    
    synthesize_task = subtasks[3]
    task_manager.start_task(synthesize_task.task_id)
    
    answered_questions = [q for q in report.questions if q.answer]
    
    task_manager.complete_task(
        synthesize_task.task_id,
        outputs={"answered_questions": len(answered_questions)},
    )
    
    report_task = subtasks[4]
    task_manager.start_task(report_task.task_id)
    
    markdown_report = research_assistant.generate_report_markdown(report)
    
    task_manager.complete_task(
        report_task.task_id,
        outputs={"report_length": len(markdown_report)},
    )
    
    task_manager.complete_task(
        main_task.task_id,
        outputs={
            "questions_researched": len(report.questions),
            "findings_collected": len(report.findings),
        },
    )
    
    return {
        "success": True,
        "task_id": main_task.task_id,
        "query": query,
        "depth": depth.value,
        "questions_count": len(report.questions),
        "findings_count": len(report.findings),
        "answered_count": len(answered_questions),
        "report": markdown_report,
        "report_data": report.to_dict(),
        "events": events,
        "memory_stats": {
            "total_scanned": memory_count,
            "relevant_found": len(relevant_memories),
        },
    }


def main() -> None:
    """Run the research task workflow."""
    import sys
    
    query = sys.argv[1] if len(sys.argv) > 1 else "What are best practices for error handling in Python?"
    
    print(f"Running research task: {query}")
    print("=" * 60)
    
    result = run_research_task(query, depth=ResearchDepth.STANDARD)
    
    print(f"\nQuestions researched: {result['questions_count']}")
    print(f"Findings collected: {result['findings_count']}")
    print(f"Questions answered: {result['answered_count']}")
    print(f"\nMemory stats: {result['memory_stats']}")
    print("\n" + "=" * 60)
    print("\nReport:")
    print(result["report"][:3000])
    
    if len(result["report"]) > 3000:
        print("\n... (truncated)")


if __name__ == "__main__":
    main()
