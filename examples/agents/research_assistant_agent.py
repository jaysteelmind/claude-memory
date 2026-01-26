"""Research Assistant Agent - Assists with research and information gathering.

This agent demonstrates:
- Question decomposition
- Information retrieval from memories
- Synthesis of findings
- Report generation
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ResearchDepth(str, Enum):
    """Research depth levels."""
    
    QUICK = "quick"
    STANDARD = "standard"
    COMPREHENSIVE = "comprehensive"


@dataclass
class ResearchQuestion:
    """A decomposed research question."""
    
    question_id: str
    text: str
    category: str
    priority: int
    parent_id: str | None = None
    answer: str | None = None
    sources: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class ResearchFinding:
    """A research finding with sources."""
    
    finding_id: str
    content: str
    sources: list[str]
    confidence: float
    relevance: float
    category: str


@dataclass
class ResearchReport:
    """Complete research report."""
    
    title: str
    query: str
    questions: list[ResearchQuestion]
    findings: list[ResearchFinding]
    synthesis: str
    generated_at: datetime
    depth: ResearchDepth
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "title": self.title,
            "query": self.query,
            "questions": [
                {
                    "question_id": q.question_id,
                    "text": q.text,
                    "category": q.category,
                    "answer": q.answer,
                    "sources": q.sources,
                    "confidence": q.confidence,
                }
                for q in self.questions
            ],
            "findings": [
                {
                    "finding_id": f.finding_id,
                    "content": f.content,
                    "sources": f.sources,
                    "confidence": f.confidence,
                    "relevance": f.relevance,
                }
                for f in self.findings
            ],
            "synthesis": self.synthesis,
            "generated_at": self.generated_at.isoformat(),
            "depth": self.depth.value,
        }


@dataclass
class ResearchAssistantConfig:
    """Configuration for ResearchAssistantAgent."""
    
    max_questions: int = 10
    max_findings: int = 20
    min_confidence: float = 0.5
    default_depth: ResearchDepth = ResearchDepth.STANDARD


class ResearchAssistantAgent:
    """Agent that assists with research and information gathering.
    
    This agent provides:
    - Question decomposition
    - Memory-based information retrieval
    - Finding synthesis
    - Report generation
    
    Example:
        agent = ResearchAssistantAgent()
        report = agent.research("What are best practices for error handling?")
        print(report.synthesis)
    """
    
    def __init__(
        self,
        config: ResearchAssistantConfig | None = None,
        memory_search_func: Any | None = None,
    ) -> None:
        """Initialize the agent.
        
        Args:
            config: Optional configuration.
            memory_search_func: Optional function to search memories.
        """
        self.config = config or ResearchAssistantConfig()
        self._memory_search = memory_search_func
        self._research_history: list[ResearchReport] = []
    
    def research(
        self,
        query: str,
        depth: ResearchDepth | None = None,
        context: dict[str, Any] | None = None,
    ) -> ResearchReport:
        """Conduct research on a query.
        
        Args:
            query: Research query or question.
            depth: Research depth level.
            context: Optional context information.
            
        Returns:
            Complete ResearchReport.
        """
        depth = depth or self.config.default_depth
        
        questions = self.decompose_question(query, depth)
        
        findings = []
        for question in questions:
            question_findings = self._research_question(question, context)
            findings.extend(question_findings)
            
            if question_findings:
                question.answer = self._synthesize_answer(question, question_findings)
                question.sources = [f.finding_id for f in question_findings]
                question.confidence = sum(f.confidence for f in question_findings) / len(question_findings)
        
        findings = self._deduplicate_findings(findings)
        findings.sort(key=lambda f: (f.relevance, f.confidence), reverse=True)
        findings = findings[:self.config.max_findings]
        
        synthesis = self._generate_synthesis(query, questions, findings)
        
        title = self._generate_title(query)
        
        report = ResearchReport(
            title=title,
            query=query,
            questions=questions,
            findings=findings,
            synthesis=synthesis,
            generated_at=datetime.now(timezone.utc),
            depth=depth,
        )
        
        self._research_history.append(report)
        return report
    
    def decompose_question(
        self,
        query: str,
        depth: ResearchDepth,
    ) -> list[ResearchQuestion]:
        """Decompose a complex question into sub-questions.
        
        Args:
            query: Main research query.
            depth: Research depth level.
            
        Returns:
            List of decomposed questions.
        """
        questions = []
        query_lower = query.lower()
        
        questions.append(ResearchQuestion(
            question_id="q_main",
            text=query,
            category="main",
            priority=1,
        ))
        
        if depth == ResearchDepth.QUICK:
            return questions
        
        categories = self._identify_categories(query_lower)
        
        for i, category in enumerate(categories):
            sub_question = self._generate_sub_question(query, category)
            questions.append(ResearchQuestion(
                question_id=f"q_sub_{i}",
                text=sub_question,
                category=category,
                priority=2,
                parent_id="q_main",
            ))
        
        if depth == ResearchDepth.COMPREHENSIVE:
            for i, category in enumerate(categories[:3]):
                detail_question = self._generate_detail_question(query, category)
                questions.append(ResearchQuestion(
                    question_id=f"q_detail_{i}",
                    text=detail_question,
                    category=f"{category}_detail",
                    priority=3,
                    parent_id=f"q_sub_{i}",
                ))
        
        return questions[:self.config.max_questions]
    
    def _identify_categories(self, query: str) -> list[str]:
        """Identify relevant categories for a query."""
        categories = []
        
        category_keywords = {
            "definition": ["what is", "define", "meaning of"],
            "implementation": ["how to", "implement", "create", "build"],
            "best_practices": ["best practice", "recommended", "should"],
            "examples": ["example", "sample", "demonstrate"],
            "comparison": ["compare", "difference", "versus", "vs"],
            "troubleshooting": ["error", "problem", "issue", "fix"],
            "performance": ["performance", "optimize", "fast", "efficient"],
            "security": ["security", "secure", "safe", "protect"],
        }
        
        for category, keywords in category_keywords.items():
            if any(kw in query for kw in keywords):
                categories.append(category)
        
        if not categories:
            categories = ["definition", "implementation", "best_practices"]
        
        return categories
    
    def _generate_sub_question(self, query: str, category: str) -> str:
        """Generate a sub-question for a category."""
        templates = {
            "definition": "What is the definition and core concept of {topic}?",
            "implementation": "How is {topic} implemented in practice?",
            "best_practices": "What are the best practices for {topic}?",
            "examples": "What are concrete examples of {topic}?",
            "comparison": "How does {topic} compare to alternatives?",
            "troubleshooting": "What are common issues with {topic} and how to solve them?",
            "performance": "How to optimize {topic} for better performance?",
            "security": "What are the security considerations for {topic}?",
        }
        
        topic = self._extract_topic(query)
        template = templates.get(category, "What about {topic}?")
        return template.format(topic=topic)
    
    def _generate_detail_question(self, query: str, category: str) -> str:
        """Generate a detailed follow-up question."""
        topic = self._extract_topic(query)
        
        detail_templates = {
            "definition": f"What are the key components and characteristics of {topic}?",
            "implementation": f"What are the specific steps to implement {topic}?",
            "best_practices": f"What mistakes should be avoided when working with {topic}?",
        }
        
        return detail_templates.get(
            category,
            f"Can you provide more details about {topic} regarding {category}?",
        )
    
    def _extract_topic(self, query: str) -> str:
        """Extract the main topic from a query."""
        stop_words = {
            "what", "is", "are", "how", "to", "the", "a", "an",
            "for", "in", "of", "and", "or", "with", "best", "practices",
        }
        
        words = re.findall(r'\b\w+\b', query.lower())
        topic_words = [w for w in words if w not in stop_words]
        
        return " ".join(topic_words[:5]) if topic_words else query[:50]
    
    def _research_question(
        self,
        question: ResearchQuestion,
        context: dict[str, Any] | None,
    ) -> list[ResearchFinding]:
        """Research a single question."""
        findings = []
        
        if self._memory_search:
            try:
                memories = self._memory_search(
                    query=question.text,
                    limit=5,
                )
                
                for i, memory in enumerate(memories):
                    findings.append(ResearchFinding(
                        finding_id=f"f_{question.question_id}_{i}",
                        content=memory.get("content", memory.get("body_preview", "")),
                        sources=[memory.get("id", f"memory_{i}")],
                        confidence=memory.get("relevance", 0.7),
                        relevance=memory.get("relevance", 0.7),
                        category=question.category,
                    ))
            except Exception:
                pass
        
        if not findings:
            findings.append(ResearchFinding(
                finding_id=f"f_{question.question_id}_sim",
                content=f"Simulated finding for: {question.text}",
                sources=["simulated"],
                confidence=0.5,
                relevance=0.5,
                category=question.category,
            ))
        
        return findings
    
    def _synthesize_answer(
        self,
        question: ResearchQuestion,
        findings: list[ResearchFinding],
    ) -> str:
        """Synthesize an answer from findings."""
        if not findings:
            return "No relevant information found."
        
        contents = [f.content for f in findings if f.confidence >= self.config.min_confidence]
        
        if not contents:
            return "Findings below confidence threshold."
        
        if len(contents) == 1:
            return contents[0][:500]
        
        return f"Based on {len(contents)} sources: " + " ".join(contents)[:500]
    
    def _deduplicate_findings(
        self,
        findings: list[ResearchFinding],
    ) -> list[ResearchFinding]:
        """Remove duplicate findings."""
        seen_content = set()
        unique = []
        
        for finding in findings:
            content_key = finding.content[:100].lower()
            if content_key not in seen_content:
                seen_content.add(content_key)
                unique.append(finding)
        
        return unique
    
    def _generate_synthesis(
        self,
        query: str,
        questions: list[ResearchQuestion],
        findings: list[ResearchFinding],
    ) -> str:
        """Generate overall synthesis of research."""
        answered = [q for q in questions if q.answer and q.confidence >= self.config.min_confidence]
        high_confidence = [f for f in findings if f.confidence >= 0.7]
        
        lines = [
            f"Research synthesis for: {query}",
            "",
            f"Analyzed {len(questions)} questions with {len(findings)} findings.",
            f"Successfully answered {len(answered)} questions.",
            f"High-confidence findings: {len(high_confidence)}",
            "",
        ]
        
        if answered:
            lines.append("Key findings:")
            for q in answered[:3]:
                if q.answer:
                    lines.append(f"- {q.category}: {q.answer[:200]}...")
        
        categories = set(f.category for f in findings)
        lines.extend([
            "",
            f"Categories covered: {', '.join(categories)}",
        ])
        
        return "\n".join(lines)
    
    def _generate_title(self, query: str) -> str:
        """Generate a title for the research report."""
        topic = self._extract_topic(query)
        return f"Research Report: {topic.title()}"
    
    def generate_report_markdown(self, report: ResearchReport) -> str:
        """Generate a markdown report.
        
        Args:
            report: Research report to format.
            
        Returns:
            Markdown formatted report.
        """
        lines = [
            f"# {report.title}",
            "",
            f"**Query:** {report.query}",
            f"**Depth:** {report.depth.value}",
            f"**Generated:** {report.generated_at.isoformat()}",
            "",
            "## Executive Summary",
            "",
            report.synthesis,
            "",
            "## Research Questions",
            "",
        ]
        
        for q in report.questions:
            status = "Answered" if q.answer else "Unanswered"
            lines.append(f"### {q.text}")
            lines.append(f"**Category:** {q.category} | **Status:** {status}")
            if q.answer:
                lines.append(f"\n{q.answer}\n")
            lines.append("")
        
        if report.findings:
            lines.extend(["## Findings", ""])
            for f in report.findings[:10]:
                lines.append(f"- **[{f.category}]** (confidence: {f.confidence:.0%})")
                lines.append(f"  {f.content[:200]}...")
                lines.append("")
        
        return "\n".join(lines)
    
    def get_research_history(self) -> list[ResearchReport]:
        """Get history of research reports."""
        return self._research_history.copy()
    
    def clear_history(self) -> None:
        """Clear research history."""
        self._research_history.clear()
