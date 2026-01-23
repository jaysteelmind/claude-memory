"""Knowledge graph storage layer using Kuzu embedded database.

This module provides the KnowledgeGraphStore class which manages all
interactions with the Kuzu graph database for the DMM system.

The store provides methods for:
- Node operations (create, read, update, delete)
- Edge operations (create, delete, query)
- Graph traversal (related memories, paths)
- Statistics and health checks

The Kuzu database is stored in .dmm/index/knowledge.kuzu/ and persists
across daemon restarts.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import kuzu

from dmm.graph.nodes import MemoryNode, TagNode, ScopeNode, ConceptNode
from dmm.graph.schema import initialize_schema


@dataclass
class GraphStats:
    """Statistics about the knowledge graph.

    Attributes:
        memory_count: Number of Memory nodes.
        tag_count: Number of Tag nodes.
        scope_count: Number of Scope nodes.
        concept_count: Number of Concept nodes.
        edge_count: Total number of edges.
        relationship_counts: Dictionary of edge counts by type.
    """

    memory_count: int
    tag_count: int
    scope_count: int
    concept_count: int
    edge_count: int
    relationship_counts: dict[str, int]


class KnowledgeGraphStore:
    """Manages the Kuzu knowledge graph database.

    Provides methods for:
    - Creating and querying nodes (Memory, Tag, Scope, Concept)
    - Creating and querying edges (relationships)
    - Graph traversal operations
    - Statistics and health checks

    The store maintains a connection to the Kuzu database and handles
    schema initialization on first use.

    Example:
        store = KnowledgeGraphStore(Path(".dmm/index/knowledge.kuzu"))
        store.initialize()
        store.upsert_memory_node(memory_node)
        related = store.get_related_memories("mem_001", max_depth=2)
        store.close()
    """

    def __init__(self, db_path: Path) -> None:
        """Initialize the knowledge graph store.

        Args:
            db_path: Path to the Kuzu database directory.
        """
        self._db_path = db_path
        self._db: Optional[kuzu.Database] = None
        self._conn: Optional[kuzu.Connection] = None
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        """Check if the store has been initialized."""
        return self._initialized and self._conn is not None

    def initialize(self) -> None:
        """Initialize database connection and schema.

        Opens the database connection and initializes the schema.
        Kuzu creates the database directory automatically.

        This method is idempotent and safe to call multiple times.
        """
        if self._initialized:
            return

        # Ensure parent directory exists (Kuzu creates the db directory itself)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = kuzu.Database(str(self._db_path))
        self._conn = kuzu.Connection(self._db)
        initialize_schema(self._conn)
        self._initialized = True

    def close(self) -> None:
        """Close the database connection.

        Releases all resources associated with the connection.
        The store can be re-initialized after closing.
        """
        self._conn = None
        self._db = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Ensure the store is initialized before operations."""
        if not self._initialized or self._conn is None:
            raise RuntimeError("KnowledgeGraphStore not initialized. Call initialize() first.")

    # =========================================================================
    # Node Operations
    # =========================================================================

    def upsert_memory_node(self, node: MemoryNode) -> None:
        """Create or update a memory node.

        If a node with the same ID exists, it will be updated.
        Otherwise, a new node is created.

        Args:
            node: MemoryNode instance to upsert.
        """
        self._ensure_initialized()

        # Try to merge (upsert) the node
        query = """
            MERGE (m:Memory {id: $id})
            SET m.path = $path,
                m.directory = $directory,
                m.title = $title,
                m.scope = $scope,
                m.priority = $priority,
                m.confidence = $confidence,
                m.status = $status,
                m.token_count = $token_count,
                m.created = $created,
                m.last_used = $last_used,
                m.usage_count = $usage_count,
                m.file_hash = $file_hash,
                m.indexed_at = $indexed_at
        """
        params = node.to_dict()
        self._conn.execute(query, params)

    def upsert_tag_node(self, node: TagNode) -> None:
        """Create or update a tag node.

        Args:
            node: TagNode instance to upsert.
        """
        self._ensure_initialized()

        query = """
            MERGE (t:Tag {id: $id})
            SET t.name = $name,
                t.normalized = $normalized,
                t.usage_count = $usage_count
        """
        self._conn.execute(query, node.to_dict())

    def upsert_scope_node(self, node: ScopeNode) -> None:
        """Create or update a scope node.

        Args:
            node: ScopeNode instance to upsert.
        """
        self._ensure_initialized()

        query = """
            MERGE (s:Scope {id: $id})
            SET s.name = $name,
                s.description = $description,
                s.memory_count = $memory_count,
                s.token_total = $token_total
        """
        self._conn.execute(query, node.to_dict())

    def upsert_concept_node(self, node: ConceptNode) -> None:
        """Create or update a concept node.

        Args:
            node: ConceptNode instance to upsert.
        """
        self._ensure_initialized()

        query = """
            MERGE (c:Concept {id: $id})
            SET c.name = $name,
                c.definition = $definition,
                c.source_count = $source_count
        """
        self._conn.execute(query, node.to_dict())

    def delete_memory_node(self, memory_id: str) -> bool:
        """Delete a memory node and all its edges.

        Args:
            memory_id: ID of the memory to delete.

        Returns:
            True if the node was deleted, False if not found.
        """
        self._ensure_initialized()

        # First check if node exists
        check_query = "MATCH (m:Memory {id: $id}) RETURN m.id"
        result = self._conn.execute(check_query, {"id": memory_id})
        if not result.has_next():
            return False

        # Delete the node (Kuzu automatically deletes connected edges)
        delete_query = "MATCH (m:Memory {id: $id}) DELETE m"
        self._conn.execute(delete_query, {"id": memory_id})
        return True

    def delete_tag_node(self, tag_id: str) -> bool:
        """Delete a tag node and all its edges.

        Args:
            tag_id: ID of the tag to delete.

        Returns:
            True if the node was deleted, False if not found.
        """
        self._ensure_initialized()

        check_query = "MATCH (t:Tag {id: $id}) RETURN t.id"
        result = self._conn.execute(check_query, {"id": tag_id})
        if not result.has_next():
            return False

        delete_query = "MATCH (t:Tag {id: $id}) DELETE t"
        self._conn.execute(delete_query, {"id": tag_id})
        return True

    def get_memory_node(self, memory_id: str) -> Optional[MemoryNode]:
        """Get a memory node by ID.

        Args:
            memory_id: ID of the memory to retrieve.

        Returns:
            MemoryNode instance if found, None otherwise.
        """
        self._ensure_initialized()

        query = """
            MATCH (m:Memory {id: $id})
            RETURN m.id, m.path, m.directory, m.title, m.scope,
                   m.priority, m.confidence, m.status, m.token_count,
                   m.created, m.last_used, m.usage_count, m.file_hash,
                   m.indexed_at
        """
        result = self._conn.execute(query, {"id": memory_id})

        if not result.has_next():
            return None

        row = result.get_next()
        return MemoryNode(
            id=row[0],
            path=row[1] or "",
            directory=row[2] or "",
            title=row[3] or "",
            scope=row[4] or "project",
            priority=float(row[5]) if row[5] is not None else 0.5,
            confidence=row[6] or "active",
            status=row[7] or "active",
            token_count=int(row[8]) if row[8] is not None else 0,
            created=row[9],
            last_used=row[10],
            usage_count=int(row[11]) if row[11] is not None else 0,
            file_hash=row[12] or "",
            indexed_at=row[13],
        )

    def get_tag_node(self, tag_id: str) -> Optional[TagNode]:
        """Get a tag node by ID.

        Args:
            tag_id: ID of the tag to retrieve.

        Returns:
            TagNode instance if found, None otherwise.
        """
        self._ensure_initialized()

        query = """
            MATCH (t:Tag {id: $id})
            RETURN t.id, t.name, t.normalized, t.usage_count
        """
        result = self._conn.execute(query, {"id": tag_id})

        if not result.has_next():
            return None

        row = result.get_next()
        return TagNode(
            id=row[0],
            name=row[1] or "",
            normalized=row[2] or "",
            usage_count=int(row[3]) if row[3] is not None else 0,
        )

    def get_scope_node(self, scope_id: str) -> Optional[ScopeNode]:
        """Get a scope node by ID.

        Args:
            scope_id: ID of the scope to retrieve.

        Returns:
            ScopeNode instance if found, None otherwise.
        """
        self._ensure_initialized()

        query = """
            MATCH (s:Scope {id: $id})
            RETURN s.id, s.name, s.description, s.memory_count, s.token_total
        """
        result = self._conn.execute(query, {"id": scope_id})

        if not result.has_next():
            return None

        row = result.get_next()
        return ScopeNode(
            id=row[0],
            name=row[1] or "",
            description=row[2] or "",
            memory_count=int(row[3]) if row[3] is not None else 0,
            token_total=int(row[4]) if row[4] is not None else 0,
        )

    def get_all_memory_nodes(self) -> list[MemoryNode]:
        """Get all memory nodes.

        Returns:
            List of all MemoryNode instances in the graph.
        """
        self._ensure_initialized()

        query = """
            MATCH (m:Memory)
            RETURN m.id, m.path, m.directory, m.title, m.scope,
                   m.priority, m.confidence, m.status, m.token_count,
                   m.created, m.last_used, m.usage_count, m.file_hash,
                   m.indexed_at
            ORDER BY m.id
        """
        result = self._conn.execute(query)

        nodes = []
        while result.has_next():
            row = result.get_next()
            nodes.append(MemoryNode(
                id=row[0],
                path=row[1] or "",
                directory=row[2] or "",
                title=row[3] or "",
                scope=row[4] or "project",
                priority=float(row[5]) if row[5] is not None else 0.5,
                confidence=row[6] or "active",
                status=row[7] or "active",
                token_count=int(row[8]) if row[8] is not None else 0,
                created=row[9],
                last_used=row[10],
                usage_count=int(row[11]) if row[11] is not None else 0,
                file_hash=row[12] or "",
                indexed_at=row[13],
            ))
        return nodes

    def get_all_tag_nodes(self) -> list[TagNode]:
        """Get all tag nodes.

        Returns:
            List of all TagNode instances in the graph.
        """
        self._ensure_initialized()

        query = """
            MATCH (t:Tag)
            RETURN t.id, t.name, t.normalized, t.usage_count
            ORDER BY t.normalized
        """
        result = self._conn.execute(query)

        nodes = []
        while result.has_next():
            row = result.get_next()
            nodes.append(TagNode(
                id=row[0],
                name=row[1] or "",
                normalized=row[2] or "",
                usage_count=int(row[3]) if row[3] is not None else 0,
            ))
        return nodes

    def get_all_scope_nodes(self) -> list[ScopeNode]:
        """Get all scope nodes.

        Returns:
            List of all ScopeNode instances in the graph.
        """
        self._ensure_initialized()

        query = """
            MATCH (s:Scope)
            RETURN s.id, s.name, s.description, s.memory_count, s.token_total
            ORDER BY s.name
        """
        result = self._conn.execute(query)

        nodes = []
        while result.has_next():
            row = result.get_next()
            nodes.append(ScopeNode(
                id=row[0],
                name=row[1] or "",
                description=row[2] or "",
                memory_count=int(row[3]) if row[3] is not None else 0,
                token_total=int(row[4]) if row[4] is not None else 0,
            ))
        return nodes

    # =========================================================================
    # Edge Operations
    # =========================================================================

    def create_edge(
        self,
        edge_type: str,
        from_id: str,
        to_id: str,
        properties: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Create an edge between nodes.

        Args:
            edge_type: Type of relationship (e.g., RELATES_TO, HAS_TAG).
            from_id: Source node ID.
            to_id: Target node ID.
            properties: Optional edge properties.

        Returns:
            True if edge was created, False otherwise.
        """
        self._ensure_initialized()
        props = properties or {}

        # Determine node types based on edge type
        from_table, to_table = self._get_edge_node_tables(edge_type)

        # Build the CREATE query with properties
        prop_sets = []
        for key, value in props.items():
            if key not in ("from_id", "to_id"):
                prop_sets.append(f"r.{key} = ${key}")

        prop_clause = ", ".join(prop_sets) if prop_sets else ""
        set_clause = f"SET {prop_clause}" if prop_clause else ""

        query = f"""
            MATCH (a:{from_table} {{id: $from_id}})
            MATCH (b:{to_table} {{id: $to_id}})
            CREATE (a)-[r:{edge_type}]->(b)
            {set_clause}
        """

        params = {"from_id": from_id, "to_id": to_id, **props}
        try:
            self._conn.execute(query, params)
            return True
        except kuzu.Error:
            return False

    def delete_edge(
        self,
        edge_type: str,
        from_id: str,
        to_id: str,
    ) -> bool:
        """Delete an edge between nodes.

        Args:
            edge_type: Type of relationship.
            from_id: Source node ID.
            to_id: Target node ID.

        Returns:
            True if edge was deleted, False if not found.
        """
        self._ensure_initialized()

        from_table, to_table = self._get_edge_node_tables(edge_type)

        query = f"""
            MATCH (a:{from_table} {{id: $from_id}})-[r:{edge_type}]->(b:{to_table} {{id: $to_id}})
            DELETE r
        """
        try:
            self._conn.execute(query, {"from_id": from_id, "to_id": to_id})
            return True
        except kuzu.Error:
            return False

    def delete_edges_from(self, node_id: str, edge_type: Optional[str] = None) -> int:
        """Delete all edges originating from a node.

        Args:
            node_id: Source node ID.
            edge_type: Optional edge type filter.

        Returns:
            Number of edges deleted.
        """
        self._ensure_initialized()

        if edge_type:
            query = f"""
                MATCH (m:Memory {{id: $id}})-[r:{edge_type}]->()
                DELETE r
            """
        else:
            query = """
                MATCH (m:Memory {id: $id})-[r]->()
                DELETE r
            """

        self._conn.execute(query, {"id": node_id})
        return 0  # Kuzu doesn't return delete count easily

    def get_edges_from(
        self,
        node_id: str,
        edge_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Get all edges originating from a node.

        Args:
            node_id: Source node ID.
            edge_type: Optional filter by edge type.

        Returns:
            List of edge dictionaries with type, to_id, and properties.
        """
        self._ensure_initialized()

        edges = []

        # Query each edge type separately for clarity
        edge_types_to_query = [edge_type] if edge_type else [
            "RELATES_TO", "SUPERSEDES", "CONTRADICTS", "SUPPORTS",
            "DEPENDS_ON", "HAS_TAG", "IN_SCOPE"
        ]

        for et in edge_types_to_query:
            from_table, to_table = self._get_edge_node_tables(et)
            query = f"""
                MATCH (a:{from_table} {{id: $id}})-[r:{et}]->(b:{to_table})
                RETURN b.id AS to_id
            """
            try:
                result = self._conn.execute(query, {"id": node_id})
                while result.has_next():
                    row = result.get_next()
                    edge_data = {
                        "type": et,
                        "from_id": node_id,
                        "to_id": row[0],
                    }
                    edges.append(edge_data)
            except Exception:
                continue

        return edges

    def get_edges_to(
        self,
        node_id: str,
        edge_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Get all edges pointing to a node.

        Args:
            node_id: Target node ID.
            edge_type: Optional filter by edge type.

        Returns:
            List of edge dictionaries with type, from_id, and properties.
        """
        self._ensure_initialized()

        edges = []

        edge_types_to_query = [edge_type] if edge_type else [
            "RELATES_TO", "SUPERSEDES", "CONTRADICTS", "SUPPORTS",
            "DEPENDS_ON", "HAS_TAG", "IN_SCOPE"
        ]

        for et in edge_types_to_query:
            from_table, to_table = self._get_edge_node_tables(et)
            query = f"""
                MATCH (a:{from_table})-[r:{et}]->(b:{to_table} {{id: $id}})
                RETURN a.id AS from_id
            """
            try:
                result = self._conn.execute(query, {"id": node_id})
                while result.has_next():
                    row = result.get_next()
                    edge_data = {
                        "type": et,
                        "from_id": row[0],
                        "to_id": node_id,
                    }
                    edges.append(edge_data)
            except Exception:
                continue

        return edges

    def edge_exists(
        self,
        edge_type: str,
        from_id: str,
        to_id: str,
    ) -> bool:
        """Check if an edge exists between two nodes.

        Args:
            edge_type: Type of relationship.
            from_id: Source node ID.
            to_id: Target node ID.

        Returns:
            True if edge exists, False otherwise.
        """
        self._ensure_initialized()

        from_table, to_table = self._get_edge_node_tables(edge_type)

        query = f"""
            MATCH (a:{from_table} {{id: $from_id}})-[r:{edge_type}]->(b:{to_table} {{id: $to_id}})
            RETURN count(r) AS cnt
        """
        result = self._conn.execute(query, {"from_id": from_id, "to_id": to_id})

        if result.has_next():
            row = result.get_next()
            return row[0] > 0
        return False

    def _get_edge_node_tables(self, edge_type: str) -> tuple[str, str]:
        """Get the from and to node table names for an edge type.

        Args:
            edge_type: Type of relationship.

        Returns:
            Tuple of (from_table, to_table) names.
        """
        edge_tables = {
            "RELATES_TO": ("Memory", "Memory"),
            "SUPERSEDES": ("Memory", "Memory"),
            "CONTRADICTS": ("Memory", "Memory"),
            "SUPPORTS": ("Memory", "Memory"),
            "DEPENDS_ON": ("Memory", "Memory"),
            "HAS_TAG": ("Memory", "Tag"),
            "IN_SCOPE": ("Memory", "Scope"),
            "TAG_COOCCURS": ("Tag", "Tag"),
            "ABOUT": ("Memory", "Concept"),
            "DEFINES": ("Memory", "Concept"),
        }
        return edge_tables.get(edge_type.upper(), ("Memory", "Memory"))

    # =========================================================================
    # Graph Queries
    # =========================================================================

    def get_related_memories(
        self,
        memory_id: str,
        max_depth: int = 1,
        edge_types: Optional[list[str]] = None,
    ) -> list[MemoryNode]:
        """Get memories related to a given memory via graph traversal.

        Traverses the graph to find connected memories up to max_depth hops.

        Args:
            memory_id: Starting memory ID.
            max_depth: Maximum traversal depth (default 1).
            edge_types: Optional list of edge types to traverse.
                If None, traverses RELATES_TO, SUPERSEDES, SUPPORTS, DEPENDS_ON.

        Returns:
            List of related MemoryNode instances (excluding the starting node).
        """
        self._ensure_initialized()

        if edge_types is None:
            edge_types = ["RELATES_TO", "SUPERSEDES", "SUPPORTS", "DEPENDS_ON"]

        # Build edge type pattern
        edge_pattern = "|".join(edge_types)

        query = f"""
            MATCH (start:Memory {{id: $id}})-[r:{edge_pattern}*1..{max_depth}]-(related:Memory)
            WHERE related.id <> $id
            RETURN DISTINCT related.id, related.path, related.directory, related.title,
                   related.scope, related.priority, related.confidence, related.status,
                   related.token_count, related.created, related.last_used,
                   related.usage_count, related.file_hash, related.indexed_at
        """

        try:
            result = self._conn.execute(query, {"id": memory_id})
        except kuzu.Error:
            return []

        nodes = []
        while result.has_next():
            row = result.get_next()
            nodes.append(MemoryNode(
                id=row[0],
                path=row[1] or "",
                directory=row[2] or "",
                title=row[3] or "",
                scope=row[4] or "project",
                priority=float(row[5]) if row[5] is not None else 0.5,
                confidence=row[6] or "active",
                status=row[7] or "active",
                token_count=int(row[8]) if row[8] is not None else 0,
                created=row[9],
                last_used=row[10],
                usage_count=int(row[11]) if row[11] is not None else 0,
                file_hash=row[12] or "",
                indexed_at=row[13],
            ))
        return nodes

    def get_memories_by_tag(self, tag: str) -> list[MemoryNode]:
        """Get all memories with a specific tag.

        Args:
            tag: Tag name (will be normalized for matching).

        Returns:
            List of MemoryNode instances with the specified tag.
        """
        self._ensure_initialized()

        normalized = tag.lower().strip()
        tag_id = f"tag_{normalized.replace(' ', '_').replace('-', '_')}"

        query = """
            MATCH (m:Memory)-[:HAS_TAG]->(t:Tag {id: $tag_id})
            RETURN m.id, m.path, m.directory, m.title, m.scope,
                   m.priority, m.confidence, m.status, m.token_count,
                   m.created, m.last_used, m.usage_count, m.file_hash,
                   m.indexed_at
            ORDER BY m.priority DESC
        """
        result = self._conn.execute(query, {"tag_id": tag_id})

        nodes = []
        while result.has_next():
            row = result.get_next()
            nodes.append(MemoryNode(
                id=row[0],
                path=row[1] or "",
                directory=row[2] or "",
                title=row[3] or "",
                scope=row[4] or "project",
                priority=float(row[5]) if row[5] is not None else 0.5,
                confidence=row[6] or "active",
                status=row[7] or "active",
                token_count=int(row[8]) if row[8] is not None else 0,
                created=row[9],
                last_used=row[10],
                usage_count=int(row[11]) if row[11] is not None else 0,
                file_hash=row[12] or "",
                indexed_at=row[13],
            ))
        return nodes

    def get_memories_by_scope(self, scope: str) -> list[MemoryNode]:
        """Get all memories in a specific scope.

        Args:
            scope: Scope name (e.g., "project", "global").

        Returns:
            List of MemoryNode instances in the specified scope.
        """
        self._ensure_initialized()

        scope_id = f"scope_{scope}"

        query = """
            MATCH (m:Memory)-[:IN_SCOPE]->(s:Scope {id: $scope_id})
            RETURN m.id, m.path, m.directory, m.title, m.scope,
                   m.priority, m.confidence, m.status, m.token_count,
                   m.created, m.last_used, m.usage_count, m.file_hash,
                   m.indexed_at
            ORDER BY m.priority DESC
        """
        result = self._conn.execute(query, {"scope_id": scope_id})

        nodes = []
        while result.has_next():
            row = result.get_next()
            nodes.append(MemoryNode(
                id=row[0],
                path=row[1] or "",
                directory=row[2] or "",
                title=row[3] or "",
                scope=row[4] or "project",
                priority=float(row[5]) if row[5] is not None else 0.5,
                confidence=row[6] or "active",
                status=row[7] or "active",
                token_count=int(row[8]) if row[8] is not None else 0,
                created=row[9],
                last_used=row[10],
                usage_count=int(row[11]) if row[11] is not None else 0,
                file_hash=row[12] or "",
                indexed_at=row[13],
            ))
        return nodes

    def get_contradiction_pairs(self) -> list[tuple[MemoryNode, MemoryNode, str]]:
        """Get all pairs of contradicting memories.

        Returns:
            List of tuples (memory1, memory2, description) for each contradiction.
        """
        self._ensure_initialized()

        query = """
            MATCH (m1:Memory)-[r:CONTRADICTS]->(m2:Memory)
            RETURN m1.id, m1.path, m1.directory, m1.title, m1.scope,
                   m1.priority, m1.confidence, m1.status, m1.token_count,
                   m2.id, m2.path, m2.directory, m2.title, m2.scope,
                   m2.priority, m2.confidence, m2.status, m2.token_count,
                   r.description
        """
        result = self._conn.execute(query)

        pairs = []
        while result.has_next():
            row = result.get_next()
            m1 = MemoryNode(
                id=row[0], path=row[1] or "", directory=row[2] or "",
                title=row[3] or "", scope=row[4] or "project",
                priority=float(row[5]) if row[5] else 0.5,
                confidence=row[6] or "active", status=row[7] or "active",
                token_count=int(row[8]) if row[8] else 0,
            )
            m2 = MemoryNode(
                id=row[9], path=row[10] or "", directory=row[11] or "",
                title=row[12] or "", scope=row[13] or "project",
                priority=float(row[14]) if row[14] else 0.5,
                confidence=row[15] or "active", status=row[16] or "active",
                token_count=int(row[17]) if row[17] else 0,
            )
            description = row[18] or ""
            pairs.append((m1, m2, description))

        return pairs

    def get_supersession_chain(self, memory_id: str) -> list[MemoryNode]:
        """Get the chain of superseded memories.

        Follows SUPERSEDES edges to find all memories that have been
        replaced, directly or transitively.

        Args:
            memory_id: Starting memory ID.

        Returns:
            List of MemoryNode instances in supersession order
            (newest to oldest).
        """
        self._ensure_initialized()

        query = """
            MATCH path = (start:Memory {id: $id})-[:SUPERSEDES*]->(old:Memory)
            RETURN old.id, old.path, old.directory, old.title, old.scope,
                   old.priority, old.confidence, old.status, old.token_count,
                   old.created, old.last_used, old.usage_count, old.file_hash,
                   old.indexed_at
        """

        try:
            result = self._conn.execute(query, {"id": memory_id})
        except kuzu.Error:
            return []

        nodes = []
        while result.has_next():
            row = result.get_next()
            nodes.append(MemoryNode(
                id=row[0],
                path=row[1] or "",
                directory=row[2] or "",
                title=row[3] or "",
                scope=row[4] or "project",
                priority=float(row[5]) if row[5] is not None else 0.5,
                confidence=row[6] or "active",
                status=row[7] or "active",
                token_count=int(row[8]) if row[8] is not None else 0,
                created=row[9],
                last_used=row[10],
                usage_count=int(row[11]) if row[11] is not None else 0,
                file_hash=row[12] or "",
                indexed_at=row[13],
            ))
        return nodes

    def find_path(
        self,
        from_id: str,
        to_id: str,
        max_depth: int = 5,
    ) -> Optional[list[str]]:
        """Find shortest path between two memories.

        Uses breadth-first search to find the shortest path.

        Args:
            from_id: Source memory ID.
            to_id: Target memory ID.
            max_depth: Maximum path length to search.

        Returns:
            List of memory IDs forming the path, or None if no path found.
        """
        self._ensure_initialized()

        query = f"""
            MATCH path = shortestPath(
                (start:Memory {{id: $from_id}})-[*1..{max_depth}]-(end:Memory {{id: $to_id}})
            )
            RETURN [node in nodes(path) | node.id] AS path_ids
        """

        try:
            result = self._conn.execute(query, {"from_id": from_id, "to_id": to_id})
            if result.has_next():
                row = result.get_next()
                return row[0] if row[0] else None
        except kuzu.Error:
            pass

        return None

    def get_tags_for_memory(self, memory_id: str) -> list[TagNode]:
        """Get all tags associated with a memory.

        Args:
            memory_id: Memory ID.

        Returns:
            List of TagNode instances.
        """
        self._ensure_initialized()

        query = """
            MATCH (m:Memory {id: $id})-[:HAS_TAG]->(t:Tag)
            RETURN t.id, t.name, t.normalized, t.usage_count
            ORDER BY t.normalized
        """
        result = self._conn.execute(query, {"id": memory_id})

        tags = []
        while result.has_next():
            row = result.get_next()
            tags.append(TagNode(
                id=row[0],
                name=row[1] or "",
                normalized=row[2] or "",
                usage_count=int(row[3]) if row[3] is not None else 0,
            ))
        return tags

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_stats(self) -> GraphStats:
        """Get statistics about the knowledge graph.

        Returns:
            GraphStats instance with counts for all node and edge types.
        """
        self._ensure_initialized()

        # Count nodes
        memory_count = self._count_nodes("Memory")
        tag_count = self._count_nodes("Tag")
        scope_count = self._count_nodes("Scope")
        concept_count = self._count_nodes("Concept")

        # Count edges by type
        edge_types = [
            "RELATES_TO", "SUPERSEDES", "CONTRADICTS", "SUPPORTS",
            "DEPENDS_ON", "HAS_TAG", "IN_SCOPE", "TAG_COOCCURS",
            "ABOUT", "DEFINES"
        ]

        relationship_counts = {}
        total_edges = 0

        for edge_type in edge_types:
            count = self._count_edges(edge_type)
            if count > 0:
                relationship_counts[edge_type] = count
                total_edges += count

        return GraphStats(
            memory_count=memory_count,
            tag_count=tag_count,
            scope_count=scope_count,
            concept_count=concept_count,
            edge_count=total_edges,
            relationship_counts=relationship_counts,
        )

    def _count_nodes(self, table: str) -> int:
        """Count nodes in a table.

        Args:
            table: Node table name.

        Returns:
            Number of nodes.
        """
        query = f"MATCH (n:{table}) RETURN count(n) AS cnt"
        try:
            result = self._conn.execute(query)
            if result.has_next():
                return result.get_next()[0]
        except kuzu.Error:
            pass
        return 0

    def _count_edges(self, edge_type: str) -> int:
        """Count edges of a specific type.

        Args:
            edge_type: Edge type name.

        Returns:
            Number of edges.
        """
        from_table, to_table = self._get_edge_node_tables(edge_type)
        query = f"MATCH (:{from_table})-[r:{edge_type}]->(:{to_table}) RETURN count(r) AS cnt"
        try:
            result = self._conn.execute(query)
            if result.has_next():
                return result.get_next()[0]
        except kuzu.Error:
            pass
        return 0

    def execute_cypher(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Execute a raw Cypher query.

        Args:
            query: Cypher query string.
            params: Optional query parameters.

        Returns:
            List of result dictionaries.
        """
        self._ensure_initialized()

        result = self._conn.execute(query, params or {})

        # Get column names from the query result
        rows = []
        column_names = result.get_column_names()

        while result.has_next():
            row = result.get_next()
            row_dict = {}
            for i, col_name in enumerate(column_names):
                row_dict[col_name] = row[i]
            rows.append(row_dict)

        return rows
