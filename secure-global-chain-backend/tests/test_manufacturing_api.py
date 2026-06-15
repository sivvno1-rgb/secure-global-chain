"""Manufacturing API: read endpoints + human-gated release/sign (audited)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from sgc.audit import verify_chain
from sgc.models.audit import AuditEvent
from sgc.models.user import User


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_batches_envelope(mfg, make_token):
    client, _, _ = mfg
    r = await client.get("/api/v1/batches", headers=_auth(make_token(roles=["operator"])))
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"items", "total", "page"}
    assert body["total"] >= 2
    assert body["page"] == 1


@pytest.mark.asyncio
async def test_get_batch_detail_field_names(mfg, make_token):
    client, _, refs = mfg
    r = await client.get(
        f"/api/v1/batches/{refs['batch']}",
        headers=_auth(make_token(roles=["operator"])),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == "TRM-2291"
    assert body["status"] == "Inspection"  # exact enum string
    assert body["yield_pct"] == 98.7
    assert len(body["steps"]) == 2
    assert len(body["ipc_checks"]) == 1
    assert body["ipc_checks"][0]["result"] == "pass"


@pytest.mark.asyncio
async def test_release_requires_authentication(mfg):
    client, _, refs = mfg
    r = await client.post(f"/api/v1/batches/{refs['batch']}/release")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_release_forbidden_without_role(mfg, make_token):
    client, _, refs = mfg
    r = await client.post(
        f"/api/v1/batches/{refs['batch']}/release",
        headers=_auth(make_token(roles=["operator"])),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_release_rejects_service_account(mfg, make_token):
    client, _, refs = mfg
    token = make_token(roles=["qa_release"], extra={"clientId": "agent-mesh"})
    r = await client.post(
        f"/api/v1/batches/{refs['batch']}/release", headers=_auth(token)
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_release_success_is_audited(mfg, make_token):
    client, maker, refs = mfg
    token = make_token(sub="qa-user-1", roles=["qa_release"])
    r = await client.post(
        f"/api/v1/batches/{refs['batch']}/release", headers=_auth(token)
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "Released"
    assert r.json()["released_by"] is not None
    event_id = r.headers.get("X-Audit-Event-Id")
    assert event_id

    async with maker() as s:
        # The audit event exists, links to the right actor, and the chain holds.
        event = (
            await s.execute(
                select(AuditEvent).where(AuditEvent.action == "release")
            )
        ).scalar_one()
        assert event.object_id == refs["batch"]
        assert event.after["status"] == "Released"
        actor = (
            await s.execute(select(User).where(User.id == event.actor_id))
        ).scalar_one()
        assert actor.keycloak_sub == "qa-user-1"
        assert await verify_chain(s) is True


@pytest.mark.asyncio
async def test_release_conflict_when_already_released(mfg, make_token):
    client, _, refs = mfg
    r = await client.post(
        f"/api/v1/batches/{refs['released_batch']}/release",
        headers=_auth(make_token(roles=["qa_release"])),
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_release_not_found(mfg, make_token):
    client, _, _ = mfg
    r = await client.post(
        "/api/v1/batches/TRM-0000/release",
        headers=_auth(make_token(roles=["qa_release"])),
    )
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


@pytest.mark.asyncio
async def test_sign_step_success_is_audited(mfg, make_token):
    client, maker, refs = mfg
    token = make_token(sub="op-user-1", roles=["operator"])
    r = await client.post(
        f"/api/v1/batches/{refs['batch']}/steps/{refs['unsigned_step']}/sign",
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["signed_by"] is not None
    assert r.headers.get("X-Audit-Event-Id")

    async with maker() as s:
        event = (
            await s.execute(select(AuditEvent).where(AuditEvent.action == "sign"))
        ).scalar_one()
        assert event.object_id == str(refs["unsigned_step"])
        assert await verify_chain(s) is True


@pytest.mark.asyncio
async def test_sign_step_conflict_when_already_signed(mfg, make_token):
    client, _, refs = mfg
    r = await client.post(
        f"/api/v1/batches/{refs['batch']}/steps/{refs['signed_step']}/sign",
        headers=_auth(make_token(roles=["operator"])),
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_sign_step_wrong_role(mfg, make_token):
    # qa_release may release but not sign steps (operator-gated).
    client, _, refs = mfg
    r = await client.post(
        f"/api/v1/batches/{refs['batch']}/steps/{refs['unsigned_step']}/sign",
        headers=_auth(make_token(roles=["qa_release"])),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_mission_summary(mfg, make_token):
    client, _, _ = mfg
    r = await client.get(
        "/api/v1/mission/summary", headers=_auth(make_token(roles=["operator"]))
    )
    assert r.status_code == 200
    assert set(r.json()) == {
        "supply_on_time_pct",
        "line_uptime_pct",
        "batches_in_process",
        "batches_released",
    }
