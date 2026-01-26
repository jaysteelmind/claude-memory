"""
Shared pytest fixtures for task module tests.
"""

import pytest
import tempfile
from pathlib import Path

from dmm.agentos.tasks import (
    Task,
    TaskStore,
    TaskScheduler,
    TaskTracker,
    TaskPlanner,
)


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def task_store(temp_dir):
    """Create initialized task store."""
    store = TaskStore(temp_dir, use_file_storage=False)
    store.initialize()
    yield store
    store.close()


@pytest.fixture
def scheduler(task_store):
    """Create task scheduler."""
    return TaskScheduler(task_store)


@pytest.fixture
def tracker(task_store):
    """Create task tracker."""
    return TaskTracker(task_store)


@pytest.fixture
def planner():
    """Create task planner."""
    return TaskPlanner()


@pytest.fixture
def sample_task():
    """Create sample task for testing."""
    return Task(
        name="Sample task",
        description="A sample task for testing",
        priority=5,
        tags=["test", "sample"],
    )
