"""Research & Evidence API. Prefix ``/api/v1/research``.

Hypotheses, evidence runs (compute behind the seam), and validation reports. The
report **sign** is the human-gated, audited e-signature (qa_release).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models.enums import HypothesisState
from ..security import Principal, get_current_principal, require_role
from ..security.users import sync_user
from . import service
from .compute import EvidenceComputer, get_evidence_computer
from .schemas import (
    EvidencePacketRead,
    EvidenceRunCreate,
    HypothesisCreate,
    HypothesisRead,
    ValidationReportCreate,
    ValidationReportRead,
)

router = APIRouter(prefix="/api/v1/research", tags=["research"])


@router.get("/hypotheses", response_model=list[HypothesisRead])
async def list_hypotheses(
    state: HypothesisState | None = None,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    return await service.list_hypotheses(session, state=state)


@router.post(
    "/hypotheses", response_model=HypothesisRead, status_code=status.HTTP_201_CREATED
)
async def pose_hypothesis(
    body: HypothesisCreate,
    response: Response,
    principal: Principal = Depends(require_role("scientist", human_only=True)),
    session: AsyncSession = Depends(get_session),
):
    actor = await sync_user(session, principal)
    hypothesis, event = await service.pose_hypothesis(
        session, actor=actor, title=body.title, domain=body.domain
    )
    await session.commit()
    await session.refresh(hypothesis)
    response.headers["X-Audit-Event-Id"] = str(event.id)
    return HypothesisRead.model_validate(hypothesis)


@router.get("/evidence/{packet_id}", response_model=EvidencePacketRead)
async def get_evidence(
    packet_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    return await service.get_packet(session, packet_id)


@router.post(
    "/evidence", response_model=EvidencePacketRead, status_code=status.HTTP_201_CREATED
)
async def run_evidence(
    body: EvidenceRunCreate,
    response: Response,
    principal: Principal = Depends(require_role("scientist", human_only=True)),
    session: AsyncSession = Depends(get_session),
    computer: EvidenceComputer = Depends(get_evidence_computer),
):
    actor = await sync_user(session, principal)
    packet, event = await service.run_evidence(
        session, actor=actor, title=body.title, method=body.method,
        computer=computer, hypothesis_id=body.hypothesis_id,
        dataset_ref=body.dataset_ref, params=body.params,
    )
    await session.commit()
    response.headers["X-Audit-Event-Id"] = str(event.id)
    return await service.get_packet(session, packet.id)


@router.get("/validation-reports", response_model=list[ValidationReportRead])
async def list_validation_reports(
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    return await service.list_validation_reports(session)


@router.post(
    "/validation-reports",
    response_model=ValidationReportRead,
    status_code=status.HTTP_201_CREATED,
)
async def author_validation_report(
    body: ValidationReportCreate,
    response: Response,
    principal: Principal = Depends(require_role("scientist", human_only=True)),
    session: AsyncSession = Depends(get_session),
):
    actor = await sync_user(session, principal)
    report, event = await service.author_validation_report(
        session, actor=actor, scope=body.scope
    )
    await session.commit()
    await session.refresh(report)
    response.headers["X-Audit-Event-Id"] = str(event.id)
    return ValidationReportRead.model_validate(report)


@router.post(
    "/validation-reports/{code}/sign", response_model=ValidationReportRead
)
async def sign_validation_report(
    code: str,
    response: Response,
    principal: Principal = Depends(require_role("qa_release", human_only=True)),
    session: AsyncSession = Depends(get_session),
):
    actor = await sync_user(session, principal)
    report, event = await service.sign_validation_report(session, code, actor)
    await session.commit()
    await session.refresh(report)
    response.headers["X-Audit-Event-Id"] = str(event.id)
    return ValidationReportRead.model_validate(report)
