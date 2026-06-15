"""Research & Evidence service layer.

Hypotheses, evidence runs (compute behind the seam), and validation reports.
Mutations are audited; the report **sign** is the human-gated e-signature.
The evidence run computes statistics only — it never sets a hypothesis verdict.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..audit import AuditPayload, append_audit_event
from ..codes import next_code
from ..errors import ConflictError, NotFoundError
from ..models.audit import AuditEvent
from ..models.enums import (
    EvidenceMethod,
    EvidenceState,
    HypothesisState,
    ValidationReportState,
)
from ..models.research import (
    EvidencePacket,
    EvidenceResult,
    Hypothesis,
    ValidationReport,
)
from ..models.user import User
from .compute import EvidenceComputer


async def list_hypotheses(
    session: AsyncSession, *, state: HypothesisState | None = None
) -> list[Hypothesis]:
    filters = []
    if state is not None:
        filters.append(Hypothesis.state == state)
    result = await session.execute(
        select(Hypothesis).where(*filters).order_by(Hypothesis.created_at)
    )
    return list(result.scalars())


async def pose_hypothesis(
    session: AsyncSession, *, actor: User, title: str, domain: str | None = None
) -> tuple[Hypothesis, AuditEvent]:
    hypothesis = Hypothesis(
        title=title, domain=domain, posed_by=actor.id, state=HypothesisState.open
    )
    session.add(hypothesis)
    await session.flush()
    event = await append_audit_event(
        session,
        AuditPayload(
            actor_id=actor.id,
            action="pose",
            object_type="hypothesis",
            object_id=str(hypothesis.id),
            after={"title": title, "state": hypothesis.state.value},
        ),
    )
    return hypothesis, event


async def get_packet(session: AsyncSession, packet_id: uuid.UUID) -> EvidencePacket:
    result = await session.execute(
        select(EvidencePacket)
        .where(EvidencePacket.id == packet_id)
        .options(selectinload(EvidencePacket.results))
    )
    packet = result.scalar_one_or_none()
    if packet is None:
        raise NotFoundError(f"Evidence packet {packet_id} not found")
    return packet


async def run_evidence(
    session: AsyncSession,
    *,
    actor: User,
    title: str,
    method: EvidenceMethod,
    computer: EvidenceComputer,
    hypothesis_id: uuid.UUID | None = None,
    dataset_ref: str | None = None,
    params: dict | None = None,
) -> tuple[EvidencePacket, AuditEvent]:
    """Create a packet and run the computation (synchronous here; Celery in prod).

    Computes statistics only — the hypothesis verdict stays a human disposition.
    """
    packet = EvidencePacket(
        hypothesis_id=hypothesis_id,
        title=title,
        dataset_ref=dataset_ref,
        method=method,
        state=EvidenceState.running,
    )
    session.add(packet)
    await session.flush()

    try:
        outcome = computer.run(method, dataset_ref=dataset_ref, params=params or {})
    except Exception as exc:
        packet.state = EvidenceState.failed
        packet.summary = f"run failed: {exc}"
        event = await append_audit_event(
            session,
            AuditPayload(
                actor_id=actor.id, action="evidence_run", object_type="evidence_packet",
                object_id=str(packet.id), after={"state": packet.state.value},
            ),
        )
        return packet, event

    packet.summary = outcome.summary
    packet.generated_by = outcome.generated_by
    packet.state = EvidenceState.complete
    for row in outcome.results:
        session.add(EvidenceResult(
            packet_id=packet.id, statistic=row.statistic, value=row.value,
            ci_low=row.ci_low, ci_high=row.ci_high, p_value=row.p_value,
            posterior_ref=row.posterior_ref,
        ))
    await session.flush()

    event = await append_audit_event(
        session,
        AuditPayload(
            actor_id=actor.id,
            action="evidence_run",
            object_type="evidence_packet",
            object_id=str(packet.id),
            after={"method": method.value, "state": packet.state.value,
                   "result_count": len(outcome.results)},
        ),
    )
    return packet, event


async def list_validation_reports(session: AsyncSession) -> list[ValidationReport]:
    result = await session.execute(
        select(ValidationReport).order_by(ValidationReport.code)
    )
    return list(result.scalars())


async def author_validation_report(
    session: AsyncSession, *, actor: User, scope: str | None = None
) -> tuple[ValidationReport, AuditEvent]:
    code = await next_code(session, ValidationReport, "VR", pad=4, start=1)
    report = ValidationReport(
        code=code, scope=scope, author_id=actor.id,
        state=ValidationReportState.in_review,
    )
    session.add(report)
    await session.flush()
    event = await append_audit_event(
        session,
        AuditPayload(
            actor_id=actor.id, action="author", object_type="validation_report",
            object_id=code, after={"state": report.state.value, "scope": scope},
        ),
    )
    return report, event


async def sign_validation_report(
    session: AsyncSession, code: str, actor: User
) -> tuple[ValidationReport, AuditEvent]:
    """Human-gated e-signature approving a validation report (requires qa_release)."""
    result = await session.execute(
        select(ValidationReport).where(ValidationReport.code == code)
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise NotFoundError(f"Validation report {code} not found")
    if report.state == ValidationReportState.approved:
        raise ConflictError(f"Validation report {code} is already approved")

    before = {"state": report.state.value}
    report.state = ValidationReportState.approved
    report.signed_by = actor.id
    report.signed_at = datetime.now(timezone.utc)

    event = await append_audit_event(
        session,
        AuditPayload(
            actor_id=actor.id,
            action="sign",
            object_type="validation_report",
            object_id=code,
            before=before,
            after={"state": report.state.value, "signed_by": str(actor.id)},
        ),
    )
    return report, event
