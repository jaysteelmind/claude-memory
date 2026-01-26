"""Performance benchmark tests for DMM.

These tests verify that operations complete within acceptable time bounds
and measure performance characteristics of the system.
"""

import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dmm.agentos.persistence.models import (
    AgentState,
    AgentStatus,
    MessageDirection,
    MessageRecord,
    SessionRecord,
)
from dmm.agentos.persistence.store import AgentOSStore


class TestPersistencePerformance:
    """Performance tests for persistence layer."""

    @pytest.fixture
    def store(self) -> AgentOSStore:
        """Create a temporary store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "agentos.db"
            store = AgentOSStore(db_path)
            store.initialize()
            yield store
            store.close()

    def test_bulk_agent_state_insert_performance(self, store: AgentOSStore) -> None:
        """Bulk insert of agent states should be fast."""
        count = 100
        
        start = time.perf_counter()
        
        for i in range(count):
            state = AgentState(
                agent_id=f"agent_{i}",
                session_id="session_perf",
                status=AgentStatus.IDLE,
                tokens_used=i * 10,
            )
            store.save_agent_state(state)
        
        elapsed = time.perf_counter() - start
        
        # Should complete in under 2 seconds
        assert elapsed < 2.0, f"Bulk insert took {elapsed:.2f}s, expected < 2s"
        
        # Verify all inserted
        states = store.get_agent_states_for_session("session_perf")
        assert len(states) == count

    def test_bulk_message_insert_performance(self, store: AgentOSStore) -> None:
        """Bulk insert of messages should be fast."""
        count = 500
        
        start = time.perf_counter()
        
        for i in range(count):
            message = MessageRecord(
                message_id=f"msg_{i}",
                session_id="session_perf",
                sender_id=f"agent_{i % 10}",
                recipient_id=f"agent_{(i + 1) % 10}",
                message_type="request",
                direction=MessageDirection.OUTBOUND,
                content={"index": i},
            )
            store.save_message(message)
        
        elapsed = time.perf_counter() - start
        
        # Should complete in under 3 seconds
        assert elapsed < 3.0, f"Bulk insert took {elapsed:.2f}s, expected < 3s"

    def test_message_query_performance(self, store: AgentOSStore) -> None:
        """Message queries should be fast even with many messages."""
        # Insert messages
        for i in range(200):
            message = MessageRecord(
                message_id=f"msg_{i}",
                session_id="session_perf",
                sender_id="agent_sender",
                recipient_id="agent_receiver",
                message_type="request",
                direction=MessageDirection.OUTBOUND,
                content={"index": i},
            )
            store.save_message(message)
        
        # Query performance
        start = time.perf_counter()
        
        for _ in range(50):
            messages = store.get_messages_for_session("session_perf", limit=50)
        
        elapsed = time.perf_counter() - start
        
        # 50 queries should complete in under 1 second
        assert elapsed < 1.0, f"Queries took {elapsed:.2f}s, expected < 1s"

    def test_session_operations_performance(self, store: AgentOSStore) -> None:
        """Session CRUD operations should be fast."""
        count = 50
        
        # Create sessions
        start = time.perf_counter()
        
        for i in range(count):
            session = SessionRecord(
                session_id=f"session_{i}",
                primary_agent_id=f"agent_{i}",
                active_agents=[f"agent_{i}", f"agent_{i+1}"],
            )
            store.create_session(session)
        
        create_elapsed = time.perf_counter() - start
        
        # Query active sessions
        start = time.perf_counter()
        
        for _ in range(20):
            active = store.get_active_sessions()
        
        query_elapsed = time.perf_counter() - start
        
        # End sessions
        start = time.perf_counter()
        
        for i in range(count):
            store.end_session(f"session_{i}")
        
        end_elapsed = time.perf_counter() - start
        
        # All operations should be fast
        assert create_elapsed < 1.0, f"Create took {create_elapsed:.2f}s"
        assert query_elapsed < 0.5, f"Query took {query_elapsed:.2f}s"
        assert end_elapsed < 1.0, f"End took {end_elapsed:.2f}s"


class TestExampleAgentPerformance:
    """Performance tests for example agents."""

    def test_code_review_agent_performance(self) -> None:
        """Code review should complete quickly for small files."""
        from examples.agents.code_review_agent import CodeReviewAgent
        
        agent = CodeReviewAgent()
        
        # Create test files
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(10):
                file_path = Path(tmpdir) / f"module_{i}.py"
                file_path.write_text(f'''"""Module {i}."""

def func_{i}(x: int) -> int:
    """Process x."""
    return x * 2

class Class_{i}:
    """Class {i}."""
    
    def method(self) -> None:
        """Do something."""
        pass
''')
            
            start = time.perf_counter()
            
            results = agent.review_directory(tmpdir, recursive=False)
            
            elapsed = time.perf_counter() - start
            
            assert len(results) == 10
            # Should complete in under 2 seconds
            assert elapsed < 2.0, f"Review took {elapsed:.2f}s, expected < 2s"

    def test_task_manager_performance(self) -> None:
        """Task manager operations should be fast."""
        from examples.agents.task_manager_agent import (
            TaskManagerAgent,
            TaskPriority,
        )
        
        agent = TaskManagerAgent()
        
        start = time.perf_counter()
        
        # Create many tasks
        for i in range(100):
            agent.create_task(
                name=f"Task {i}",
                description=f"Description for task {i}",
                priority=TaskPriority.NORMAL,
            )
        
        create_elapsed = time.perf_counter() - start
        
        # Schedule tasks
        start = time.perf_counter()
        agent.schedule_tasks()
        schedule_elapsed = time.perf_counter() - start
        
        # Get execution order
        start = time.perf_counter()
        order = agent.get_execution_order()
        order_elapsed = time.perf_counter() - start
        
        assert len(order) == 100
        assert create_elapsed < 0.5, f"Create took {create_elapsed:.2f}s"
        assert schedule_elapsed < 0.2, f"Schedule took {schedule_elapsed:.2f}s"
        assert order_elapsed < 0.1, f"Order took {order_elapsed:.2f}s"

    def test_research_assistant_decomposition_performance(self) -> None:
        """Question decomposition should be fast."""
        from examples.agents.research_assistant_agent import (
            ResearchAssistantAgent,
            ResearchDepth,
        )
        
        agent = ResearchAssistantAgent()
        
        queries = [
            "What are best practices for error handling?",
            "How to implement caching in Python?",
            "What is the difference between threads and processes?",
            "How to write effective unit tests?",
            "What are design patterns in software engineering?",
        ]
        
        start = time.perf_counter()
        
        for query in queries:
            questions = agent.decompose_question(query, ResearchDepth.COMPREHENSIVE)
            assert len(questions) > 0
        
        elapsed = time.perf_counter() - start
        
        # All decompositions should complete quickly
        assert elapsed < 0.5, f"Decomposition took {elapsed:.2f}s, expected < 0.5s"


class TestMemoryCuratorPerformance:
    """Performance tests for memory curator."""

    def test_memory_scan_performance(self) -> None:
        """Memory scanning should be efficient."""
        from examples.agents.memory_curator_agent import MemoryCuratorAgent
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = Path(tmpdir)
            
            # Create test memories
            project_dir = memory_dir / "project"
            project_dir.mkdir(parents=True)
            
            for i in range(50):
                (project_dir / f"memory_{i}.md").write_text(f'''---
id: mem_{i:03d}
tags: [test, performance, batch_{i % 5}]
scope: project
priority: {0.5 + (i % 5) * 0.1}
confidence: active
status: active
---

# Memory {i}

This is test memory number {i} for performance testing.
''')
            
            agent = MemoryCuratorAgent(memory_dir=memory_dir)
            
            start = time.perf_counter()
            count = agent.scan_memories()
            elapsed = time.perf_counter() - start
            
            assert count == 50
            # Scanning 50 files should be fast
            assert elapsed < 1.0, f"Scan took {elapsed:.2f}s, expected < 1s"

    def test_conflict_detection_performance(self) -> None:
        """Conflict detection should scale reasonably."""
        from examples.agents.memory_curator_agent import MemoryCuratorAgent
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_dir = Path(tmpdir)
            project_dir = memory_dir / "project"
            project_dir.mkdir(parents=True)
            
            # Create memories with overlapping tags
            for i in range(30):
                tags = [f"tag_{i % 3}", f"tag_{(i + 1) % 3}", "common"]
                (project_dir / f"memory_{i}.md").write_text(f'''---
id: mem_{i:03d}
tags: {tags}
scope: project
priority: 0.5
confidence: active
status: active
---

# Memory {i}

Content for memory {i}.
''')
            
            agent = MemoryCuratorAgent(memory_dir=memory_dir)
            agent.scan_memories()
            
            start = time.perf_counter()
            conflicts = agent.find_potential_conflicts()
            elapsed = time.perf_counter() - start
            
            # O(n^2) comparison should still be fast for 30 items
            assert elapsed < 0.5, f"Conflict detection took {elapsed:.2f}s"


class TestWorkflowPerformance:
    """Performance tests for workflows."""

    def test_code_review_pipeline_performance(self) -> None:
        """Code review pipeline should complete in reasonable time."""
        from examples.workflows.code_review_pipeline import run_code_review_pipeline
        
        start = time.perf_counter()
        
        result = run_code_review_pipeline(
            target_path="examples/agents",
            recursive=False,
        )
        
        elapsed = time.perf_counter() - start
        
        assert result["success"] is True
        # Pipeline for ~4 files should be fast
        assert elapsed < 3.0, f"Pipeline took {elapsed:.2f}s, expected < 3s"
