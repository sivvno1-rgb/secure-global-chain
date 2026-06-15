"""Mission Control view-model (FRONTEND_WIRING.md §4).

A read-only backend-for-frontend projection composed from the existing
manufacturing / quality / telemetry / devices services. No domain logic is
duplicated and **no audit events** are written — consequential actions still go
through the gated routes. All field names match the §4 contract exactly.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..devices import service as devices_svc
from ..manufacturing import service as mfg_svc
from ..models.enums import BatchStatus, DeviceState, QualityState, Severity, StatusToken
from ..models.manufacturing import Site
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


async def build_mission(session: AsyncSession) -> dict:
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
