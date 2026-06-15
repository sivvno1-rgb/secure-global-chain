"""Quality & Compliance API: reads + human-gated, audited transitions."""

from __future__ import annotations

import re

import pytest
from sqlalchemy import select

from sgc.audit import verify_chain
from sgc.models.audit import AuditEvent


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_deviations_envelope_and_filter(qual, make_token):
    client, _, _ = qual
    token = _auth(make_token(roles=["quality"]))
    r = await client.get("/api/v1/deviations", headers=token)
    assert r.status_code == 200
    assert set(r.json()) == {"items", "total", "page"}
    assert r.json()["total"] == 2

    r2 = await client.get("/api/v1/deviations?state=Escalated", headers=token)
    assert r2.status_code == 200
    assert [d["code"] for d in r2.json()["items"]] == ["DEV-1001"]


@pytest.mark.asyncio
async def test_raise_deviation_unauthenticated(qual):
    client, _, _ = qual
    r = await client.post("/api/v1/deviations", json={"title": "x", "severity": "Minor"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_raise_deviation_forbidden_for_other_role(qual, make_token):
    client, _, _ = qual
    r = await client.post(
        "/api/v1/deviations",
        json={"title": "x", "severity": "Minor"},
        headers=_auth(make_token(roles=["scientist"])),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_raise_deviation_success_is_audited(qual, make_token):
    client, maker, _ = qual
    token = make_token(sub="op-1", roles=["operator"])
    r = await client.post(
        "/api/v1/deviations",
        json={"title": "Fill weight drift", "severity": "Major"},
        headers=_auth(token),
    )
    assert r.status_code == 201, r.text
    code = r.json()["code"]
    assert re.match(r"^DEV-\d{4}$", code)
    assert r.json()["state"] == "Review"
    assert r.headers.get("X-Audit-Event-Id")

    async with maker() as s:
        event = (
            await s.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "raise", AuditEvent.object_id == code
                )
            )
        ).scalar_one()
        assert event.object_type == "deviation"
        assert await verify_chain(s) is True


@pytest.mark.asyncio
async def test_raise_deviation_rejects_service_account(qual, make_token):
    client, _, _ = qual
    token = make_token(roles=["quality"], extra={"clientId": "agent-mesh"})
    r = await client.post(
        "/api/v1/deviations",
        json={"title": "x", "severity": "Minor"},
        headers=_auth(token),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_escalate_success_is_audited(qual, make_token):
    client, maker, refs = qual
    r = await client.post(
        f"/api/v1/deviations/{refs['deviation']}/escalate",
        headers=_auth(make_token(roles=["quality"])),
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "Escalated"
    assert r.headers.get("X-Audit-Event-Id")
    async with maker() as s:
        event = (
            await s.execute(
                select(AuditEvent).where(AuditEvent.action == "escalate")
            )
        ).scalar_one()
        assert event.object_id == refs["deviation"]
        assert await verify_chain(s) is True


@pytest.mark.asyncio
async def test_escalate_wrong_role(qual, make_token):
    client, _, refs = qual
    r = await client.post(
        f"/api/v1/deviations/{refs['deviation']}/escalate",
        headers=_auth(make_token(roles=["operator"])),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_escalate_conflict_when_already_escalated(qual, make_token):
    client, _, refs = qual
    r = await client.post(
        f"/api/v1/deviations/{refs['escalated_deviation']}/escalate",
        headers=_auth(make_token(roles=["quality"])),
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_escalate_not_found(qual, make_token):
    client, _, _ = qual
    r = await client.post(
        "/api/v1/deviations/DEV-9999/escalate",
        headers=_auth(make_token(roles=["quality"])),
    )
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


@pytest.mark.asyncio
async def test_capa_effectiveness_is_audited(qual, make_token):
    client, maker, refs = qual
    r = await client.post(
        f"/api/v1/capas/{refs['capa']}/effectiveness",
        json={"result": "pass", "effectiveness_state": "effective", "on_time_pct": 100.0},
        headers=_auth(make_token(roles=["quality"])),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pass"
    assert r.json()["effectiveness_state"] == "effective"
    assert r.headers.get("X-Audit-Event-Id")
    async with maker() as s:
        event = (
            await s.execute(
                select(AuditEvent).where(AuditEvent.action == "effectiveness")
            )
        ).scalar_one()
        assert event.object_id == refs["capa"]
        assert await verify_chain(s) is True


@pytest.mark.asyncio
async def test_capa_effectiveness_wrong_role(qual, make_token):
    client, _, refs = qual
    r = await client.post(
        f"/api/v1/capas/{refs['capa']}/effectiveness",
        json={"result": "pass"},
        headers=_auth(make_token(roles=["operator"])),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_audits_and_findings(qual, make_token):
    client, _, refs = qual
    token = _auth(make_token(roles=["auditor"]))
    audits = await client.get("/api/v1/audits", headers=token)
    assert audits.status_code == 200
    assert len(audits.json()) == 1

    findings = await client.get(
        f"/api/v1/audits/{refs['audit_id']}/findings", headers=token
    )
    assert findings.status_code == 200
    assert len(findings.json()) == 1
    assert findings.json()[0]["framework"] == "GMP"


@pytest.mark.asyncio
async def test_compliance_area_filter(qual, make_token):
    client, _, _ = qual
    token = _auth(make_token(roles=["quality"]))
    allf = await client.get("/api/v1/compliance/area", headers=token)
    assert allf.status_code == 200
    assert len(allf.json()) == 2

    gmp = await client.get("/api/v1/compliance/area?framework=GMP", headers=token)
    assert gmp.status_code == 200
    assert [c["framework"] for c in gmp.json()] == ["GMP"]
