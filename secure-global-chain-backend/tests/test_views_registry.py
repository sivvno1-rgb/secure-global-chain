"""Every §7 view-model route: role-gating, reads-only, and contract shape.

Covers the master registry (FRONTEND_WIRING.md §7):
  * each route is reachable with its role, 403 with a wrong role, 401 unauth;
  * new-domain / illustrative routes return ``{}`` (frontend keeps demo data);
  * the §5/§6 contracts (quality / operations) match their authored shape;
  * hitting every read-model writes **no** audit events.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from sgc.models import AuditEvent
from sgc.views.registry import REGISTRY

TONES = {"pass", "warn", "fail"}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _path(spec) -> str:
    return f"/api/v1/views/{spec.key}"


# --- role-gating, reachability, empty-body contract ----------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("spec", REGISTRY, ids=lambda s: s.key)
async def test_route_is_role_gated_and_reads(spec, executive, make_token):
    client, _, _ = executive

    # right role → 200
    ok = await client.get(_path(spec), headers=_auth(make_token(roles=[spec.role])))
    assert ok.status_code == 200, ok.text
    assert isinstance(ok.json(), dict)

    # wrong role → 403
    denied = await client.get(_path(spec), headers=_auth(make_token(roles=["nobody"])))
    assert denied.status_code == 403, denied.text

    # no token → 401
    assert (await client.get(_path(spec))).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "spec",
    [s for s in REGISTRY if s.availability in ("new-domain", "illustrative")],
    ids=lambda s: s.key,
)
async def test_demo_only_routes_return_empty(spec, executive, make_token):
    """new-domain + illustrative scaffolds return {} so the frontend uses demo."""
    client, _, _ = executive
    r = await client.get(_path(spec), headers=_auth(make_token(roles=[spec.role])))
    assert r.status_code == 200
    assert r.json() == {}


# --- all 27 keys are registered exactly once -----------------------------------
def test_every_registry_key_has_one_route():
    from sgc.views.router import router as views_router

    paths = [r.path for r in views_router.routes]
    assert sorted(paths) == sorted(_path(s) for s in REGISTRY)
    assert len(paths) == len(set(paths)) == 27  # one route per key, no dupes
    keys = [s.key for s in REGISTRY]
    assert len(keys) == len(set(keys))


# --- reads-only: no audit events written ---------------------------------------
@pytest.mark.asyncio
async def test_views_write_no_audit_events(executive, make_token):
    client, maker, _ = executive
    async with maker() as s:
        before = await s.scalar(select(func.count()).select_from(AuditEvent))
    for spec in REGISTRY:
        await client.get(_path(spec), headers=_auth(make_token(roles=[spec.role])))
    async with maker() as s:
        after = await s.scalar(select(func.count()).select_from(AuditEvent))
    assert after == before


# --- operations (§6) shape -----------------------------------------------------
@pytest.mark.asyncio
async def test_operations_matches_contract(executive, make_token):
    client, _, _ = executive
    r = await client.get("/api/v1/views/operations", headers=_auth(make_token(roles=["operator"])))
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) <= {"tasks", "devices", "env", "batch"}

    for t in body.get("tasks", []):
        assert set(t) <= {"id", "t", "st", "kind", "due"}
        assert {"id", "t", "st", "kind"} <= set(t)
        assert t["st"] in {"done", "now", "todo"}
    for d in body.get("devices", []):
        assert {"id", "loc", "st", "live"} <= set(d)
        assert d["st"] in TONES
        assert isinstance(d["live"], bool)
    for e in body.get("env", []):
        assert {"k", "v", "ok"} <= set(e)
        assert isinstance(e["ok"], bool)
    if "batch" in body:
        assert "code" in body["batch"]
        # executive fixture seeds one in-process batch
        assert body["batch"]["code"] == "TRM-2292"

    # the seeded quarantined device renders as a fail tile, not live
    dev = next(d for d in body["devices"] if d["id"] == "DEV-9")
    assert dev["st"] == "fail" and dev["live"] is False


# --- quality (§5) shape --------------------------------------------------------
@pytest.mark.asyncio
async def test_quality_matches_contract(executive, make_token):
    client, _, _ = executive
    r = await client.get("/api/v1/views/quality", headers=_auth(make_token(roles=["quality"])))
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) <= {"kpis", "changes", "reviews", "docs", "ci", "agents"}

    # KPIs that are emitted must be a subset of the §5 labels, in §5 order
    spec_order = ["SOX on-time", "Periodic review on-time", "Training (ATRR)",
                  "Open change controls", "Open CAPAs", "Audit readiness"]
    labels = [k["label"] for k in body.get("kpis", [])]
    assert labels == [lbl for lbl in spec_order if lbl in labels]
    for k in body.get("kpis", []):
        assert k["tone"] in TONES
        assert isinstance(k["v"], str)

    # the seeded passing compliance item yields a 100% on-time tile
    sox = next((k for k in body.get("kpis", []) if k["label"] == "SOX on-time"), None)
    assert sox is not None and sox["v"] == "100" and sox["tone"] == "pass"

    for a in body.get("agents", []):
        assert "t" in a


# --- facility-map (live) shape -------------------------------------------------
@pytest.mark.asyncio
async def test_facility_map_shape(executive, make_token):
    client, _, _ = executive
    r = await client.get("/api/v1/views/ops/facility-map", headers=_auth(make_token(roles=["operator"])))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "sites" in body  # executive fixture seeds Schaffhausen + Line B
    site = next(s for s in body["sites"] if s["name"] == "Schaffhausen")
    assert site["status"] in TONES
    assert any(ln["name"] == "Line B" for ln in site["lines"])
