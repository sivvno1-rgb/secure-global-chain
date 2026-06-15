"""Executive read-models API: overview, risk, portfolio."""

from __future__ import annotations

import pytest


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_overview_projection(executive, make_token):
    client, _, _ = executive
    r = await client.get(
        "/api/v1/executive/overview?range=monthly",
        headers=_auth(make_token(roles=["executive"])),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["range"] == "monthly"
    assert body["portfolio"]["batches_total"] == 2
    assert body["portfolio"]["batches_released"] == 1
    assert body["portfolio"]["batches_in_process"] == 1
    assert body["kpis"]["line_uptime_pct"] == 98.0
    assert body["kpis"]["supply_on_time_pct"] == 50.0  # 1 of 2 suppliers pass
    # A critical escalated deviation + quarantined device → Critical risk.
    assert body["risk"]["risk_level"] == "Critical"
    assert body["risk"]["quarantined_devices"] == 1


@pytest.mark.asyncio
async def test_risk_view_by_severity(executive, make_token):
    client, _, _ = executive
    r = await client.get(
        "/api/v1/executive/risk", headers=_auth(make_token(roles=["auditor"]))
    )
    assert r.status_code == 200
    body = r.json()
    assert body["risk_level"] == "Critical"
    assert body["critical_deviations"] == 1
    assert body["escalated_deviations"] == 1
    assert body["open_excursions"] == 1
    assert set(body["by_severity"]) == {"Critical", "Major", "Minor"}
    assert body["by_severity"]["Critical"] == 1


@pytest.mark.asyncio
async def test_portfolio_view(executive, make_token):
    client, _, _ = executive
    r = await client.get(
        "/api/v1/executive/portfolio?range=yearly",
        headers=_auth(make_token(roles=["executive"])),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["range"] == "yearly"
    assert body["batches_total"] == 2
    assert body["batches_released"] == 1
    trm = next(p for p in body["products"] if p["code"] == "TRM")
    assert trm["batches_total"] == 2
    assert trm["batches_released"] == 1


@pytest.mark.asyncio
async def test_range_window_excludes_old_releases(executive, make_token):
    """A daily window still includes the release made 'now'; an invalid range 422s."""
    client, _, _ = executive
    token = _auth(make_token(roles=["executive"]))
    daily = await client.get("/api/v1/executive/overview?range=daily", headers=token)
    assert daily.status_code == 200
    assert daily.json()["portfolio"]["batches_released"] == 1

    bad = await client.get("/api/v1/executive/overview?range=hourly", headers=token)
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_executive_requires_executive_or_auditor(executive, make_token):
    client, _, _ = executive
    denied = await client.get(
        "/api/v1/executive/overview", headers=_auth(make_token(roles=["operator"]))
    )
    assert denied.status_code == 403
    unauth = await client.get("/api/v1/executive/overview")
    assert unauth.status_code == 401
