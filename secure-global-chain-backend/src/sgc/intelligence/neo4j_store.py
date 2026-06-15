"""Neo4j-backed :class:`GraphStore` (production target — not yet wired).

Skeleton showing the Cypher behind each operation. It is kept out of the default
wiring because there is no Neo4j server in this environment and the ``neo4j``
driver is not a runtime dependency yet. To enable: add ``neo4j`` to deps, run a
Neo4j service, point the outbox→Celery sync at it, and override the
``get_graph_store`` dependency to return this adapter.

The shared business ``id`` on every node is the join key back to Postgres
(ARCHITECTURE.md §3).
"""

from __future__ import annotations

from .graph import GraphEdge, GraphNode, GraphView, NodeDetail

# Cypher for the chain-of-custody / blast-radius traversals (reference).
TRACE_CYPHER = """
MATCH path = (start {id: $id})-[*0..]-(connected)
RETURN connected
"""

IMPACT_CYPHER = """
MATCH (start {id: $id})-[*1..]->(affected)
RETURN DISTINCT affected
"""

UPSERT_NODE_CYPHER = """
MERGE (n {id: $id})
SET n.label = $label, n.category = $category, n.status = $status, n.type = $type
"""


class Neo4jGraphStore:
    """Async Cypher implementation of the GraphStore seam (wire up later)."""

    def __init__(self, driver) -> None:  # neo4j.AsyncDriver
        self._driver = driver

    async def upsert_node(self, node: GraphNode) -> None:  # pragma: no cover
        raise NotImplementedError("Neo4j adapter is not wired in this environment")

    async def upsert_edge(self, edge: GraphEdge) -> None:  # pragma: no cover
        raise NotImplementedError("Neo4j adapter is not wired in this environment")

    async def graph(self, *, category: str | None = None) -> GraphView:  # pragma: no cover
        raise NotImplementedError("Neo4j adapter is not wired in this environment")

    async def node(self, node_id: str) -> NodeDetail | None:  # pragma: no cover
        raise NotImplementedError("Neo4j adapter is not wired in this environment")

    async def trace(self, node_id: str) -> GraphView:  # pragma: no cover
        raise NotImplementedError("Neo4j adapter is not wired in this environment")

    async def impact(self, node_id: str) -> GraphView:  # pragma: no cover
        raise NotImplementedError("Neo4j adapter is not wired in this environment")

    async def signals(self) -> list[GraphNode]:  # pragma: no cover
        raise NotImplementedError("Neo4j adapter is not wired in this environment")
