"""Pydantic v2 response schemas. Field names match DOMAIN_MODEL.md exactly."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ..models.enums import BatchStatus, StatusToken, TaskKind
from ..pagination import Page

__all__ = [
    "Page",
    "LineRead",
    "BatchSummary",
    "BatchStepRead",
    "IpcCheckRead",
    "BatchDetail",
    "TaskRead",
    "MissionSummary",
]


class LineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    stage: str | None
    uptime_pct: float | None
    status: StatusToken


class BatchSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    line_id: uuid.UUID | None
    stage: str | None
    status: BatchStatus
    yield_pct: float | None


class BatchStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    sequence: int
    signed_by: uuid.UUID | None
    signed_at: datetime | None
    record_url: str | None


class IpcCheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    value: float | None
    spec_low: float | None
    spec_high: float | None
    result: StatusToken
    at: datetime | None


class BatchDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    product_id: uuid.UUID | None
    line_id: uuid.UUID | None
    stage: str | None
    status: BatchStatus
    yield_pct: float | None
    started_at: datetime | None
    released_at: datetime | None
    released_by: uuid.UUID | None
    steps: list[BatchStepRead]
    ipc_checks: list[IpcCheckRead]


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    kind: TaskKind
    due_at: datetime | None
    status: StatusToken
    batch_id: uuid.UUID | None
    assignee_id: uuid.UUID | None


class MissionSummary(BaseModel):
    supply_on_time_pct: float
    line_uptime_pct: float
    batches_in_process: int
    batches_released: int
