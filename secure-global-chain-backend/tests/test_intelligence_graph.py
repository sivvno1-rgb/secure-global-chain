"""GraphStore traversals + the Postgres→graph projector."""

from __future__ import annotations

import pytest

from sgc.intelligence.graph import GraphEdge, GraphNode, InMemoryGraphStore
from sgc.intelligence.projector import project_from_postgres


def _n(id, type="X", category="mfg", status="neutral"):
    return GraphNode(id=id, label=id, category=category, status=status, type=type)


@pytest.mark.asyncio
async def test_inmemory_trace_and_impact():
    store = InMemoryGraphStore()
    for nid, cat, st in [("L", "mfg", "warn"), ("B", "mfg", "warn"),
                         ("D", "quality", "fail"), ("S", "supply", "neutral")]:
        await store.upsert_node(_n(nid, category=cat, status=st))
    await store.upsert_edge(GraphEdge("L", "B", "PRODUCES"))
    await store.upsert_edge(GraphEdge("B", "D", "HAS_DEVIATION"))
    await store.upsert_edge(GraphEdge("S", "B", "CARRIES"))

    # impact of L = everything downstream: B and D (not S, not L itself)
    impact = await store.impact("L")
    assert {n.id for n in impact.nodes} == {"B", "D"}

    # trace of B = whole connected component
    trace = await store.trace("B")
    assert {n.id for n in trace.nodes} == {"L", "B", "D", "S"}

    # node detail degree
    detail = await store.node("B")
    assert detail.connection_count == 3  # in: L,S ; out: D

    # dangling edges are ignored
    await store.upsert_edge(GraphEdge("B", "GHOST", "X"))
    assert (await store.node("B")).connection_count == 3


@pytest.mark.asyncio
async def test_signals_filter_and_order():
    store = InMemoryGraphStore()
    await store.upsert_node(_n("a", status="pass"))
    await store.upsert_node(_n("b", status="fail"))
    await store.upsert_node(_n("c", status="neutral"))
    await store.upsert_node(_n("d", status="warn"))
    signals = await store.signals()
    assert [n.status for n in signals] == ["fail", "warn", "pass"]
    assert all(n.status != "neutral" for n in signals)


@pytest.mark.asyncio
async def test_projector_builds_graph_from_postgres(db_session):
    import sgc.models as models
    from sgc.models.enums import (
        BatchStatus,
        DeviceState,
        QualityState,
        Severity,
        StatusToken,
    )

    site = models.Site(name="Site")
    db_session.add(site)
    await db_session.flush()
    line = models.Line(site_id=site.id, name="Line B", status=StatusToken.warn)
    db_session.add(line)
    await db_session.flush()
    batch = models.Batch(code="TRM-2291", line_id=line.id, status=BatchStatus.released)
    db_session.add(batch)
    await db_session.flush()
    dev = models.Deviation(code="DEV-1", title="d", severity=Severity.major,
                           batch_id=batch.id, state=QualityState.escalated)
    db_session.add(dev)
    await db_session.commit()

    store = InMemoryGraphStore()
    await project_from_postgres(db_session, store)

    view = await store.graph()
    ids = {n.id for n in view.nodes}
    assert {"TRM-2291", "DEV-1", str(line.id), str(site.id)} <= ids
    # released batch projects to a "pass" status
    batch_node = next(n for n in view.nodes if n.id == "TRM-2291")
    assert batch_node.status == "pass"
    # escalated deviation projects to "fail"
    dev_node = next(n for n in view.nodes if n.id == "DEV-1")
    assert dev_node.status == "fail"
    rels = {e.rel for e in view.edges}
    assert {"RUNS", "PRODUCES", "HAS_DEVIATION"} <= rels
