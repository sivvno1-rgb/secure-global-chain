"""Device Fleet context models (DOMAIN_MODEL.md §Device Fleet).

NeuroSecure secure-MCU devices. Device identity keys and the firmware signing key
live in **Vault PKI**, not Postgres — only public keys, digests, and references
are stored here (SECURITY.md §2-3).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base, UUIDType
from ._mixins import TimestampMixin
from .enums import DeviceState, FirmwareState, StatusToken, sa_enum


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)


class FirmwareBuild(Base, TimestampMixin):
    __tablename__ = "firmware_builds"

    id: Mapped[uuid.UUID] = _pk()
    version: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )
    # "sha256:…" — set when signed; the signature itself lives in Vault.
    digest: Mapped[str | None] = mapped_column(String(128), nullable=True)
    signed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id"), nullable=True
    )
    signed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    state: Mapped[FirmwareState] = mapped_column(
        sa_enum(FirmwareState), nullable=False, default=FirmwareState.draft
    )
    release_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_url: Mapped[str | None] = mapped_column(String(512), nullable=True)


class Device(Base, TimestampMixin):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = _pk()
    serial: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    model: Mapped[str] = mapped_column(String(64), nullable=False, default="NeuroSecure")
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("sites.id"), nullable=True
    )
    line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("lines.id"), nullable=True
    )
    # Public key only — the private hardware identity key never leaves the device.
    hw_identity_pubkey: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[DeviceState] = mapped_column(
        sa_enum(DeviceState), nullable=False, default=DeviceState.provisioned
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(nullable=True)
    firmware_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("firmware_builds.id"), nullable=True
    )
    tamper_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    firmware: Mapped["FirmwareBuild | None"] = relationship()
    attestations: Mapped[list["DeviceAttestation"]] = relationship(
        back_populates="device",
        order_by="DeviceAttestation.at",
        cascade="all, delete-orphan",
    )


class FirmwareRollout(Base, TimestampMixin):
    __tablename__ = "firmware_rollouts"

    id: Mapped[uuid.UUID] = _pk()
    firmware_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("firmware_builds.id"), nullable=False, index=True
    )
    cohort: Mapped[str | None] = mapped_column(String(128), nullable=True)
    devices_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    devices_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[FirmwareState] = mapped_column(
        sa_enum(FirmwareState), nullable=False, default=FirmwareState.staged
    )
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    started_by: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id"), nullable=True
    )


class DeviceAttestation(Base, TimestampMixin):
    __tablename__ = "device_attestations"

    id: Mapped[uuid.UUID] = _pk()
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("devices.id"), nullable=False, index=True
    )
    firmware_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("firmware_builds.id"), nullable=True
    )
    measured_digest: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verdict: Mapped[StatusToken] = mapped_column(
        sa_enum(StatusToken), nullable=False, default=StatusToken.neutral
    )
    at: Mapped[datetime | None] = mapped_column(nullable=True)

    device: Mapped["Device"] = relationship(back_populates="attestations")


class ProvisionRequest(Base, TimestampMixin):
    __tablename__ = "provision_requests"

    id: Mapped[uuid.UUID] = _pk()
    device_serial: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id"), nullable=True
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    at: Mapped[datetime | None] = mapped_column(nullable=True)
