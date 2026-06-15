"""Project Postgres records into the graph (ARCHITECTURE.md §3).

This is the logic the production **outbox → Celery → Neo4j upsert** sync runs on
each domain event. For dev/tests we run it on demand to populate an
:class:`~sgc.intelligence.graph.InMemoryGraphStore` from the current Postgres
state. Only nodes/edges derivable from existing FKs are projected.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.devices import Device
from ..models.enums import (
    BatchStatus,
    DeviceState,
    QualityState,
    Severity,
    StatusToken,
)
from ..models.manufacturing import Batch, Line, Site, Supplier
from ..models.quality import Deviation
from ..models.telemetry import ColdchainLane, Excursion, Shipment
from .graph import GraphEdge, GraphNode, GraphStore

# --- status mappers: domain enums → StatusToken value ----------------------

_BATCH_STATUS = {
    BatchStatus.released: "pass",
    BatchStatus.rejected: "fail",
    BatchStatus.quarantine: "fail",
    BatchStatus.hold: "warn",
    BatchStatus.inspection: "warn",
    BatchStatus.in_process: "info",
}
_DEVIATION_STATE = {
    QualityState.escalated: "fail",
    QualityState.quarantine: "fail",
    QualityState.review: "warn",
    QualityState.watch: "warn",
    QualityState.verified: "pass",
    QualityState.compliant: "pass",
}
_DEVICE_STATE = {
    DeviceState.quarantined: "fail",
    DeviceState.offline: "warn",
    DeviceState.online: "pass",
    DeviceState.transmitting: "pass",
    DeviceState.provisioned: "info",
    DeviceState.decommissioned: "neutral",
}
_SEVERITY = {Severity.critical: "fail", Severity.major: "fail", Severity.minor: "warn"}


def _token(value) -> str:
    return value.value if isinstance(value, StatusToken) else str(value)


async def project_from_postgres(session: AsyncSession, store: GraphStore) -> None:
    """Upsert nodes and edges into ``store`` from current Postgres state."""
    # Index helpers to resolve UUID FKs to business-key node ids.
    site_ids: dict = {}
    line_ids: dict = {}
    batch_ids: dict = {}
    lane_ids: dict = {}
    shipment_ids: dict = {}

    for supplier in (await session.execute(select(Supplier))).scalars():
        await store.upsert_node(GraphNode(
            id=str(supplier.id), label=supplier.name, category="supply",
            status=_token(supplier.status), type="Supplier"))

    for site in (await session.execute(select(Site))).scalars():
        site_ids[site.id] = str(site.id)
        await store.upsert_node(GraphNode(
            id=str(site.id), label=site.name, category="mfg",
            status="neutral", type="Site"))

    for line in (await session.execute(select(Line))).scalars():
        line_ids[line.id] = str(line.id)
        await store.upsert_node(GraphNode(
            id=str(line.id), label=line.name, category="mfg",
            status=_token(line.status), type="Line"))
        if line.site_id in site_ids:
            await store.upsert_edge(GraphEdge(site_ids[line.site_id], str(line.id), "RUNS"))

    for batch in (await session.execute(select(Batch))).scalars():
        batch_ids[batch.id] = batch.code
        await store.upsert_node(GraphNode(
            id=batch.code, label=batch.code, category="mfg",
            status=_BATCH_STATUS.get(batch.status, "neutral"), type="Batch"))
        if batch.line_id in line_ids:
            await store.upsert_edge(GraphEdge(line_ids[batch.line_id], batch.code, "PRODUCES"))

    for dev in (await session.execute(select(Deviation))).scalars():
        await store.upsert_node(GraphNode(
            id=dev.code, label=dev.title or dev.code, category="quality",
            status=_DEVIATION_STATE.get(dev.state, "neutral"), type="Deviation"))
        if dev.batch_id in batch_ids:
            await store.upsert_edge(GraphEdge(batch_ids[dev.batch_id], dev.code, "HAS_DEVIATION"))

    for device in (await session.execute(select(Device))).scalars():
        await store.upsert_node(GraphNode(
            id=device.serial, label=device.serial, category="compliance",
            status=_DEVICE_STATE.get(device.state, "neutral"), type="Device"))
        if device.line_id in line_ids:
            await store.upsert_edge(GraphEdge(device.serial, line_ids[device.line_id], "MONITORS"))

    for lane in (await session.execute(select(ColdchainLane))).scalars():
        lane_ids[lane.id] = lane.code
        await store.upsert_node(GraphNode(
            id=lane.code, label=lane.code, category="supply",
            status=_token(lane.status), type="Lane"))

    for shipment in (await session.execute(select(Shipment))).scalars():
        sid = str(shipment.id)
        shipment_ids[shipment.id] = sid
        await store.upsert_node(GraphNode(
            id=sid, label=f"Shipment {sid[:8]}", category="supply",
            status="neutral", type="Shipment"))
        if shipment.lane_id in lane_ids:
            await store.upsert_edge(GraphEdge(sid, lane_ids[shipment.lane_id], "DISTRIBUTED_VIA"))
        if shipment.batch_id in batch_ids:
            await store.upsert_edge(GraphEdge(sid, batch_ids[shipment.batch_id], "CARRIES"))

    for exc in (await session.execute(select(Excursion))).scalars():
        eid = str(exc.id)
        await store.upsert_node(GraphNode(
            id=eid, label=exc.kind or "excursion", category="quality",
            status=_SEVERITY.get(exc.severity, "warn"), type="Excursion"))
        if exc.shipment_id in shipment_ids:
            await store.upsert_edge(GraphEdge(eid, shipment_ids[exc.shipment_id], "AFFECTS"))
