"""Optimization & Scenario Lab API. Prefix ``/api/v1/optimization``.

Solve schedules (CP-SAT, behind the seam), run what-if scenarios, and the
human-gated **commit** of an advisory schedule.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..security import Principal, get_current_principal, require_role
from ..security.users import sync_user
from . import service
from .schemas import (
    ScenarioCreate,
    ScenarioRead,
    ScheduleCreate,
    ScheduleRead,
)
from .solver import ScheduleSolver, get_schedule_solver

router = APIRouter(prefix="/api/v1/optimization", tags=["optimization"])


@router.post(
    "/schedules", response_model=ScheduleRead, status_code=status.HTTP_201_CREATED
)
async def create_schedule(
    body: ScheduleCreate,
    response: Response,
    principal: Principal = Depends(require_role("planner", human_only=True)),
    session: AsyncSession = Depends(get_session),
    solver: ScheduleSolver = Depends(get_schedule_solver),
):
    actor = await sync_user(session, principal)
    schedule, event = await service.create_schedule(
        session, actor=actor, solver=solver, line_id=body.line_id,
        horizon=body.horizon, objective=body.objective,
        jobs=[j.model_dump() for j in body.jobs],
    )
    await session.commit()
    response.headers["X-Audit-Event-Id"] = str(event.id)
    return await service.get_schedule(session, schedule.id)


@router.get("/schedules/{schedule_id}", response_model=ScheduleRead)
async def get_schedule(
    schedule_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    return await service.get_schedule(session, schedule_id)


@router.post("/schedules/{schedule_id}/commit", response_model=ScheduleRead)
async def commit_schedule(
    schedule_id: uuid.UUID,
    response: Response,
    principal: Principal = Depends(require_role("planner", human_only=True)),
    session: AsyncSession = Depends(get_session),
):
    actor = await sync_user(session, principal)
    schedule, event = await service.commit_schedule(session, schedule_id, actor)
    await session.commit()
    response.headers["X-Audit-Event-Id"] = str(event.id)
    return await service.get_schedule(session, schedule.id)


@router.post(
    "/scenarios", response_model=ScenarioRead, status_code=status.HTTP_201_CREATED
)
async def create_scenario(
    body: ScenarioCreate,
    response: Response,
    principal: Principal = Depends(require_role("planner", human_only=True)),
    session: AsyncSession = Depends(get_session),
    solver: ScheduleSolver = Depends(get_schedule_solver),
):
    actor = await sync_user(session, principal)
    scenario, event = await service.run_scenario(
        session, actor=actor, solver=solver, name=body.name,
        base_schedule_id=body.base_schedule_id, params=body.params,
    )
    await session.commit()
    await session.refresh(scenario)
    response.headers["X-Audit-Event-Id"] = str(event.id)
    return ScenarioRead.model_validate(scenario)


@router.get("/scenarios/{scenario_id}", response_model=ScenarioRead)
async def get_scenario(
    scenario_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    return await service.get_scenario(session, scenario_id)
