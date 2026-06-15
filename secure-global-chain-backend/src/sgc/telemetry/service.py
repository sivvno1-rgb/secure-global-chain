"""Telemetry & cold-chain service layer.

Read queries, the human-gated excursion disposition (audited), and the
signed-ingestion path used by the ingest worker (verify → write reading →
quarantine on signature failure).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import AuditPayload, append_audit_event
from ..errors import ConflictError, NotFoundError
from ..models.audit import AuditEvent
from ..models.devices import Device
from ..models.enums import DeviceState, StreamKind
from ..models.telemetry import (
    ColdchainLane,
    Excursion,
    Reading,
    SensorStream,
    Shipment,
)
from ..models.user import User
from .ingest import TelemetryVerifier, reading_payload


async def list_readings(
    session: AsyncSession,
    serial: str,
    *,
    kind: StreamKind | None = None,
    ts_from: datetime | None = None,
    ts_to: datetime | None = None,
    page: int = 1,
    limit: int = 200,
) -> tuple[list[tuple[Reading, SensorStream]], int]:
    device = await session.scalar(select(Device).where(Device.serial == serial))
    if device is None:
        raise NotFoundError(f"Device {serial} not found")

    filters = [SensorStream.device_id == device.id]
    if kind is not None:
        filters.append(SensorStream.kind == kind)
    if ts_from is not None:
        filters.append(Reading.ts >= ts_from)
    if ts_to is not None:
        filters.append(Reading.ts <= ts_to)

    base = select(Reading, SensorStream).join(
        SensorStream, Reading.stream_id == SensorStream.id
    ).where(*filters)
    total = await session.scalar(
        select(func.count()).select_from(base.subquery())
    )
    result = await session.execute(
        base.order_by(Reading.ts).offset((page - 1) * limit).limit(limit)
    )
    return list(result.all()), int(total or 0)


async def list_lanes(session: AsyncSession) -> list[ColdchainLane]:
    result = await session.execute(
        select(ColdchainLane).order_by(ColdchainLane.code)
    )
    return list(result.scalars())


async def list_excursions(
    session: AsyncSession,
    *,
    lane_id: uuid.UUID | None = None,
    open_only: bool | None = None,
) -> list[Excursion]:
    filters = []
    if lane_id is not None:
        filters.append(Excursion.lane_id == lane_id)
    if open_only:
        filters.append(Excursion.ended_at.is_(None))
    result = await session.execute(
        select(Excursion).where(*filters).order_by(Excursion.started_at)
    )
    return list(result.scalars())


async def disposition_excursion(
    session: AsyncSession,
    excursion_id: uuid.UUID,
    actor: User,
    *,
    disposition: str,
    close: bool = True,
) -> tuple[Excursion, AuditEvent]:
    """Human-gated cold-chain excursion disposition (route requires ``quality``)."""
    excursion = await session.get(Excursion, excursion_id)
    if excursion is None:
        raise NotFoundError(f"Excursion {excursion_id} not found")
    if excursion.disposition is not None:
        raise ConflictError("Excursion already dispositioned")

    before = {"disposition": excursion.disposition, "ended_at": None}
    excursion.disposition = disposition
    if close and excursion.ended_at is None:
        excursion.ended_at = datetime.now(timezone.utc)

    event = await append_audit_event(
        session,
        AuditPayload(
            actor_id=actor.id,
            action="disposition",
            object_type="excursion",
            object_id=str(excursion.id),
            before=before,
            after={
                "disposition": disposition,
                "ended_at": excursion.ended_at.isoformat() if excursion.ended_at else None,
            },
        ),
    )
    return excursion, event


async def ingest_signed_reading(
    session: AsyncSession,
    *,
    serial: str,
    kind: StreamKind,
    value: float,
    ts: datetime,
    signature: str,
    verifier: TelemetryVerifier,
) -> tuple[Reading, bool]:
    """Verify a signed reading, persist it, and report whether it is in-spec.

    On signature failure the device is **quarantined** and the reading rejected
    (AGENTS_AND_COMPUTE.md §5). Returns ``(reading, in_spec)`` on success.
    """
    device = await session.scalar(select(Device).where(Device.serial == serial))
    if device is None:
        raise NotFoundError(f"Device {serial} not found")

    payload = reading_payload(serial, kind.value, ts.astimezone(timezone.utc).isoformat(), value)
    if not verifier.verify(device.hw_identity_pubkey, payload, signature):
        before = {"state": device.state.value}
        device.state = DeviceState.quarantined
        device.tamper_locked = True
        await append_audit_event(
            session,
            AuditPayload(
                actor_id=None,
                action="quarantine",
                object_type="device",
                object_id=serial,
                before=before,
                after={"state": device.state.value, "reason": "signature_verification_failed"},
            ),
        )
        raise ConflictError(f"Invalid telemetry signature for device {serial}")

    stream = await session.scalar(
        select(SensorStream).where(
            SensorStream.device_id == device.id, SensorStream.kind == kind
        )
    )
    if stream is None:
        raise NotFoundError(f"No {kind.value} stream for device {serial}")

    reading = Reading(stream_id=stream.id, ts=ts, value=value)
    session.add(reading)
    await session.flush()

    in_spec = True
    if stream.spec_low is not None and value < stream.spec_low:
        in_spec = False
    if stream.spec_high is not None and value > stream.spec_high:
        in_spec = False
    return reading, in_spec
