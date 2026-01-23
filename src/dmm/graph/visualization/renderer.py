"""
Graph visualization renderer.

Renders the knowledge graph in multiple output formats for
visualization and documentation purposes.

Output Formats:
- HTML: Interactive D3.js force-directed graph
- JSON: Raw graph data for custom visualization
- DOT: Graphviz format for static diagrams
- Mermaid: Mermaid syntax for markdown documentation

Features:
- Configurable node and edge styling
- Filtering by scope, edge type, or memory ID
- Cluster highlighting
- Layout hints for DOT format
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from dmm.graph.inference.cluster import MemoryCluster


logger = logging.getLogger(__name__)


# Edge type to color mapping
EDGE_COLORS = {
    "RELATES_TO": "#6c757d",
    "SUPPORTS": "#28a745",
    "CONTRADICTS": "#dc3545",
    "DEPENDS_ON": "#007bff",
    "SUPERSEDES": "#fd7e14",
}

# Scope to node color mapping
SCOPE_COLORS = {
    "baseline": "#6f42c1",
    "global": "#20c997",
    "project": "#17a2b8",
    "ephemeral": "#ffc107",
    "agent": "#e83e8c",
}


@dataclass(frozen=True)
class RenderConfig:
    """
    Configuration for graph rendering.
    
    Attributes:
        output_format: Output format (html, json, dot, mermaid)
        include_edge_labels: Show edge type labels
        include_weights: Show edge weights
        color_by_scope: Color nodes by scope
        color_edges_by_type: Color edges by relationship type
        highlight_clusters: Highlight cluster membership
        max_label_length: Maximum node label length
        node_size_by_priority: Scale node size by priority
        layout_direction: Direction for DOT (TB, LR, BT, RL)
        filter_scopes: Only include these scopes
        filter_edge_types: Only include these edge types
        filter_memory_ids: Only include these memories
        html_width: Width for HTML output
        html_height: Height for HTML output
    """
    
    output_format: str = "html"
    include_edge_labels: bool = True
    include_weights: bool = True
    color_by_scope: bool = True
    color_edges_by_type: bool = True
    highlight_clusters: bool = False
    max_label_length: int = 30
    node_size_by_priority: bool = True
    layout_direction: str = "TB"
    filter_scopes: tuple[str, ...] | None = None
    filter_edge_types: tuple[str, ...] | None = None
    filter_memory_ids: tuple[str, ...] | None = None
    html_width: int = 1200
    html_height: int = 800


@dataclass
class RenderResult:
    """
    Result of graph rendering.
    
    Attributes:
        content: Rendered output string
        format: Output format used
        node_count: Number of nodes rendered
        edge_count: Number of edges rendered
        warnings: Any warnings during rendering
    """
    
    content: str = ""
    format: str = "html"
    node_count: int = 0
    edge_count: int = 0
    warnings: list[str] = field(default_factory=list)
    
    def save(self, path: str) -> None:
        """Save rendered content to file."""
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.content)


class GraphRenderer:
    """
    Renders knowledge graph visualizations.
    
    The renderer extracts graph data and formats it for various
    visualization tools. It supports filtering and styling options.
    
    Example:
        renderer = GraphRenderer(graph_store, config)
        result = renderer.render()
        result.save("graph.html")
    """
    
    def __init__(
        self,
        graph_store: Any,
        config: RenderConfig | None = None,
    ) -> None:
        """
        Initialize the renderer.
        
        Args:
            graph_store: Knowledge graph store
            config: Render configuration
        """
        self._graph = graph_store
        self._config = config or RenderConfig()
        self._clusters: list[MemoryCluster] = []
    
    @property
    def config(self) -> RenderConfig:
        """Return current configuration."""
        return self._config
    
    def set_clusters(self, clusters: list[MemoryCluster]) -> None:
        """Set cluster data for highlighting."""
        self._clusters = clusters
    
    def render(
        self,
        config: RenderConfig | None = None,
    ) -> RenderResult:
        """
        Render the graph in the configured format.
        
        Args:
            config: Optional override configuration
            
        Returns:
            RenderResult with formatted output
        """
        cfg = config or self._config
        
        nodes, edges = self._extract_graph_data(cfg)
        
        if cfg.output_format == "json":
            return self._render_json(nodes, edges, cfg)
        elif cfg.output_format == "dot":
            return self._render_dot(nodes, edges, cfg)
        elif cfg.output_format == "mermaid":
            return self._render_mermaid(nodes, edges, cfg)
        else:
            return self._render_html(nodes, edges, cfg)
    
    def _extract_graph_data(
        self,
        config: RenderConfig,
    ) -> tuple[list[dict], list[dict]]:
        """
        Extract nodes and edges from graph store.
        
        Args:
            config: Render configuration
            
        Returns:
            Tuple of (nodes list, edges list)
        """
        nodes: list[dict] = []
        edges: list[dict] = []
        
        try:
            memories = self._graph.get_all_memory_nodes()
        except Exception as e:
            logger.error(f"Failed to get memories: {e}")
            return nodes, edges
        
        cluster_map: dict[str, str] = {}
        if config.highlight_clusters and self._clusters:
            for cluster in self._clusters:
                for mid in cluster.memory_ids:
                    cluster_map[mid] = cluster.cluster_id
        
        included_ids: set[str] = set()
        
        for memory in memories:
            mid = memory.id if hasattr(memory, "id") else str(memory)
            
            if config.filter_memory_ids and mid not in config.filter_memory_ids:
                continue
            
            scope = getattr(memory, "scope", "global")
            if config.filter_scopes and scope not in config.filter_scopes:
                continue
            
            title = getattr(memory, "title", mid)
            if len(title) > config.max_label_length:
                title = title[:config.max_label_length - 3] + "..."
            
            priority = getattr(memory, "priority", 0.5)
            tags = getattr(memory, "tags", []) or []
            
            node = {
                "id": mid,
                "label": title,
                "scope": scope,
                "priority": priority,
                "tags": tags,
                "color": SCOPE_COLORS.get(scope, "#6c757d") if config.color_by_scope else "#6c757d",
                "size": 10 + (priority * 20) if config.node_size_by_priority else 15,
            }
            
            if mid in cluster_map:
                node["cluster"] = cluster_map[mid]
            
            nodes.append(node)
            included_ids.add(mid)
        
        edge_types = ["RELATES_TO", "SUPPORTS", "CONTRADICTS", "DEPENDS_ON", "SUPERSEDES"]
        if config.filter_edge_types:
            edge_types = [et for et in edge_types if et in config.filter_edge_types]
        
        seen_edges: set[tuple[str, str, str]] = set()
        
        for mid in included_ids:
            for edge_type in edge_types:
                try:
                    graph_edges = self._graph.get_edges_from(mid, edge_type)
                    for edge in graph_edges:
                        target = edge.get("to_id", edge.get("target_id", ""))
                        
                        if target not in included_ids:
                            continue
                        
                        edge_key = (mid, target, edge_type)
                        if edge_key in seen_edges:
                            continue
                        seen_edges.add(edge_key)
                        
                        weight = edge.get("weight", edge.get("strength", 0.5))
                        
                        edges.append({
                            "source": mid,
                            "target": target,
                            "type": edge_type,
                            "weight": weight,
                            "color": EDGE_COLORS.get(edge_type, "#6c757d") if config.color_edges_by_type else "#6c757d",
                        })
                except Exception as e:
                    logger.debug(f"Failed to get edges for {mid}: {e}")
        
        return nodes, edges
    
    def _render_html(
        self,
        nodes: list[dict],
        edges: list[dict],
        config: RenderConfig,
    ) -> RenderResult:
        """Render as interactive HTML with D3.js."""
        
        nodes_json = json.dumps(nodes)
        edges_json = json.dumps(edges)
        
        html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>DMM Knowledge Graph</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        body {{ margin: 0; font-family: sans-serif; }}
        #graph {{ width: {config.html_width}px; height: {config.html_height}px; border: 1px solid #ccc; }}
        .node {{ cursor: pointer; }}
        .node text {{ font-size: 10px; pointer-events: none; }}
        .link {{ stroke-opacity: 0.6; }}
        .link-label {{ font-size: 8px; fill: #666; }}
        #info {{ padding: 10px; background: #f5f5f5; }}
        #legend {{ padding: 10px; display: flex; gap: 20px; flex-wrap: wrap; }}
        .legend-item {{ display: flex; align-items: center; gap: 5px; }}
        .legend-color {{ width: 15px; height: 15px; border-radius: 3px; }}
    </style>
</head>
<body>
    <div id="info">
        <strong>DMM Knowledge Graph</strong> | 
        Nodes: {len(nodes)} | Edges: {len(edges)} |
        Generated: {datetime.now(timezone.utc).isoformat()}Z
    </div>
    <div id="legend">
        <strong>Scopes:</strong>
        {"".join(f'<span class="legend-item"><span class="legend-color" style="background:{c}"></span>{s}</span>' for s, c in SCOPE_COLORS.items())}
        <strong style="margin-left:20px">Edges:</strong>
        {"".join(f'<span class="legend-item"><span class="legend-color" style="background:{c}"></span>{e}</span>' for e, c in EDGE_COLORS.items())}
    </div>
    <svg id="graph"></svg>
    <script>
        const nodes = {nodes_json};
        const links = {edges_json};
        
        const width = {config.html_width};
        const height = {config.html_height};
        
        const svg = d3.select("#graph")
            .attr("width", width)
            .attr("height", height);
        
        const simulation = d3.forceSimulation(nodes)
            .force("link", d3.forceLink(links).id(d => d.id).distance(100))
            .force("charge", d3.forceManyBody().strength(-200))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collision", d3.forceCollide().radius(30));
        
        const link = svg.append("g")
            .selectAll("line")
            .data(links)
            .join("line")
            .attr("class", "link")
            .attr("stroke", d => d.color)
            .attr("stroke-width", d => 1 + d.weight * 2);
        
        const linkLabels = svg.append("g")
            .selectAll("text")
            .data(links)
            .join("text")
            .attr("class", "link-label")
            .text(d => {"'"}{"" if not config.include_edge_labels else "d.type"}{"'"});
        
        const node = svg.append("g")
            .selectAll("g")
            .data(nodes)
            .join("g")
            .attr("class", "node")
            .call(d3.drag()
                .on("start", dragstarted)
                .on("drag", dragged)
                .on("end", dragended));
        
        node.append("circle")
            .attr("r", d => d.size)
            .attr("fill", d => d.color);
        
        node.append("text")
            .attr("dx", 12)
            .attr("dy", 4)
            .text(d => d.label);
        
        node.append("title")
            .text(d => `${{d.id}}\\nScope: ${{d.scope}}\\nPriority: ${{d.priority.toFixed(2)}}\\nTags: ${{d.tags.join(", ")}}`);
        
        simulation.on("tick", () => {{
            link
                .attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);
            
            linkLabels
                .attr("x", d => (d.source.x + d.target.x) / 2)
                .attr("y", d => (d.source.y + d.target.y) / 2);
            
            node.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
        }});
        
        function dragstarted(event) {{
            if (!event.active) simulation.alphaTarget(0.3).restart();
            event.subject.fx = event.subject.x;
            event.subject.fy = event.subject.y;
        }}
        
        function dragged(event) {{
            event.subject.fx = event.x;
            event.subject.fy = event.y;
        }}
        
        function dragended(event) {{
            if (!event.active) simulation.alphaTarget(0);
            event.subject.fx = null;
            event.subject.fy = null;
        }}
    </script>
</body>
</html>'''
        
        return RenderResult(
            content=html,
            format="html",
            node_count=len(nodes),
            edge_count=len(edges),
        )
    
    def _render_json(
        self,
        nodes: list[dict],
        edges: list[dict],
        config: RenderConfig,
    ) -> RenderResult:
        """Render as JSON data."""
        
        data = {
            "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": nodes,
            "edges": edges,
        }
        
        if self._clusters:
            data["clusters"] = [c.to_dict() for c in self._clusters]
        
        return RenderResult(
            content=json.dumps(data, indent=2),
            format="json",
            node_count=len(nodes),
            edge_count=len(edges),
        )
    
    def _render_dot(
        self,
        nodes: list[dict],
        edges: list[dict],
        config: RenderConfig,
    ) -> RenderResult:
        """Render as Graphviz DOT format."""
        
        lines = [
            f'digraph KnowledgeGraph {{',
            f'    rankdir={config.layout_direction};',
            f'    node [shape=box, style=filled];',
            '',
        ]
        
        for node in nodes:
            color = node.get("color", "#6c757d")
            label = node.get("label", node["id"]).replace('"', '\\"')
            lines.append(f'    "{node["id"]}" [label="{label}", fillcolor="{color}"];')
        
        lines.append('')
        
        for edge in edges:
            color = edge.get("color", "#6c757d")
            label = edge.get("type", "") if config.include_edge_labels else ""
            weight_str = f" ({edge.get('weight', 0.5):.2f})" if config.include_weights else ""
            
            edge_label = f'{label}{weight_str}' if label or weight_str else ""
            label_attr = f', label="{edge_label}"' if edge_label else ""
            
            lines.append(
                f'    "{edge["source"]}" -> "{edge["target"]}" '
                f'[color="{color}"{label_attr}];'
            )
        
        lines.append('}')
        
        return RenderResult(
            content='\n'.join(lines),
            format="dot",
            node_count=len(nodes),
            edge_count=len(edges),
        )
    
    def _render_mermaid(
        self,
        nodes: list[dict],
        edges: list[dict],
        config: RenderConfig,
    ) -> RenderResult:
        """Render as Mermaid diagram syntax."""
        
        direction = {"TB": "TD", "LR": "LR", "BT": "BU", "RL": "RL"}.get(
            config.layout_direction, "TD"
        )
        
        lines = [f'graph {direction}']
        
        for node in nodes:
            label = node.get("label", node["id"]).replace('"', "'")
            node_id = node["id"].replace("-", "_").replace(".", "_")
            lines.append(f'    {node_id}["{label}"]')
        
        edge_styles = {
            "RELATES_TO": "---",
            "SUPPORTS": "-->",
            "CONTRADICTS": "-.->",
            "DEPENDS_ON": "==>",
            "SUPERSEDES": "-->>",
        }
        
        for edge in edges:
            source = edge["source"].replace("-", "_").replace(".", "_")
            target = edge["target"].replace("-", "_").replace(".", "_")
            style = edge_styles.get(edge.get("type", ""), "-->")
            
            if config.include_edge_labels:
                label = edge.get("type", "")
                if config.include_weights:
                    label += f" {edge.get('weight', 0.5):.1f}"
                lines.append(f'    {source} {style}|{label}| {target}')
            else:
                lines.append(f'    {source} {style} {target}')
        
        return RenderResult(
            content='\n'.join(lines),
            format="mermaid",
            node_count=len(nodes),
            edge_count=len(edges),
        )
