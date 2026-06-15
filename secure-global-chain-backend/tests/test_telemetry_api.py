"""Telemetry & cold-chain API: reads + human-gated excursion disposition."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from sgc.audit import verify_chain
from sgc.models.audit import AuditEvent


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_readings(telem, make_token):
    client, _, refs = telem
    token = _auth(make_token(roles=["operator"]))
    r = await client.get(f"/api/v1/streams/{refs['device']}/readings", headers=token)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"items", "total", "page"}
    assert body["total"] == 3
    assert body["items"][0]["kind"] == "temp"
    assert body["items"][0]["unit"] == "C"


@pytest.mark.asyncio
async def test_list_readings_kind_filter_and_404(telem, make_token):
    client, _, refs = telem
    token = _auth(make_token(roles=["operator"]))
    humid = await client.get(
        f"/api/v1/streams/{refs['device']}/readings?kind=humidity", headers=token
    )
    assert humid.status_code == 200
    assert humid.json()["total"] == 0

    missing = await client.get("/api/v1/streams/DEV-0000/readings", headers=token)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_list_lanes(telem, make_token):
    client, _, _ = telem
    r = await client.get(
        "/api/v1/coldchain/lanes", headers=_auth(make_token(roles=["operator"]))
    )
    assert r.status_code == 200
    assert r.json()[0]["code"] == "SG→EU"


@pytest.mark.asyncio
async def test_list_excursions_open_filter(telem, make_token):
    client, _, refs = telem
    token = _auth(make_token(roles=["quality"]))
    openx = await client.get("/api/v1/coldchain/excursions?open=true", headers=token)
    assert openx.status_code == 200
    assert len(openx.json()) == 1
    assert openx.json()[0]["disposition"] is None


@pytest.mark.asyncio
async def test_disposition_requires_role(telem, make_token):
    client, _, refs = telem
    r = await client.post(
        f"/api/v1/coldchain/excursions/{refs['excursion']}/disposition",
        json={"disposition": "Product released after review"},
        headers=_auth(make_token(roles=["operator"])),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_disposition_success_is_audited(telem, make_token):
    client, maker, refs = telem
    r = await client.post(
        f"/api/v1/coldchain/excursions/{refs['excursion']}/disposition",
        json={"disposition": "Rejected — excursion exceeded limit", "close": True},
        headers=_auth(make_token(roles=["quality"])),
    )
    assert r.status_code == 200, r.text
    assert r.json()["disposition"].startswith("Rejected")
    assert r.json()["ended_at"] is not None
    assert r.headers.get("X-Audit-Event-Id")
    async with maker() as s:
        event = (
            await s.execute(
                select(AuditEvent).where(AuditEvent.action == "disposition")
            )
        ).scalar_one()
        assert event.object_type == "excursion"
        assert await verify_chain(s) is True


@pytest.mark.asyncio
async def test_disposition_conflict_when_already_set(telem, make_token):
    client, _, refs = telem
    token = _auth(make_token(roles=["quality"]))
    first = await client.post(
        f"/api/v1/coldchain/excursions/{refs['excursion']}/disposition",
        json={"disposition": "x"},
        headers=token,
    )
    assert first.status_code == 200
    again = await client.post(
        f"/api/v1/coldchain/excursions/{refs['excursion']}/disposition",
        json={"disposition": "y"},
        headers=token,
    )
    assert again.status_code == 409
