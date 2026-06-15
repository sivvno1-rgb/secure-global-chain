"""Idempotent demo seed across every context.

Run against the configured database (``SGC_DATABASE_URL``):

    python -m sgc.seed                 # assumes schema exists (alembic upgrade head)
    python -m sgc.seed --create-tables # also create tables first (dev/sqlite only)

Idempotent: entities are keyed by their business key (code / serial / version /
name / keycloak_sub) and only created if missing; child rows (steps, IPC checks,
attestations, excursions, agent runs, …) are added only when their parent is
newly created, so re-running never duplicates data.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import models as m
from .db import Base, get_engine, get_sessionmaker
from .models.enums import (
    AgentRunStatus,
    BatchStatus,
    DeviceState,
    EvidenceMethod,
    EvidenceState,
    FirmwareState,
    Framework,
    HypothesisState,
    MaterialKind,
    QualityState,
    ScheduleState,
    Severity,
    ShipmentState,
    SolverStatus,
    Sourcing,
    StatusToken,
    StreamKind,
    TaskKind,
    ValidationReportState,
)

NOW = datetime.now(timezone.utc)


def ago(**kw) -> datetime:
    return NOW - timedelta(**kw)


async def get_or_create(session: AsyncSession, model, *, defaults=None, **keys):
    obj = (await session.execute(select(model).filter_by(**keys))).scalar_one_or_none()
    if obj is not None:
        return obj, False
    obj = model(**keys, **(defaults or {}))
    session.add(obj)
    await session.flush()
    return obj, True


async def _count(session: AsyncSession, model) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def seed(session: AsyncSession) -> dict[str, int]:
    # --- users (for created_by / signed_by / actor refs) ------------------
    users = {}
    for sub, name, roles in [
        ("seed-operator", "Olivia Operator", ["operator"]),
        ("seed-qa", "Quinn QA", ["qa_release", "quality"]),
        ("seed-fleet", "Felix Fleet", ["fleet_admin"]),
        ("seed-scientist", "Sara Scientist", ["scientist"]),
        ("seed-planner", "Pat Planner", ["planner"]),
        ("seed-exec", "Erin Exec", ["executive"]),
    ]:
        u, _ = await get_or_create(
            session, m.User, keycloak_sub=sub,
            defaults={"display_name": name, "email": f"{sub}@dev.local", "roles": roles},
        )
        users[sub] = u

    # --- manufacturing master data ----------------------------------------
    site, _ = await get_or_create(
        session, m.Site, name="Schaffhausen",
        defaults={"cleanroom": "CR4", "gmp_status": "GMP"},
    )
    lines = {}
    for name, stage, uptime, status in [
        ("Line A", "Filling", 98.7, StatusToken.pass_),
        ("Line B", "Filling", 95.2, StatusToken.warn),
        ("Line C", "Inspection", 99.1, StatusToken.pass_),
    ]:
        ln, _ = await get_or_create(
            session, m.Line, name=name,
            defaults={"site_id": site.id, "stage": stage, "uptime_pct": uptime, "status": status},
        )
        lines[name] = ln

    products = {}
    for code, pname, modality in [("TRM", "Guselkumab", "mAb"), ("RIS", "Risankizumab", "mAb")]:
        p, _ = await get_or_create(
            session, m.Product, code=code, defaults={"name": pname, "modality": modality}
        )
        products[code] = p

    sup_ok, sup_created = await get_or_create(
        session, m.Supplier, name="Helvetia Biologics",
        defaults={"material": "Guselkumab DS", "sourcing": Sourcing.dual,
                  "site_country": "CH", "lead_time_days": 30, "status": StatusToken.pass_},
    )
    sup_watch, _ = await get_or_create(
        session, m.Supplier, name="Rhein Excipients",
        defaults={"material": "Excipient blend", "sourcing": Sourcing.single,
                  "site_country": "DE", "lead_time_days": 45, "status": StatusToken.warn},
    )
    if sup_created:
        await get_or_create(session, m.Material, name="Guselkumab DS",
                            defaults={"kind": MaterialKind.ds, "supplier_id": sup_ok.id})
    await get_or_create(session, m.Equipment, name="Balance 12",
                        defaults={"kind": "balance", "calibration_due": NOW + timedelta(days=20),
                                  "calibration_status": StatusToken.pass_})

    # --- a dozen batches across the lifecycle -----------------------------
    batch_specs = [
        ("TRM-2290", "TRM", "Line A", BatchStatus.released, 98.9),
        ("TRM-2291", "TRM", "Line A", BatchStatus.inspection, 98.7),
        ("TRM-2292", "TRM", "Line B", BatchStatus.in_process, None),
        ("TRM-2293", "TRM", "Line B", BatchStatus.hold, 96.1),
        ("TRM-2294", "TRM", "Line C", BatchStatus.quarantine, 91.4),
        ("TRM-2295", "TRM", "Line A", BatchStatus.released, 99.2),
        ("TRM-2296", "TRM", "Line C", BatchStatus.rejected, 88.0),
        ("RIS-1180", "RIS", "Line B", BatchStatus.in_process, None),
        ("RIS-1181", "RIS", "Line A", BatchStatus.inspection, 97.3),
        ("RIS-1182", "RIS", "Line C", BatchStatus.released, 98.1),
        ("RIS-1183", "RIS", "Line B", BatchStatus.hold, 95.5),
        ("RIS-1184", "RIS", "Line A", BatchStatus.in_process, None),
    ]
    batches = {}
    for code, pcode, lname, status, yield_pct in batch_specs:
        defaults = {
            "product_id": products[pcode].id, "line_id": lines[lname].id,
            "stage": lines[lname].stage, "status": status, "yield_pct": yield_pct,
            "started_at": ago(days=6), "created_by": users["seed-operator"].id,
        }
        if status is BatchStatus.released:
            defaults["released_at"] = ago(days=1)
            defaults["released_by"] = users["seed-qa"].id
        batch, created = await get_or_create(session, m.Batch, code=code, defaults=defaults)
        batches[code] = batch
        if created:
            for seq, sname in enumerate(["Compounding", "Filling", "Inspection"], start=1):
                signed = sname == "Compounding"
                session.add(m.BatchStep(
                    batch_id=batch.id, name=sname, sequence=seq,
                    signed_by=users["seed-operator"].id if signed else None,
                    signed_at=ago(days=2) if signed else None,
                    record_url=f"s3://records/{code}/{sname.lower()}",
                ))
            session.add(m.IpcCheck(
                batch_id=batch.id, kind="weight", value=10.1, spec_low=9.5,
                spec_high=10.5, result=StatusToken.pass_, at=ago(days=2)))
            session.add(m.IpcCheck(
                batch_id=batch.id, kind="ph", value=7.4, spec_low=7.0,
                spec_high=7.6, result=StatusToken.pass_, at=ago(days=2)))

    # a few operator tasks
    if await _count(session, m.Task) == 0:
        session.add_all([
            m.Task(assignee_id=users["seed-operator"].id, title="Line A clearance",
                   kind=TaskKind.clearance, due_at=NOW + timedelta(hours=4),
                   status=StatusToken.warn, batch_id=batches["TRM-2292"].id),
            m.Task(assignee_id=users["seed-operator"].id, title="Balance 12 calibration",
                   kind=TaskKind.calibration, due_at=NOW + timedelta(days=2),
                   status=StatusToken.neutral),
        ])

    # --- quality ----------------------------------------------------------
    dev_specs = [
        ("DEV-1180", "Fill weight drift", Severity.major, "Line B", "TRM-2293", QualityState.review),
        ("DEV-1182", "Environmental excursion CR4", Severity.critical, "Line C", "TRM-2294", QualityState.escalated),
        ("DEV-1185", "Particle count warning", Severity.minor, "Line A", None, QualityState.watch),
    ]
    deviations = {}
    for code, title, sev, lname, bcode, state in dev_specs:
        d, _ = await get_or_create(
            session, m.Deviation, code=code,
            defaults={"title": title, "severity": sev, "line_id": lines[lname].id,
                      "batch_id": batches[bcode].id if bcode else None, "state": state,
                      "raised_by": users["seed-operator"].id, "raised_at": ago(days=3),
                      "description": f"{title} observed during routine monitoring."},
        )
        deviations[code] = d
    await get_or_create(
        session, m.Capa, code="CAPA-0441",
        defaults={"deviation_id": deviations["DEV-1182"].id, "owner_id": users["seed-qa"].id,
                  "due_at": NOW + timedelta(days=14), "effectiveness_state": "pending",
                  "on_time_pct": 92.0, "status": StatusToken.warn},
    )
    await get_or_create(
        session, m.Capa, code="CAPA-0442",
        defaults={"deviation_id": deviations["DEV-1180"].id, "owner_id": users["seed-qa"].id,
                  "due_at": NOW + timedelta(days=30), "effectiveness_state": "effective",
                  "on_time_pct": 100.0, "status": StatusToken.pass_},
    )
    for fw, area, title, state in [
        (Framework.gmp, "CR4", "Gowning log", StatusToken.pass_),
        (Framework.gmp, "CR4", "Environmental monitoring", StatusToken.warn),
        (Framework.glp, "Lab 2", "Balance calibration", StatusToken.pass_),
    ]:
        await get_or_create(session, m.ComplianceItem, framework=fw, area=area, title=title,
                            defaults={"state": state, "evidence_url": "s3://evidence/x"})
    audit_obj, audit_created = await get_or_create(
        session, m.Audit, scope="CR4 annual GMP",
        defaults={"framework": Framework.gmp, "readiness_pct": 86.0,
                  "scheduled_at": NOW + timedelta(days=10), "lead_id": users["seed-qa"].id},
    )
    if audit_created:
        session.add(m.AuditFinding(audit_id=audit_obj.id, framework=Framework.gmp,
                                   severity=Severity.minor, status=StatusToken.warn,
                                   remediation_due=NOW + timedelta(days=21)))

    # --- device fleet -----------------------------------------------------
    fw_signed, _ = await get_or_create(
        session, m.FirmwareBuild, version="v4.1.0",
        defaults={"digest": "sha256:9f3a1c0b", "signed_by": users["seed-fleet"].id,
                  "signed_at": ago(days=20), "state": FirmwareState.signed,
                  "release_notes": "Baseline secure-MCU build", "artifact_url": "s3://fw/v4.1.0"},
    )
    fw_draft, _ = await get_or_create(
        session, m.FirmwareBuild, version="v4.2.1",
        defaults={"state": FirmwareState.draft, "release_notes": "Adds attestation v2",
                  "artifact_url": "s3://fw/v4.2.1"},
    )
    device_specs = [
        ("NS-1001", DeviceState.online, "Line A"),
        ("NS-1002", DeviceState.transmitting, "Line A"),
        ("NS-1003", DeviceState.online, "Line B"),
        ("NS-1004", DeviceState.offline, "Line B"),
        ("NS-1005", DeviceState.quarantined, "Line C"),
        ("NS-1006", DeviceState.online, "Line C"),
        ("NS-1007", DeviceState.provisioned, None),
    ]
    for serial, state, lname in device_specs:
        dev, created = await get_or_create(
            session, m.Device, serial=serial,
            defaults={"model": "NeuroSecure", "site_id": site.id,
                      "line_id": lines[lname].id if lname else None,
                      "hw_identity_pubkey": f"dev-pub:{serial}", "state": state,
                      "last_seen_at": ago(minutes=3), "firmware_id": fw_signed.id,
                      "tamper_locked": state is DeviceState.quarantined},
        )
        if created:
            session.add(m.DeviceAttestation(
                device_id=dev.id, firmware_id=fw_signed.id, measured_digest="sha256:9f3a1c0b",
                verdict=StatusToken.fail if state is DeviceState.quarantined else StatusToken.pass_,
                at=ago(minutes=5)))
    if await _count(session, m.FirmwareRollout) == 0:
        session.add(m.FirmwareRollout(
            firmware_id=fw_signed.id, cohort="ring-0", devices_total=7, devices_done=6,
            state=FirmwareState.rolling, started_at=ago(days=2), started_by=users["seed-fleet"].id))
    await get_or_create(
        session, m.ProvisionRequest, device_serial="NS-1008",
        defaults={"requested_by": users["seed-operator"].id, "status": "pending", "at": ago(hours=2)})

    # --- telemetry & cold chain -------------------------------------------
    # one temp stream + readings on the first online device
    first_dev = (await session.execute(
        select(m.Device).where(m.Device.serial == "NS-1001"))).scalar_one()
    stream, stream_created = await get_or_create(
        session, m.SensorStream, device_id=first_dev.id, kind=StreamKind.temp,
        defaults={"unit": "C", "spec_low": 2.0, "spec_high": 8.0})
    if stream_created:
        for i in range(6):
            session.add(m.Reading(stream_id=stream.id, ts=ago(minutes=i * 10), value=5.0 + (i % 3) * 0.4))

    lane_eu, lane_created = await get_or_create(
        session, m.ColdchainLane, code="SG→EU",
        defaults={"origin": "Singapore", "destination": "Frankfurt", "spec_low": 2.0,
                  "spec_high": 8.0, "status": StatusToken.warn})
    lane_us, _ = await get_or_create(
        session, m.ColdchainLane, code="US→EU",
        defaults={"origin": "Newark", "destination": "Amsterdam", "spec_low": 2.0,
                  "spec_high": 8.0, "status": StatusToken.pass_})
    if lane_created:
        ship = m.Shipment(lane_id=lane_eu.id, batch_id=batches["TRM-2290"].id,
                          state=ShipmentState.in_transit, departed_at=ago(days=1),
                          eta=NOW + timedelta(days=1))
        session.add(ship)
        await session.flush()
        # one open excursion + one already-dispositioned
        session.add(m.Excursion(
            lane_id=lane_eu.id, shipment_id=ship.id, kind="cold-chain", started_at=ago(hours=6),
            peak_value=11.2, severity=Severity.major, disposition=None))
        session.add(m.Excursion(
            lane_id=lane_eu.id, shipment_id=ship.id, kind="cold-chain", started_at=ago(days=2),
            ended_at=ago(days=2) + timedelta(hours=1), peak_value=9.1, severity=Severity.minor,
            disposition="Reviewed — within stability budget; released"))

    # --- research ---------------------------------------------------------
    hyp, hyp_created = await get_or_create(
        session, m.Hypothesis, title="Dual sourcing reduces fill-weight variance",
        defaults={"posed_by": users["seed-scientist"].id, "state": HypothesisState.under_review,
                  "domain": "formulation"})
    if hyp_created:
        packet = m.EvidencePacket(
            hypothesis_id=hyp.id, title="Fill-weight t-test Q2", dataset_ref="ds://fill-weights/q2",
            method=EvidenceMethod.frequentist, summary="t=-0.83, p=0.41, n=42 (seed=1729)",
            generated_by="local:numpy/scipy", state=EvidenceState.complete)
        session.add(packet)
        await session.flush()
        session.add(m.EvidenceResult(packet_id=packet.id, statistic="t", value=-0.83, p_value=0.41))
        session.add(m.EvidenceResult(packet_id=packet.id, statistic="mean", value=10.02,
                                     ci_low=9.94, ci_high=10.10))
    await get_or_create(
        session, m.ValidationReport, code="VR-0001",
        defaults={"scope": "Process validation TRM line A", "author_id": users["seed-scientist"].id,
                  "state": ValidationReportState.in_review})
    await get_or_create(
        session, m.ValidationReport, code="VR-0002",
        defaults={"scope": "Cleaning validation CR4", "author_id": users["seed-scientist"].id,
                  "state": ValidationReportState.approved, "signed_by": users["seed-qa"].id,
                  "signed_at": ago(days=5)})

    # --- optimization -----------------------------------------------------
    if await _count(session, m.Schedule) == 0:
        sched = m.Schedule(line_id=lines["Line A"].id, horizon=480, objective="makespan",
                           generated_by="cp-sat", state=ScheduleState.solved,
                           solver_status=SolverStatus.optimal)
        session.add(sched)
        await session.flush()
        start = 0
        for code, dur in [("TRM-2291", 90), ("TRM-2295", 120), ("RIS-1181", 60)]:
            session.add(m.ScheduleSlot(schedule_id=sched.id, batch_id=batches[code].id,
                                       start_at=start, end_at=start + dur, setup_minutes=10))
            start += dur

    # --- agents (advisory runs) -------------------------------------------
    if await _count(session, m.AgentRun) == 0:
        session.add_all([
            m.AgentRun(agent="tracer", graph_node="propose", input_ref="TRM-2294",
                       output_ref="memory://agent/tracer/TRM-2294", model="ollama:llama3.1:8b",
                       started_at=ago(hours=3), ended_at=ago(hours=3),
                       status=AgentRunStatus.accepted, human_disposition="accepted",
                       proposed_action={"kind": "trace_summary", "target": "TRM-2294",
                                        "summary": "Chain of custody assembled", "requires_human": True}),
            m.AgentRun(agent="fleet_sentinel", graph_node="propose", input_ref="NS-1005",
                       output_ref="memory://agent/fleet_sentinel/NS-1005", model="ollama:llama3.1:8b",
                       started_at=ago(hours=1), ended_at=ago(hours=1),
                       status=AgentRunStatus.awaiting_human,
                       proposed_action={"kind": "propose_quarantine", "target": "NS-1005",
                                        "summary": "Attestation digest mismatch", "requires_human": True}),
            m.AgentRun(agent="quality_analyst", graph_node="propose", input_ref="DEV-1180",
                       output_ref="memory://agent/quality_analyst/DEV-1180", model="ollama:llama3.1:8b",
                       started_at=ago(hours=2), ended_at=ago(hours=2),
                       status=AgentRunStatus.rejected, human_disposition="rejected",
                       proposed_action={"kind": "capa_suggestion", "target": "DEV-1180",
                                        "summary": "Draft CAPA: recalibrate balance", "requires_human": True}),
        ])

    await session.commit()

    return {
        "users": await _count(session, m.User),
        "lines": await _count(session, m.Line),
        "batches": await _count(session, m.Batch),
        "deviations": await _count(session, m.Deviation),
        "capas": await _count(session, m.Capa),
        "devices": await _count(session, m.Device),
        "firmware_builds": await _count(session, m.FirmwareBuild),
        "excursions": await _count(session, m.Excursion),
        "agent_runs": await _count(session, m.AgentRun),
        "audit_events": await _count(session, m.AuditEvent),
    }


async def main(create_tables: bool = False) -> None:
    if create_tables:
        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    async with get_sessionmaker()() as session:
        counts = await seed(session)
    print("Seed complete (idempotent). Row counts:")
    for table, n in counts.items():
        print(f"  {table:16} {n}")


if __name__ == "__main__":
    asyncio.run(main(create_tables="--create-tables" in sys.argv))
