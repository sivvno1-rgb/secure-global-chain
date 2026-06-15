"""Telemetry & cold-chain API. Prefix ``/api/v1``.

REST reads plus the human-gated, audited excursion disposition. Live readings
over ``WS /ws/telemetry`` (Redis fan-out) are a follow-up; ingestion of signed
telemetry runs in the Celery ingest worker via :mod:`sgc.telemetry.service`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models.enums import StreamKind
from ..pagination import Page
from ..security import Principal, get_current_principal, require_role
from ..security.users import sync_user
from . import service
from .schemas import (
    ColdchainLaneRead,
    DispositionRequest,
    ExcursionRead,
    ReadingRead,
)

router = APIRouter(prefix="/api/v1", tags=["telemetry"])


@router.get("/streams/{device}/readings", response_model=Page[ReadingRead])
async def list_readings(
    device: str,
    kind: StreamKind | None = None,
    ts_from: datetime | None = Query(None, alias="from"),
    ts_to: datetime | None = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    limit: int = Query(200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    rows, total = await service.list_readings(
        session, device, kind=kind, ts_from=ts_from, ts_to=ts_to, page=page, limit=limit
    )
    items = [
        ReadingRead(
            stream_id=reading.stream_id,
            kind=stream.kind,
            unit=stream.unit,
            ts=reading.ts,
            value=reading.value,
        )
        for reading, stream in rows
    ]
    return Page[ReadingRead](items=items, total=total, page=page)


@router.get("/coldchain/lanes", response_model=list[ColdchainLaneRead])
async def list_lanes(
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    return await service.list_lanes(session)


@router.get("/coldchain/excursions", response_model=list[ExcursionRead])
async def list_excursions(
    lane: uuid.UUID | None = None,
    open: bool | None = None,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    return await service.list_excursions(session, lane_id=lane, open_only=open)


@router.post(
    "/coldchain/excursions/{excursion_id}/disposition",
    response_model=ExcursionRead,
)
async def disposition_excursion(
    excursion_id: uuid.UUID,
    body: DispositionRequest,
    response: Response,
    principal: Principal = Depends(require_role("quality", human_only=True)),
    session: AsyncSession = Depends(get_session),
):
    actor = await sync_user(session, principal)
    excursion, event = await service.disposition_excursion(
        session, excursion_id, actor, disposition=body.disposition, close=body.close
    )
    await session.commit()
    await session.refresh(excursion)
    response.headers["X-Audit-Event-Id"] = str(event.id)
    return ExcursionRead.model_validate(excursion)
