"""Research API: hypotheses, evidence runs, validation-report signing."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from sgc.audit import verify_chain
from sgc.models.audit import AuditEvent
from sgc.models.enums import HypothesisState


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_and_pose_hypothesis(research, make_token):
    client, maker, _ = research
    token = _auth(make_token(sub="sci-1", roles=["scientist"]))
    listing = await client.get("/api/v1/research/hypotheses", headers=token)
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    created = await client.post(
        "/api/v1/research/hypotheses",
        json={"title": "New hypothesis", "domain": "stability"},
        headers=token,
    )
    assert created.status_code == 201, created.text
    assert created.json()["state"] == "open"
    assert created.headers.get("X-Audit-Event-Id")


@pytest.mark.asyncio
async def test_pose_hypothesis_requires_scientist(research, make_token):
    client, _, _ = research
    r = await client.post(
        "/api/v1/research/hypotheses",
        json={"title": "x"},
        headers=_auth(make_token(roles=["operator"])),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_evidence_run_frequentist_persists_results(research, make_token):
    client, maker, refs = research
    token = _auth(make_token(sub="sci-1", roles=["scientist"]))
    r = await client.post(
        "/api/v1/research/evidence",
        json={
            "title": "Fill weight t-test",
            "method": "frequentist",
            "hypothesis_id": str(refs["hypothesis_id"]),
            "dataset_ref": "ds://fill",
            "params": {"sample": [5.1, 4.9, 5.2, 5.0, 4.8], "popmean": 5.0},
        },
        headers=token,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["state"] == "complete"
    assert body["method"] == "frequentist"
    stats_present = {row["statistic"] for row in body["results"]}
    assert {"t", "mean"} <= stats_present
    assert r.headers.get("X-Audit-Event-Id")

    # The run does NOT change the hypothesis verdict (humans decide).
    async with maker() as s:
        from sgc.models.research import Hypothesis
        hyp = await s.get(Hypothesis, refs["hypothesis_id"])
        assert hyp.state is HypothesisState.open
        event = (
            await s.execute(
                select(AuditEvent).where(AuditEvent.action == "evidence_run")
            )
        ).scalar_one()
        assert event.object_type == "evidence_packet"
        assert await verify_chain(s) is True


@pytest.mark.asyncio
async def test_get_evidence_packet(research, make_token):
    client, _, refs = research
    token = _auth(make_token(roles=["scientist"]))
    created = await client.post(
        "/api/v1/research/evidence",
        json={"title": "bayes", "method": "bayesian",
              "params": {"sample": [1.0, 2.0, 3.0, 2.5]}},
        headers=token,
    )
    packet_id = created.json()["id"]
    got = await client.get(f"/api/v1/research/evidence/{packet_id}", headers=token)
    assert got.status_code == 200
    assert got.json()["results"][0]["statistic"] == "posterior_mean"


@pytest.mark.asyncio
async def test_sign_validation_report_requires_qa_release(research, make_token):
    client, _, refs = research
    r = await client.post(
        f"/api/v1/research/validation-reports/{refs['report']}/sign",
        headers=_auth(make_token(roles=["scientist"])),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_sign_validation_report_success_is_audited(research, make_token):
    client, maker, refs = research
    r = await client.post(
        f"/api/v1/research/validation-reports/{refs['report']}/sign",
        headers=_auth(make_token(sub="qa-1", roles=["qa_release"])),
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "approved"
    assert r.json()["signed_by"] is not None
    assert r.headers.get("X-Audit-Event-Id")
    async with maker() as s:
        event = (
            await s.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "sign",
                    AuditEvent.object_type == "validation_report",
                )
            )
        ).scalar_one()
        assert event.object_id == refs["report"]
        assert await verify_chain(s) is True


@pytest.mark.asyncio
async def test_sign_validation_report_conflict_when_approved(research, make_token):
    client, _, refs = research
    r = await client.post(
        f"/api/v1/research/validation-reports/{refs['approved_report']}/sign",
        headers=_auth(make_token(roles=["qa_release"])),
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_author_and_sign_flow(research, make_token):
    client, _, _ = research
    authored = await client.post(
        "/api/v1/research/validation-reports",
        json={"scope": "Computer system validation"},
        headers=_auth(make_token(roles=["scientist"])),
    )
    assert authored.status_code == 201, authored.text
    code = authored.json()["code"]
    assert code.startswith("VR-")
    signed = await client.post(
        f"/api/v1/research/validation-reports/{code}/sign",
        headers=_auth(make_token(roles=["qa_release"])),
    )
    assert signed.status_code == 200
    assert signed.json()["state"] == "approved"
