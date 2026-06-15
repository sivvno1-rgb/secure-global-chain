"""Device Fleet API (NeuroSecure). Prefix ``/api/v1``.

Consequential verbs are explicit sub-resources protected by role + human actor
and write an audit event; mutating responses carry ``X-Audit-Event-Id``.
Firmware signing is Vault-backed via the PKI seam.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models.enums import DeviceState
from ..pagination import Page
from ..security import (
    Principal,
    get_current_principal,
    require_any_role,
    require_role,
)
from ..security.users import sync_user
from . import service
from .pki import (
    DeviceIdentityProvider,
    FirmwareSigner,
    get_device_identity_provider,
    get_firmware_signer,
)
from .schemas import (
    DeviceDetail,
    DeviceSummary,
    FirmwareBuildRead,
    FirmwareRolloutRead,
    ProvisionCreate,
    ProvisionRequestRead,
    RolloutCreate,
)

router = APIRouter(prefix="/api/v1", tags=["devices"])


@router.get("/devices", response_model=Page[DeviceSummary])
async def list_devices(
    state: DeviceState | None = None,
    site: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    items, total = await service.list_devices(
        session, state=state, site_id=site, page=page, limit=limit
    )
    return Page[DeviceSummary](
        items=[DeviceSummary.model_validate(d) for d in items], total=total, page=page
    )


@router.get("/devices/{serial}", response_model=DeviceDetail)
async def get_device(
    serial: str,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    return await service.get_device(session, serial)


@router.post(
    "/devices/provision",
    response_model=ProvisionRequestRead,
    status_code=status.HTTP_201_CREATED,
)
async def provision(
    body: ProvisionCreate,
    response: Response,
    principal: Principal = Depends(
        require_any_role("operator", "fleet_admin", human_only=True)
    ),
    session: AsyncSession = Depends(get_session),
):
    actor = await sync_user(session, principal)
    req, event = await service.request_provision(
        session,
        actor=actor,
        device_serial=body.device_serial,
        site_id=body.site_id,
        line_id=body.line_id,
    )
    await session.commit()
    await session.refresh(req)
    response.headers["X-Audit-Event-Id"] = str(event.id)
    return ProvisionRequestRead.model_validate(req)


@router.post(
    "/devices/provision-requests/{request_id}/approve",
    response_model=DeviceDetail,
)
async def approve_provision(
    request_id: uuid.UUID,
    response: Response,
    site: uuid.UUID | None = None,
    line: uuid.UUID | None = None,
    principal: Principal = Depends(require_role("fleet_admin", human_only=True)),
    session: AsyncSession = Depends(get_session),
    identity: DeviceIdentityProvider = Depends(get_device_identity_provider),
):
    actor = await sync_user(session, principal)
    device, event = await service.approve_provision(
        session, request_id, actor, identity, site_id=site, line_id=line
    )
    await session.commit()
    response.headers["X-Audit-Event-Id"] = str(event.id)
    return await service.get_device(session, device.serial)


@router.post("/devices/{serial}/quarantine", response_model=DeviceDetail)
async def quarantine_device(
    serial: str,
    response: Response,
    principal: Principal = Depends(require_role("fleet_admin", human_only=True)),
    session: AsyncSession = Depends(get_session),
):
    actor = await sync_user(session, principal)
    device, event = await service.quarantine_device(session, serial, actor)
    await session.commit()
    response.headers["X-Audit-Event-Id"] = str(event.id)
    return await service.get_device(session, serial)


@router.get("/firmware", response_model=list[FirmwareBuildRead])
async def list_firmware(
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    return await service.list_firmware(session)


@router.post("/firmware/{version}/sign", response_model=FirmwareBuildRead)
async def sign_firmware(
    version: str,
    response: Response,
    principal: Principal = Depends(require_role("fleet_admin", human_only=True)),
    session: AsyncSession = Depends(get_session),
    signer: FirmwareSigner = Depends(get_firmware_signer),
):
    actor = await sync_user(session, principal)
    fw, event = await service.sign_firmware(session, version, actor, signer)
    await session.commit()
    await session.refresh(fw)
    response.headers["X-Audit-Event-Id"] = str(event.id)
    return FirmwareBuildRead.model_validate(fw)


@router.post(
    "/firmware/{version}/rollouts",
    response_model=FirmwareRolloutRead,
    status_code=status.HTTP_201_CREATED,
)
async def start_rollout(
    version: str,
    body: RolloutCreate,
    response: Response,
    principal: Principal = Depends(require_role("fleet_admin", human_only=True)),
    session: AsyncSession = Depends(get_session),
):
    actor = await sync_user(session, principal)
    rollout, event = await service.start_rollout(
        session, version, actor, cohort=body.cohort, devices_total=body.devices_total
    )
    await session.commit()
    await session.refresh(rollout)
    response.headers["X-Audit-Event-Id"] = str(event.id)
    return FirmwareRolloutRead.model_validate(rollout)


@router.get("/firmware/rollouts/{rollout_id}", response_model=FirmwareRolloutRead)
async def get_rollout(
    rollout_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(get_current_principal),
):
    return await service.get_rollout(session, rollout_id)
