"""
Graph integration for AgentOS.

Connects AgentOS components with the Kuzu knowledge graph for
persistent storage, querying, and relationship tracking.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from pathlib import Path


@dataclass
class GraphConfig:
    """Configuration for graph integration."""
    db_path: Optional[str] = None
    auto_sync: bool = True
    sync_interval_seconds: float = 30.0


class AgentOSGraphBridge:
    """
    Bridge between AgentOS and the knowledge graph.
    
    Provides:
    - Agent state persistence
    - Task history storage
    - Skill/tool relationship tracking
    - Memory integration
    """
    
    def __init__(self, config: Optional[GraphConfig] = None) -> None:
        self._config = config or GraphConfig()
        self._graph = None
        self._initialized = False
    
    def initialize(self) -> bool:
        """Initialize graph connection."""
        try:
            from dmm.graph import KuzuMemoryGraph
            from dmm.core.constants import get_memory_root
            
            db_path = self._config.db_path or str(get_memory_root() / "graph_db")
            self._graph = KuzuMemoryGraph(db_path)
            self._initialized = True
            return True
        except Exception:
            return False
    
    @property
    def is_connected(self) -> bool:
        return self._initialized and self._graph is not None
    
    # -------------------------------------------------------------------------
    # Agent Operations
    # -------------------------------------------------------------------------
    
    def save_agent(self, agent_id: str, name: str, capabilities: list[str], metadata: dict[str, Any]) -> bool:
        """Save agent to graph."""
        if not self.is_connected:
            return False
        
        try:
            props = {
                "agent_id": agent_id,
                "name": name,
                "capabilities": ",".join(capabilities),
                "created_at": datetime.utcnow().isoformat(),
                **{k: str(v) for k, v in metadata.items()},
            }
            self._graph.add_memory(
                memory_id=f"agent:{agent_id}",
                content=f"Agent: {name}",
                memory_type="agent",
                tags=["agent"] + capabilities[:5],
                extra_props=props,
            )
            return True
        except Exception:
            return False
    
    def get_agent(self, agent_id: str) -> Optional[dict[str, Any]]:
        """Get agent from graph."""
        if not self.is_connected:
            return None
        
        try:
            results = self._graph.query_memories(
                query=f"agent:{agent_id}",
                memory_type="agent",
                limit=1,
            )
            return results[0] if results else None
        except Exception:
            return None
    
    def list_agents(self) -> list[dict[str, Any]]:
        """List all agents from graph."""
        if not self.is_connected:
            return []
        
        try:
            return self._graph.query_memories(
                query="",
                memory_type="agent",
                limit=100,
            )
        except Exception:
            return []
    
    # -------------------------------------------------------------------------
    # Task Operations
    # -------------------------------------------------------------------------
    
    def save_task(self, task_id: str, name: str, status: str, agent_id: Optional[str], metadata: dict[str, Any]) -> bool:
        """Save task to graph."""
        if not self.is_connected:
            return False
        
        try:
            props = {
                "task_id": task_id,
                "name": name,
                "status": status,
                "assigned_agent": agent_id or "",
                "updated_at": datetime.utcnow().isoformat(),
                **{k: str(v) for k, v in metadata.items()},
            }
            self._graph.add_memory(
                memory_id=f"task:{task_id}",
                content=f"Task: {name} ({status})",
                memory_type="task",
                tags=["task", status],
                extra_props=props,
            )
            
            # Create relationship to agent if assigned
            if agent_id:
                self._graph.add_relationship(
                    source_id=f"task:{task_id}",
                    target_id=f"agent:{agent_id}",
                    rel_type="ASSIGNED_TO",
                )
            
            return True
        except Exception:
            return False
    
    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        """Get task from graph."""
        if not self.is_connected:
            return None
        
        try:
            results = self._graph.query_memories(
                query=f"task:{task_id}",
                memory_type="task",
                limit=1,
            )
            return results[0] if results else None
        except Exception:
            return None
    
    def get_agent_tasks(self, agent_id: str) -> list[dict[str, Any]]:
        """Get tasks assigned to an agent."""
        if not self.is_connected:
            return []
        
        try:
            return self._graph.get_related_memories(
                memory_id=f"agent:{agent_id}",
                rel_type="ASSIGNED_TO",
                direction="incoming",
            )
        except Exception:
            return []
    
    # -------------------------------------------------------------------------
    # Skill Operations
    # -------------------------------------------------------------------------
    
    def save_skill(self, skill_id: str, name: str, description: str, version: str) -> bool:
        """Save skill to graph."""
        if not self.is_connected:
            return False
        
        try:
            self._graph.add_memory(
                memory_id=f"skill:{skill_id}",
                content=f"Skill: {name} - {description}",
                memory_type="skill",
                tags=["skill", version],
                extra_props={"skill_id": skill_id, "name": name, "version": version},
            )
            return True
        except Exception:
            return False
    
    def link_agent_skill(self, agent_id: str, skill_id: str) -> bool:
        """Link agent to skill."""
        if not self.is_connected:
            return False
        
        try:
            self._graph.add_relationship(
                source_id=f"agent:{agent_id}",
                target_id=f"skill:{skill_id}",
                rel_type="HAS_SKILL",
            )
            return True
        except Exception:
            return False
    
    def get_agent_skills(self, agent_id: str) -> list[dict[str, Any]]:
        """Get skills for an agent."""
        if not self.is_connected:
            return []
        
        try:
            return self._graph.get_related_memories(
                memory_id=f"agent:{agent_id}",
                rel_type="HAS_SKILL",
                direction="outgoing",
            )
        except Exception:
            return []
    
    # -------------------------------------------------------------------------
    # Memory Integration
    # -------------------------------------------------------------------------
    
    def link_task_memory(self, task_id: str, memory_id: str, rel_type: str = "USES") -> bool:
        """Link task to a memory."""
        if not self.is_connected:
            return False
        
        try:
            self._graph.add_relationship(
                source_id=f"task:{task_id}",
                target_id=memory_id,
                rel_type=rel_type,
            )
            return True
        except Exception:
            return False
    
    def get_task_memories(self, task_id: str) -> list[dict[str, Any]]:
        """Get memories related to a task."""
        if not self.is_connected:
            return []
        
        try:
            return self._graph.get_related_memories(
                memory_id=f"task:{task_id}",
                direction="outgoing",
            )
        except Exception:
            return []
    
    # -------------------------------------------------------------------------
    # Query Operations
    # -------------------------------------------------------------------------
    
    def search(self, query: str, memory_type: Optional[str] = None, limit: int = 20) -> list[dict[str, Any]]:
        """Search across AgentOS entities."""
        if not self.is_connected:
            return []
        
        try:
            return self._graph.query_memories(
                query=query,
                memory_type=memory_type,
                limit=limit,
            )
        except Exception:
            return []
    
    def get_stats(self) -> dict[str, Any]:
        """Get graph statistics."""
        if not self.is_connected:
            return {"connected": False}
        
        try:
            stats = self._graph.get_stats()
            stats["connected"] = True
            return stats
        except Exception:
            return {"connected": True, "error": "Failed to get stats"}
    
    # -------------------------------------------------------------------------
    # Sync Operations
    # -------------------------------------------------------------------------
    
    def sync_agent_registry(self, registry) -> int:
        """Sync agents from registry to graph."""
        if not self.is_connected:
            return 0
        
        count = 0
        for agent_data in registry.list_agents():
            if self.save_agent(
                agent_id=agent_data["id"],
                name=agent_data.get("name", ""),
                capabilities=agent_data.get("capabilities", []),
                metadata=agent_data,
            ):
                count += 1
        return count
    
    def sync_task_store(self, store) -> int:
        """Sync tasks from store to graph."""
        if not self.is_connected:
            return 0
        
        count = 0
        for task in store.list_tasks(limit=1000):
            if self.save_task(
                task_id=task.id,
                name=task.name,
                status=task.status.value,
                agent_id=task.assigned_agent,
                metadata={"priority": task.priority.value},
            ):
                count += 1
        return count
