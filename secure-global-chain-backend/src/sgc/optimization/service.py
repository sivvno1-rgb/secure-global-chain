"""Optimization & Scenario Lab service layer.

Runs CP-SAT solves (synchronous here; Celery ``optimize`` queue in prod), stores
schedules + slots + honest ``solver_status``, runs what-if scenarios computing
``kpi_delta``, and the human-gated **commit** (a person commits the advisory plan).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..audit import AuditPayload, append_audit_event
from ..errors import ConflictError, NotFoundError
from ..models.audit import AuditEvent
from ..models.enums import ScheduleState, SolverStatus
from ..models.optimization import Schedule, ScheduleSlot, Scenario
from ..models.user import User
from .solver import Job, ScheduleSolver


async def get_schedule(session: AsyncSession, schedule_id: uuid.UUID) -> Schedule:
    result = await session.execute(
        select(Schedule)
        .where(Schedule.id == schedule_id)
        .options(selectinload(Schedule.slots))
    )
    schedule = result.scalar_one_or_none()
    if schedule is None:
        raise NotFoundError(f"Schedule {schedule_id} not found")
    return schedule


async def create_schedule(
    session: AsyncSession,
    *,
    actor: User,
    solver: ScheduleSolver,
    line_id: uuid.UUID | None,
    horizon: int,
    objective: str | None,
    jobs: list[dict],
) -> tuple[Schedule, AuditEvent]:
    solver_jobs = [
        Job(
            batch_id=str(j["batch_id"]) if j.get("batch_id") else None,
            duration_minutes=int(j["duration_minutes"]),
            setup_minutes=int(j.get("setup_minutes", 0)),
        )
        for j in jobs
    ]
    result = solver.solve(solver_jobs, horizon_minutes=horizon)

    schedule = Schedule(
        line_id=line_id,
        horizon=horizon,
        objective=objective,
        generated_by="cp-sat",
        solver_status=result.status,
        state=(
            ScheduleState.solved
            if result.status in (SolverStatus.optimal, SolverStatus.feasible)
            else ScheduleState.failed
        ),
    )
    session.add(schedule)
    await session.flush()

    for slot in result.slots:
        session.add(ScheduleSlot(
            schedule_id=schedule.id,
            batch_id=uuid.UUID(slot.batch_id) if slot.batch_id else None,
            start_at=slot.start_at,
            end_at=slot.end_at,
            setup_minutes=slot.setup_minutes,
        ))
    await session.flush()

    event = await append_audit_event(
        session,
        AuditPayload(
            actor_id=actor.id,
            action="optimize",
            object_type="schedule",
            object_id=str(schedule.id),
            after={"solver_status": result.status.value, "state": schedule.state.value,
                   "makespan": result.makespan, "slots": len(result.slots)},
        ),
    )
    return schedule, event


async def commit_schedule(
    session: AsyncSession, schedule_id: uuid.UUID, actor: User
) -> tuple[Schedule, AuditEvent]:
    """Human-gated commit of an advisory schedule (route requires ``planner``)."""
    schedule = await get_schedule(session, schedule_id)
    if schedule.state == ScheduleState.committed:
        raise ConflictError("Schedule is already committed")
    if schedule.state != ScheduleState.solved:
        raise ConflictError(f"Schedule is {schedule.state.value}; only solved schedules can be committed")

    before = {"state": schedule.state.value}
    schedule.state = ScheduleState.committed
    schedule.committed_by = actor.id
    schedule.committed_at = datetime.now(timezone.utc)

    event = await append_audit_event(
        session,
        AuditPayload(
            actor_id=actor.id,
            action="commit",
            object_type="schedule",
            object_id=str(schedule.id),
            before=before,
            after={"state": schedule.state.value},
        ),
    )
    return schedule, event


def _makespan(schedule: Schedule) -> int:
    ends = [s.end_at for s in schedule.slots if s.end_at is not None]
    return max(ends) if ends else 0


async def run_scenario(
    session: AsyncSession,
    *,
    actor: User,
    solver: ScheduleSolver,
    name: str,
    base_schedule_id: uuid.UUID,
    params: dict,
) -> tuple[Scenario, AuditEvent]:
    """Re-solve a base schedule with perturbed params; persist KPI deltas."""
    base = await get_schedule(session, base_schedule_id)
    if not base.slots:
        raise ConflictError("Base schedule has no slots to perturb")

    duration_scale = float(params.get("duration_scale", 1.0))
    horizon_scale = float(params.get("horizon_scale", 1.0))
    base_makespan = _makespan(base)

    jobs = [
        Job(
            batch_id=str(s.batch_id) if s.batch_id else None,
            duration_minutes=max(
                1, int(round(((s.end_at or 0) - (s.start_at or 0) - s.setup_minutes) * duration_scale))
            ),
            setup_minutes=s.setup_minutes,
        )
        for s in base.slots
    ]
    horizon = int(round((base.horizon or base_makespan) * horizon_scale))
    result = solver.solve(jobs, horizon_minutes=horizon)
    scenario_makespan = result.makespan if result.makespan is not None else None

    kpi_delta = {
        "base_makespan_minutes": base_makespan,
        "scenario_makespan_minutes": scenario_makespan,
        "delta_minutes": (
            scenario_makespan - base_makespan if scenario_makespan is not None else None
        ),
        "solver_status": result.status.value,
    }
    scenario = Scenario(
        name=name,
        base_schedule_id=base_schedule_id,
        params=params,
        kpi_delta=kpi_delta,
        created_by=actor.id,
    )
    session.add(scenario)
    await session.flush()

    event = await append_audit_event(
        session,
        AuditPayload(
            actor_id=actor.id,
            action="scenario",
            object_type="scenario",
            object_id=str(scenario.id),
            after=kpi_delta,
        ),
    )
    return scenario, event


async def get_scenario(session: AsyncSession, scenario_id: uuid.UUID) -> Scenario:
    scenario = await session.get(Scenario, scenario_id)
    if scenario is None:
        raise NotFoundError(f"Scenario {scenario_id} not found")
    return scenario
