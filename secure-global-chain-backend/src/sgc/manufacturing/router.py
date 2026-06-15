"""Manufacturing API (Mission / Operations). Prefix ``/api/v1``.

Consequential verbs are explicit sub-resources protected by ``require_role`` and
write an audit event; mutating responses carry ``X-Audit-Event-Id``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models.enums import BatchStatus
from ..security import Principal, get_current_principal, require_role
from ..security.users import sync_user
from . import service
from .schemas import (
    BatchDetail,
    BatchStepRead,
    BatchSummary,
    LineRead,
    MissionSummary,
    Page,
    TaskRead,
)

router = APIRouter(prefix="/api/v1", tags=["manufacturing"])


@router.get("/mission/summary", response_model=MissionSummary)
async def mission_summary(
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
) -> dict:
    return await service.mission_summary(session)


@router.get("/lines", response_model=list[LineRead])
async def list_lines(
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    return await service.list_lines(session)


@router.get("/batches", response_model=Page[BatchSummary])
async def list_batches(
    line: uuid.UUID | None = None,
    status: BatchStatus | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    items, total = await service.list_batches(
        session, line=line, status=status, page=page, limit=limit
    )
    return Page[BatchSummary](
        items=[BatchSummary.model_validate(b) for b in items],
        total=total,
        page=page,
    )


@router.get("/batches/{code}", response_model=BatchDetail)
async def get_batch(
    code: str,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    return await service.get_batch(session, code)


@router.post("/batches/{code}/release", response_model=BatchDetail)
async def release_batch(
    code: str,
    response: Response,
    principal: Principal = Depends(require_role("qa_release", human_only=True)),
    session: AsyncSession = Depends(get_session),
):
    actor = await sync_user(session, principal)
    batch, event = await service.release_batch(session, code, actor)
    await session.commit()
    await session.refresh(batch)
    response.headers["X-Audit-Event-Id"] = str(event.id)
    return await service.get_batch(session, code)


@router.post("/batches/{code}/quarantine", response_model=BatchDetail)
async def quarantine_batch(
    code: str,
    response: Response,
    principal: Principal = Depends(require_role("quality", human_only=True)),
    session: AsyncSession = Depends(get_session),
):
    actor = await sync_user(session, principal)
    batch, event = await service.quarantine_batch(session, code, actor)
    await session.commit()
    response.headers["X-Audit-Event-Id"] = str(event.id)
    return await service.get_batch(session, code)


@router.post("/batches/{code}/steps/{step_id}/sign", response_model=BatchStepRead)
async def sign_step(
    code: str,
    step_id: uuid.UUID,
    response: Response,
    principal: Principal = Depends(require_role("operator", human_only=True)),
    session: AsyncSession = Depends(get_session),
):
    actor = await sync_user(session, principal)
    step, event = await service.sign_step(session, code, step_id, actor)
    await session.commit()
    await session.refresh(step)
    response.headers["X-Audit-Event-Id"] = str(event.id)
    return BatchStepRead.model_validate(step)


@router.get("/tasks", response_model=Page[TaskRead])
async def list_tasks(
    assignee: str | None = Query(None, description="'me' or a user id"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
):
    assignee_id: uuid.UUID | None = None
    if assignee == "me":
        actor = await sync_user(session, principal)
        await session.commit()
        assignee_id = actor.id
    elif assignee:
        assignee_id = uuid.UUID(assignee)
    items, total = await service.list_tasks(
        session, assignee_id=assignee_id, page=page, limit=limit
    )
    return Page[TaskRead](
        items=[TaskRead.model_validate(t) for t in items], total=total, page=page
    )


@router.post("/tasks/{task_id}/complete", response_model=TaskRead)
async def complete_task(
    task_id: uuid.UUID,
    principal: Principal = Depends(require_role("operator", human_only=True)),
    session: AsyncSession = Depends(get_session),
):
    from ..errors import NotFoundError
    from ..models.enums import StatusToken
    from ..models.manufacturing import Task

    task = await session.get(Task, task_id)
    if task is None:
        raise NotFoundError(f"Task {task_id} not found")
    task.status = StatusToken.pass_
    await session.commit()
    await session.refresh(task)
    return TaskRead.model_validate(task)
