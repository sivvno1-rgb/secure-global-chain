"""Graph model + store seam for the Intelligence context.

Postgres is the system of record; the graph is the relationship/traversal layer
(ARCHITECTURE.md §3). Nodes are thin — ``{ id, label, category, status }`` plus a
type — and full records are resolved from Postgres by ``id`` (DOMAIN_MODEL.md
§Intelligence).

The :class:`GraphStore` protocol is the seam. :class:`InMemoryGraphStore` backs
dev/tests (populated by :mod:`sgc.intelligence.projector`); a Neo4j/Cypher
adapter (see :mod:`sgc.intelligence.neo4j_store`) plugs in for production.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Protocol

# Node categories used by the Systems Map filter.
CATEGORIES = ("supply", "mfg", "quality", "compliance")


@dataclass(frozen=True)
class GraphNode:
    id: str  # shared business key (e.g. "TRM-2291", "DEV-1182")
    label: str
    category: str  # one of CATEGORIES
    status: str  # StatusToken value: pass|warn|fail|info|neutral
    type: str  # Supplier|Site|Line|Batch|Deviation|Device|Lane|Shipment|Excursion


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    rel: str  # SUPPLIES|RUNS|PRODUCES|HAS_DEVIATION|MONITORS|DISTRIBUTED_VIA|AFFECTS|CARRIES


@dataclass
class GraphView:
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)


@dataclass
class NodeDetail:
    node: GraphNode
    connection_count: int
    signal: str


class GraphStore(Protocol):
    async def upsert_node(self, node: GraphNode) -> None: ...
    async def upsert_edge(self, edge: GraphEdge) -> None: ...
    async def graph(self, *, category: str | None = None) -> GraphView: ...
    async def node(self, node_id: str) -> NodeDetail | None: ...
    async def trace(self, node_id: str) -> GraphView: ...
    async def impact(self, node_id: str) -> GraphView: ...
    async def signals(self) -> list[GraphNode]: ...


# StatusToken ranking for the signal feed (most urgent first).
_STATUS_RANK = {"fail": 0, "warn": 1, "info": 2, "pass": 3, "neutral": 4}


class InMemoryGraphStore:
    """Adjacency-list graph store. Async methods match the future Neo4j adapter."""

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._out: dict[str, list[GraphEdge]] = {}
        self._in: dict[str, list[GraphEdge]] = {}
        self._edges: list[GraphEdge] = []

    async def upsert_node(self, node: GraphNode) -> None:
        self._nodes[node.id] = node

    async def upsert_edge(self, edge: GraphEdge) -> None:
        # Only connect nodes that exist; ignore dangling references.
        if edge.source not in self._nodes or edge.target not in self._nodes:
            return
        self._edges.append(edge)
        self._out.setdefault(edge.source, []).append(edge)
        self._in.setdefault(edge.target, []).append(edge)

    async def graph(self, *, category: str | None = None) -> GraphView:
        if category is None:
            nodes = list(self._nodes.values())
            return GraphView(nodes=nodes, edges=list(self._edges))
        keep = {n.id for n in self._nodes.values() if n.category == category}
        nodes = [self._nodes[i] for i in keep]
        edges = [e for e in self._edges if e.source in keep and e.target in keep]
        return GraphView(nodes=nodes, edges=edges)

    async def node(self, node_id: str) -> NodeDetail | None:
        node = self._nodes.get(node_id)
        if node is None:
            return None
        degree = len(self._out.get(node_id, [])) + len(self._in.get(node_id, []))
        return NodeDetail(node=node, connection_count=degree, signal=node.status)

    async def trace(self, node_id: str) -> GraphView:
        """End-to-end chain of custody: the connected component (both directions)."""
        if node_id not in self._nodes:
            return GraphView()
        seen: set[str] = set()
        edges: list[GraphEdge] = []
        queue: deque[str] = deque([node_id])
        while queue:
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            for edge in self._out.get(current, []):
                edges.append(edge)
                queue.append(edge.target)
            for edge in self._in.get(current, []):
                queue.append(edge.source)
        nodes = [self._nodes[i] for i in seen]
        chain_edges = [e for e in self._edges if e.source in seen and e.target in seen]
        return GraphView(nodes=nodes, edges=chain_edges)

    async def impact(self, node_id: str) -> GraphView:
        """Blast radius: nodes reachable downstream (following outgoing edges)."""
        if node_id not in self._nodes:
            return GraphView()
        seen: set[str] = {node_id}
        queue: deque[str] = deque([node_id])
        edges: list[GraphEdge] = []
        while queue:
            current = queue.popleft()
            for edge in self._out.get(current, []):
                edges.append(edge)
                if edge.target not in seen:
                    seen.add(edge.target)
                    queue.append(edge.target)
        # Exclude the origin node from the affected set; keep traversed edges.
        nodes = [self._nodes[i] for i in seen if i != node_id]
        return GraphView(nodes=nodes, edges=edges)

    async def signals(self) -> list[GraphNode]:
        active = [n for n in self._nodes.values() if n.status in ("fail", "warn", "pass")]
        return sorted(active, key=lambda n: (_STATUS_RANK.get(n.status, 9), n.id))
