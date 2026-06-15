"""Quality & Compliance service layer.

Reads plus the human-gated, audited transitions (raise / escalate deviation,
record CAPA effectiveness). Each mutation appends an ``audit_events`` row in the
same transaction (SECURITY.md §5); the route commits.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import AuditPayload, append_audit_event
from ..codes import next_code
from ..errors import ConflictError, NotFoundError
from ..models.audit import AuditEvent
from ..models.enums import Framework, QualityState, Severity, StatusToken
from ..models.quality import (
    Audit,
    AuditFinding,
    Capa,
    ComplianceItem,
    Deviation,
)
from ..models.user import User


async def list_deviations(
    session: AsyncSession,
    *,
    severity: Severity | None = None,
    state: QualityState | None = None,
    page: int = 1,
    limit: int = 50,
) -> tuple[list[Deviation], int]:
    filters = []
    if severity is not None:
        filters.append(Deviation.severity == severity)
    if state is not None:
        filters.append(Deviation.state == state)
    total = await session.scalar(
        select(func.count()).select_from(Deviation).where(*filters)
    )
    result = await session.execute(
        select(Deviation)
        .where(*filters)
        .order_by(Deviation.code)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return list(result.scalars()), int(total or 0)


async def get_deviation(session: AsyncSession, code: str) -> Deviation:
    result = await session.execute(
        select(Deviation).where(Deviation.code == code)
    )
    deviation = result.scalar_one_or_none()
    if deviation is None:
        raise NotFoundError(f"Deviation {code} not found")
    return deviation


async def raise_deviation(
    session: AsyncSession,
    *,
    actor: User,
    title: str,
    severity: Severity,
    line_id: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
    description: str | None = None,
) -> tuple[Deviation, AuditEvent]:
    code = await next_code(session, Deviation, "DEV", pad=4, start=1000)
    deviation = Deviation(
        code=code,
        title=title,
        severity=severity,
        line_id=line_id,
        batch_id=batch_id,
        state=QualityState.review,
        raised_by=actor.id,
        raised_at=datetime.now(timezone.utc),
        description=description,
    )
    session.add(deviation)
    await session.flush()

    event = await append_audit_event(
        session,
        AuditPayload(
            actor_id=actor.id,
            action="raise",
            object_type="deviation",
            object_id=code,
            after={
                "title": title,
                "severity": severity.value,
                "state": deviation.state.value,
            },
        ),
    )
    return deviation, event


async def escalate_deviation(
    session: AsyncSession, code: str, actor: User
) -> tuple[Deviation, AuditEvent]:
    deviation = await get_deviation(session, code)
    if deviation.state == QualityState.escalated:
        raise ConflictError(f"Deviation {code} is already Escalated")

    before = {"state": deviation.state.value}
    deviation.state = QualityState.escalated

    event = await append_audit_event(
        session,
        AuditPayload(
            actor_id=actor.id,
            action="escalate",
            object_type="deviation",
            object_id=code,
            before=before,
            after={"state": deviation.state.value},
        ),
    )
    return deviation, event


async def list_capas(
    session: AsyncSession,
    *,
    status: StatusToken | None = None,
    page: int = 1,
    limit: int = 50,
) -> tuple[list[Capa], int]:
    filters = []
    if status is not None:
        filters.append(Capa.status == status)
    total = await session.scalar(
        select(func.count()).select_from(Capa).where(*filters)
    )
    result = await session.execute(
        select(Capa)
        .where(*filters)
        .order_by(Capa.code)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return list(result.scalars()), int(total or 0)


async def get_capa(session: AsyncSession, code: str) -> Capa:
    result = await session.execute(select(Capa).where(Capa.code == code))
    capa = result.scalar_one_or_none()
    if capa is None:
        raise NotFoundError(f"CAPA {code} not found")
    return capa


async def record_capa_effectiveness(
    session: AsyncSession,
    code: str,
    actor: User,
    *,
    result_token: StatusToken,
    effectiveness_state: str | None = None,
    on_time_pct: float | None = None,
) -> tuple[Capa, AuditEvent]:
    capa = await get_capa(session, code)
    before = {
        "status": capa.status.value,
        "effectiveness_state": capa.effectiveness_state,
    }
    capa.status = result_token
    if effectiveness_state is not None:
        capa.effectiveness_state = effectiveness_state
    if on_time_pct is not None:
        capa.on_time_pct = on_time_pct

    event = await append_audit_event(
        session,
        AuditPayload(
            actor_id=actor.id,
            action="effectiveness",
            object_type="capa",
            object_id=code,
            before=before,
            after={
                "status": capa.status.value,
                "effectiveness_state": capa.effectiveness_state,
            },
        ),
    )
    return capa, event


async def list_audits(session: AsyncSession) -> list[Audit]:
    result = await session.execute(select(Audit).order_by(Audit.scheduled_at))
    return list(result.scalars())


async def list_audit_findings(
    session: AsyncSession, audit_id: uuid.UUID
) -> list[AuditFinding]:
    audit = await session.get(Audit, audit_id)
    if audit is None:
        raise NotFoundError(f"Audit {audit_id} not found")
    result = await session.execute(
        select(AuditFinding).where(AuditFinding.audit_id == audit_id)
    )
    return list(result.scalars())


async def list_compliance_items(
    session: AsyncSession, *, framework: Framework | None = None
) -> list[ComplianceItem]:
    filters = []
    if framework is not None:
        filters.append(ComplianceItem.framework == framework)
    result = await session.execute(
        select(ComplianceItem).where(*filters).order_by(ComplianceItem.area)
    )
    return list(result.scalars())
