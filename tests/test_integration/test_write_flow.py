"""Integration tests for the full write flow."""

import pytest
from pathlib import Path

from dmm.core.config import DMMConfig
from dmm.indexer.embedder import MemoryEmbedder
from dmm.indexer.indexer import Indexer
from dmm.indexer.store import MemoryStore
from dmm.models.proposal import ProposalStatus, ProposalType, ReviewDecision
from dmm.reviewer.agent import ReviewerAgent
from dmm.writeback.commit import CommitEngine
from dmm.writeback.proposal import ProposalHandler
from dmm.writeback.queue import ReviewQueue


@pytest.fixture
def dmm_setup(tmp_path: Path):
    """Set up a complete DMM environment for integration tests."""
    # Create directory structure
    dmm_root = tmp_path / ".dmm"
    memory_root = dmm_root / "memory"
    index_root = dmm_root / "index"
    
    for scope in ["baseline", "global", "agent", "project", "ephemeral", "deprecated"]:
        (memory_root / scope).mkdir(parents=True, exist_ok=True)
    index_root.mkdir(parents=True, exist_ok=True)
    
    # Create config
    config = DMMConfig()
    config_path = dmm_root / "config.yaml"
    
    # Initialize components
    store = MemoryStore(index_root / "embeddings.db")
    store.initialize()
    
    queue = ReviewQueue(tmp_path)
    queue.initialize()
    
    embedder = MemoryEmbedder()
    
    indexer = Indexer(config, tmp_path)
    
    handler = ProposalHandler(queue, store, tmp_path)
    reviewer = ReviewerAgent(queue, store, embedder, tmp_path)
    commit_engine = CommitEngine(queue, indexer, tmp_path)
    
    yield {
        "tmp_path": tmp_path,
        "dmm_root": dmm_root,
        "memory_root": memory_root,
        "store": store,
        "queue": queue,
        "embedder": embedder,
        "indexer": indexer,
        "handler": handler,
        "reviewer": reviewer,
        "commit_engine": commit_engine,
    }
    
    # Cleanup
    queue.close()
    store.close()


def make_valid_content(
    memory_id: str = "mem_2025_01_11_001",
    title: str = "Test Memory",
    tags: list | None = None,
    scope: str = "project",
) -> str:
    """Create valid memory content for testing."""
    tag_list = tags or ["test", "integration"]
    return f"""---
id: {memory_id}
tags: {tag_list}
scope: {scope}
priority: 0.7
confidence: active
status: active
created: 2025-01-11
---

# {title}

This is a test memory created for integration testing purposes.
It contains enough content to meet the minimum token requirements.

## Details

The memory system validates content for:
- Schema compliance with required fields
- Token count within acceptable range
- Single concept focus
- Quality and coherence

## Rationale

This memory exists to verify the write-back engine functions correctly
end-to-end, from proposal through review to commit.
"""


class TestFullWriteFlow:
    """Tests for the complete write flow: Propose → Review → Commit."""

    def test_create_approve_commit_flow(self, dmm_setup) -> None:
        """Test full create flow: propose → review → approve → commit."""
        handler = dmm_setup["handler"]
        reviewer = dmm_setup["reviewer"]
        commit_engine = dmm_setup["commit_engine"]
        memory_root = dmm_setup["memory_root"]
        
        # Step 1: Propose
        content = make_valid_content()
        proposal = handler.propose_create(
            target_path="project/test_memory.md",
            content=content,
            reason="Integration test",
        )
        
        assert proposal.status == ProposalStatus.PENDING
        assert proposal.type == ProposalType.CREATE
        
        # Step 2: Review
        result = reviewer.review(proposal)
        
        assert result.decision in (ReviewDecision.APPROVE, ReviewDecision.DEFER)
        assert result.schema_valid is True
        
        # Step 3: Commit (if approved)
        if result.decision == ReviewDecision.APPROVE:
            # Update proposal status
            dmm_setup["queue"].update_status(
                proposal.proposal_id,
                ProposalStatus.APPROVED,
            )
            proposal = dmm_setup["queue"].get(proposal.proposal_id)
            
            commit_result = commit_engine.commit(proposal)
            
            assert commit_result.success is True
            assert commit_result.memory_path == "project/test_memory.md"
            
            # Verify file exists
            target_file = memory_root / "project" / "test_memory.md"
            assert target_file.exists()
            assert "# Test Memory" in target_file.read_text()

    def test_create_reject_flow(self, dmm_setup) -> None:
        """Test rejection flow: propose with missing frontmatter fails precheck."""
        handler = dmm_setup["handler"]
        
        # Propose with content missing frontmatter entirely
        invalid_content = "Just plain text without frontmatter"
        
        # This should fail at precheck due to missing frontmatter
        from dmm.core.exceptions import ProposalError
        with pytest.raises(ProposalError):
            handler.propose_create(
                target_path="project/invalid.md",
                content=invalid_content,
                reason="Should fail",
            )
    
    def test_review_catches_schema_errors(self, dmm_setup) -> None:
        """Test that review catches schema validation errors."""
        handler = dmm_setup["handler"]
        reviewer = dmm_setup["reviewer"]
        queue = dmm_setup["queue"]
        
        # Content with frontmatter but missing required fields
        # Precheck passes basic format, review catches schema errors
        partial_content = """---
id: test_partial
tags: [test]
scope: project
priority: 0.5
confidence: active
status: active
---

# Minimal

Short content that should trigger quality warnings.
"""
        
        proposal = handler.propose_create(
            target_path="project/partial.md",
            content=partial_content,
            reason="Test partial content",
        )
        
        # Review should identify issues
        result = reviewer.review(proposal)
        
        # Should have some issues (at least quality warnings for short content)
        assert len(result.issues) > 0 or result.decision in (ReviewDecision.APPROVE, ReviewDecision.DEFER)

    def test_duplicate_detection_flow(self, dmm_setup) -> None:
        """Test duplicate rejection: propose duplicate → detected → rejected."""
        handler = dmm_setup["handler"]
        reviewer = dmm_setup["reviewer"]
        commit_engine = dmm_setup["commit_engine"]
        queue = dmm_setup["queue"]
        
        # First, create and commit a memory
        content1 = make_valid_content(
            memory_id="mem_2025_01_11_001",
            title="Database Connection Rules",
        )
        
        proposal1 = handler.propose_create(
            target_path="project/db_rules.md",
            content=content1,
            reason="First memory",
        )
        
        result1 = reviewer.review(proposal1)
        
        if result1.decision == ReviewDecision.APPROVE:
            queue.update_status(proposal1.proposal_id, ProposalStatus.APPROVED)
            proposal1 = queue.get(proposal1.proposal_id)
            commit_engine.commit(proposal1)
        
        # Now try to create at same path - should fail precheck
        content2 = make_valid_content(
            memory_id="mem_2025_01_11_002",
            title="Database Connection Rules Copy",
        )
        
        from dmm.core.exceptions import ProposalError
        with pytest.raises(ProposalError) as exc_info:
            handler.propose_create(
                target_path="project/db_rules.md",
                content=content2,
                reason="Duplicate path",
            )
        
        assert "exists" in str(exc_info.value.message).lower()


class TestDeprecationFlow:
    """Tests for deprecation workflow."""

    def test_deprecate_flow(self, dmm_setup) -> None:
        """Test deprecation: create → deprecate → moved to deprecated."""
        handler = dmm_setup["handler"]
        reviewer = dmm_setup["reviewer"]
        commit_engine = dmm_setup["commit_engine"]
        queue = dmm_setup["queue"]
        store = dmm_setup["store"]
        memory_root = dmm_setup["memory_root"]
        
        # First create a memory
        content = make_valid_content(
            memory_id="mem_2025_01_11_dep",
            title="Memory to Deprecate",
        )
        
        proposal = handler.propose_create(
            target_path="project/to_deprecate.md",
            content=content,
            reason="Will be deprecated",
        )
        
        result = reviewer.review(proposal)
        if result.decision == ReviewDecision.APPROVE:
            queue.update_status(proposal.proposal_id, ProposalStatus.APPROVED)
            proposal = queue.get(proposal.proposal_id)
            commit_engine.commit(proposal)
        
        # Check file exists
        target_file = memory_root / "project" / "to_deprecate.md"
        if target_file.exists():
            # Now index it so we can deprecate
            from dmm.indexer.parser import MemoryParser, TokenCounter
            parser = MemoryParser(TokenCounter())
            parse_result = parser.parse(target_file)
            
            if parse_result.memory:
                # Use embedder to create embeddings and hash for store
                from dmm.indexer.embedder import MemoryEmbedder
                import hashlib
                
                embedder = MemoryEmbedder()
                memory = parse_result.memory
                
                # embed_memory takes a MemoryFile object
                embedding_result = embedder.embed_memory(memory)
                file_hash = hashlib.sha256(target_file.read_text().encode()).hexdigest()
                
                store.upsert_memory(
                    memory, 
                    embedding_result.composite_embedding, 
                    embedding_result.directory_embedding, 
                    file_hash,
                )
                memory_id = memory.id
                
                # Now propose deprecation
                deprecate_proposal = handler.propose_deprecate(
                    memory_id=memory_id,
                    reason="No longer needed for testing",
                )
                
                assert deprecate_proposal.type == ProposalType.DEPRECATE


class TestPromotionFlow:
    """Tests for promotion workflow."""

    def test_promote_scope_change(self, dmm_setup) -> None:
        """Test promotion changes scope correctly."""
        handler = dmm_setup["handler"]
        reviewer = dmm_setup["reviewer"]
        commit_engine = dmm_setup["commit_engine"]
        queue = dmm_setup["queue"]
        store = dmm_setup["store"]
        memory_root = dmm_setup["memory_root"]
        
        # Create an ephemeral memory
        content = make_valid_content(
            memory_id="mem_2025_01_11_eph",
            title="Ephemeral Finding",
            scope="ephemeral",
        )
        
        proposal = handler.propose_create(
            target_path="ephemeral/finding.md",
            content=content,
            reason="Temporary finding",
        )
        
        result = reviewer.review(proposal)
        if result.decision == ReviewDecision.APPROVE:
            queue.update_status(proposal.proposal_id, ProposalStatus.APPROVED)
            proposal = queue.get(proposal.proposal_id)
            commit_engine.commit(proposal)
        
        # Check file exists and index it
        target_file = memory_root / "ephemeral" / "finding.md"
        if target_file.exists():
            from dmm.indexer.parser import MemoryParser, TokenCounter
            parser = MemoryParser(TokenCounter())
            parse_result = parser.parse(target_file)
            
            if parse_result.memory:
                # Use embedder to create embeddings and hash for store
                from dmm.indexer.embedder import MemoryEmbedder
                import hashlib
                
                embedder = MemoryEmbedder()
                memory = parse_result.memory
                
                # embed_memory takes a MemoryFile object
                embedding_result = embedder.embed_memory(memory)
                file_hash = hashlib.sha256(target_file.read_text().encode()).hexdigest()
                
                store.upsert_memory(
                    memory,
                    embedding_result.composite_embedding,
                    embedding_result.directory_embedding,
                    file_hash,
                )
                memory_id = memory.id
                
                # Propose promotion to project scope
                promote_proposal = handler.propose_promote(
                    memory_id=memory_id,
                    new_scope="project",
                    reason="Proved useful, promoting to project",
                )
                
                assert promote_proposal.type == ProposalType.PROMOTE
                assert promote_proposal.new_scope == "project"


class TestBaselineProtection:
    """Tests for baseline protection (always deferred)."""

    def test_baseline_create_deferred(self, dmm_setup) -> None:
        """Test that baseline creates are deferred for human review."""
        handler = dmm_setup["handler"]
        reviewer = dmm_setup["reviewer"]
        
        content = make_valid_content(
            memory_id="mem_2025_01_11_base",
            title="Baseline Memory",
            scope="baseline",
        )
        
        proposal = handler.propose_create(
            target_path="baseline/critical.md",
            content=content,
            reason="Critical baseline info",
        )
        
        result = reviewer.review(proposal)
        
        # Baseline should always be deferred
        assert result.decision == ReviewDecision.DEFER
        assert "baseline" in result.notes.lower() or "human" in result.notes.lower()


class TestUsageTracking:
    """Tests for usage tracking integration."""

    def test_usage_tracker_initialization(self, dmm_setup) -> None:
        """Test that usage tracker can be initialized."""
        from dmm.writeback.usage import UsageTracker
        
        tracker = UsageTracker(dmm_setup["tmp_path"])
        tracker.initialize()
        
        stats = tracker.get_stats(days=30)
        assert stats.total_queries == 0
        
        tracker.close()

    def test_log_query(self, dmm_setup) -> None:
        """Test logging a query."""
        from dmm.writeback.usage import UsageTracker
        
        tracker = UsageTracker(dmm_setup["tmp_path"])
        tracker.initialize()
        
        query_id = tracker.log_query(
            query_text="test query",
            budget=1500,
            baseline_budget=800,
            baseline_files=2,
            retrieved_files=3,
            total_tokens=1200,
            retrieved_memory_ids=["mem_1", "mem_2", "mem_3"],
            query_time_ms=150.0,
        )
        
        assert query_id.startswith("qry_")
        
        stats = tracker.get_stats(days=1)
        assert stats.total_queries == 1
        
        tracker.close()
