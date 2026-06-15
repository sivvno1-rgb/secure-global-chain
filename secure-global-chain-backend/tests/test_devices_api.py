"""Device Fleet API: reads + human-gated, audited firmware/device actions."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from sgc.audit import verify_chain
from sgc.models.audit import AuditEvent
from sgc.models.devices import Device


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_devices_envelope_and_filter(fleet, make_token):
    client, _, _ = fleet
    token = _auth(make_token(roles=["fleet_admin"]))
    r = await client.get("/api/v1/devices", headers=token)
    assert r.status_code == 200
    assert set(r.json()) == {"items", "total", "page"}
    assert r.json()["total"] == 1

    online = await client.get("/api/v1/devices?state=Online", headers=token)
    assert [d["serial"] for d in online.json()["items"]] == ["DEV-1182"]
    none = await client.get("/api/v1/devices?state=Quarantined", headers=token)
    assert none.json()["total"] == 0


@pytest.mark.asyncio
async def test_device_detail_includes_attestations(fleet, make_token):
    client, _, refs = fleet
    r = await client.get(
        f"/api/v1/devices/{refs['device']}",
        headers=_auth(make_token(roles=["auditor"])),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["serial"] == "DEV-1182"
    assert body["state"] == "Online"
    assert len(body["attestations"]) == 1
    assert body["attestations"][0]["verdict"] == "pass"


@pytest.mark.asyncio
async def test_firmware_sign_requires_role(fleet, make_token):
    client, _, refs = fleet
    r = await client.post(
        f"/api/v1/firmware/{refs['draft_firmware']}/sign",
        headers=_auth(make_token(roles=["operator"])),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_firmware_sign_rejects_service_account(fleet, make_token):
    client, _, refs = fleet
    token = make_token(roles=["fleet_admin"], extra={"clientId": "agent-mesh"})
    r = await client.post(
        f"/api/v1/firmware/{refs['draft_firmware']}/sign", headers=_auth(token)
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_firmware_sign_success_is_audited(fleet, make_token):
    client, maker, refs = fleet
    token = make_token(sub="fa-1", roles=["fleet_admin"])
    r = await client.post(
        f"/api/v1/firmware/{refs['draft_firmware']}/sign", headers=_auth(token)
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "Signed"
    assert body["digest"].startswith("sha256:")
    assert body["signed_by"] is not None
    assert r.headers.get("X-Audit-Event-Id")

    async with maker() as s:
        event = (
            await s.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "sign",
                    AuditEvent.object_type == "firmware",
                )
            )
        ).scalar_one()
        assert event.object_id == refs["draft_firmware"]
        assert event.after["digest"].startswith("sha256:")
        assert await verify_chain(s) is True


@pytest.mark.asyncio
async def test_firmware_sign_conflict_when_already_signed(fleet, make_token):
    client, _, refs = fleet
    r = await client.post(
        f"/api/v1/firmware/{refs['signed_firmware']}/sign",
        headers=_auth(make_token(roles=["fleet_admin"])),
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_rollout_requires_signed_firmware(fleet, make_token):
    client, _, refs = fleet
    token = _auth(make_token(roles=["fleet_admin"]))
    # draft firmware cannot be rolled out
    r = await client.post(
        f"/api/v1/firmware/{refs['draft_firmware']}/rollouts",
        json={"cohort": "ring-0", "devices_total": 10},
        headers=token,
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_rollout_start_and_progress(fleet, make_token):
    client, _, refs = fleet
    token = _auth(make_token(roles=["fleet_admin"]))
    start = await client.post(
        f"/api/v1/firmware/{refs['signed_firmware']}/rollouts",
        json={"cohort": "ring-0", "devices_total": 10},
        headers=token,
    )
    assert start.status_code == 201, start.text
    assert start.json()["state"] == "Rolling"
    assert start.headers.get("X-Audit-Event-Id")
    rollout_id = start.json()["id"]

    progress = await client.get(
        f"/api/v1/firmware/rollouts/{rollout_id}", headers=token
    )
    assert progress.status_code == 200
    assert progress.json()["devices_total"] == 10
    assert progress.json()["devices_done"] == 0


@pytest.mark.asyncio
async def test_quarantine_device_is_audited(fleet, make_token):
    client, maker, refs = fleet
    r = await client.post(
        f"/api/v1/devices/{refs['device']}/quarantine",
        headers=_auth(make_token(roles=["fleet_admin"])),
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "Quarantined"
    assert r.json()["tamper_locked"] is True
    async with maker() as s:
        event = (
            await s.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "quarantine",
                    AuditEvent.object_type == "device",
                )
            )
        ).scalar_one()
        assert event.object_id == refs["device"]
        assert await verify_chain(s) is True


@pytest.mark.asyncio
async def test_provision_request_then_approve_creates_device(fleet, make_token):
    client, maker, _ = fleet
    # Operator requests provisioning.
    req = await client.post(
        "/api/v1/devices/provision",
        json={"device_serial": "DEV-3000"},
        headers=_auth(make_token(sub="op-2", roles=["operator"])),
    )
    assert req.status_code == 201, req.text
    assert req.json()["status"] == "pending"
    assert req.headers.get("X-Audit-Event-Id")
    request_id = req.json()["id"]

    # Operator cannot approve.
    denied = await client.post(
        f"/api/v1/devices/provision-requests/{request_id}/approve",
        headers=_auth(make_token(roles=["operator"])),
    )
    assert denied.status_code == 403

    # fleet_admin approves → device created (Provisioned) with a Vault-issued pubkey.
    ok = await client.post(
        f"/api/v1/devices/provision-requests/{request_id}/approve",
        headers=_auth(make_token(sub="fa-2", roles=["fleet_admin"])),
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["serial"] == "DEV-3000"
    assert ok.json()["state"] == "Provisioned"
    assert ok.json()["hw_identity_pubkey"]

    async with maker() as s:
        device = (
            await s.execute(select(Device).where(Device.serial == "DEV-3000"))
        ).scalar_one()
        assert device.state.value == "Provisioned"
        assert await verify_chain(s) is True


@pytest.mark.asyncio
async def test_approve_conflict_when_already_approved(fleet, make_token):
    client, _, refs = fleet
    token = _auth(make_token(roles=["fleet_admin"]))
    first = await client.post(
        f"/api/v1/devices/provision-requests/{refs['pending_request']}/approve",
        headers=token,
    )
    assert first.status_code == 200
    again = await client.post(
        f"/api/v1/devices/provision-requests/{refs['pending_request']}/approve",
        headers=token,
    )
    assert again.status_code == 409
