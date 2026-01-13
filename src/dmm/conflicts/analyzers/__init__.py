"""Conflict detection analyzers.

Each analyzer implements a specific detection method:
- TagOverlapAnalyzer: Detects conflicts via shared tags and contradiction patterns
- SemanticClusteringAnalyzer: Detects conflicts via embedding similarity
- SupersessionChainAnalyzer: Detects broken supersession relationships
- RuleExtractionAnalyzer: Uses LLM to extract and compare rules (optional)
"""

from dmm.conflicts.analyzers.tag_overlap import TagOverlapAnalyzer
from dmm.conflicts.analyzers.semantic import SemanticClusteringAnalyzer
from dmm.conflicts.analyzers.supersession import SupersessionChainAnalyzer
from dmm.conflicts.analyzers.rule_extraction import RuleExtractionAnalyzer

__all__ = [
    "TagOverlapAnalyzer",
    "SemanticClusteringAnalyzer",
    "SupersessionChainAnalyzer",
    "RuleExtractionAnalyzer",
]
