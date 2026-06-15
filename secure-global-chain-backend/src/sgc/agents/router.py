"""Agent mesh API. Prefix ``/api/v1/agents``.

Mesh status, run log, invoke (produces a proposal), and human disposition.
**No endpoint here finalizes a consequential action** — agents propose; a human
accepts via the relevant center's human-gated route.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..security import (
    Principal,
    get_current_principal,
    require_human,
)
from ..security.users import sync_user
from . import service
from .mesh import AgentMesh, get_agent_mesh
from .schemas import AgentRunRead, AgentStatus, DispositionRequest, InvokeRequest

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@router.get("", response_model=list[AgentStatus])
async def list_agents(
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    return await service.list_agents(session)


@router.get("/runs", response_model=list[AgentRunRead])
async def list_runs(
    agent: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    return await service.list_runs(session, agent=agent)


@router.post(
    "/{agent}/invoke", response_model=AgentRunRead, status_code=status.HTTP_201_CREATED
)
async def invoke_agent(
    agent: str,
    body: InvokeRequest,
    mesh: AgentMesh = Depends(get_agent_mesh),
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    run = await service.invoke_agent(
        session, agent=agent, mesh=mesh, input_ref=body.input_ref, params=body.params
    )
    await session.commit()
    await session.refresh(run)
    return AgentRunRead.model_validate(run)


@router.post("/runs/{run_id}/disposition", response_model=AgentRunRead)
async def disposition_run(
    run_id: uuid.UUID,
    body: DispositionRequest,
    response: Response,
    principal: Principal = Depends(require_human),
    session: AsyncSession = Depends(get_session),
):
    actor = await sync_user(session, principal)
    run, event = await service.disposition_run(
        session, run_id, actor, disposition=body.disposition, note=body.note
    )
    await session.commit()
    await session.refresh(run)
    response.headers["X-Audit-Event-Id"] = str(event.id)
    return AgentRunRead.model_validate(run)
