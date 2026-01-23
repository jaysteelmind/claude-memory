"""
LLM-assisted relationship extractor.

Uses language model reasoning to discover complex relationships between
memories that simpler heuristics might miss. This extractor is more
expensive (API calls) and should be used selectively for high-priority
memories.

Algorithm Complexity:
- Single extraction: O(c) where c is context size (API call dominated)
- Context selection: O(n * log(k)) using top-k selection
- Response parsing: O(r) where r is response length

Design Considerations:
- Only processes high-priority memories (configurable threshold)
- Uses structured JSON output for reliable parsing
- Includes retry logic with exponential backoff
- Validates extracted relationships against known edge types
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from dmm.graph.edges import (
    Edge,
    RelatesTo,
    Supersedes,
    Contradicts,
    Supports,
    DependsOn,
)
from dmm.graph.extractors.base import (
    BaseExtractor,
    ExtractionMethod,
    ExtractionResult,
    MemoryLike,
)


logger = logging.getLogger(__name__)


EXTRACTION_PROMPT_TEMPLATE = '''You are analyzing memories in a knowledge management system to identify relationships.

Given a TARGET MEMORY and a set of CONTEXT MEMORIES, identify meaningful relationships between the target and context memories.

Relationship Types:
1. SUPPORTS - Target memory provides evidence or reinforcement for a context memory
2. CONTRADICTS - Target memory conflicts with or opposes a context memory
3. DEPENDS_ON - Target memory requires understanding of a context memory as prerequisite
4. SUPERSEDES - Target memory is a newer/updated version replacing a context memory
5. RELATES_TO - Target memory is topically related to a context memory

TARGET MEMORY:
ID: {target_id}
Title: {target_title}
Scope: {target_scope}
Tags: {target_tags}
Content:
{target_content}

CONTEXT MEMORIES:
{context_memories}

Instructions:
1. Analyze the target memory against each context memory
2. Only identify relationships where there is clear evidence
3. Assign confidence scores based on strength of evidence (0.5-1.0)
4. Provide brief reasoning for each relationship
5. Do not force relationships - return empty list if none found

Respond with valid JSON only, no other text:
{{
  "relationships": [
    {{
      "type": "RELATIONSHIP_TYPE",
      "target_id": "context_memory_id",
      "confidence": 0.85,
      "reason": "Brief explanation"
    }}
  ]
}}'''


CONTEXT_MEMORY_TEMPLATE = '''---
ID: {id}
Title: {title}
Scope: {scope}
Tags: {tags}
Content:
{content}
---'''


@dataclass(frozen=True)
class LLMExtractionConfig:
    """
    Configuration for LLM-assisted extraction.
    
    Attributes:
        enabled: Whether LLM extraction is enabled
        min_priority: Minimum memory priority to trigger LLM analysis
        max_context_memories: Maximum context memories to include in prompt
        model: LLM model identifier
        temperature: Sampling temperature for LLM
        max_tokens: Maximum response tokens
        timeout_seconds: API call timeout
        max_retries: Maximum retry attempts on failure
        retry_delay_seconds: Base delay between retries
        min_confidence: Minimum confidence to accept extracted relationship
        api_base_url: Base URL for API (if using HTTP client)
    """
    
    enabled: bool = True
    min_priority: float = 0.7
    max_context_memories: int = 10
    model: str = "claude-sonnet-4-20250514"
    temperature: float = 0.0
    max_tokens: int = 2000
    timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    min_confidence: float = 0.6
    api_base_url: str | None = None


@dataclass
class LLMResponse:
    """
    Parsed response from LLM extraction.
    
    Attributes:
        relationships: List of extracted relationships
        raw_response: Original response text
        parse_success: Whether parsing succeeded
        error: Error message if parsing failed
    """
    
    relationships: list[dict[str, Any]] = field(default_factory=list)
    raw_response: str = ""
    parse_success: bool = True
    error: str | None = None


class LLMExtractor(BaseExtractor):
    """
    Extracts relationships using LLM reasoning.
    
    This extractor is designed for high-priority memories where deep
    semantic analysis is valuable. It constructs a prompt with the
    target memory and selected context memories, then parses the
    LLM response to create edges.
    
    Usage Considerations:
    - API costs: Each extraction makes at least one API call
    - Latency: Significantly slower than heuristic extractors
    - Quality: Can discover nuanced relationships others miss
    - Selectivity: Use min_priority to limit to important memories
    
    The extractor is async-native for efficient API interaction but
    provides sync wrappers for compatibility with the base interface.
    """
    
    VALID_RELATIONSHIP_TYPES = {
        "SUPPORTS", "CONTRADICTS", "DEPENDS_ON", "SUPERSEDES", "RELATES_TO"
    }
    
    def __init__(
        self,
        config: LLMExtractionConfig | None = None,
        llm_client: Any | None = None,
    ) -> None:
        """
        Initialize the LLM extractor.
        
        Args:
            config: Extraction configuration
            llm_client: Optional pre-configured LLM client
        """
        super().__init__()
        self._config = config or LLMExtractionConfig()
        self._llm_client = llm_client
        self._call_count = 0
        self._total_tokens_used = 0
    
    @property
    def config(self) -> LLMExtractionConfig:
        """Return the current configuration."""
        return self._config
    
    def extract(
        self,
        memory: MemoryLike,
        all_memories: list[MemoryLike],
    ) -> ExtractionResult:
        """
        Synchronous extraction wrapper.
        
        Runs the async extraction in an event loop.
        
        Args:
            memory: The memory to analyze
            all_memories: All memories for context
            
        Returns:
            ExtractionResult with discovered edges
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.extract_async(memory, all_memories)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.extract_async(memory, all_memories)
                )
        except RuntimeError:
            return asyncio.run(self.extract_async(memory, all_memories))
    
    async def extract_async(
        self,
        memory: MemoryLike,
        all_memories: list[MemoryLike],
    ) -> ExtractionResult:
        """
        Extract relationships using LLM analysis.
        
        Args:
            memory: The memory to analyze
            all_memories: All memories for context selection
            
        Returns:
            ExtractionResult with discovered edges
        """
        start_time = time.perf_counter()
        
        if not self._config.enabled:
            return self._build_result(
                edges=[],
                source_id=memory.id,
                method=ExtractionMethod.LLM_ANALYSIS,
                duration_ms=(time.perf_counter() - start_time) * 1000,
                metadata={"reason": "llm_extraction_disabled"},
            )
        
        if memory.priority < self._config.min_priority:
            return self._build_result(
                edges=[],
                source_id=memory.id,
                method=ExtractionMethod.LLM_ANALYSIS,
                duration_ms=(time.perf_counter() - start_time) * 1000,
                metadata={
                    "reason": "priority_below_threshold",
                    "memory_priority": memory.priority,
                    "threshold": self._config.min_priority,
                },
            )
        
        context_memories = self._select_context_memories(memory, all_memories)
        
        if not context_memories:
            return self._build_result(
                edges=[],
                source_id=memory.id,
                method=ExtractionMethod.LLM_ANALYSIS,
                duration_ms=(time.perf_counter() - start_time) * 1000,
                metadata={"reason": "no_context_memories_available"},
            )
        
        prompt = self._build_prompt(memory, context_memories)
        
        llm_response = await self._call_llm_with_retry(prompt)
        
        if not llm_response.parse_success:
            logger.warning(
                f"LLM extraction failed for {memory.id}: {llm_response.error}"
            )
            return self._build_result(
                edges=[],
                source_id=memory.id,
                method=ExtractionMethod.LLM_ANALYSIS,
                duration_ms=(time.perf_counter() - start_time) * 1000,
                metadata={
                    "reason": "llm_response_parse_failed",
                    "error": llm_response.error,
                },
            )
        
        context_ids = {m.id for m in context_memories}
        edges = self._create_edges_from_response(
            memory.id, llm_response.relationships, context_ids
        )
        
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        return self._build_result(
            edges=edges,
            source_id=memory.id,
            method=ExtractionMethod.LLM_ANALYSIS,
            duration_ms=duration_ms,
            candidates_considered=len(context_memories),
            edges_filtered=len(llm_response.relationships) - len(edges),
            metadata={
                "context_memory_count": len(context_memories),
                "raw_relationships_found": len(llm_response.relationships),
                "valid_edges_created": len(edges),
                "model": self._config.model,
            },
        )
    
    def _select_context_memories(
        self,
        target: MemoryLike,
        all_memories: list[MemoryLike],
    ) -> list[MemoryLike]:
        """
        Select context memories for the LLM prompt.
        
        Prioritizes memories that are likely to have relationships:
        1. Same or related scope
        2. Shared tags
        3. Higher priority
        
        Args:
            target: The target memory
            all_memories: All available memories
            
        Returns:
            Selected context memories, limited by max_context_memories
        """
        candidates: list[tuple[MemoryLike, float]] = []
        target_tags = set(t.lower() for t in (target.tags or []))
        
        for memory in all_memories:
            if memory.id == target.id:
                continue
            
            if memory.status == "deprecated":
                continue
            
            score = 0.0
            
            if memory.scope == target.scope:
                score += 0.3
            elif self._scopes_related(memory.scope, target.scope):
                score += 0.15
            
            if target_tags:
                memory_tags = set(t.lower() for t in (memory.tags or []))
                if memory_tags:
                    overlap = len(target_tags & memory_tags)
                    tag_score = overlap / max(len(target_tags), len(memory_tags))
                    score += tag_score * 0.4
            
            score += memory.priority * 0.3
            
            candidates.append((memory, score))
        
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        return [m for m, _ in candidates[:self._config.max_context_memories]]
    
    def _scopes_related(self, scope1: str, scope2: str) -> bool:
        """Check if two scopes are related."""
        related = {
            ("baseline", "global"),
            ("global", "project"),
            ("project", "ephemeral"),
            ("agent", "global"),
        }
        pair = tuple(sorted([scope1, scope2]))
        return pair in related
    
    def _build_prompt(
        self,
        target: MemoryLike,
        context_memories: list[MemoryLike],
    ) -> str:
        """
        Build the extraction prompt.
        
        Args:
            target: Target memory
            context_memories: Context memories to include
            
        Returns:
            Formatted prompt string
        """
        context_sections = []
        for memory in context_memories:
            section = CONTEXT_MEMORY_TEMPLATE.format(
                id=memory.id,
                title=memory.title,
                scope=memory.scope,
                tags=", ".join(memory.tags or []),
                content=self._get_content(memory),
            )
            context_sections.append(section)
        
        prompt = EXTRACTION_PROMPT_TEMPLATE.format(
            target_id=target.id,
            target_title=target.title,
            target_scope=target.scope,
            target_tags=", ".join(target.tags or []),
            target_content=self._get_content(target),
            context_memories="\n".join(context_sections),
        )
        
        return prompt
    
    def _get_content(self, memory: MemoryLike) -> str:
        """Get the body content of a memory."""
        content = getattr(memory, "body", None)
        if content:
            return content
        
        content = getattr(memory, "content", None)
        if content:
            return content
        
        return getattr(memory, "title", "")
    
    async def _call_llm_with_retry(self, prompt: str) -> LLMResponse:
        """
        Call the LLM with retry logic.
        
        Args:
            prompt: The prompt to send
            
        Returns:
            Parsed LLM response
        """
        last_error: str | None = None
        
        for attempt in range(self._config.max_retries):
            try:
                response_text = await self._call_llm(prompt)
                self._call_count += 1
                
                return self._parse_response(response_text)
                
            except asyncio.TimeoutError:
                last_error = "Request timed out"
                logger.warning(f"LLM call attempt {attempt + 1} timed out")
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"LLM call attempt {attempt + 1} failed: {e}")
            
            if attempt < self._config.max_retries - 1:
                delay = self._config.retry_delay_seconds * (2 ** attempt)
                await asyncio.sleep(delay)
        
        return LLMResponse(
            parse_success=False,
            error=f"All {self._config.max_retries} attempts failed: {last_error}",
        )
    
    async def _call_llm(self, prompt: str) -> str:
        """
        Make the actual LLM API call.
        
        This method should be overridden or the llm_client should be
        provided for actual API integration.
        
        Args:
            prompt: The prompt to send
            
        Returns:
            Raw response text
        """
        if self._llm_client is not None:
            if hasattr(self._llm_client, "messages"):
                response = await asyncio.wait_for(
                    self._llm_client.messages.create(
                        model=self._config.model,
                        max_tokens=self._config.max_tokens,
                        temperature=self._config.temperature,
                        messages=[{"role": "user", "content": prompt}],
                    ),
                    timeout=self._config.timeout_seconds,
                )
                return response.content[0].text
            
            elif callable(self._llm_client):
                response = await asyncio.wait_for(
                    self._llm_client(prompt),
                    timeout=self._config.timeout_seconds,
                )
                return response
        
        logger.warning("No LLM client configured, returning empty response")
        return '{"relationships": []}'
    
    def _parse_response(self, response_text: str) -> LLMResponse:
        """
        Parse the LLM response JSON.
        
        Args:
            response_text: Raw response text
            
        Returns:
            Parsed LLMResponse
        """
        try:
            cleaned = response_text.strip()
            
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            
            data = json.loads(cleaned)
            
            relationships = data.get("relationships", [])
            
            if not isinstance(relationships, list):
                return LLMResponse(
                    raw_response=response_text,
                    parse_success=False,
                    error="'relationships' is not a list",
                )
            
            return LLMResponse(
                relationships=relationships,
                raw_response=response_text,
                parse_success=True,
            )
            
        except json.JSONDecodeError as e:
            return LLMResponse(
                raw_response=response_text,
                parse_success=False,
                error=f"JSON parse error: {e}",
            )
    
    def _create_edges_from_response(
        self,
        source_id: str,
        relationships: list[dict[str, Any]],
        valid_target_ids: set[str],
    ) -> list[Edge]:
        """
        Create edge objects from parsed relationships.
        
        Args:
            source_id: Source memory ID
            relationships: Parsed relationship dictionaries
            valid_target_ids: Set of valid target memory IDs
            
        Returns:
            List of valid Edge objects
        """
        edges: list[Edge] = []
        
        for rel in relationships:
            rel_type = rel.get("type", "").upper()
            target_id = rel.get("target_id", "")
            confidence = rel.get("confidence", 0.0)
            reason = rel.get("reason", "")
            
            if rel_type not in self.VALID_RELATIONSHIP_TYPES:
                logger.debug(f"Skipping invalid relationship type: {rel_type}")
                continue
            
            if target_id not in valid_target_ids:
                logger.debug(f"Skipping invalid target ID: {target_id}")
                continue
            
            try:
                confidence = float(confidence)
            except (ValueError, TypeError):
                confidence = 0.5
            
            if confidence < self._config.min_confidence:
                logger.debug(
                    f"Skipping low confidence relationship: {confidence}"
                )
                continue
            
            edge = self._create_typed_edge(
                rel_type, source_id, target_id, confidence, reason
            )
            if edge is not None:
                edges.append(edge)
        
        return edges
    
    def _create_typed_edge(
        self,
        rel_type: str,
        from_id: str,
        to_id: str,
        confidence: float,
        reason: str,
    ) -> Edge | None:
        """
        Create a typed edge based on relationship type.
        
        Args:
            rel_type: Relationship type string
            from_id: Source memory ID
            to_id: Target memory ID
            confidence: Confidence score
            reason: Explanation for the relationship
            
        Returns:
            Typed Edge object or None
        """
        if rel_type == "SUPPORTS":
            return Supports(
                from_id=from_id,
                to_id=to_id,
                strength=round(confidence, 4),
            )
        
        elif rel_type == "CONTRADICTS":
            return Contradicts(
                from_id=from_id,
                to_id=to_id,
                description=reason or "LLM-detected contradiction",
            )
        
        elif rel_type == "DEPENDS_ON":
            return DependsOn(
                from_id=from_id,
                to_id=to_id,
            )
        
        elif rel_type == "SUPERSEDES":
            return Supersedes(
                from_id=from_id,
                to_id=to_id,
                reason=reason or "LLM-detected supersession",
            )
        
        elif rel_type == "RELATES_TO":
            return RelatesTo(
                from_id=from_id,
                to_id=to_id,
                weight=round(confidence, 4),
                context=reason or "LLM-detected relationship",
            )
        
        return None
    
    def get_usage_stats(self) -> dict[str, Any]:
        """
        Get LLM usage statistics.
        
        Returns:
            Dictionary with usage statistics
        """
        base_stats = self.get_stats()
        return {
            **base_stats,
            "llm_call_count": self._call_count,
            "total_tokens_used": self._total_tokens_used,
            "model": self._config.model,
        }
