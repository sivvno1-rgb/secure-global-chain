"""Manufacturing service layer.

Holds read queries and the human-gated lifecycle transitions. Every mutating
transition appends an ``audit_events`` row in the same transaction (SECURITY.md
§5); the route layer commits and surfaces ``X-Audit-Event-Id``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..audit import AuditPayload, append_audit_event
from ..errors import ConflictError, NotFoundError
from ..models.audit import AuditEvent
from ..models.enums import BatchStatus
from ..models.manufacturing import Batch, BatchStep, Line, Supplier, Task
from ..models.user import User

# Batch statuses from which a release is not allowed.
_TERMINAL_FOR_RELEASE = {BatchStatus.released, BatchStatus.rejected}


async def list_lines(session: AsyncSession) -> list[Line]:
    result = await session.execute(select(Line).order_by(Line.name))
    return list(result.scalars())


async def list_batches(
    session: AsyncSession,
    *,
    line: uuid.UUID | None = None,
    status: BatchStatus | None = None,
    page: int = 1,
    limit: int = 50,
) -> tuple[list[Batch], int]:
    filters = []
    if line is not None:
        filters.append(Batch.line_id == line)
    if status is not None:
        filters.append(Batch.status == status)

    total = await session.scalar(
        select(func.count()).select_from(Batch).where(*filters)
    )
    result = await session.execute(
        select(Batch)
        .where(*filters)
        .order_by(Batch.code)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return list(result.scalars()), int(total or 0)


async def get_batch(session: AsyncSession, code: str) -> Batch:
    result = await session.execute(
        select(Batch)
        .where(Batch.code == code)
        .options(selectinload(Batch.steps), selectinload(Batch.ipc_checks))
    )
    batch = result.scalar_one_or_none()
    if batch is None:
        raise NotFoundError(f"Batch {code} not found")
    return batch


async def release_batch(
    session: AsyncSession, code: str, actor: User
) -> tuple[Batch, AuditEvent]:
    """Human-gated batch release. Caller must hold ``qa_release`` (route layer)."""
    batch = await get_batch(session, code)
    if batch.status in _TERMINAL_FOR_RELEASE:
        raise ConflictError(
            f"Batch {code} is already {batch.status.value}; cannot release"
        )

    before = {"status": batch.status.value}
    batch.status = BatchStatus.released
    batch.released_at = datetime.now(timezone.utc)
    batch.released_by = actor.id
    batch.updated_by = actor.id

    event = await append_audit_event(
        session,
        AuditPayload(
            actor_id=actor.id,
            action="release",
            object_type="batch",
            object_id=code,
            before=before,
            after={
                "status": batch.status.value,
                "released_by": str(actor.id),
                "released_at": batch.released_at.isoformat(),
            },
        ),
    )
    return batch, event


async def quarantine_batch(
    session: AsyncSession, code: str, actor: User
) -> tuple[Batch, AuditEvent]:
    """Human-gated quarantine disposition (route requires ``quality``)."""
    batch = await get_batch(session, code)
    if batch.status == BatchStatus.quarantine:
        raise ConflictError(f"Batch {code} is already in Quarantine")

    before = {"status": batch.status.value}
    batch.status = BatchStatus.quarantine
    batch.updated_by = actor.id

    event = await append_audit_event(
        session,
        AuditPayload(
            actor_id=actor.id,
            action="quarantine",
            object_type="batch",
            object_id=code,
            before=before,
            after={"status": batch.status.value},
        ),
    )
    return batch, event


async def sign_step(
    session: AsyncSession, code: str, step_id: uuid.UUID, actor: User
) -> tuple[BatchStep, AuditEvent]:
    """E-signature on a batch step (route requires a human ``operator``)."""
    batch = await get_batch(session, code)
    result = await session.execute(
        select(BatchStep).where(
            BatchStep.id == step_id, BatchStep.batch_id == batch.id
        )
    )
    step = result.scalar_one_or_none()
    if step is None:
        raise NotFoundError(f"Step {step_id} not found on batch {code}")
    if step.signed_by is not None:
        raise ConflictError("Step is already signed")

    step.signed_by = actor.id
    step.signed_at = datetime.now(timezone.utc)

    event = await append_audit_event(
        session,
        AuditPayload(
            actor_id=actor.id,
            action="sign",
            object_type="batch_step",
            object_id=str(step.id),
            after={
                "batch": code,
                "step": step.name,
                "signed_by": str(actor.id),
                "signed_at": step.signed_at.isoformat(),
            },
        ),
    )
    return step, event


async def list_tasks(
    session: AsyncSession,
    *,
    assignee_id: uuid.UUID | None = None,
    page: int = 1,
    limit: int = 50,
) -> tuple[list[Task], int]:
    filters = []
    if assignee_id is not None:
        filters.append(Task.assignee_id == assignee_id)
    total = await session.scalar(
        select(func.count()).select_from(Task).where(*filters)
    )
    result = await session.execute(
        select(Task)
        .where(*filters)
        .order_by(Task.due_at)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return list(result.scalars()), int(total or 0)


async def mission_summary(session: AsyncSession) -> dict:
    """KPI tiles for the Mission center (read-model-lite over the context)."""
    lines = await list_lines(session)
    uptimes = [line.uptime_pct for line in lines if line.uptime_pct is not None]
    line_uptime = sum(uptimes) / len(uptimes) if uptimes else 0.0

    from ..models.enums import StatusToken

    suppliers_total = await session.scalar(
        select(func.count()).select_from(Supplier)
    )
    suppliers_on_time = await session.scalar(
        select(func.count())
        .select_from(Supplier)
        .where(Supplier.status == StatusToken.pass_)
    )
    supply_on_time = (
        100.0 * (suppliers_on_time or 0) / suppliers_total
        if suppliers_total
        else 0.0
    )

    in_process = await session.scalar(
        select(func.count())
        .select_from(Batch)
        .where(Batch.status == BatchStatus.in_process)
    )
    released = await session.scalar(
        select(func.count())
        .select_from(Batch)
        .where(Batch.status == BatchStatus.released)
    )
    return {
        "supply_on_time_pct": round(supply_on_time, 1),
        "line_uptime_pct": round(line_uptime, 1),
        "batches_in_process": int(in_process or 0),
        "batches_released": int(released or 0),
    }
