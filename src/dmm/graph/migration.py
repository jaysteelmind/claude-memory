"""Migration utilities for populating the knowledge graph from existing memories.

This module provides the GraphMigration class which handles the complete
migration of existing DMM memories into the Kuzu knowledge graph.

Migration process:
1. Create scope nodes for all defined scopes
2. Create memory nodes from IndexedMemory records
3. Create tag nodes from all unique tags
4. Create HAS_TAG edges (memory -> tag)
5. Create IN_SCOPE edges (memory -> scope)
6. Process explicit relationships from frontmatter (supersedes, related)
7. Calculate and create TAG_COOCCURS edges
8. Update scope statistics

The migration is idempotent - running it multiple times will update
existing nodes rather than creating duplicates.
"""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from dmm.graph.store import KnowledgeGraphStore
from dmm.graph.nodes import (
    MemoryNode,
    TagNode,
    ScopeNode,
    SCOPE_DEFINITIONS,
    create_all_scope_nodes,
)
from dmm.graph.edges import (
    RelatesTo,
    Supersedes,
    HasTag,
    InScope,
    TagCooccurs,
)


@dataclass
class MigrationStats:
    """Statistics from a migration run.

    Attributes:
        memories: Number of memory nodes created/updated.
        tags: Number of tag nodes created/updated.
        scopes: Number of scope nodes created.
        has_tag_edges: Number of HAS_TAG edges created.
        in_scope_edges: Number of IN_SCOPE edges created.
        relates_to_edges: Number of RELATES_TO edges created.
        supersedes_edges: Number of SUPERSEDES edges created.
        tag_cooccurs_edges: Number of TAG_COOCCURS edges created.
        errors: List of error messages encountered.
        duration_ms: Total migration duration in milliseconds.
    """

    memories: int = 0
    tags: int = 0
    scopes: int = 0
    has_tag_edges: int = 0
    in_scope_edges: int = 0
    relates_to_edges: int = 0
    supersedes_edges: int = 0
    tag_cooccurs_edges: int = 0
    errors: list[str] = field(default_factory=list)
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "memories": self.memories,
            "tags": self.tags,
            "scopes": self.scopes,
            "has_tag_edges": self.has_tag_edges,
            "in_scope_edges": self.in_scope_edges,
            "relates_to_edges": self.relates_to_edges,
            "supersedes_edges": self.supersedes_edges,
            "tag_cooccurs_edges": self.tag_cooccurs_edges,
            "errors": self.errors,
            "duration_ms": self.duration_ms,
        }


class GraphMigration:
    """Handles migration from flat memory storage to knowledge graph.

    This class orchestrates the complete migration process, transforming
    the existing SQLite-based memory storage into a rich knowledge graph
    with nodes and relationships.

    Example:
        graph_store = KnowledgeGraphStore(graph_path)
        graph_store.initialize()

        memory_store = MemoryStore(embeddings_path)
        memory_store.initialize()

        migration = GraphMigration(graph_store, memory_store)
        stats = migration.migrate()
        print(f"Migrated {stats.memories} memories")
    """

    def __init__(
        self,
        graph_store: KnowledgeGraphStore,
        memory_store: Any,  # MemoryStore type, but avoiding circular import
    ) -> None:
        """Initialize the migration handler.

        Args:
            graph_store: Initialized KnowledgeGraphStore instance.
            memory_store: Initialized MemoryStore instance.
        """
        self._graph = graph_store
        self._memory_store = memory_store

    def migrate(
        self,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> MigrationStats:
        """Execute full migration from flat storage to graph.

        This method performs the complete migration in sequence:
        1. Create scope nodes
        2. Create memory nodes
        3. Create tag nodes and HAS_TAG edges
        4. Create IN_SCOPE edges
        5. Process explicit relationships
        6. Calculate tag co-occurrence
        7. Update scope statistics

        Args:
            progress_callback: Optional callback for progress updates.
                Signature: callback(step_name, current, total)

        Returns:
            MigrationStats instance with counts and any errors.
        """
        start_time = datetime.now()
        stats = MigrationStats()

        def report_progress(step: str, current: int, total: int) -> None:
            if progress_callback:
                progress_callback(step, current, total)

        # Step 1: Create scope nodes
        report_progress("Creating scope nodes", 0, len(SCOPE_DEFINITIONS))
        self._create_scope_nodes(stats)
        report_progress("Creating scope nodes", len(SCOPE_DEFINITIONS), len(SCOPE_DEFINITIONS))

        # Step 2: Load all memories from the memory store
        memories = self._load_memories()
        total_memories = len(memories)

        # Step 3: Create memory nodes
        report_progress("Creating memory nodes", 0, total_memories)
        self._create_memory_nodes(memories, stats, progress_callback)

        # Step 4: Create tag nodes and HAS_TAG edges
        report_progress("Creating tag structure", 0, total_memories)
        self._create_tag_structure(memories, stats, progress_callback)

        # Step 5: Create IN_SCOPE edges
        report_progress("Creating scope edges", 0, total_memories)
        self._create_scope_edges(memories, stats, progress_callback)

        # Step 6: Process explicit relationships from frontmatter
        report_progress("Processing relationships", 0, total_memories)
        self._process_explicit_relationships(memories, stats, progress_callback)

        # Step 7: Calculate tag co-occurrence
        report_progress("Calculating tag co-occurrence", 0, 1)
        self._calculate_tag_cooccurrence(stats)
        report_progress("Calculating tag co-occurrence", 1, 1)

        # Step 8: Update scope statistics
        report_progress("Updating scope statistics", 0, 1)
        self._update_scope_stats(stats)
        report_progress("Updating scope statistics", 1, 1)

        # Calculate duration
        end_time = datetime.now()
        stats.duration_ms = int((end_time - start_time).total_seconds() * 1000)

        return stats

    def _load_memories(self) -> list[Any]:
        """Load all memories from the memory store.

        Returns:
            List of IndexedMemory objects.
        """
        # The memory store should have a method to get all memories
        if hasattr(self._memory_store, "get_all_memories"):
            return self._memory_store.get_all_memories()
        elif hasattr(self._memory_store, "get_all"):
            return self._memory_store.get_all()
        else:
            # Fallback: try to query directly
            return []

    def _create_scope_nodes(self, stats: MigrationStats) -> None:
        """Create nodes for all memory scopes.

        Args:
            stats: MigrationStats to update.
        """
        scope_nodes = create_all_scope_nodes()
        for node in scope_nodes:
            try:
                self._graph.upsert_scope_node(node)
                stats.scopes += 1
            except Exception as e:
                stats.errors.append(f"Scope {node.name}: {str(e)}")

    def _create_memory_nodes(
        self,
        memories: list[Any],
        stats: MigrationStats,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> None:
        """Create memory nodes from indexed memories.

        Args:
            memories: List of IndexedMemory objects.
            stats: MigrationStats to update.
            progress_callback: Optional progress callback.
        """
        total = len(memories)
        for i, memory in enumerate(memories):
            try:
                node = MemoryNode.from_indexed_memory(memory)
                self._graph.upsert_memory_node(node)
                stats.memories += 1
            except Exception as e:
                memory_id = getattr(memory, "id", "unknown")
                stats.errors.append(f"Memory {memory_id}: {str(e)}")

            if progress_callback and (i + 1) % 10 == 0:
                progress_callback("Creating memory nodes", i + 1, total)

    def _create_tag_structure(
        self,
        memories: list[Any],
        stats: MigrationStats,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> None:
        """Create tag nodes and HAS_TAG edges.

        Args:
            memories: List of IndexedMemory objects.
            stats: MigrationStats to update.
            progress_callback: Optional progress callback.
        """
        # Collect all unique tags with usage counts
        tag_usage: dict[str, int] = defaultdict(int)
        for memory in memories:
            tags = self._get_memory_tags(memory)
            for tag in tags:
                normalized = tag.lower().strip()
                tag_usage[normalized] += 1

        # Create tag nodes
        for tag_name, count in tag_usage.items():
            try:
                node = TagNode.from_tag_name(tag_name)
                node.usage_count = count
                self._graph.upsert_tag_node(node)
                stats.tags += 1
            except Exception as e:
                stats.errors.append(f"Tag {tag_name}: {str(e)}")

        # Create HAS_TAG edges
        total = len(memories)
        for i, memory in enumerate(memories):
            memory_id = getattr(memory, "id", None)
            if not memory_id:
                continue

            tags = self._get_memory_tags(memory)
            for tag in tags:
                normalized = tag.lower().strip()
                tag_id = f"tag_{normalized.replace(' ', '_').replace('-', '_')}"

                try:
                    # Check if edge already exists
                    if not self._graph.edge_exists("HAS_TAG", memory_id, tag_id):
                        self._graph.create_edge("HAS_TAG", memory_id, tag_id)
                        stats.has_tag_edges += 1
                except Exception as e:
                    stats.errors.append(f"HAS_TAG {memory_id}->{tag_id}: {str(e)}")

            if progress_callback and (i + 1) % 10 == 0:
                progress_callback("Creating tag structure", i + 1, total)

    def _create_scope_edges(
        self,
        memories: list[Any],
        stats: MigrationStats,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> None:
        """Create IN_SCOPE edges.

        Args:
            memories: List of IndexedMemory objects.
            stats: MigrationStats to update.
            progress_callback: Optional progress callback.
        """
        total = len(memories)
        for i, memory in enumerate(memories):
            memory_id = getattr(memory, "id", None)
            scope = self._get_memory_scope(memory)

            if not memory_id or not scope:
                continue

            scope_id = f"scope_{scope}"

            try:
                if not self._graph.edge_exists("IN_SCOPE", memory_id, scope_id):
                    self._graph.create_edge("IN_SCOPE", memory_id, scope_id)
                    stats.in_scope_edges += 1
            except Exception as e:
                stats.errors.append(f"IN_SCOPE {memory_id}->{scope_id}: {str(e)}")

            if progress_callback and (i + 1) % 10 == 0:
                progress_callback("Creating scope edges", i + 1, total)

    def _process_explicit_relationships(
        self,
        memories: list[Any],
        stats: MigrationStats,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> None:
        """Process supersedes and related fields from frontmatter.

        Args:
            memories: List of IndexedMemory objects.
            stats: MigrationStats to update.
            progress_callback: Optional progress callback.
        """
        # Build memory ID set for validation
        memory_ids = {getattr(m, "id", None) for m in memories}
        memory_ids.discard(None)

        total = len(memories)
        for i, memory in enumerate(memories):
            memory_id = getattr(memory, "id", None)
            if not memory_id:
                continue

            # Process supersedes
            supersedes = self._get_memory_supersedes(memory)
            for superseded_id in supersedes:
                if superseded_id in memory_ids:
                    try:
                        if not self._graph.edge_exists("SUPERSEDES", memory_id, superseded_id):
                            self._graph.create_edge(
                                "SUPERSEDES",
                                memory_id,
                                superseded_id,
                                {"reason": "Declared in frontmatter"},
                            )
                            stats.supersedes_edges += 1
                    except Exception as e:
                        stats.errors.append(f"SUPERSEDES {memory_id}->{superseded_id}: {str(e)}")

            # Process related
            related = self._get_memory_related(memory)
            for related_id in related:
                if related_id in memory_ids:
                    try:
                        if not self._graph.edge_exists("RELATES_TO", memory_id, related_id):
                            self._graph.create_edge(
                                "RELATES_TO",
                                memory_id,
                                related_id,
                                {"weight": 1.0, "context": "Declared in frontmatter"},
                            )
                            stats.relates_to_edges += 1
                    except Exception as e:
                        stats.errors.append(f"RELATES_TO {memory_id}->{related_id}: {str(e)}")

            if progress_callback and (i + 1) % 10 == 0:
                progress_callback("Processing relationships", i + 1, total)

    def _calculate_tag_cooccurrence(self, stats: MigrationStats) -> None:
        """Calculate tag co-occurrence relationships.

        Creates TAG_COOCCURS edges between tags that appear together
        in multiple memories.

        Args:
            stats: MigrationStats to update.
        """
        # Count co-occurrences by querying the graph
        query = """
            MATCH (m:Memory)-[:HAS_TAG]->(t1:Tag)
            MATCH (m)-[:HAS_TAG]->(t2:Tag)
            WHERE t1.id < t2.id
            RETURN t1.id AS tag1_id, t2.id AS tag2_id, count(*) AS co_count
        """

        try:
            results = self._graph.execute_cypher(query)
        except Exception as e:
            stats.errors.append(f"Tag co-occurrence query failed: {str(e)}")
            return

        for row in results:
            t1_id = row["tag1_id"]
            t2_id = row["tag2_id"]
            count = row["co_count"]

            # Only create edges for meaningful co-occurrence (at least 2)
            if count >= 2:
                # Calculate strength (normalized by max possible)
                strength = min(1.0, count / 10.0)

                try:
                    if not self._graph.edge_exists("TAG_COOCCURS", t1_id, t2_id):
                        self._graph.create_edge(
                            "TAG_COOCCURS",
                            t1_id,
                            t2_id,
                            {"count": count, "strength": strength},
                        )
                        stats.tag_cooccurs_edges += 1
                except Exception as e:
                    stats.errors.append(f"TAG_COOCCURS {t1_id}->{t2_id}: {str(e)}")

    def _update_scope_stats(self, stats: MigrationStats) -> None:
        """Update scope nodes with memory counts and token totals.

        Args:
            stats: MigrationStats (not modified, just for consistency).
        """
        query = """
            MATCH (m:Memory)-[:IN_SCOPE]->(s:Scope)
            RETURN s.id AS scope_id, count(*) AS mem_count, sum(m.token_count) AS token_sum
        """

        try:
            results = self._graph.execute_cypher(query)
        except Exception:
            return

        for row in results:
            scope_id = row["scope_id"]
            mem_count = row["mem_count"] or 0
            token_sum = row["token_sum"] or 0

            # Get existing scope node and update
            scope_node = self._graph.get_scope_node(scope_id)
            if scope_node:
                scope_node.memory_count = mem_count
                scope_node.token_total = token_sum
                self._graph.upsert_scope_node(scope_node)

    # Helper methods to extract data from memory objects

    def _get_memory_tags(self, memory: Any) -> list[str]:
        """Extract tags from a memory object."""
        if hasattr(memory, "tags"):
            tags = memory.tags
            if isinstance(tags, str):
                try:
                    return json.loads(tags)
                except json.JSONDecodeError:
                    return []
            return list(tags) if tags else []
        if hasattr(memory, "tags_json"):
            try:
                return json.loads(memory.tags_json)
            except json.JSONDecodeError:
                return []
        return []

    def _get_memory_scope(self, memory: Any) -> str:
        """Extract scope from a memory object."""
        if hasattr(memory, "scope"):
            scope = memory.scope
            if hasattr(scope, "value"):
                return scope.value
            return str(scope)
        return "project"

    def _get_memory_supersedes(self, memory: Any) -> list[str]:
        """Extract supersedes list from a memory object."""
        if hasattr(memory, "supersedes"):
            supersedes = memory.supersedes
            if isinstance(supersedes, str):
                try:
                    return json.loads(supersedes)
                except json.JSONDecodeError:
                    return []
            return list(supersedes) if supersedes else []
        if hasattr(memory, "supersedes_json"):
            try:
                return json.loads(memory.supersedes_json)
            except json.JSONDecodeError:
                return []
        return []

    def _get_memory_related(self, memory: Any) -> list[str]:
        """Extract related list from a memory object."""
        if hasattr(memory, "related"):
            related = memory.related
            if isinstance(related, str):
                try:
                    return json.loads(related)
                except json.JSONDecodeError:
                    return []
            return list(related) if related else []
        if hasattr(memory, "related_json"):
            try:
                return json.loads(memory.related_json)
            except json.JSONDecodeError:
                return []
        return []


def migrate_from_memory_store(
    graph_path: Path,
    embeddings_path: Path,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> MigrationStats:
    """Convenience function to run migration with paths.

    Creates the necessary store instances and runs migration.

    Args:
        graph_path: Path to Kuzu database directory.
        embeddings_path: Path to SQLite embeddings database.
        progress_callback: Optional progress callback.

    Returns:
        MigrationStats from the migration.
    """
    # Import here to avoid circular dependency
    from dmm.indexer.store import MemoryStore

    graph_store = KnowledgeGraphStore(graph_path)
    graph_store.initialize()

    memory_store = MemoryStore(embeddings_path)
    memory_store.initialize()

    try:
        migration = GraphMigration(graph_store, memory_store)
        return migration.migrate(progress_callback)
    finally:
        graph_store.close()
        memory_store.close()
