"""Pydantic v2 schemas for the Device Fleet context."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ..models.enums import DeviceState, FirmwareState, StatusToken


class DeviceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    serial: str
    model: str
    state: DeviceState
    firmware_id: uuid.UUID | None
    last_seen_at: datetime | None


class AttestationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    firmware_id: uuid.UUID | None
    measured_digest: str | None
    verdict: StatusToken
    at: datetime | None


class DeviceDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    serial: str
    model: str
    site_id: uuid.UUID | None
    line_id: uuid.UUID | None
    hw_identity_pubkey: str | None
    state: DeviceState
    last_seen_at: datetime | None
    firmware_id: uuid.UUID | None
    tamper_locked: bool
    attestations: list[AttestationRead]


class FirmwareBuildRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: str
    digest: str | None
    signed_by: uuid.UUID | None
    signed_at: datetime | None
    state: FirmwareState
    release_notes: str | None
    artifact_url: str | None


class FirmwareRolloutRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    firmware_id: uuid.UUID
    cohort: str | None
    devices_total: int
    devices_done: int
    state: FirmwareState
    started_at: datetime | None
    started_by: uuid.UUID | None


class ProvisionRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_serial: str
    requested_by: uuid.UUID | None
    approved_by: uuid.UUID | None
    status: str
    at: datetime | None


class ProvisionCreate(BaseModel):
    device_serial: str
    site_id: uuid.UUID | None = None
    line_id: uuid.UUID | None = None


class RolloutCreate(BaseModel):
    cohort: str | None = None
    devices_total: int = 0
