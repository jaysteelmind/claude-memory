"""Example workflows demonstrating multi-agent collaboration."""

from .code_review_pipeline import run_code_review_pipeline
from .research_task import run_research_task
from .system_maintenance import run_system_maintenance

__all__ = [
    "run_code_review_pipeline",
    "run_research_task",
    "run_system_maintenance",
]
