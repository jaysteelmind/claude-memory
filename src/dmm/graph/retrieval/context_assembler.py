"""
Graph-enhanced context assembler.

Formats retrieval results into structured context with relationship
annotations, contradiction warnings, and dependency ordering.

Features:
- Annotates memories with their graph relationships
- Warns about contradictions in result set
- Orders by dependency graph (prerequisites first)
- Includes relationship map for navigation
- Respects token budgets

Output Formats:
- Markdown: Human-readable with sections
- JSON: Machine-parseable structure
- Plain: Minimal formatting for context windows
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from dmm.graph.retrieval.hybrid_retriever import RetrievalResult


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContextAssemblerConfig:
    """
    Configuration for context assembly.
    
    Attributes:
        output_format: Output format (markdown, json, plain)
        include_scores: Include scoring details
        include_relationships: Include relationship annotations
        include_warnings: Include contradiction warnings
        include_relationship_map: Include full relationship map
        include_metadata: Include memory metadata
        max_relationship_context: Max relationships to show per memory
        token_budget: Maximum tokens for output (0 = unlimited)
        tokens_per_char: Approximate tokens per character
        section_separator: Separator between sections
        memory_separator: Separator between memories
    """
    
    output_format: str = "markdown"
    include_scores: bool = True
    include_relationships: bool = True
    include_warnings: bool = True
    include_relationship_map: bool = True
    include_metadata: bool = False
    max_relationship_context: int = 5
    token_budget: int = 0
    tokens_per_char: float = 0.25
    section_separator: str = "\n---\n"
    memory_separator: str = "\n\n"


@dataclass
class AssembledContext:
    """
    Assembled context ready for use.
    
    Attributes:
        content: Formatted content string
        format: Output format used
        memory_count: Number of memories included
        total_tokens: Estimated token count
        warnings: List of warnings (contradictions, etc.)
        truncated: Whether content was truncated
        metadata: Additional assembly metadata
    """
    
    content: str = ""
    format: str = "markdown"
    memory_count: int = 0
    total_tokens: int = 0
    warnings: list[str] = field(default_factory=list)
    truncated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "format": self.format,
            "memory_count": self.memory_count,
            "total_tokens": self.total_tokens,
            "warnings": self.warnings,
            "truncated": self.truncated,
            "metadata": self.metadata,
        }


class GraphContextAssembler:
    """
    Assembles retrieval results into formatted context.
    
    The assembler takes hybrid retrieval results and produces
    structured output suitable for AI context windows. It:
    
    1. Detects contradictions between retrieved memories
    2. Orders memories by dependency relationships
    3. Annotates each memory with its connections
    4. Formats output in the requested format
    5. Respects token budgets with intelligent truncation
    
    Contradiction Detection:
    - Checks for CONTRADICTS edges between results
    - Warns about memories with opposing information
    - Does not remove contradictions (let the consumer decide)
    
    Dependency Ordering:
    - Memories that others DEPEND_ON come first
    - Uses topological sort where possible
    - Falls back to score-based ordering
    
    Example:
        assembler = GraphContextAssembler(config)
        context = assembler.assemble(retrieval_results, query="auth")
        print(context.content)
    """
    
    def __init__(
        self,
        config: ContextAssemblerConfig | None = None,
        graph_store: Any | None = None,
    ) -> None:
        """
        Initialize the context assembler.
        
        Args:
            config: Assembly configuration
            graph_store: Optional graph store for relationship lookup
        """
        self._config = config or ContextAssemblerConfig()
        self._graph_store = graph_store
    
    @property
    def config(self) -> ContextAssemblerConfig:
        """Return the current configuration."""
        return self._config
    
    def set_graph_store(self, graph_store: Any) -> None:
        """Set the graph store for relationship lookup."""
        self._graph_store = graph_store
    
    def assemble(
        self,
        results: list[RetrievalResult],
        query: str = "",
        baseline_content: str = "",
    ) -> AssembledContext:
        """
        Assemble retrieval results into formatted context.
        
        Args:
            results: List of retrieval results
            query: Original query string
            baseline_content: Pre-assembled baseline content
            
        Returns:
            AssembledContext with formatted output
        """
        if not results:
            return AssembledContext(
                content=baseline_content or "No memories retrieved.",
                format=self._config.output_format,
                memory_count=0,
            )
        
        warnings = self._detect_contradictions(results)
        
        ordered_results = self._order_by_dependencies(results)
        
        if self._config.output_format == "json":
            content = self._format_json(ordered_results, query, warnings, baseline_content)
        elif self._config.output_format == "plain":
            content = self._format_plain(ordered_results, query, warnings, baseline_content)
        else:
            content = self._format_markdown(ordered_results, query, warnings, baseline_content)
        
        truncated = False
        if self._config.token_budget > 0:
            estimated_tokens = int(len(content) * self._config.tokens_per_char)
            if estimated_tokens > self._config.token_budget:
                content, truncated = self._truncate_to_budget(
                    content, self._config.token_budget
                )
        
        total_tokens = int(len(content) * self._config.tokens_per_char)
        
        return AssembledContext(
            content=content,
            format=self._config.output_format,
            memory_count=len(results),
            total_tokens=total_tokens,
            warnings=warnings,
            truncated=truncated,
            metadata={
                "query": query,
                "has_baseline": bool(baseline_content),
                "avg_combined_score": sum(r.combined_score for r in results) / len(results),
            },
        )
    
    def _detect_contradictions(
        self,
        results: list[RetrievalResult],
    ) -> list[str]:
        """
        Detect contradictions between retrieved memories.
        
        Args:
            results: Retrieval results to check
            
        Returns:
            List of warning strings
        """
        warnings: list[str] = []
        result_ids = {r.memory_id for r in results}
        
        if self._graph_store is None:
            return warnings
        
        for result in results:
            try:
                edges = self._graph_store.get_edges_from(
                    result.memory_id, "CONTRADICTS"
                )
                for edge in edges:
                    target_id = edge.get("to_id", "")
                    if target_id in result_ids:
                        description = edge.get("description", "conflicting information")
                        warnings.append(
                            f"Potential contradiction: {result.memory_id} <-> {target_id}: {description}"
                        )
            except Exception as e:
                logger.debug(f"Failed to check contradictions for {result.memory_id}: {e}")
        
        seen = set()
        unique_warnings = []
        for w in warnings:
            key = tuple(sorted(w.split("<->")[0:2])) if "<->" in w else w
            if key not in seen:
                seen.add(key)
                unique_warnings.append(w)
        
        return unique_warnings
    
    def _order_by_dependencies(
        self,
        results: list[RetrievalResult],
    ) -> list[RetrievalResult]:
        """
        Order results so dependencies come first.
        
        Uses topological sort on DEPENDS_ON relationships.
        Falls back to score-based ordering if no dependencies.
        
        Args:
            results: Results to order
            
        Returns:
            Ordered results list
        """
        if self._graph_store is None or len(results) <= 1:
            return sorted(results, key=lambda r: r.combined_score, reverse=True)
        
        result_ids = {r.memory_id for r in results}
        result_map = {r.memory_id: r for r in results}
        
        dependencies: dict[str, set[str]] = {mid: set() for mid in result_ids}
        
        for result in results:
            try:
                edges = self._graph_store.get_edges_from(
                    result.memory_id, "DEPENDS_ON"
                )
                for edge in edges:
                    target_id = edge.get("to_id", "")
                    if target_id in result_ids:
                        dependencies[result.memory_id].add(target_id)
            except Exception:
                pass
        
        ordered: list[str] = []
        remaining = set(result_ids)
        
        while remaining:
            ready = [
                mid for mid in remaining
                if not (dependencies[mid] - set(ordered))
            ]
            
            if not ready:
                ready = sorted(
                    remaining,
                    key=lambda m: result_map[m].combined_score,
                    reverse=True
                )
            else:
                ready = sorted(
                    ready,
                    key=lambda m: result_map[m].combined_score,
                    reverse=True
                )
            
            for mid in ready:
                ordered.append(mid)
                remaining.discard(mid)
                if len(ordered) + len(remaining) == len(result_ids):
                    break
        
        return [result_map[mid] for mid in ordered]
    
    def _format_markdown(
        self,
        results: list[RetrievalResult],
        query: str,
        warnings: list[str],
        baseline_content: str,
    ) -> str:
        """Format results as markdown."""
        sections: list[str] = []
        
        header = "# DMM Memory Pack (Graph-Enhanced)\n"
        header += f"Generated: {datetime.now(timezone.utc).isoformat()}Z\n"
        if query:
            header += f'Query: "{query}"\n'
        header += f"Retrieved: {len(results)} memories\n"
        
        if self._config.include_scores:
            avg_vector = sum(r.vector_score for r in results) / len(results) if results else 0
            avg_graph = sum(r.graph_score for r in results) / len(results) if results else 0
            header += f"Avg Vector Score: {avg_vector:.2f} | Avg Graph Score: {avg_graph:.2f}\n"
            header += "Retrieval Mode: Hybrid (Vector + Graph)\n"
        
        sections.append(header)
        
        if self._config.include_warnings and warnings:
            warning_section = "## Warnings\n\n"
            warning_section += "**The following memories may contain conflicting information:**\n"
            for w in warnings:
                warning_section += f"- {w}\n"
            sections.append(warning_section)
        
        if baseline_content:
            sections.append("## Baseline Context\n\n" + baseline_content)
        
        memory_section = "## Retrieved Context\n"
        
        for result in results:
            memory_section += self._format_memory_markdown(result)
        
        sections.append(memory_section)
        
        if self._config.include_relationship_map:
            rel_map = self._build_relationship_map(results)
            if rel_map:
                map_section = "## Relationship Map\n\n"
                map_section += rel_map
                sections.append(map_section)
        
        return self._config.section_separator.join(sections)
    
    def _format_memory_markdown(self, result: RetrievalResult) -> str:
        """Format a single memory as markdown."""
        output = f"\n### {self._get_memory_title(result.memory)}\n"
        
        if self._config.include_scores:
            output += f"*ID: {result.memory_id} | "
            output += f"Vector: {result.vector_score:.2f} | "
            output += f"Graph: {result.graph_score:.2f} | "
            output += f"Combined: {result.combined_score:.2f}*\n"
        
        if self._config.include_relationships and result.relationship_context:
            output += "\n**Connections:**\n"
            for ctx in result.relationship_context[:self._config.max_relationship_context]:
                output += f"  - {ctx}\n"
        
        output += f"\n{self._get_memory_content(result.memory)}\n"
        
        return output
    
    def _format_json(
        self,
        results: list[RetrievalResult],
        query: str,
        warnings: list[str],
        baseline_content: str,
    ) -> str:
        """Format results as JSON."""
        data = {
            "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
            "query": query,
            "memory_count": len(results),
            "retrieval_mode": "hybrid",
            "warnings": warnings if self._config.include_warnings else [],
            "baseline": baseline_content if baseline_content else None,
            "memories": [],
        }
        
        if self._config.include_scores:
            data["avg_vector_score"] = sum(r.vector_score for r in results) / len(results) if results else 0
            data["avg_graph_score"] = sum(r.graph_score for r in results) / len(results) if results else 0
        
        for result in results:
            memory_data = {
                "id": result.memory_id,
                "title": self._get_memory_title(result.memory),
                "content": self._get_memory_content(result.memory),
            }
            
            if self._config.include_scores:
                memory_data["scores"] = {
                    "vector": round(result.vector_score, 4),
                    "graph": round(result.graph_score, 4),
                    "combined": round(result.combined_score, 4),
                }
            
            if self._config.include_relationships:
                memory_data["relationships"] = result.relationship_context
            
            if self._config.include_metadata:
                memory_data["metadata"] = self._get_memory_metadata(result.memory)
            
            data["memories"].append(memory_data)
        
        return json.dumps(data, indent=2)
    
    def _format_plain(
        self,
        results: list[RetrievalResult],
        query: str,
        warnings: list[str],
        baseline_content: str,
    ) -> str:
        """Format results as plain text."""
        sections: list[str] = []
        
        if warnings and self._config.include_warnings:
            sections.append("WARNINGS: " + "; ".join(warnings))
        
        if baseline_content:
            sections.append("BASELINE:\n" + baseline_content)
        
        sections.append("RETRIEVED MEMORIES:")
        
        for result in results:
            memory_text = f"\n[{result.memory_id}] {self._get_memory_title(result.memory)}"
            if self._config.include_scores:
                memory_text += f" (score: {result.combined_score:.2f})"
            memory_text += f"\n{self._get_memory_content(result.memory)}"
            sections.append(memory_text)
        
        return "\n\n".join(sections)
    
    def _build_relationship_map(self, results: list[RetrievalResult]) -> str:
        """Build a text representation of relationships."""
        lines: list[str] = []
        
        for result in results:
            if result.relationship_context:
                lines.append(f"**{result.memory_id}**:")
                for ctx in result.relationship_context[:self._config.max_relationship_context]:
                    lines.append(f"  {ctx}")
        
        return "\n".join(lines)
    
    def _truncate_to_budget(
        self,
        content: str,
        budget: int,
    ) -> tuple[str, bool]:
        """
        Truncate content to fit token budget.
        
        Args:
            content: Content to truncate
            budget: Token budget
            
        Returns:
            Tuple of (truncated content, was_truncated)
        """
        estimated_tokens = int(len(content) * self._config.tokens_per_char)
        
        if estimated_tokens <= budget:
            return content, False
        
        target_chars = int(budget / self._config.tokens_per_char)
        
        truncated = content[:target_chars]
        
        last_separator = truncated.rfind(self._config.section_separator)
        if last_separator > target_chars * 0.5:
            truncated = truncated[:last_separator]
        
        truncated += "\n\n[Content truncated to fit token budget]"
        
        return truncated, True
    
    def _get_memory_title(self, memory: Any) -> str:
        """Extract title from memory object."""
        if hasattr(memory, "title"):
            return memory.title
        if isinstance(memory, dict):
            return memory.get("title", "Untitled")
        return "Untitled"
    
    def _get_memory_content(self, memory: Any) -> str:
        """Extract content from memory object."""
        if hasattr(memory, "body"):
            return memory.body
        if hasattr(memory, "content"):
            return memory.content
        if isinstance(memory, dict):
            return memory.get("body", memory.get("content", ""))
        return str(memory)
    
    def _get_memory_metadata(self, memory: Any) -> dict[str, Any]:
        """Extract metadata from memory object."""
        metadata = {}
        
        for attr in ["scope", "priority", "confidence", "status", "tags", "created"]:
            if hasattr(memory, attr):
                value = getattr(memory, attr)
                if value is not None:
                    metadata[attr] = value
            elif isinstance(memory, dict) and attr in memory:
                metadata[attr] = memory[attr]
        
        return metadata
