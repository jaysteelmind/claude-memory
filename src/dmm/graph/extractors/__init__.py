"""
DMM Graph Extractors Module.

Provides relationship extraction strategies for building the knowledge graph.
Extractors analyze memories and discover connections based on:
- Tag overlap analysis
- Semantic embedding similarity
- Temporal and versioning patterns
- LLM-assisted deep analysis

All extractors implement a common interface and are coordinated by the
ExtractionOrchestrator for unified relationship discovery.
"""

from dmm.graph.extractors.base import (
    BaseExtractor,
    ExtractionConfig,
    ExtractionResult,
)
from dmm.graph.extractors.tag_extractor import TagExtractor, TagExtractionConfig
from dmm.graph.extractors.semantic_extractor import SemanticExtractor, SemanticExtractionConfig
from dmm.graph.extractors.temporal_extractor import TemporalExtractor, TemporalExtractionConfig
from dmm.graph.extractors.llm_extractor import LLMExtractor, LLMExtractionConfig
from dmm.graph.extractors.orchestrator import ExtractionOrchestrator, OrchestratorConfig

__all__ = [
    # Base
    "BaseExtractor",
    "ExtractionConfig",
    "ExtractionResult",
    # Extractors
    "TagExtractor",
    "TagExtractionConfig",
    "SemanticExtractor",
    "SemanticExtractionConfig",
    "TemporalExtractor",
    "TemporalExtractionConfig",
    "LLMExtractor",
    "LLMExtractionConfig",
    # Orchestrator
    "ExtractionOrchestrator",
    "OrchestratorConfig",
]
