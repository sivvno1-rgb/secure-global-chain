"""Pydantic v2 schemas for the Optimization & Scenario Lab context."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ..models.enums import ScheduleState, SolverStatus


class JobInput(BaseModel):
    batch_id: uuid.UUID | None = None
    duration_minutes: int
    setup_minutes: int = 0


class ScheduleCreate(BaseModel):
    line_id: uuid.UUID | None = None
    horizon: int  # minutes
    objective: str | None = "makespan"
    jobs: list[JobInput]


class ScheduleSlotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    batch_id: uuid.UUID | None
    start_at: int | None
    end_at: int | None
    setup_minutes: int


class ScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_id: uuid.UUID | None
    horizon: int | None
    objective: str | None
    generated_by: str | None
    state: ScheduleState
    solver_status: SolverStatus | None
    committed_by: uuid.UUID | None
    committed_at: datetime | None
    slots: list[ScheduleSlotRead]


class ScenarioCreate(BaseModel):
    name: str
    base_schedule_id: uuid.UUID
    params: dict = {}


class ScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    base_schedule_id: uuid.UUID | None
    params: dict
    kpi_delta: dict
    created_by: uuid.UUID | None
