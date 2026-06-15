"""GET /api/v1/views/mission returns exactly the FRONTEND_WIRING.md §4 shape."""

from __future__ import annotations

import pytest

KPI_LABELS = [
    "Mission health",
    "Active risks",
    "Pending decisions",
    "Facilities healthy",
    "Shipments delayed",
    "Value at risk",
]
TONES = {"pass", "warn", "fail"}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_mission_view_matches_contract(executive, make_token):
    client, _, _ = executive
    r = await client.get(
        "/api/v1/views/mission", headers=_auth(make_token(roles=["operator"]))
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # top-level keys exactly per §4
    assert set(body) == {"headline", "kpis", "events", "facilities", "shipments"}

    # headline
    assert isinstance(body["headline"]["mission_pct"], int)
    assert 0 <= body["headline"]["mission_pct"] <= 100
    assert isinstance(body["headline"]["critical_events"], int)

    # exactly the 6 KPIs, in order
    assert [k["label"] for k in body["kpis"]] == KPI_LABELS
    for k in body["kpis"]:
        assert isinstance(k["v"], str)
        assert k["tone"] in TONES
    assert body["kpis"][0]["u"] == "%"  # Mission health carries a unit
    assert body["kpis"][3]["u"].startswith("/ ")  # Facilities healthy "/ N"
    assert "u" not in body["kpis"][1]  # Active risks has no unit (excluded)

    # events: ranked, fail-first; each carries the full contract shape
    severities = [e["sev"] for e in body["events"]]
    assert severities == sorted(severities, key=lambda s: 0 if s == "fail" else 1)
    for e in body["events"]:
        assert set(e) == {"sev", "c", "cat", "title", "desc", "impact", "action", "go", "btn"}
        assert e["sev"] in {"fail", "warn"}
        assert e["c"].startswith("#")
        assert isinstance(e["impact"], list)
        for pair in e["impact"]:
            assert len(pair) == 2 and all(isinstance(x, str) for x in pair)
    # headline.critical_events == number of fail events
    assert body["headline"]["critical_events"] == sum(1 for e in body["events"] if e["sev"] == "fail")

    # facilities / shipments: [name, detail, status] triples
    for row in body["facilities"] + body["shipments"]:
        assert len(row) == 3
        assert all(isinstance(x, str) for x in row)
        assert row[2] in TONES


@pytest.mark.asyncio
async def test_mission_view_is_operator_gated(executive, make_token):
    client, _, _ = executive
    # wrong role → 403
    denied = await client.get(
        "/api/v1/views/mission", headers=_auth(make_token(roles=["scientist"]))
    )
    assert denied.status_code == 403
    # no token → 401
    assert (await client.get("/api/v1/views/mission")).status_code == 401
