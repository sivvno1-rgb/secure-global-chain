"""Telemetry context models (DOMAIN_MODEL.md §Telemetry).

Cold chain, biosignal and cleanroom streams. ``readings`` is the high-volume,
time-series table — in production a Timescale hypertable / time-partitioned; here
it is ordinary relational with a ``(stream_id, ts)`` index.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base, UUIDType
from ._mixins import TimestampMixin
from .enums import Severity, ShipmentState, StatusToken, StreamKind, sa_enum


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)


class SensorStream(Base, TimestampMixin):
    __tablename__ = "sensor_streams"

    id: Mapped[uuid.UUID] = _pk()
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("devices.id"), nullable=False, index=True
    )
    kind: Mapped[StreamKind] = mapped_column(sa_enum(StreamKind), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    spec_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    spec_high: Mapped[float | None] = mapped_column(Float, nullable=True)

    readings: Mapped[list["Reading"]] = relationship(
        back_populates="stream", cascade="all, delete-orphan"
    )


class Reading(Base):
    __tablename__ = "readings"
    __table_args__ = (Index("ix_readings_stream_ts", "stream_id", "ts"),)

    id: Mapped[uuid.UUID] = _pk()
    stream_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("sensor_streams.id"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)

    stream: Mapped["SensorStream"] = relationship(back_populates="readings")


class ColdchainLane(Base, TimestampMixin):
    __tablename__ = "coldchain_lanes"

    id: Mapped[uuid.UUID] = _pk()
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    origin: Mapped[str | None] = mapped_column(String(64), nullable=True)
    destination: Mapped[str | None] = mapped_column(String(64), nullable=True)
    spec_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    spec_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[StatusToken] = mapped_column(
        sa_enum(StatusToken), nullable=False, default=StatusToken.neutral
    )


class Shipment(Base, TimestampMixin):
    __tablename__ = "shipments"

    id: Mapped[uuid.UUID] = _pk()
    lane_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("coldchain_lanes.id"), nullable=True
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("batches.id"), nullable=True
    )
    state: Mapped[ShipmentState] = mapped_column(
        sa_enum(ShipmentState), nullable=False, default=ShipmentState.in_transit
    )
    departed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    eta: Mapped[datetime | None] = mapped_column(nullable=True)


class Excursion(Base, TimestampMixin):
    __tablename__ = "excursions"

    id: Mapped[uuid.UUID] = _pk()
    lane_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("coldchain_lanes.id"), nullable=True
    )
    shipment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("shipments.id"), nullable=True
    )
    kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    peak_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[Severity] = mapped_column(sa_enum(Severity), nullable=False)
    disposition: Mapped[str | None] = mapped_column(String(255), nullable=True)
