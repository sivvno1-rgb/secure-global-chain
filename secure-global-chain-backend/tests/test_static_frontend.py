"""The operator frontend is served: GET / returns the SPA shell, /static is
mounted, and the API surface (e.g. /api/v1/views/mission) is unaffected."""

from __future__ import annotations

import pytest


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_root_serves_index_html(executive):
    client, _, _ = executive
    r = await client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert r.text.lstrip().startswith("<!DOCTYPE html>")


@pytest.mark.asyncio
async def test_static_mount_serves_index(executive):
    client, _, _ = executive
    r = await client.get("/static/index.html")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")


@pytest.mark.asyncio
async def test_api_surface_still_works_alongside_root(executive, make_token):
    """Serving the SPA at / must not shadow the /api/v1/* routes."""
    client, _, _ = executive
    r = await client.get(
        "/api/v1/views/mission", headers=_auth(make_token(roles=["operator"]))
    )
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"headline", "kpis", "events", "facilities", "shipments"}
    # health endpoint also unaffected
    assert (await client.get("/health")).json() == {"status": "ok"}
