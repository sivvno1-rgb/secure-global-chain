"""Optimization API: solve schedule, commit (human-gated), scenarios."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from sgc.audit import verify_chain
from sgc.models.audit import AuditEvent


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _solve(client, token, horizon=1000):
    return await client.post(
        "/api/v1/optimization/schedules",
        json={
            "horizon": horizon,
            "objective": "makespan",
            "jobs": [
                {"duration_minutes": 60},
                {"duration_minutes": 90},
                {"duration_minutes": 30},
            ],
        },
        headers=token,
    )


@pytest.mark.asyncio
async def test_create_schedule_solves_and_audits(optimization, make_token):
    client, maker = optimization
    token = _auth(make_token(sub="planner-1", roles=["planner"]))
    r = await _solve(client, token)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["solver_status"] in ("optimal", "feasible")
    assert body["state"] == "solved"
    assert len(body["slots"]) == 3
    assert r.headers.get("X-Audit-Event-Id")
    async with maker() as s:
        event = (
            await s.execute(select(AuditEvent).where(AuditEvent.action == "optimize"))
        ).scalar_one()
        assert event.object_type == "schedule"
        assert await verify_chain(s) is True


@pytest.mark.asyncio
async def test_create_schedule_requires_planner(optimization, make_token):
    client, _ = optimization
    r = await _solve(client, _auth(make_token(roles=["operator"])))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_infeasible_schedule_marked_failed(optimization, make_token):
    client, _ = optimization
    token = _auth(make_token(roles=["planner"]))
    r = await client.post(
        "/api/v1/optimization/schedules",
        json={"horizon": 100, "jobs": [{"duration_minutes": 100}, {"duration_minutes": 100}]},
        headers=token,
    )
    assert r.status_code == 201
    assert r.json()["solver_status"] == "infeasible"
    assert r.json()["state"] == "failed"


@pytest.mark.asyncio
async def test_commit_is_human_gated_and_audited(optimization, make_token):
    client, maker = optimization
    token = _auth(make_token(roles=["planner"]))
    schedule = (await _solve(client, token)).json()
    sid = schedule["id"]

    # service account cannot commit
    svc = _auth(make_token(roles=["planner"], extra={"clientId": "agent"}))
    assert (await client.post(f"/api/v1/optimization/schedules/{sid}/commit", headers=svc)).status_code == 403

    committed = await client.post(
        f"/api/v1/optimization/schedules/{sid}/commit", headers=token
    )
    assert committed.status_code == 200, committed.text
    assert committed.json()["state"] == "committed"
    assert committed.json()["committed_by"] is not None

    # committing again conflicts
    again = await client.post(
        f"/api/v1/optimization/schedules/{sid}/commit", headers=token
    )
    assert again.status_code == 409
    async with maker() as s:
        assert await verify_chain(s) is True


@pytest.mark.asyncio
async def test_scenario_computes_kpi_delta(optimization, make_token):
    client, _ = optimization
    token = _auth(make_token(roles=["planner"]))
    base = (await _solve(client, token)).json()

    scenario = await client.post(
        "/api/v1/optimization/scenarios",
        json={
            "name": "20% slower",
            "base_schedule_id": base["id"],
            "params": {"duration_scale": 1.2, "horizon_scale": 2.0},
        },
        headers=token,
    )
    assert scenario.status_code == 201, scenario.text
    kpi = scenario.json()["kpi_delta"]
    assert kpi["base_makespan_minutes"] == 180
    # 20% slower → larger makespan
    assert kpi["scenario_makespan_minutes"] >= 180
    assert kpi["delta_minutes"] == kpi["scenario_makespan_minutes"] - 180

    got = await client.get(
        f"/api/v1/optimization/scenarios/{scenario.json()['id']}", headers=token
    )
    assert got.status_code == 200
    assert got.json()["name"] == "20% slower"
