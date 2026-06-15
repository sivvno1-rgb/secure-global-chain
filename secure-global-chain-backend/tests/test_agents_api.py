"""Agent mesh API: status, invoke (proposal-only), human disposition.

The hard rule — agents propose, humans decide; no agent path finalizes a
consequential action — is asserted here.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from sgc.audit import verify_chain
from sgc.models.audit import AuditEvent
from sgc.models.enums import BatchStatus
from sgc.models.manufacturing import Batch


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_agents_mesh_status(agents, make_token):
    client, _, _ = agents
    r = await client.get("/api/v1/agents", headers=_auth(make_token(roles=["quality"])))
    assert r.status_code == 200
    names = {a["name"] for a in r.json()}
    assert {"tracer", "quality_analyst", "fleet_sentinel"} <= names
    assert all(a["model"].startswith("ollama:") for a in r.json())


@pytest.mark.asyncio
async def test_invoke_produces_proposal_awaiting_human(agents, make_token):
    client, maker, refs = agents
    token = _auth(make_token(roles=["quality"]))
    r = await client.post(
        "/api/v1/agents/quality_analyst/invoke",
        json={"input_ref": refs["batch"], "params": {"cites": ["TRM-2291"]}},
        headers=token,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "awaiting_human"
    assert body["human_disposition"] is None
    assert body["proposed_action"]["requires_human"] is True
    assert body["model"].startswith("ollama:")


@pytest.mark.asyncio
async def test_invoke_unknown_agent_404(agents, make_token):
    client, _, _ = agents
    r = await client.post(
        "/api/v1/agents/nonesuch/invoke", json={}, headers=_auth(make_token(roles=["quality"]))
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_invoke_does_not_mutate_consequential_state(agents, make_token):
    """Invoking an agent must not change the batch — it only proposes."""
    client, maker, refs = agents
    token = _auth(make_token(roles=["quality"]))
    await client.post(
        "/api/v1/agents/quality_analyst/invoke",
        json={"input_ref": refs["batch"]},
        headers=token,
    )
    async with maker() as s:
        batch = (
            await s.execute(select(Batch).where(Batch.code == refs["batch"]))
        ).scalar_one()
        assert batch.status is BatchStatus.inspection  # unchanged
        assert batch.released_at is None
        assert batch.released_by is None


@pytest.mark.asyncio
async def test_disposition_requires_human(agents, make_token):
    client, _, refs = agents
    # create a run first
    invoked = await client.post(
        "/api/v1/agents/tracer/invoke", json={"input_ref": refs["batch"]},
        headers=_auth(make_token(roles=["quality"])),
    )
    run_id = invoked.json()["id"]
    # a service account (clientId) is not human → 403
    svc = _auth(make_token(roles=["quality"], extra={"clientId": "agent-mesh"}))
    r = await client.post(
        f"/api/v1/agents/runs/{run_id}/disposition",
        json={"disposition": "accepted"}, headers=svc,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_disposition_accept_is_audited_but_not_executed(agents, make_token):
    client, maker, refs = agents
    token = _auth(make_token(sub="qa-1", roles=["quality"]))
    invoked = await client.post(
        "/api/v1/agents/fleet_sentinel/invoke",
        json={"input_ref": refs["batch"]}, headers=token,
    )
    run_id = invoked.json()["id"]

    r = await client.post(
        f"/api/v1/agents/runs/{run_id}/disposition",
        json={"disposition": "accepted", "note": "looks right"}, headers=token,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "accepted"
    assert r.json()["human_disposition"] == "accepted"
    assert r.headers.get("X-Audit-Event-Id")

    async with maker() as s:
        event = (
            await s.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "disposition",
                    AuditEvent.object_type == "agent_run",
                )
            )
        ).scalar_one()
        # The audit trail records that acceptance is not execution.
        assert event.after["executed"] is False
        assert await verify_chain(s) is True
        # The batch is still untouched — acceptance recorded the decision only.
        batch = (
            await s.execute(select(Batch).where(Batch.code == refs["batch"]))
        ).scalar_one()
        assert batch.status is BatchStatus.inspection


@pytest.mark.asyncio
async def test_disposition_conflict_when_already_done(agents, make_token):
    client, _, refs = agents
    token = _auth(make_token(roles=["quality"]))
    invoked = await client.post(
        "/api/v1/agents/tracer/invoke", json={"input_ref": refs["batch"]}, headers=token
    )
    run_id = invoked.json()["id"]
    first = await client.post(
        f"/api/v1/agents/runs/{run_id}/disposition",
        json={"disposition": "rejected"}, headers=token,
    )
    assert first.status_code == 200
    again = await client.post(
        f"/api/v1/agents/runs/{run_id}/disposition",
        json={"disposition": "accepted"}, headers=token,
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_runs_log_filterable_by_agent(agents, make_token):
    client, _, refs = agents
    token = _auth(make_token(roles=["quality"]))
    await client.post("/api/v1/agents/tracer/invoke", json={"input_ref": "x"}, headers=token)
    await client.post("/api/v1/agents/quality_analyst/invoke", json={"input_ref": "y"}, headers=token)
    only_tracer = await client.get("/api/v1/agents/runs?agent=tracer", headers=token)
    assert only_tracer.status_code == 200
    assert {r["agent"] for r in only_tracer.json()} == {"tracer"}
