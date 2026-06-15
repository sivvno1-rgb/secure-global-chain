"""Pydantic v2 schemas for the Telemetry & cold-chain context."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ..models.enums import Severity, StatusToken, StreamKind


class ReadingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stream_id: uuid.UUID
    kind: StreamKind
    unit: str | None
    ts: datetime
    value: float | None


class ColdchainLaneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    origin: str | None
    destination: str | None
    spec_low: float | None
    spec_high: float | None
    status: StatusToken


class ExcursionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lane_id: uuid.UUID | None
    shipment_id: uuid.UUID | None
    kind: str | None
    started_at: datetime | None
    ended_at: datetime | None
    peak_value: float | None
    severity: Severity
    disposition: str | None


class DispositionRequest(BaseModel):
    disposition: str
    close: bool = True
