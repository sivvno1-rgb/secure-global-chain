"""Signed-telemetry ingestion path + verifier seam (AGENTS_AND_COMPUTE §5)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from sgc.errors import ConflictError, NotFoundError
from sgc.models.devices import Device
from sgc.models.enums import DeviceState, StreamKind
from sgc.models.telemetry import Reading, SensorStream
from sgc.telemetry.ingest import LocalDevTelemetryVerifier, reading_payload
from sgc.telemetry.service import ingest_signed_reading


async def _seed_device_stream(session, *, spec_low=2.0, spec_high=8.0):
    device = Device(
        serial="DEV-1182", state=DeviceState.online, hw_identity_pubkey="dev-pub:k"
    )
    session.add(device)
    await session.flush()
    stream = SensorStream(
        device_id=device.id, kind=StreamKind.temp, unit="C",
        spec_low=spec_low, spec_high=spec_high,
    )
    session.add(stream)
    await session.commit()
    return device, stream


def _valid_signature(pubkey, serial, value, ts):
    payload = reading_payload(
        serial, "temp", ts.astimezone(timezone.utc).isoformat(), value
    )
    return LocalDevTelemetryVerifier().sign(pubkey, payload)


@pytest.mark.asyncio
async def test_valid_signed_reading_is_written_in_spec(db_session):
    device, _ = await _seed_device_stream(db_session)
    ts = datetime.now(timezone.utc)
    sig = _valid_signature(device.hw_identity_pubkey, "DEV-1182", 5.0, ts)
    reading, in_spec = await ingest_signed_reading(
        db_session, serial="DEV-1182", kind=StreamKind.temp, value=5.0,
        ts=ts, signature=sig, verifier=LocalDevTelemetryVerifier(),
    )
    await db_session.commit()
    assert in_spec is True
    stored = (await db_session.execute(select(Reading))).scalars().all()
    assert len(stored) == 1
    assert stored[0].value == 5.0


@pytest.mark.asyncio
async def test_out_of_spec_reading_flagged(db_session):
    device, _ = await _seed_device_stream(db_session)
    ts = datetime.now(timezone.utc)
    sig = _valid_signature(device.hw_identity_pubkey, "DEV-1182", 11.0, ts)
    _, in_spec = await ingest_signed_reading(
        db_session, serial="DEV-1182", kind=StreamKind.temp, value=11.0,
        ts=ts, signature=sig, verifier=LocalDevTelemetryVerifier(),
    )
    assert in_spec is False


@pytest.mark.asyncio
async def test_bad_signature_quarantines_device_and_rejects(db_session):
    await _seed_device_stream(db_session)
    ts = datetime.now(timezone.utc)
    with pytest.raises(ConflictError):
        await ingest_signed_reading(
            db_session, serial="DEV-1182", kind=StreamKind.temp, value=5.0,
            ts=ts, signature="forged", verifier=LocalDevTelemetryVerifier(),
        )
    # The device is quarantined; no reading persisted.
    device = (
        await db_session.execute(select(Device).where(Device.serial == "DEV-1182"))
    ).scalar_one()
    assert device.state is DeviceState.quarantined
    assert device.tamper_locked is True
    assert (await db_session.execute(select(Reading))).scalars().first() is None


@pytest.mark.asyncio
async def test_unknown_device_raises_not_found(db_session):
    ts = datetime.now(timezone.utc)
    with pytest.raises(NotFoundError):
        await ingest_signed_reading(
            db_session, serial="NOPE", kind=StreamKind.temp, value=5.0,
            ts=ts, signature="x", verifier=LocalDevTelemetryVerifier(),
        )
