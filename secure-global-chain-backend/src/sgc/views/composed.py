"""Composed view-models for the remaining *live* §7 rows whose detailed JSON
contracts are not yet authored (FRONTEND_WIRING.md §7).

Each builder aggregates an existing context service and returns a small, stable
read-model. Per §7 every field is best-effort: a builder returns only the keys
it can compose from the system of record and omits the rest, so the frontend
keeps its demo data for anything not yet supplied. Reads only — no audit events.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents import service as agents_svc
from ..audit.chain import verify_chain
from ..devices import service as devices_svc
from ..intelligence.graph import InMemoryGraphStore
from ..intelligence.projector import project_from_postgres
from ..manufacturing import service as mfg_svc
from ..models.enums import AgentRunStatus
from ..models.manufacturing import Site
from ..models.optimization import Scenario, Schedule, ScheduleSlot
from ..models.research import EvidencePacket
from ..research import service as research_svc
from ..telemetry import service as telemetry_svc


async def _graph_store(session: AsyncSession) -> InMemoryGraphStore:
    """Project the current Postgres state into an in-memory graph (same seam the
    intelligence router uses via ``get_graph_store``)."""
    store = InMemoryGraphStore()
    await project_from_postgres(session, store)
    return store


def _node_dict(node) -> dict:
    return {"id": node.id, "label": node.label, "category": node.category,
            "status": node.status, "type": node.type}


# ==============================================================================
# operations · facility map  (live)
# ==============================================================================
async def build_ops_facility_map(session: AsyncSession, range_: str | None = None) -> dict:
    """Site + line health roll-up for the facility map."""
    sites = list((await session.execute(select(Site).order_by(Site.name))).scalars())
    lines = await mfg_svc.list_lines(session)
    by_site: dict = {}
    for ln in lines:
        by_site.setdefault(ln.site_id, []).append(ln)

    rows: list[dict] = []
    for site in sites:
        site_lines = by_site.get(site.id, [])
        line_rows = [{"name": ln.name, "status": ln.status.value,
                      "uptime": ln.uptime_pct} for ln in site_lines]
        # Site status is the worst of its lines.
        tones = {ln.status.value for ln in site_lines}
        status = "fail" if "fail" in tones else "warn" if "warn" in tones else "pass"
        rows.append({"name": site.name, "status": status, "lines": line_rows})
    return {"sites": rows} if rows else {}


# ==============================================================================
# intelligence (live)
# ==============================================================================
async def build_intel_globe(session: AsyncSession, range_: str | None = None) -> dict:
    """Sites, device footprint, and the ranked signal feed for the global map."""
    out: dict = {}
    sites = list((await session.execute(select(Site).order_by(Site.name))).scalars())
    if sites:
        out["sites"] = [{"name": s.name} for s in sites]
    devices, total = await devices_svc.list_devices(session, limit=500)
    if total:
        out["devices_total"] = total
    store = await _graph_store(session)
    signals = await store.signals()
    if signals:
        out["signals"] = [_node_dict(n) for n in signals]
    return out


async def build_intel_dependencies(session: AsyncSession, range_: str | None = None) -> dict:
    """Dependency graph (nodes + edges) — same projection as /intelligence/graph."""
    store = await _graph_store(session)
    view = await store.graph()
    if not view.nodes:
        return {}
    return {
        "nodes": [_node_dict(n) for n in view.nodes],
        "edges": [{"source": e.source, "target": e.target, "rel": e.rel} for e in view.edges],
    }


async def build_intel_hardware(session: AsyncSession, range_: str | None = None) -> dict:
    """Cold-chain hardware view: device fleet + lanes + open excursion count."""
    out: dict = {}
    devices, _ = await devices_svc.list_devices(session, limit=500)
    if devices:
        out["devices"] = [{
            "serial": d.serial,
            "state": d.state.value,
            "last_seen_at": d.last_seen_at,
            "firmware": d.firmware.version if d.firmware else None,
        } for d in devices]
    lanes = await telemetry_svc.list_lanes(session)
    if lanes:
        out["lanes"] = [{"code": ln.code, "status": ln.status.value} for ln in lanes]
    open_exc = await telemetry_svc.list_excursions(session, open_only=True)
    out["open_excursions"] = len(open_exc)
    return out


async def build_intel_evidence(session: AsyncSession, range_: str | None = None) -> dict:
    """Research evidence packets surfaced into the intelligence center."""
    return await _evidence_packets(session)


# ==============================================================================
# research (live)
# ==============================================================================
async def _evidence_packets(session: AsyncSession) -> dict:
    packets = list(
        (await session.execute(select(EvidencePacket).order_by(EvidencePacket.created_at))).scalars()
    )
    if not packets:
        return {}
    return {"packets": [{
        "id": str(p.id),
        "title": p.title,
        "method": p.method.value,
        "state": p.state.value,
        "summary": p.summary,
    } for p in packets]}


async def build_research_reports(session: AsyncSession, range_: str | None = None) -> dict:
    reports = await research_svc.list_validation_reports(session)
    if not reports:
        return {}
    return {"reports": [{
        "code": r.code,
        "scope": r.scope,
        "state": r.state.value,
        "signed": r.signed_at is not None,
    } for r in reports]}


async def build_research_hypotheses(session: AsyncSession, range_: str | None = None) -> dict:
    hyps = await research_svc.list_hypotheses(session)
    if not hyps:
        return {}
    return {"hypotheses": [{
        "id": str(h.id),
        "title": h.title,
        "state": h.state.value,
        "domain": h.domain,
    } for h in hyps]}


async def build_research_evidence(session: AsyncSession, range_: str | None = None) -> dict:
    return await _evidence_packets(session)


async def build_research_lockout(session: AsyncSession, range_: str | None = None) -> dict:
    """Agent lockout posture: mesh status, dispositions, and audit-chain integrity."""
    runs = await agents_svc.list_runs(session)
    awaiting = sum(1 for r in runs if r.status == AgentRunStatus.awaiting_human)
    rejected = sum(1 for r in runs if r.status == AgentRunStatus.rejected)
    failed = sum(1 for r in runs if r.status == AgentRunStatus.failed)
    return {
        "runs_total": len(runs),
        "runs_awaiting_human": awaiting,
        "runs_rejected": rejected,
        "runs_failed": failed,
        # A locked-out mesh is one with failed runs or an unverifiable trail.
        "locked_out": failed > 0,
        "audit_chain_intact": await verify_chain(session),
    }


# ==============================================================================
# optimization (live)
# ==============================================================================
async def build_optimization_schedule(session: AsyncSession, range_: str | None = None) -> dict:
    schedules = list(
        (await session.execute(select(Schedule).order_by(Schedule.created_at.desc()))).scalars()
    )
    if not schedules:
        return {}
    rows: list[dict] = []
    for sch in schedules:
        slots = await session.scalar(
            select(func.count()).select_from(ScheduleSlot).where(ScheduleSlot.schedule_id == sch.id)
        )
        rows.append({
            "id": str(sch.id),
            "objective": sch.objective,
            "horizon": sch.horizon,
            "state": sch.state.value,
            "solver_status": sch.solver_status.value if sch.solver_status else None,
            "committed": sch.committed_at is not None,
            "slots": int(slots or 0),
        })
    return {"schedules": rows}


async def build_optimization_scenario(session: AsyncSession, range_: str | None = None) -> dict:
    scenarios = list(
        (await session.execute(select(Scenario).order_by(Scenario.created_at.desc()))).scalars()
    )
    if not scenarios:
        return {}
    return {"scenarios": [{
        "id": str(s.id),
        "name": s.name,
        "kpi_delta": s.kpi_delta,
    } for s in scenarios]}


# ==============================================================================
# agents (live)
# ==============================================================================
async def build_agents(session: AsyncSession, range_: str | None = None) -> dict:
    """Agent mesh status + recent runs (proposals only — never finalized)."""
    mesh = await agents_svc.list_agents(session)
    runs = await agents_svc.list_runs(session)
    out: dict = {}
    if mesh:
        out["mesh"] = [{
            "name": a["name"],
            "job": a["job"],
            "model": a["model"],
            "last_run_at": a["last_run_at"],
            "last_status": a["last_status"].value if a["last_status"] else None,
        } for a in mesh]
    if runs:
        out["runs"] = [{
            "id": str(r.id),
            "agent": r.agent,
            "status": r.status.value,
            "proposed_action": r.proposed_action,
            "disposition": r.human_disposition,
        } for r in runs]
    return out
