"""Quality & Compliance API. Prefix ``/api/v1``.

Consequential verbs are explicit sub-resources protected by role + human actor
and write an audit event; mutating responses carry ``X-Audit-Event-Id``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models.enums import Framework, QualityState, Severity, StatusToken
from ..security import (
    Principal,
    get_current_principal,
    require_any_role,
    require_role,
)
from ..security.users import sync_user
from . import service
from .schemas import (
    AuditFindingRead,
    AuditRead,
    CapaRead,
    ComplianceItemRead,
    DeviationCreate,
    DeviationRead,
    EffectivenessRequest,
)
from ..pagination import Page

router = APIRouter(prefix="/api/v1", tags=["quality"])


@router.get("/deviations", response_model=Page[DeviationRead])
async def list_deviations(
    severity: Severity | None = None,
    state: QualityState | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    items, total = await service.list_deviations(
        session, severity=severity, state=state, page=page, limit=limit
    )
    return Page[DeviationRead](
        items=[DeviationRead.model_validate(d) for d in items],
        total=total,
        page=page,
    )


@router.post(
    "/deviations",
    response_model=DeviationRead,
    status_code=status.HTTP_201_CREATED,
)
async def raise_deviation(
    body: DeviationCreate,
    response: Response,
    principal: Principal = Depends(
        require_any_role("operator", "quality", human_only=True)
    ),
    session: AsyncSession = Depends(get_session),
):
    actor = await sync_user(session, principal)
    deviation, event = await service.raise_deviation(
        session,
        actor=actor,
        title=body.title,
        severity=body.severity,
        line_id=body.line_id,
        batch_id=body.batch_id,
        description=body.description,
    )
    await session.commit()
    await session.refresh(deviation)
    response.headers["X-Audit-Event-Id"] = str(event.id)
    return DeviationRead.model_validate(deviation)


@router.post("/deviations/{code}/escalate", response_model=DeviationRead)
async def escalate_deviation(
    code: str,
    response: Response,
    principal: Principal = Depends(require_role("quality", human_only=True)),
    session: AsyncSession = Depends(get_session),
):
    actor = await sync_user(session, principal)
    deviation, event = await service.escalate_deviation(session, code, actor)
    await session.commit()
    await session.refresh(deviation)
    response.headers["X-Audit-Event-Id"] = str(event.id)
    return DeviationRead.model_validate(deviation)


@router.get("/capas", response_model=Page[CapaRead])
async def list_capas(
    status_token: StatusToken | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    items, total = await service.list_capas(
        session, status=status_token, page=page, limit=limit
    )
    return Page[CapaRead](
        items=[CapaRead.model_validate(c) for c in items], total=total, page=page
    )


@router.post("/capas/{code}/effectiveness", response_model=CapaRead)
async def record_effectiveness(
    code: str,
    body: EffectivenessRequest,
    response: Response,
    principal: Principal = Depends(require_role("quality", human_only=True)),
    session: AsyncSession = Depends(get_session),
):
    actor = await sync_user(session, principal)
    capa, event = await service.record_capa_effectiveness(
        session,
        code,
        actor,
        result_token=body.result,
        effectiveness_state=body.effectiveness_state,
        on_time_pct=body.on_time_pct,
    )
    await session.commit()
    await session.refresh(capa)
    response.headers["X-Audit-Event-Id"] = str(event.id)
    return CapaRead.model_validate(capa)


@router.get("/audits", response_model=list[AuditRead])
async def list_audits(
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    return await service.list_audits(session)


@router.get("/audits/{audit_id}/findings", response_model=list[AuditFindingRead])
async def list_audit_findings(
    audit_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    return await service.list_audit_findings(session, audit_id)


@router.get("/compliance/area", response_model=list[ComplianceItemRead])
async def compliance_area(
    framework: Framework | None = None,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    return await service.list_compliance_items(session, framework=framework)
