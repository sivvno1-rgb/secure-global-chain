"""Intelligence / Systems Map API: graph, node, trace, impact, signals."""

from __future__ import annotations

import pytest


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_graph_nodes_and_edges(intel, make_token):
    client, _, _ = intel
    token = _auth(make_token(roles=["operator"]))
    r = await client.get("/api/v1/intel/graph", headers=token)
    assert r.status_code == 200
    body = r.json()
    node_ids = {n["id"] for n in body["nodes"]}
    assert {"TRM-2291", "DEV-1182", "DEV-9000", "SG→EU"} <= node_ids
    rels = {e["rel"] for e in body["edges"]}
    assert {"PRODUCES", "HAS_DEVIATION", "MONITORS", "CARRIES"} <= rels


@pytest.mark.asyncio
async def test_graph_category_filter(intel, make_token):
    client, _, _ = intel
    token = _auth(make_token(roles=["operator"]))
    r = await client.get("/api/v1/intel/graph?filter=quality", headers=token)
    assert r.status_code == 200
    assert all(n["category"] == "quality" for n in r.json()["nodes"])
    # deviation is a quality node
    assert any(n["id"] == "DEV-1182" for n in r.json()["nodes"])

    bad = await client.get("/api/v1/intel/graph?filter=bogus", headers=token)
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_node_detail_connection_count(intel, make_token):
    client, _, refs = intel
    token = _auth(make_token(roles=["operator"]))
    r = await client.get(f"/api/v1/intel/node/{refs['batch']}", headers=token)
    assert r.status_code == 200
    body = r.json()
    assert body["node"]["type"] == "Batch"
    # PRODUCES (in) + CARRIES (in) + HAS_DEVIATION (out)
    assert body["connection_count"] >= 3

    missing = await client.get("/api/v1/intel/node/NOPE", headers=token)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_trace_chain_of_custody(intel, make_token):
    client, _, refs = intel
    token = _auth(make_token(roles=["auditor"]))
    r = await client.get(f"/api/v1/intel/trace/{refs['batch']}", headers=token)
    assert r.status_code == 200
    ids = {n["id"] for n in r.json()["nodes"]}
    # full connected custody: line, site, deviation, lane, device all reachable
    assert {"TRM-2291", "DEV-1182", "SG→EU", "DEV-9000", refs["line_id"], refs["site_id"]} <= ids

    missing = await client.get("/api/v1/intel/trace/TRM-0000", headers=token)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_impact_blast_radius(intel, make_token):
    client, _, refs = intel
    token = _auth(make_token(roles=["operator"]))
    # Downstream of the line: the batch it produces and that batch's deviation.
    r = await client.get(f"/api/v1/intel/impact/{refs['line_id']}", headers=token)
    assert r.status_code == 200
    ids = {n["id"] for n in r.json()["nodes"]}
    assert "TRM-2291" in ids
    assert "DEV-1182" in ids
    # the line itself is excluded from its own blast radius
    assert refs["line_id"] not in ids


@pytest.mark.asyncio
async def test_signals_feed_orders_failures_first(intel, make_token):
    client, _, _ = intel
    token = _auth(make_token(roles=["executive"]))
    r = await client.get("/api/v1/intel/signals?range=weekly", headers=token)
    assert r.status_code == 200
    statuses = [n["status"] for n in r.json()]
    # only active signals, fail before warn before pass
    assert set(statuses) <= {"fail", "warn", "pass"}
    rank = {"fail": 0, "warn": 1, "pass": 2}
    assert statuses == sorted(statuses, key=lambda s: rank[s])
    assert any(n["status"] == "fail" for n in r.json())


@pytest.mark.asyncio
async def test_intel_requires_auth(intel):
    client, _, _ = intel
    assert (await client.get("/api/v1/intel/graph")).status_code == 401
