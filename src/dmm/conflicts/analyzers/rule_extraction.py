"""Rule extraction conflict detection analyzer (LLM-based).

This analyzer uses LLM to extract explicit rules from memory content
and compare them for logical contradictions. This is an optional,
more expensive analysis method that provides high-confidence results.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from dmm.core.constants import (
    RULE_EXTRACTION_ENABLED,
    RULE_EXTRACTION_TIMEOUT_SECONDS,
)
from dmm.models.conflict import ConflictCandidate, DetectionMethod

if TYPE_CHECKING:
    from dmm.models.memory import IndexedMemory


logger = logging.getLogger(__name__)


RULE_EXTRACTION_PROMPT = """Analyze these two memory entries and determine if they conflict.

## Memory 1
Path: {path1}
Title: {title1}
Content:
{content1}

## Memory 2
Path: {path2}
Title: {title2}
Content:
{content2}

## Analysis Tasks

1. Extract the key rules or claims from each memory
2. Compare the rules for logical contradiction
3. Determine if they conflict

## Response Format

Respond with a JSON object only, no other text:
{{
  "memory1_rules": ["rule1", "rule2"],
  "memory2_rules": ["rule1", "rule2"],
  "conflicts": [
    {{
      "rule1": "rule from memory 1",
      "rule2": "rule from memory 2",
      "contradiction": "description of how they contradict",
      "severity": "high|medium|low"
    }}
  ],
  "overall_conflict": true|false,
  "confidence": 0.0-1.0,
  "explanation": "brief explanation"
}}

Be conservative: only report conflicts if the rules genuinely contradict.
Different recommendations for different contexts are not conflicts.
"""


@dataclass
class LLMConfig:
    """Configuration for LLM-based rule extraction."""
    
    enabled: bool = RULE_EXTRACTION_ENABLED
    timeout_seconds: int = RULE_EXTRACTION_TIMEOUT_SECONDS
    model: str = "claude-3-haiku-20240307"
    max_tokens: int = 1024
    temperature: float = 0.0


@dataclass
class RuleExtractionConfig:
    """Configuration for rule extraction analysis."""
    
    llm_config: LLMConfig = field(default_factory=LLMConfig)
    max_candidates: int = 50
    min_confidence: float = 0.6
    max_content_length: int = 2000


@dataclass
class RuleExtractionResult:
    """Result from LLM rule extraction."""
    
    memory1_rules: list[str]
    memory2_rules: list[str]
    conflicts: list[dict[str, Any]]
    overall_conflict: bool
    confidence: float
    explanation: str
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuleExtractionResult":
        """Create from dictionary."""
        return cls(
            memory1_rules=data.get("memory1_rules", []),
            memory2_rules=data.get("memory2_rules", []),
            conflicts=data.get("conflicts", []),
            overall_conflict=data.get("overall_conflict", False),
            confidence=data.get("confidence", 0.0),
            explanation=data.get("explanation", ""),
        )


class RuleExtractionAnalyzer:
    """Detects conflicts via LLM-based rule extraction.
    
    This analyzer:
    1. Takes candidate pairs from other analyzers
    2. Uses LLM to extract explicit rules from each memory
    3. Compares rules for logical contradiction
    4. Returns high-confidence conflict assessments
    
    This is an optional, more expensive analysis method.
    It should be used as a second pass on candidates from
    heuristic-based analyzers.
    """

    def __init__(
        self,
        config: RuleExtractionConfig | None = None,
        llm_client: Any | None = None,
    ) -> None:
        """Initialize the analyzer.
        
        Args:
            config: Optional configuration.
            llm_client: Optional LLM client. If None, LLM calls are disabled.
        """
        self._config = config or RuleExtractionConfig()
        self._llm_client = llm_client
        self._enabled = self._config.llm_config.enabled and llm_client is not None

    @property
    def is_enabled(self) -> bool:
        """Check if LLM analysis is enabled."""
        return self._enabled

    def analyze_pair(
        self,
        m1: "IndexedMemory",
        m2: "IndexedMemory",
    ) -> ConflictCandidate | None:
        """Analyze a pair of memories for conflicts using LLM.
        
        Args:
            m1: First memory.
            m2: Second memory.
            
        Returns:
            Conflict candidate if conflict found, None otherwise.
        """
        if not self._enabled:
            logger.debug("LLM rule extraction is disabled")
            return None
        
        try:
            result = self._extract_and_compare(m1, m2)
            
            if result.overall_conflict and result.confidence >= self._config.min_confidence:
                return ConflictCandidate(
                    memory_ids=(m1.id, m2.id),
                    detection_method=DetectionMethod.RULE_EXTRACTION,
                    raw_score=result.confidence,
                    evidence={
                        "memory1_rules": result.memory1_rules,
                        "memory2_rules": result.memory2_rules,
                        "conflicts": result.conflicts,
                        "explanation": result.explanation,
                        "llm_confidence": result.confidence,
                    },
                )
            
            return None
            
        except Exception as e:
            logger.warning(f"LLM rule extraction failed for {m1.id} vs {m2.id}: {e}")
            return None

    def analyze_candidates(
        self,
        candidates: list[ConflictCandidate],
        memory_map: dict[str, "IndexedMemory"],
    ) -> list[ConflictCandidate]:
        """Refine candidates using LLM analysis.
        
        This method takes candidates from other analyzers and uses
        LLM to provide more confident assessments.
        
        Args:
            candidates: Candidates from heuristic analyzers.
            memory_map: Map of memory ID to memory object.
            
        Returns:
            Refined list of conflict candidates.
        """
        if not self._enabled:
            logger.debug("LLM rule extraction is disabled, returning original candidates")
            return candidates
        
        refined = []
        
        for candidate in candidates[:self._config.max_candidates]:
            m1_id, m2_id = candidate.memory_ids
            m1 = memory_map.get(m1_id)
            m2 = memory_map.get(m2_id)
            
            if m1 is None or m2 is None:
                continue
            
            try:
                result = self._extract_and_compare(m1, m2)
                
                if result.overall_conflict:
                    new_score = (candidate.raw_score + result.confidence) / 2
                    
                    enhanced_evidence = dict(candidate.evidence)
                    enhanced_evidence["llm_analysis"] = {
                        "memory1_rules": result.memory1_rules,
                        "memory2_rules": result.memory2_rules,
                        "conflicts": result.conflicts,
                        "explanation": result.explanation,
                        "llm_confidence": result.confidence,
                    }
                    
                    refined.append(ConflictCandidate(
                        memory_ids=candidate.memory_ids,
                        detection_method=candidate.detection_method,
                        raw_score=new_score,
                        evidence=enhanced_evidence,
                    ))
                    
            except Exception as e:
                logger.warning(f"LLM analysis failed for candidate {m1_id} vs {m2_id}: {e}")
                refined.append(candidate)
        
        return refined

    def _extract_and_compare(
        self,
        m1: "IndexedMemory",
        m2: "IndexedMemory",
    ) -> RuleExtractionResult:
        """Extract rules from both memories and compare.
        
        Args:
            m1: First memory.
            m2: Second memory.
            
        Returns:
            Rule extraction result.
        """
        content1 = self._truncate_content(m1.body)
        content2 = self._truncate_content(m2.body)
        
        prompt = RULE_EXTRACTION_PROMPT.format(
            path1=m1.path,
            title1=m1.title,
            content1=content1,
            path2=m2.path,
            title2=m2.title,
            content2=content2,
        )
        
        response = self._call_llm(prompt)
        
        return self._parse_response(response)

    def _truncate_content(self, content: str) -> str:
        """Truncate content to maximum length."""
        if len(content) <= self._config.max_content_length:
            return content
        return content[:self._config.max_content_length] + "..."

    def _call_llm(self, prompt: str) -> str:
        """Call the LLM with the given prompt.
        
        Args:
            prompt: The prompt to send.
            
        Returns:
            The LLM response text.
            
        Raises:
            RuntimeError: If LLM call fails.
        """
        if self._llm_client is None:
            raise RuntimeError("LLM client not configured")
        
        try:
            response = self._llm_client.messages.create(
                model=self._config.llm_config.model,
                max_tokens=self._config.llm_config.max_tokens,
                temperature=self._config.llm_config.temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ],
            )
            
            if response.content and len(response.content) > 0:
                return response.content[0].text
            
            raise RuntimeError("Empty response from LLM")
            
        except Exception as e:
            raise RuntimeError(f"LLM call failed: {e}")

    def _parse_response(self, response: str) -> RuleExtractionResult:
        """Parse LLM response into structured result.
        
        Args:
            response: Raw LLM response text.
            
        Returns:
            Parsed rule extraction result.
        """
        try:
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()
            
            data = json.loads(response)
            return RuleExtractionResult.from_dict(data)
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            return RuleExtractionResult(
                memory1_rules=[],
                memory2_rules=[],
                conflicts=[],
                overall_conflict=False,
                confidence=0.0,
                explanation=f"Failed to parse response: {e}",
            )

    def analyze_without_llm(
        self,
        m1: "IndexedMemory",
        m2: "IndexedMemory",
    ) -> ConflictCandidate | None:
        """Perform heuristic rule extraction without LLM.
        
        This is a fallback method when LLM is not available.
        It uses simple heuristics to detect rule-like statements.
        
        Args:
            m1: First memory.
            m2: Second memory.
            
        Returns:
            Conflict candidate if conflict found, None otherwise.
        """
        rules1 = self._extract_rules_heuristic(m1.body)
        rules2 = self._extract_rules_heuristic(m2.body)
        
        if not rules1 or not rules2:
            return None
        
        conflicts = self._compare_rules_heuristic(rules1, rules2)
        
        if conflicts:
            confidence = min(0.6, len(conflicts) * 0.2)
            return ConflictCandidate(
                memory_ids=(m1.id, m2.id),
                detection_method=DetectionMethod.RULE_EXTRACTION,
                raw_score=confidence,
                evidence={
                    "memory1_rules": rules1,
                    "memory2_rules": rules2,
                    "conflicts": conflicts,
                    "explanation": "Heuristic rule extraction (no LLM)",
                    "heuristic": True,
                },
            )
        
        return None

    def _extract_rules_heuristic(self, content: str) -> list[str]:
        """Extract rule-like statements using heuristics.
        
        Args:
            content: Memory content.
            
        Returns:
            List of extracted rules.
        """
        rules = []
        
        rule_indicators = [
            "must", "should", "always", "never", "required",
            "forbidden", "mandatory", "use", "avoid", "prefer",
        ]
        
        sentences = content.replace("\n", " ").split(".")
        
        for sentence in sentences:
            sentence = sentence.strip().lower()
            if any(indicator in sentence for indicator in rule_indicators):
                if len(sentence) > 10 and len(sentence) < 200:
                    rules.append(sentence)
        
        return rules[:10]

    def _compare_rules_heuristic(
        self,
        rules1: list[str],
        rules2: list[str],
    ) -> list[dict[str, str]]:
        """Compare rules using simple heuristics.
        
        Args:
            rules1: Rules from first memory.
            rules2: Rules from second memory.
            
        Returns:
            List of detected conflicts.
        """
        conflicts = []
        
        opposites = [
            ("always", "never"),
            ("must", "must not"),
            ("use", "avoid"),
            ("enable", "disable"),
            ("allow", "prohibit"),
            ("required", "forbidden"),
        ]
        
        for r1 in rules1:
            for r2 in rules2:
                for pos, neg in opposites:
                    if (pos in r1 and neg in r2) or (neg in r1 and pos in r2):
                        conflicts.append({
                            "rule1": r1,
                            "rule2": r2,
                            "contradiction": f"Opposite indicators: {pos}/{neg}",
                            "severity": "medium",
                        })
                        break
        
        return conflicts

    def get_stats(self) -> dict:
        """Get analyzer statistics."""
        return {
            "enabled": self._enabled,
            "llm_model": self._config.llm_config.model if self._enabled else None,
            "min_confidence": self._config.min_confidence,
            "max_candidates": self._config.max_candidates,
            "max_content_length": self._config.max_content_length,
        }
