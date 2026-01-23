"""
Temporal relationship extractor.

Discovers relationships between memories based on temporal patterns
and version detection. Identifies supersession chains and temporal
proximity relationships.

Algorithm Complexity:
- Single extraction: O(n) where n is number of memories
- Version parsing: O(len(title)) per memory
- Title similarity: O(min(len(t1), len(t2))) per pair

Mathematical Foundation:
- Temporal proximity weight: w = 1 - (days_apart / max_days) * decay_factor
- Version comparison: Semantic versioning (major.minor.patch)
- Title similarity: Normalized Levenshtein distance or token overlap
"""

import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterator

from dmm.graph.edges import RelatesTo, Supersedes
from dmm.graph.extractors.base import (
    BaseExtractor,
    ExtractionMethod,
    ExtractionResult,
    MemoryLike,
    Edge,
)


@dataclass(frozen=True)
class TemporalExtractionConfig:
    """
    Configuration for temporal extraction.
    
    Attributes:
        proximity_days: Maximum days apart to consider temporally related
        detect_versions: Enable version pattern detection in titles
        version_patterns: Regex patterns for detecting versions
        title_similarity_threshold: Minimum title similarity for version matching
        max_edges_per_memory: Maximum edges to create per source memory
        proximity_weight_decay: Decay factor for proximity weight calculation
        require_same_scope_for_supersession: Only detect supersession within same scope
    """
    
    proximity_days: int = 7
    detect_versions: bool = True
    version_patterns: tuple[str, ...] = (
        r"(?:v|version|ver|rev)[\s._-]?(\d+(?:\.\d+)*)",
        r"\bv(\d+(?:\.\d+)*)\b",
        r"(\d+\.\d+(?:\.\d+)?)\s*$",
    )
    title_similarity_threshold: float = 0.6
    max_edges_per_memory: int = 10
    proximity_weight_decay: float = 0.5
    require_same_scope_for_supersession: bool = True


class TemporalExtractor(BaseExtractor):
    """
    Extracts relationships based on temporal patterns.
    
    This extractor analyzes creation dates and title patterns to discover:
    
    - SUPERSEDES: When one memory appears to be a newer version of another,
      detected through version numbers in titles (e.g., "API Design v2"
      supersedes "API Design v1")
    - RELATES_TO: When memories were created within a temporal window,
      suggesting they may be part of the same work effort
    
    Version Detection Algorithm:
    1. Extract version numbers from titles using regex patterns
    2. Remove version from title to get "base title"
    3. Compare base titles for similarity
    4. If similar and versions differ, newer supersedes older
    
    Temporal Proximity Algorithm:
    1. Calculate days between creation dates
    2. If within proximity_days window, create RELATES_TO edge
    3. Weight decreases with temporal distance
    """
    
    def __init__(self, config: TemporalExtractionConfig | None = None) -> None:
        """
        Initialize the temporal extractor.
        
        Args:
            config: Extraction configuration, uses defaults if None
        """
        super().__init__()
        self._config = config or TemporalExtractionConfig()
        self._version_patterns = [
            re.compile(p, re.IGNORECASE) for p in self._config.version_patterns
        ]
    
    @property
    def config(self) -> TemporalExtractionConfig:
        """Return the current configuration."""
        return self._config
    
    def extract(
        self,
        memory: MemoryLike,
        all_memories: list[MemoryLike],
    ) -> ExtractionResult:
        """
        Extract temporal relationships for a memory.
        
        Args:
            memory: The memory to analyze
            all_memories: All memories for comparison
            
        Returns:
            ExtractionResult with SUPERSEDES and RELATES_TO edges
        """
        start_time = time.perf_counter()
        
        edges: list[Edge] = []
        candidates_considered = 0
        
        mem_created = self._get_created_date(memory)
        mem_version = self._extract_version(memory.title) if self._config.detect_versions else None
        mem_base_title = self._get_base_title(memory.title) if self._config.detect_versions else ""
        
        supersession_edges: list[Edge] = []
        proximity_edges: list[tuple[Edge, float]] = []
        
        for other in all_memories:
            if other.id == memory.id:
                continue
            
            if other.status == "deprecated":
                continue
            
            candidates_considered += 1
            
            if self._config.detect_versions and mem_version is not None:
                if self._config.require_same_scope_for_supersession:
                    if memory.scope != other.scope:
                        continue
                
                other_version = self._extract_version(other.title)
                
                if other_version is not None:
                    other_base_title = self._get_base_title(other.title)
                    
                    title_similarity = self._title_similarity(mem_base_title, other_base_title)
                    
                    if title_similarity >= self._config.title_similarity_threshold:
                        version_cmp = self._compare_versions(mem_version, other_version)
                        
                        if version_cmp > 0:
                            edge = Supersedes(
                                from_id=memory.id,
                                to_id=other.id,
                                reason=f"Version {self._format_version(mem_version)} supersedes {self._format_version(other_version)}",
                            )
                            supersession_edges.append(edge)
            
            if mem_created is not None:
                other_created = self._get_created_date(other)
                
                if other_created is not None:
                    days_apart = abs((mem_created - other_created).days)
                    
                    if days_apart <= self._config.proximity_days and days_apart > 0:
                        weight = self._calculate_proximity_weight(days_apart)
                        
                        if weight >= 0.3:
                            edge = RelatesTo(
                                from_id=memory.id,
                                to_id=other.id,
                                weight=round(weight, 4),
                                context=f"Created within {days_apart} days",
                            )
                            proximity_edges.append((edge, weight))
        
        edges.extend(supersession_edges)
        
        proximity_edges.sort(key=lambda x: x[1], reverse=True)
        remaining_slots = self._config.max_edges_per_memory - len(supersession_edges)
        
        if remaining_slots > 0:
            for edge, _ in proximity_edges[:remaining_slots]:
                edges.append(edge)
        
        edges_filtered = max(0, len(proximity_edges) - remaining_slots) if remaining_slots > 0 else len(proximity_edges)
        
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        return self._build_result(
            edges=edges,
            source_id=memory.id,
            method=ExtractionMethod.TEMPORAL_PATTERN,
            duration_ms=duration_ms,
            candidates_considered=candidates_considered,
            edges_filtered=edges_filtered,
            metadata={
                "supersession_count": len(supersession_edges),
                "proximity_count": len(edges) - len(supersession_edges),
                "source_version": self._format_version(mem_version) if mem_version else None,
                "source_created": mem_created.isoformat() if mem_created else None,
            },
        )
    
    def _extract_version(self, title: str) -> tuple[int, ...] | None:
        """
        Extract version number from a title.
        
        Args:
            title: Memory title
            
        Returns:
            Version as tuple of integers, or None if not found
        """
        if not title:
            return None
        
        for pattern in self._version_patterns:
            match = pattern.search(title)
            if match:
                version_str = match.group(1)
                try:
                    parts = tuple(int(p) for p in version_str.split("."))
                    return parts
                except ValueError:
                    continue
        
        return None
    
    def _get_base_title(self, title: str) -> str:
        """
        Remove version information from title.
        
        Args:
            title: Memory title
            
        Returns:
            Title without version suffix
        """
        if not title:
            return ""
        
        result = title
        for pattern in self._version_patterns:
            result = pattern.sub("", result)
        
        result = re.sub(r"[\s._-]+$", "", result)
        result = result.strip()
        
        return result.lower()
    
    def _title_similarity(self, title1: str, title2: str) -> float:
        """
        Calculate similarity between two base titles.
        
        Uses token overlap for efficiency. For more sophisticated
        matching, consider Levenshtein distance.
        
        Args:
            title1: First title (normalized)
            title2: Second title (normalized)
            
        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not title1 or not title2:
            return 0.0
        
        if title1 == title2:
            return 1.0
        
        tokens1 = set(re.findall(r"\w+", title1))
        tokens2 = set(re.findall(r"\w+", title2))
        
        if not tokens1 or not tokens2:
            return 0.0
        
        intersection = tokens1 & tokens2
        union = tokens1 | tokens2
        
        return len(intersection) / len(union)
    
    def _compare_versions(self, v1: tuple[int, ...], v2: tuple[int, ...]) -> int:
        """
        Compare two version tuples.
        
        Args:
            v1: First version
            v2: Second version
            
        Returns:
            1 if v1 > v2, -1 if v1 < v2, 0 if equal
        """
        len1, len2 = len(v1), len(v2)
        max_len = max(len1, len2)
        
        v1_padded = v1 + (0,) * (max_len - len1)
        v2_padded = v2 + (0,) * (max_len - len2)
        
        for a, b in zip(v1_padded, v2_padded):
            if a > b:
                return 1
            if a < b:
                return -1
        
        return 0
    
    def _format_version(self, version: tuple[int, ...] | None) -> str | None:
        """Format version tuple as string."""
        if version is None:
            return None
        return ".".join(str(p) for p in version)
    
    def _get_created_date(self, memory: MemoryLike) -> datetime | None:
        """
        Get the creation date of a memory.
        
        Args:
            memory: Memory object
            
        Returns:
            Creation datetime or None
        """
        created = getattr(memory, "created", None)
        
        if created is None:
            created = getattr(memory, "created_at", None)
        
        if isinstance(created, datetime):
            return created
        
        if isinstance(created, str):
            try:
                return datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                pass
            
            try:
                return datetime.strptime(created, "%Y-%m-%d")
            except ValueError:
                pass
        
        return None
    
    def _calculate_proximity_weight(self, days_apart: int) -> float:
        """
        Calculate edge weight based on temporal proximity.
        
        Weight decreases as days apart increases:
        w = (1 - days/max_days) * decay_factor + base
        
        Args:
            days_apart: Number of days between creation dates
            
        Returns:
            Weight between 0.0 and 1.0
        """
        if days_apart <= 0:
            return 0.0
        
        if days_apart > self._config.proximity_days:
            return 0.0
        
        normalized = 1.0 - (days_apart / self._config.proximity_days)
        
        weight = normalized * self._config.proximity_weight_decay
        
        base_weight = 0.3
        weight = base_weight + (weight * (1.0 - base_weight))
        
        return min(1.0, max(0.0, weight))
    
    def find_version_chains(
        self,
        memories: list[MemoryLike],
    ) -> list[list[str]]:
        """
        Find chains of memory versions.
        
        Groups memories by base title and orders by version.
        
        Args:
            memories: All memories to analyze
            
        Returns:
            List of version chains, each chain is ordered by version
        """
        title_groups: dict[str, list[tuple[MemoryLike, tuple[int, ...]]]] = {}
        
        for memory in memories:
            if memory.status == "deprecated":
                continue
            
            version = self._extract_version(memory.title)
            if version is None:
                continue
            
            base_title = self._get_base_title(memory.title)
            if not base_title:
                continue
            
            if base_title not in title_groups:
                title_groups[base_title] = []
            title_groups[base_title].append((memory, version))
        
        chains: list[list[str]] = []
        
        for base_title, versions in title_groups.items():
            if len(versions) < 2:
                continue
            
            versions.sort(key=lambda x: x[1])
            chain = [memory.id for memory, _ in versions]
            chains.append(chain)
        
        chains.sort(key=len, reverse=True)
        return chains
    
    def find_temporal_clusters(
        self,
        memories: list[MemoryLike],
        window_days: int | None = None,
    ) -> list[list[str]]:
        """
        Find clusters of memories created around the same time.
        
        Args:
            memories: All memories to analyze
            window_days: Clustering window (defaults to proximity_days)
            
        Returns:
            List of temporal clusters, each is a list of memory IDs
        """
        if window_days is None:
            window_days = self._config.proximity_days
        
        dated_memories: list[tuple[MemoryLike, datetime]] = []
        
        for memory in memories:
            if memory.status == "deprecated":
                continue
            
            created = self._get_created_date(memory)
            if created is not None:
                dated_memories.append((memory, created))
        
        if len(dated_memories) < 2:
            return []
        
        dated_memories.sort(key=lambda x: x[1])
        
        clusters: list[list[str]] = []
        current_cluster: list[str] = []
        cluster_end: datetime | None = None
        
        for memory, created in dated_memories:
            if cluster_end is None or created <= cluster_end:
                current_cluster.append(memory.id)
                new_end = created + timedelta(days=window_days)
                if cluster_end is None or new_end > cluster_end:
                    cluster_end = new_end
            else:
                if len(current_cluster) >= 2:
                    clusters.append(current_cluster)
                current_cluster = [memory.id]
                cluster_end = created + timedelta(days=window_days)
        
        if len(current_cluster) >= 2:
            clusters.append(current_cluster)
        
        return clusters
