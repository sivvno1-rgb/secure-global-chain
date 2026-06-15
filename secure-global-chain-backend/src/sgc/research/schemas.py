"""Pydantic v2 schemas for the Research & Evidence context."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ..models.enums import (
    EvidenceMethod,
    EvidenceState,
    HypothesisState,
    ValidationReportState,
)


class HypothesisCreate(BaseModel):
    title: str
    domain: str | None = None


class HypothesisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    posed_by: uuid.UUID | None
    state: HypothesisState
    domain: str | None


class EvidenceRunCreate(BaseModel):
    title: str
    method: EvidenceMethod
    hypothesis_id: uuid.UUID | None = None
    dataset_ref: str | None = None
    params: dict = {}


class EvidenceResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    statistic: str
    value: float | None
    ci_low: float | None
    ci_high: float | None
    p_value: float | None
    posterior_ref: str | None


class EvidencePacketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    hypothesis_id: uuid.UUID | None
    title: str
    dataset_ref: str | None
    method: EvidenceMethod
    summary: str | None
    generated_by: str | None
    reviewed_by: uuid.UUID | None
    state: EvidenceState
    results: list[EvidenceResultRead]


class ValidationReportCreate(BaseModel):
    scope: str | None = None


class ValidationReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    scope: str | None
    author_id: uuid.UUID | None
    state: ValidationReportState
    signed_by: uuid.UUID | None
    signed_at: datetime | None
