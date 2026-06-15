"""Device Fleet service layer.

Reads plus the human-gated, audited transitions: provision request/approval,
device quarantine, firmware signing (Vault-backed), and staged rollouts. Each
mutation appends an ``audit_events`` row in the same transaction (SECURITY.md §5).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..audit import AuditPayload, append_audit_event
from ..errors import ConflictError, NotFoundError
from ..models.audit import AuditEvent
from ..models.devices import (
    Device,
    FirmwareBuild,
    FirmwareRollout,
    ProvisionRequest,
)
from ..models.enums import DeviceState, FirmwareState
from ..models.user import User
from .pki import DeviceIdentityProvider, FirmwareSigner


async def list_devices(
    session: AsyncSession,
    *,
    state: DeviceState | None = None,
    site_id: uuid.UUID | None = None,
    page: int = 1,
    limit: int = 50,
) -> tuple[list[Device], int]:
    filters = []
    if state is not None:
        filters.append(Device.state == state)
    if site_id is not None:
        filters.append(Device.site_id == site_id)
    total = await session.scalar(
        select(func.count()).select_from(Device).where(*filters)
    )
    result = await session.execute(
        select(Device)
        .where(*filters)
        .order_by(Device.serial)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return list(result.scalars()), int(total or 0)


async def get_device(session: AsyncSession, serial: str) -> Device:
    result = await session.execute(
        select(Device)
        .where(Device.serial == serial)
        .options(selectinload(Device.attestations))
    )
    device = result.scalar_one_or_none()
    if device is None:
        raise NotFoundError(f"Device {serial} not found")
    return device


async def request_provision(
    session: AsyncSession,
    *,
    actor: User,
    device_serial: str,
    site_id: uuid.UUID | None = None,
    line_id: uuid.UUID | None = None,
) -> tuple[ProvisionRequest, AuditEvent]:
    req = ProvisionRequest(
        device_serial=device_serial,
        requested_by=actor.id,
        status="pending",
        at=datetime.now(timezone.utc),
    )
    session.add(req)
    await session.flush()
    event = await append_audit_event(
        session,
        AuditPayload(
            actor_id=actor.id,
            action="provision_request",
            object_type="provision_request",
            object_id=device_serial,
            after={"status": req.status, "site_id": str(site_id) if site_id else None,
                   "line_id": str(line_id) if line_id else None},
        ),
    )
    return req, event


async def approve_provision(
    session: AsyncSession,
    request_id: uuid.UUID,
    actor: User,
    identity: DeviceIdentityProvider,
    *,
    site_id: uuid.UUID | None = None,
    line_id: uuid.UUID | None = None,
) -> tuple[Device, AuditEvent]:
    req = await session.get(ProvisionRequest, request_id)
    if req is None:
        raise NotFoundError(f"Provision request {request_id} not found")
    if req.status != "pending":
        raise ConflictError(f"Provision request is already {req.status}")

    existing = await session.scalar(
        select(Device).where(Device.serial == req.device_serial)
    )
    if existing is not None:
        raise ConflictError(f"Device {req.device_serial} already provisioned")

    req.status = "approved"
    req.approved_by = actor.id

    device = Device(
        serial=req.device_serial,
        model="NeuroSecure",
        site_id=site_id,
        line_id=line_id,
        hw_identity_pubkey=identity.issue_pubkey(req.device_serial),
        state=DeviceState.provisioned,
    )
    session.add(device)
    await session.flush()

    event = await append_audit_event(
        session,
        AuditPayload(
            actor_id=actor.id,
            action="provision",
            object_type="device",
            object_id=device.serial,
            after={"state": device.state.value, "approved_request": str(request_id)},
        ),
    )
    return device, event


async def quarantine_device(
    session: AsyncSession, serial: str, actor: User
) -> tuple[Device, AuditEvent]:
    device = await get_device(session, serial)
    if device.state == DeviceState.quarantined:
        raise ConflictError(f"Device {serial} is already Quarantined")
    before = {"state": device.state.value}
    device.state = DeviceState.quarantined
    device.tamper_locked = True
    event = await append_audit_event(
        session,
        AuditPayload(
            actor_id=actor.id,
            action="quarantine",
            object_type="device",
            object_id=serial,
            before=before,
            after={"state": device.state.value},
        ),
    )
    return device, event


async def list_firmware(session: AsyncSession) -> list[FirmwareBuild]:
    result = await session.execute(
        select(FirmwareBuild).order_by(FirmwareBuild.version)
    )
    return list(result.scalars())


async def get_firmware(session: AsyncSession, version: str) -> FirmwareBuild:
    result = await session.execute(
        select(FirmwareBuild).where(FirmwareBuild.version == version)
    )
    fw = result.scalar_one_or_none()
    if fw is None:
        raise NotFoundError(f"Firmware {version} not found")
    return fw


async def sign_firmware(
    session: AsyncSession, version: str, actor: User, signer: FirmwareSigner
) -> tuple[FirmwareBuild, AuditEvent]:
    """Human-gated firmware signing (Vault-backed in prod). Requires fleet_admin."""
    fw = await get_firmware(session, version)
    if fw.state != FirmwareState.draft:
        raise ConflictError(f"Firmware {version} is {fw.state.value}; cannot sign")

    signed = signer.sign(version, fw.artifact_url)
    fw.digest = signed.digest
    fw.signed_by = actor.id
    fw.signed_at = datetime.now(timezone.utc)
    fw.state = FirmwareState.signed

    event = await append_audit_event(
        session,
        AuditPayload(
            actor_id=actor.id,
            action="sign",
            object_type="firmware",
            object_id=version,
            after={
                "digest": fw.digest,
                "state": fw.state.value,
                "signing_key_ref": signed.signing_key_ref,
            },
        ),
    )
    return fw, event


async def start_rollout(
    session: AsyncSession,
    version: str,
    actor: User,
    *,
    cohort: str | None = None,
    devices_total: int = 0,
) -> tuple[FirmwareRollout, AuditEvent]:
    fw = await get_firmware(session, version)
    if fw.state not in (FirmwareState.signed, FirmwareState.staged, FirmwareState.deployed):
        raise ConflictError(
            f"Firmware {version} must be signed before rollout (is {fw.state.value})"
        )
    rollout = FirmwareRollout(
        firmware_id=fw.id,
        cohort=cohort,
        devices_total=devices_total,
        devices_done=0,
        state=FirmwareState.rolling,
        started_at=datetime.now(timezone.utc),
        started_by=actor.id,
    )
    session.add(rollout)
    await session.flush()
    event = await append_audit_event(
        session,
        AuditPayload(
            actor_id=actor.id,
            action="rollout",
            object_type="firmware_rollout",
            object_id=version,
            after={"rollout_id": str(rollout.id), "cohort": cohort,
                   "devices_total": devices_total, "state": rollout.state.value},
        ),
    )
    return rollout, event


async def get_rollout(
    session: AsyncSession, rollout_id: uuid.UUID
) -> FirmwareRollout:
    rollout = await session.get(FirmwareRollout, rollout_id)
    if rollout is None:
        raise NotFoundError(f"Rollout {rollout_id} not found")
    return rollout
