"""Pydantic v2 schemas for the Quality & Compliance context."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ..models.enums import Framework, QualityState, Severity, StatusToken


class DeviationCreate(BaseModel):
    title: str
    severity: Severity
    line_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    description: str | None = None


class DeviationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    title: str
    severity: Severity
    line_id: uuid.UUID | None
    batch_id: uuid.UUID | None
    state: QualityState
    raised_by: uuid.UUID | None
    raised_at: datetime | None
    description: str | None


class CapaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    deviation_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    due_at: datetime | None
    effectiveness_state: str | None
    on_time_pct: float | None
    status: StatusToken


class EffectivenessRequest(BaseModel):
    result: StatusToken
    effectiveness_state: str | None = None
    on_time_pct: float | None = None


class ComplianceItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    framework: Framework
    area: str | None
    title: str
    state: StatusToken
    evidence_url: str | None


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scope: str | None
    framework: Framework
    readiness_pct: float | None
    scheduled_at: datetime | None
    lead_id: uuid.UUID | None


class AuditFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    audit_id: uuid.UUID
    framework: Framework
    severity: Severity
    status: StatusToken
    remediation_due: datetime | None
