"""Knowledge graph schema definitions for Kuzu database.

This module defines the complete schema for the DMM knowledge graph including:
- Node tables: Memory, Tag, Scope, Concept
- Relationship tables: RELATES_TO, SUPERSEDES, CONTRADICTS, SUPPORTS, DEPENDS_ON,
  HAS_TAG, IN_SCOPE, TAG_COOCCURS, ABOUT, DEFINES

Schema version is tracked for future migrations.
"""

from typing import Final

import kuzu

# Schema version for tracking migrations
SCHEMA_VERSION: Final[str] = "2.0.0"

# Node table definitions using Kuzu DDL syntax
NODE_SCHEMAS: Final[dict[str, str]] = {
    "Memory": """
        CREATE NODE TABLE IF NOT EXISTS Memory (
            id STRING,
            path STRING,
            directory STRING,
            title STRING,
            scope STRING,
            priority DOUBLE,
            confidence STRING,
            status STRING,
            token_count INT64,
            created TIMESTAMP,
            last_used TIMESTAMP,
            usage_count INT64,
            file_hash STRING,
            indexed_at TIMESTAMP,
            PRIMARY KEY (id)
        )
    """,
    "Tag": """
        CREATE NODE TABLE IF NOT EXISTS Tag (
            id STRING,
            name STRING,
            normalized STRING,
            usage_count INT64,
            PRIMARY KEY (id)
        )
    """,
    "Scope": """
        CREATE NODE TABLE IF NOT EXISTS Scope (
            id STRING,
            name STRING,
            description STRING,
            memory_count INT64,
            token_total INT64,
            PRIMARY KEY (id)
        )
    """,
    "Concept": """
        CREATE NODE TABLE IF NOT EXISTS Concept (
            id STRING,
            name STRING,
            definition STRING,
            source_count INT64,
            PRIMARY KEY (id)
        )
    """,
    "Skill": """
        CREATE NODE TABLE IF NOT EXISTS Skill (
            id STRING,
            name STRING,
            version STRING,
            description STRING,
            category STRING,
            tags STRING[],
            enabled BOOLEAN,
            inputs_schema STRING,
            outputs_schema STRING,
            dependencies_json STRING,
            tools_json STRING,
            memory_requirements_json STRING,
            execution_config_json STRING,
            file_path STRING,
            created TIMESTAMP,
            updated TIMESTAMP,
            PRIMARY KEY (id)
        )
    """,
    "Tool": """
        CREATE NODE TABLE IF NOT EXISTS Tool (
            id STRING,
            name STRING,
            version STRING,
            tool_type STRING,
            description STRING,
            category STRING,
            tags STRING[],
            enabled BOOLEAN,
            config_json STRING,
            inputs_schema STRING,
            outputs_schema STRING,
            constraints_json STRING,
            file_path STRING,
            created TIMESTAMP,
            updated TIMESTAMP,
            PRIMARY KEY (id)
        )
    """,
    "Agent": """
        CREATE NODE TABLE IF NOT EXISTS Agent (
            id STRING,
            name STRING,
            version STRING,
            description STRING,
            category STRING,
            tags STRING[],
            enabled BOOLEAN,
            skills_json STRING,
            tools_json STRING,
            memory_config_json STRING,
            behavior_json STRING,
            constraints_json STRING,
            file_path STRING,
            created TIMESTAMP,
            updated TIMESTAMP,
            PRIMARY KEY (id)
        )
    """,
}

# Relationship table definitions using Kuzu DDL syntax
EDGE_SCHEMAS: Final[dict[str, str]] = {
    "RELATES_TO": """
        CREATE REL TABLE IF NOT EXISTS RELATES_TO (
            FROM Memory TO Memory,
            weight DOUBLE,
            context STRING
        )
    """,
    "SUPERSEDES": """
        CREATE REL TABLE IF NOT EXISTS SUPERSEDES (
            FROM Memory TO Memory,
            reason STRING,
            superseded_at TIMESTAMP
        )
    """,
    "CONTRADICTS": """
        CREATE REL TABLE IF NOT EXISTS CONTRADICTS (
            FROM Memory TO Memory,
            description STRING,
            resolution STRING
        )
    """,
    "SUPPORTS": """
        CREATE REL TABLE IF NOT EXISTS SUPPORTS (
            FROM Memory TO Memory,
            strength DOUBLE
        )
    """,
    "DEPENDS_ON": """
        CREATE REL TABLE IF NOT EXISTS DEPENDS_ON (
            FROM Memory TO Memory
        )
    """,
    "HAS_TAG": """
        CREATE REL TABLE IF NOT EXISTS HAS_TAG (
            FROM Memory TO Tag
        )
    """,
    "IN_SCOPE": """
        CREATE REL TABLE IF NOT EXISTS IN_SCOPE (
            FROM Memory TO Scope
        )
    """,
    "TAG_COOCCURS": """
        CREATE REL TABLE IF NOT EXISTS TAG_COOCCURS (
            FROM Tag TO Tag,
            count INT64,
            strength DOUBLE
        )
    """,
    "ABOUT": """
        CREATE REL TABLE IF NOT EXISTS ABOUT (
            FROM Memory TO Concept,
            relevance DOUBLE
        )
    """,
    "DEFINES": """
        CREATE REL TABLE IF NOT EXISTS DEFINES (
            FROM Memory TO Concept
        )
    """,
    "REQUIRES_SKILL": """
        CREATE REL TABLE IF NOT EXISTS REQUIRES_SKILL (
            FROM Memory TO Skill,
            relevance DOUBLE,
            reason STRING
        )
    """,
    "USES_TOOL": """
        CREATE REL TABLE IF NOT EXISTS USES_TOOL (
            FROM Skill TO Tool,
            required BOOLEAN,
            purpose STRING
        )
    """,
    "HAS_SKILL": """
        CREATE REL TABLE IF NOT EXISTS HAS_SKILL (
            FROM Agent TO Skill,
            proficiency STRING
        )
    """,
    "HAS_TOOL": """
        CREATE REL TABLE IF NOT EXISTS HAS_TOOL (
            FROM Agent TO Tool,
            enabled BOOLEAN
        )
    """,
    "SKILL_DEPENDS_ON": """
        CREATE REL TABLE IF NOT EXISTS SKILL_DEPENDS_ON (
            FROM Skill TO Skill,
            execution_order INT64
        )
    """,
    "PREFERS_SCOPE": """
        CREATE REL TABLE IF NOT EXISTS PREFERS_SCOPE (
            FROM Agent TO Scope,
            required BOOLEAN,
            priority INT64
        )
    """
}


def initialize_schema(conn: kuzu.Connection) -> None:
    """Initialize the knowledge graph schema.

    Creates all node and relationship tables if they do not exist.
    This function is idempotent and safe to call multiple times.

    Args:
        conn: Active Kuzu database connection.

    Raises:
        kuzu.Error: If schema creation fails due to database issues.
    """
    # Create node tables first (relationships depend on them)
    for table_name, ddl in NODE_SCHEMAS.items():
        try:
            conn.execute(ddl)
        except kuzu.Error as e:
            # Ignore "table already exists" errors for idempotency
            error_msg = str(e).lower()
            if "already exists" not in error_msg and "duplicate" not in error_msg:
                raise

    # Create relationship tables
    for table_name, ddl in EDGE_SCHEMAS.items():
        try:
            conn.execute(ddl)
        except kuzu.Error as e:
            error_msg = str(e).lower()
            if "already exists" not in error_msg and "duplicate" not in error_msg:
                raise


def get_schema_version() -> str:
    """Return the current schema version.

    Returns:
        Schema version string in semver format.
    """
    return SCHEMA_VERSION


def get_node_tables() -> list[str]:
    """Return list of all node table names.

    Returns:
        List of node table names defined in the schema.
    """
    return list(NODE_SCHEMAS.keys())


def get_edge_tables() -> list[str]:
    """Return list of all edge table names.

    Returns:
        List of edge/relationship table names defined in the schema.
    """
    return list(EDGE_SCHEMAS.keys())
