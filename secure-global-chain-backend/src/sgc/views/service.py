"""Fully-specced view-models (FRONTEND_WIRING.md §4–6): mission, operations,
quality.

Read-only backend-for-frontend projections composed from the existing
manufacturing / quality / telemetry / devices / agents services. No domain logic
is duplicated and **no audit events** are written — consequential actions still
go through the gated routes. All field names match the contracts exactly.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents import service as agents_svc
from ..devices import service as devices_svc
from ..manufacturing import service as mfg_svc
from ..models.enums import (
    AgentRunStatus,
    BatchStatus,
    DeviceState,
    QualityState,
    Severity,
    StatusToken,
    StreamKind,
)
from ..models.manufacturing import BatchStep, Site
from ..models.telemetry import Reading, SensorStream
from ..quality import service as quality_svc
from ..telemetry import service as telemetry_svc

# Severity accent colors used by the screen.
_ACCENT = {"fail": "#b5341f", "warn": "#c98a1a"}
# Deviation states considered "open".
_OPEN_DEV = (QualityState.review, QualityState.escalated, QualityState.watch, QualityState.quarantine)
_RISK_SEVERITY = (Severity.critical, Severity.major)
# At-risk batch statuses and a stable per-batch value estimate (USD millions).
_AT_RISK_BATCH = (BatchStatus.quarantine, BatchStatus.rejected, BatchStatus.hold)
_VALUE_PER_BATCH_M = 1.2
_EVENT_LIMIT = 8


def _sev_for(severity: Severity) -> str:
    return "fail" if severity in _RISK_SEVERITY else "warn"


def _status_from_token(token: StatusToken) -> str:
    if token == StatusToken.fail:
        return "fail"
    if token == StatusToken.warn:
        return "warn"
    return "pass"


async def build_mission(session: AsyncSession, range_: str | None = None) -> dict:
    # --- gather (compose existing services) -------------------------------
    lines = await mfg_svc.list_lines(session)
    batches, _ = await mfg_svc.list_batches(session, page=1, limit=1000)
    deviations, _ = await quality_svc.list_deviations(session, page=1, limit=1000)
    compliance = await quality_svc.list_compliance_items(session)
    open_excursions = await telemetry_svc.list_excursions(session, open_only=True)
    lanes = await telemetry_svc.list_lanes(session)
    devices, _ = await devices_svc.list_devices(session, page=1, limit=1000)
    summary = await mfg_svc.mission_summary(session)
    sites = list((await session.execute(select(Site).order_by(Site.name))).scalars())

    line_to_site = {ln.id: ln.site_id for ln in lines}
    line_name = {ln.id: ln.name for ln in lines}
    lane_code = {ex.lane_id: None for ex in open_excursions}
    for lane in lanes:
        lane_code[lane.id] = lane.code

    open_devs = [d for d in deviations if d.state in _OPEN_DEV]
    critical_open = [d for d in open_devs if d.severity in _RISK_SEVERITY]
    quarantined_devices = [dv for dv in devices if dv.state == DeviceState.quarantined]
    quarantined_batches = [b for b in batches if b.status == BatchStatus.quarantine]
    at_risk_batches = [b for b in batches if b.status in _AT_RISK_BATCH]
    escalated_devs = [d for d in open_devs if d.state == QualityState.escalated]

    # --- events (ranked union; build before KPIs so counts agree) ---------
    events: list[dict] = []
    for d in critical_open:
        sev = _sev_for(d.severity)
        events.append({
            "sev": sev, "c": _ACCENT[sev], "cat": "Quality deviation",
            "title": d.title, "desc": d.description or f"Deviation {d.code} is open.",
            "impact": [["Severity", d.severity.value], ["Line", line_name.get(d.line_id, "—")],
                       ["State", d.state.value]],
            "action": "Escalate + investigate", "go": "escalate", "btn": "Open incident",
        })
    for ex in open_excursions:
        sev = _sev_for(ex.severity)
        code = lane_code.get(ex.lane_id) or "lane"
        events.append({
            "sev": sev, "c": _ACCENT[sev], "cat": "Cold-chain excursion",
            "title": f"Excursion on {code}",
            "desc": f"{ex.kind or 'cold-chain'} excursion, peak {ex.peak_value}.",
            "impact": [["Severity", ex.severity.value], ["Lane", code],
                       ["Peak", str(ex.peak_value)]],
            "action": "Review disposition", "go": "escalate", "btn": "Open incident",
        })
    for b in quarantined_batches:
        events.append({
            "sev": "warn", "c": _ACCENT["warn"], "cat": "Quality hold",
            "title": f"{b.code} quarantined",
            "desc": f"Batch {b.code} on hold pending QA disposition.",
            "impact": [["Status", b.status.value], ["Line", line_name.get(b.line_id, "—")],
                       ["Yield", str(b.yield_pct)]],
            "action": "Review hold", "go": "operations", "btn": "Open batch",
        })
    # rank: fail before warn, then stable; keep top N
    events.sort(key=lambda e: 0 if e["sev"] == "fail" else 1)
    events = events[:_EVENT_LIMIT]
    critical_events = sum(1 for e in events if e["sev"] == "fail")

    # --- facilities roll-up -----------------------------------------------
    site_critical: set = set()
    site_warn: set = set()
    site_detail: dict = {}
    for d in open_devs:
        site_id = line_to_site.get(d.line_id)
        if site_id is None:
            continue
        if d.severity in _RISK_SEVERITY and d.severity == Severity.critical:
            site_critical.add(site_id)
            site_detail.setdefault(site_id, d.title)
        else:
            site_warn.add(site_id)
            site_detail.setdefault(site_id, d.title)
    for dv in quarantined_devices:
        if dv.site_id is not None:
            site_warn.add(dv.site_id)
            site_detail.setdefault(dv.site_id, f"Device {dv.serial} quarantined")

    facilities: list[list[str]] = []
    healthy = 0
    for site in sites:
        if site.id in site_critical:
            facilities.append([site.name, site_detail.get(site.id, "Critical signal"), "fail"])
        elif site.id in site_warn:
            facilities.append([site.name, site_detail.get(site.id, "Open signal"), "warn"])
        else:
            facilities.append([site.name, "Nominal", "pass"])
            healthy += 1
    total_sites = len(sites)

    # --- shipments roll-up (cold-chain lanes) -----------------------------
    lanes_with_open_exc = {ex.lane_id: ex for ex in open_excursions}
    shipments: list[list[str]] = []
    delayed = 0
    for lane in lanes:
        if lane.id in lanes_with_open_exc:
            ex = lanes_with_open_exc[lane.id]
            shipments.append([lane.code, "Cold-chain excursion", _sev_for(ex.severity)])
            delayed += 1
        else:
            tone = _status_from_token(lane.status)
            shipments.append([lane.code, "On time" if tone == "pass" else "Watch", tone])
            if tone != "pass":
                delayed += 1

    # --- KPIs (composite) -------------------------------------------------
    compliance_pct = (
        100.0 * sum(1 for c in compliance if c.state == StatusToken.pass_) / len(compliance)
        if compliance else 100.0
    )
    active_risks = len(critical_open) + len(open_excursions) + len(quarantined_devices)
    pending_decisions = len(quarantined_batches) + len(escalated_devs)
    value_at_risk_m = round(len(at_risk_batches) * _VALUE_PER_BATCH_M, 1)

    # weighted composite, penalized by open risk; stable formula
    base = 0.4 * compliance_pct + 0.3 * summary["line_uptime_pct"] + 0.3 * summary["supply_on_time_pct"]
    penalty = min(active_risks * 3, 30)
    mission_pct = max(0, min(100, round(base - penalty)))

    mission_tone = "pass" if mission_pct >= 90 else "warn" if mission_pct >= 75 else "fail"
    risks_tone = "fail" if critical_open else "warn" if active_risks else "pass"
    decisions_tone = "warn" if pending_decisions else "pass"
    if total_sites and healthy == total_sites:
        fac_tone = "pass"
    elif total_sites and healthy / total_sites < 0.7:
        fac_tone = "fail"
    else:
        fac_tone = "pass" if total_sites == 0 else "warn"
    ship_tone = "pass" if delayed == 0 else "warn"
    var_tone = "fail" if value_at_risk_m >= 10 else "warn" if value_at_risk_m > 0 else "pass"

    kpis = [
        {"label": "Mission health", "v": str(mission_pct), "u": "%", "tone": mission_tone},
        {"label": "Active risks", "v": str(active_risks), "tone": risks_tone},
        {"label": "Pending decisions", "v": str(pending_decisions), "tone": decisions_tone},
        {"label": "Facilities healthy", "v": str(healthy), "u": f"/ {total_sites}", "tone": fac_tone},
        {"label": "Shipments delayed", "v": str(delayed), "tone": ship_tone},
        {"label": "Value at risk", "v": f"${value_at_risk_m}M", "tone": var_tone},
    ]

    return {
        "headline": {"mission_pct": mission_pct, "critical_events": critical_events},
        "kpis": kpis,
        "events": events,
        "facilities": facilities,
        "shipments": shipments,
    }


# ==============================================================================
# operations (§6)
# ==============================================================================

# Device states that count as a healthy "pass" tile / a "live" device.
_DEVICE_FAIL = (DeviceState.quarantined,)
_DEVICE_WARN = (DeviceState.offline, DeviceState.decommissioned)
_DEVICE_LIVE = (DeviceState.online, DeviceState.transmitting)
# Cleanroom reading tile labels per stream kind.
_ENV_LABEL = {
    StreamKind.particle: "Particle",
    StreamKind.temp: "Temperature",
    StreamKind.biosignal: "Biosignal",
    StreamKind.humidity: "Humidity",
}
_ENV_ORDER = (StreamKind.particle, StreamKind.temp, StreamKind.humidity, StreamKind.biosignal)


def _device_tone(state: DeviceState) -> str:
    if state in _DEVICE_FAIL:
        return "fail"
    if state in _DEVICE_WARN:
        return "warn"
    return "pass"


def _fmt_num(value: float | None) -> str:
    if value is None:
        return "—"
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.2f}"


async def build_operations(session: AsyncSession, range_: str | None = None) -> dict:
    """OperatorHome view-model (§6): shift task queue, assigned devices,
    cleanroom readings, active batch. Returns only the fields it can compose."""
    out: dict = {}

    # --- tasks (st: completed→done; first open→now; rest→todo) -------------
    tasks, _ = await mfg_svc.list_tasks(session, limit=100)
    task_rows: list[dict] = []
    now_assigned = False
    for t in tasks:
        if t.status == StatusToken.pass_:
            st = "done"
        elif not now_assigned:
            st = "now"
            now_assigned = True
        else:
            st = "todo"
        row = {"id": str(t.id), "t": t.title, "st": st, "kind": t.kind.value}
        if t.due_at is not None:
            row["due"] = t.due_at.strftime("%H:%M")
        task_rows.append(row)
    if task_rows:
        out["tasks"] = task_rows

    # --- assigned devices --------------------------------------------------
    devices, _ = await devices_svc.list_devices(session, limit=100)
    lines = {ln.id: ln for ln in await mfg_svc.list_lines(session)}
    sites = {s.id: s for s in (await session.execute(select(Site))).scalars()}
    device_rows: list[dict] = []
    for dv in devices:
        loc_parts = []
        if dv.site_id in sites:
            loc_parts.append(sites[dv.site_id].name)
        if dv.line_id in lines:
            loc_parts.append(lines[dv.line_id].name)
        device_rows.append({
            "id": dv.serial,
            "loc": " · ".join(loc_parts) or "—",
            "st": _device_tone(dv.state),
            "live": dv.state in _DEVICE_LIVE,
        })
    if device_rows:
        out["devices"] = device_rows

    # --- cleanroom environment (latest reading per stream kind) ------------
    reading_rows = (
        await session.execute(
            select(SensorStream, Reading)
            .join(Reading, Reading.stream_id == SensorStream.id)
            .order_by(Reading.ts.desc())
        )
    ).all()
    latest_by_kind: dict[StreamKind, tuple[SensorStream, Reading]] = {}
    for stream, reading in reading_rows:
        latest_by_kind.setdefault(stream.kind, (stream, reading))
    env_rows: list[dict] = []
    for kind in _ENV_ORDER:
        if kind not in latest_by_kind:
            continue
        stream, reading = latest_by_kind[kind]
        ok = True
        if stream.spec_low is not None and reading.value is not None:
            ok = ok and reading.value >= stream.spec_low
        if stream.spec_high is not None and reading.value is not None:
            ok = ok and reading.value <= stream.spec_high
        tile = {"k": _ENV_LABEL.get(kind, kind.value), "v": _fmt_num(reading.value), "ok": ok}
        if stream.unit:
            tile["u"] = stream.unit
        env_rows.append(tile)
    if env_rows:
        out["env"] = env_rows

    # --- active batch (the operator's in-process batch) --------------------
    batches, _ = await mfg_svc.list_batches(session, page=1, limit=1000)
    active = next((b for b in batches if b.status == BatchStatus.in_process), None)
    if active is not None:
        batch: dict = {"code": active.code}
        if active.stage:
            batch["stage"] = active.stage
        total_steps = await session.scalar(
            select(func.count()).select_from(BatchStep).where(BatchStep.batch_id == active.id)
        )
        if total_steps:
            signed = await session.scalar(
                select(func.count())
                .select_from(BatchStep)
                .where(BatchStep.batch_id == active.id, BatchStep.signed_at.isnot(None))
            )
            batch["completion"] = round(100 * (signed or 0) / total_steps)
        out["batch"] = batch

    return out


# ==============================================================================
# quality (§5)
# ==============================================================================
# Open CAPAs are those not yet closed out (status not "pass").
_OPEN_CAPA = (StatusToken.warn, StatusToken.fail, StatusToken.info, StatusToken.neutral)


def _pct_tone(pct: float, *, good: float = 95.0, bad: float = 80.0) -> str:
    if pct >= good:
        return "pass"
    if pct >= bad:
        return "warn"
    return "fail"


async def build_quality(session: AsyncSession, range_: str | None = None) -> dict:
    """Quality & Compliance console (§5). Composes the tiles the quality context
    can source today (compliance, CAPAs, audits, agent drafts); fields backed by
    not-yet-modeled domains (change-control, periodic review, training) are
    omitted so the screen falls back to demo for them."""
    out: dict = {}

    compliance = await quality_svc.list_compliance_items(session)
    capas, _ = await quality_svc.list_capas(session)
    audits = await quality_svc.list_audits(session)

    # --- KPIs (only the §5 tiles with a real source, in §5 order) ----------
    kpis: list[dict] = []
    if compliance:
        comp_pct = 100.0 * sum(1 for c in compliance if c.state == StatusToken.pass_) / len(compliance)
        kpis.append({"label": "SOX on-time", "v": str(round(comp_pct)), "u": "%",
                     "tone": _pct_tone(comp_pct)})
    open_capas = [c for c in capas if c.status in _OPEN_CAPA]
    if capas:
        kpis.append({"label": "Open CAPAs", "v": str(len(open_capas)),
                     "tone": "warn" if open_capas else "pass"})
    readiness = [a.readiness_pct for a in audits if a.readiness_pct is not None]
    if readiness:
        avg_ready = sum(readiness) / len(readiness)
        kpis.append({"label": "Audit readiness", "v": str(round(avg_ready)), "u": "%",
                     "tone": _pct_tone(avg_ready, good=90, bad=75)})
    if kpis:
        out["kpis"] = kpis

    # --- what the agents drafted (proposals awaiting a human) --------------
    runs = await agents_svc.list_runs(session)
    agent_rows: list[dict] = []
    for r in runs:
        if r.status != AgentRunStatus.awaiting_human:
            continue
        action = ""
        if isinstance(r.proposed_action, dict):
            action = r.proposed_action.get("summary") or r.proposed_action.get("kind") or ""
        agent_rows.append({
            "t": action or f"{r.agent} proposal",
            "m": "Awaiting human disposition",
            "act": "Review",
        })
    if agent_rows:
        out["agents"] = agent_rows

    return out
