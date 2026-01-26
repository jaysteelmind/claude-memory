"""Tests for ResearchAssistantAgent."""

import pytest

from examples.agents.research_assistant_agent import (
    ResearchAssistantAgent,
    ResearchAssistantConfig,
    ResearchDepth,
    ResearchFinding,
    ResearchQuestion,
    ResearchReport,
)


class TestResearchAssistantAgent:
    """Tests for ResearchAssistantAgent."""

    def test_init_default_config(self) -> None:
        """Agent initializes with default config."""
        agent = ResearchAssistantAgent()
        
        assert agent.config.max_questions == 10
        assert agent.config.default_depth == ResearchDepth.STANDARD

    def test_init_custom_config(self) -> None:
        """Agent initializes with custom config."""
        config = ResearchAssistantConfig(
            max_questions=5,
            default_depth=ResearchDepth.QUICK,
        )
        agent = ResearchAssistantAgent(config=config)
        
        assert agent.config.max_questions == 5

    def test_decompose_question_quick(self) -> None:
        """Decompose question at quick depth."""
        agent = ResearchAssistantAgent()
        
        questions = agent.decompose_question(
            query="What is error handling?",
            depth=ResearchDepth.QUICK,
        )
        
        assert len(questions) == 1
        assert questions[0].category == "main"

    def test_decompose_question_standard(self) -> None:
        """Decompose question at standard depth."""
        agent = ResearchAssistantAgent()
        
        questions = agent.decompose_question(
            query="What is error handling?",
            depth=ResearchDepth.STANDARD,
        )
        
        assert len(questions) > 1
        assert questions[0].category == "main"
        assert any(q.parent_id == "q_main" for q in questions[1:])

    def test_decompose_question_comprehensive(self) -> None:
        """Decompose question at comprehensive depth."""
        agent = ResearchAssistantAgent()
        
        questions = agent.decompose_question(
            query="What is error handling?",
            depth=ResearchDepth.COMPREHENSIVE,
        )
        
        assert len(questions) > 3
        assert any(q.priority == 3 for q in questions)

    def test_decompose_identifies_categories(self) -> None:
        """Decomposition identifies relevant categories."""
        agent = ResearchAssistantAgent()
        
        questions = agent.decompose_question(
            query="How to implement caching?",
            depth=ResearchDepth.STANDARD,
        )
        
        categories = [q.category for q in questions]
        assert "implementation" in categories or "main" in categories

    def test_research_returns_report(self) -> None:
        """Research returns a complete report."""
        agent = ResearchAssistantAgent()
        
        report = agent.research(
            query="What are best practices?",
            depth=ResearchDepth.QUICK,
        )
        
        assert isinstance(report, ResearchReport)
        assert report.query == "What are best practices?"
        assert len(report.questions) >= 1

    def test_research_with_memory_search(self) -> None:
        """Research uses memory search function."""
        search_called = []
        
        def mock_search(query: str, limit: int = 5) -> list:
            search_called.append(query)
            return [
                {
                    "id": "mem_001",
                    "content": "Test content about the topic.",
                    "relevance": 0.8,
                }
            ]
        
        agent = ResearchAssistantAgent(memory_search_func=mock_search)
        
        report = agent.research("Test query", depth=ResearchDepth.QUICK)
        
        assert len(search_called) >= 1
        assert len(report.findings) >= 1

    def test_research_comprehensive(self) -> None:
        """Research at comprehensive depth."""
        agent = ResearchAssistantAgent()
        
        report = agent.research(
            query="How to handle errors in Python?",
            depth=ResearchDepth.COMPREHENSIVE,
        )
        
        assert len(report.questions) > 3
        assert report.depth == ResearchDepth.COMPREHENSIVE

    def test_generate_report_markdown(self) -> None:
        """Generate markdown report."""
        agent = ResearchAssistantAgent()
        
        report = agent.research("Test query", depth=ResearchDepth.QUICK)
        markdown = agent.generate_report_markdown(report)
        
        assert "# " in markdown
        assert "Test query" in markdown
        assert "## Executive Summary" in markdown

    def test_research_history(self) -> None:
        """Research history is maintained."""
        agent = ResearchAssistantAgent()
        
        agent.research("Query 1", depth=ResearchDepth.QUICK)
        agent.research("Query 2", depth=ResearchDepth.QUICK)
        
        history = agent.get_research_history()
        
        assert len(history) == 2

    def test_clear_history(self) -> None:
        """Clear research history."""
        agent = ResearchAssistantAgent()
        
        agent.research("Query 1", depth=ResearchDepth.QUICK)
        agent.clear_history()
        
        assert len(agent.get_research_history()) == 0

    def test_extract_topic(self) -> None:
        """Topic extraction from query."""
        agent = ResearchAssistantAgent()
        
        topic = agent._extract_topic("What are the best practices for error handling?")
        
        assert "error" in topic.lower() or "handling" in topic.lower()

    def test_synthesis_generation(self) -> None:
        """Synthesis is generated from findings."""
        agent = ResearchAssistantAgent()
        
        report = agent.research(
            query="How to write tests?",
            depth=ResearchDepth.STANDARD,
        )
        
        assert report.synthesis is not None
        assert len(report.synthesis) > 0

    def test_finding_deduplication(self) -> None:
        """Duplicate findings are removed."""
        agent = ResearchAssistantAgent()
        
        findings = [
            ResearchFinding(
                finding_id="f1",
                content="Same content here",
                sources=["s1"],
                confidence=0.8,
                relevance=0.8,
                category="test",
            ),
            ResearchFinding(
                finding_id="f2",
                content="Same content here",
                sources=["s2"],
                confidence=0.7,
                relevance=0.7,
                category="test",
            ),
        ]
        
        unique = agent._deduplicate_findings(findings)
        
        assert len(unique) == 1

    def test_report_to_dict(self) -> None:
        """Report converts to dictionary."""
        agent = ResearchAssistantAgent()
        
        report = agent.research("Test query", depth=ResearchDepth.QUICK)
        data = report.to_dict()
        
        assert "title" in data
        assert "query" in data
        assert "questions" in data
        assert "findings" in data
        assert "synthesis" in data


class TestResearchQuestion:
    """Tests for ResearchQuestion dataclass."""

    def test_create_question(self) -> None:
        """Create research question."""
        question = ResearchQuestion(
            question_id="q_001",
            text="What is X?",
            category="definition",
            priority=1,
        )
        
        assert question.question_id == "q_001"
        assert question.answer is None
        assert question.confidence == 0.0


class TestResearchFinding:
    """Tests for ResearchFinding dataclass."""

    def test_create_finding(self) -> None:
        """Create research finding."""
        finding = ResearchFinding(
            finding_id="f_001",
            content="Finding content",
            sources=["source_1"],
            confidence=0.8,
            relevance=0.9,
            category="test",
        )
        
        assert finding.finding_id == "f_001"
        assert finding.confidence == 0.8


class TestResearchDepth:
    """Tests for ResearchDepth enum."""

    def test_depth_values(self) -> None:
        """Depth enum has expected values."""
        assert ResearchDepth.QUICK.value == "quick"
        assert ResearchDepth.STANDARD.value == "standard"
        assert ResearchDepth.COMPREHENSIVE.value == "comprehensive"
