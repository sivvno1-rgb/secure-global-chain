"""Device models + the PKI seam stub."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from sgc.devices.pki import LocalDevIdentityProvider, LocalDevSigner
from sgc.models.devices import Device, DeviceAttestation, FirmwareBuild
from sgc.models.enums import DeviceState, FirmwareState, StatusToken


@pytest.mark.asyncio
async def test_device_and_attestation_persist(db_session):
    fw = FirmwareBuild(version="v4.2.1", state=FirmwareState.signed,
                       digest="sha256:abc")
    db_session.add(fw)
    await db_session.flush()
    dev = Device(serial="DEV-1182", model="NeuroSecure", state=DeviceState.online,
                 firmware_id=fw.id, hw_identity_pubkey="dev-pub:x")
    db_session.add(dev)
    await db_session.flush()
    att = DeviceAttestation(device_id=dev.id, firmware_id=fw.id,
                            measured_digest="sha256:abc", verdict=StatusToken.pass_)
    db_session.add(att)
    await db_session.commit()

    loaded = (
        await db_session.execute(select(Device).where(Device.serial == "DEV-1182"))
    ).scalar_one()
    assert loaded.state is DeviceState.online


@pytest.mark.asyncio
async def test_device_enum_value_strings(db_session):
    dev = Device(serial="DEV-9", state=DeviceState.quarantined)
    db_session.add(dev)
    await db_session.commit()
    raw = await db_session.execute(
        select(Device.__table__.c.state).where(Device.__table__.c.serial == "DEV-9")
    )
    assert raw.scalar_one() == "Quarantined"
    assert FirmwareState.rolled_back.value == "Rolled back"
    assert DeviceState.transmitting.value == "Transmitting"


def test_local_dev_signer_is_deterministic_sha256():
    signer = LocalDevSigner()
    a = signer.sign("v4.2.1", "s3://fw/v4.2.1")
    b = signer.sign("v4.2.1", "s3://fw/v4.2.1")
    assert a.digest == b.digest
    assert a.digest.startswith("sha256:")
    assert len(a.digest.split(":")[1]) == 64
    assert a.signing_key_ref.startswith("vault:")


def test_local_dev_identity_provider():
    pub = LocalDevIdentityProvider().issue_pubkey("DEV-1182")
    assert pub.startswith("dev-pub:")
