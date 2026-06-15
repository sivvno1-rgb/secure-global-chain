"""RBAC dependency behaviour end-to-end (SECURITY.md §1, §4).

401 = missing/invalid token; 403 = authenticated but lacks the role; consequential
gates (``human_only``) reject service tokens even when the role is present.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sgc.main import app
from sgc.security.deps import get_jwt_validator


@pytest.fixture
def client(validator):
    app.dependency_overrides[get_jwt_validator] = lambda: validator
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_missing_token_is_401(client):
    assert client.get("/api/v1/me").status_code == 401


def test_invalid_token_is_401(client):
    r = client.get("/api/v1/me", headers=_auth("garbage"))
    assert r.status_code == 401


def test_authenticated_me_ok(client, make_token):
    r = client.get("/api/v1/me", headers=_auth(make_token(roles=["operator"])))
    assert r.status_code == 200
    assert r.json()["sub"] == "user-sub-123"
    assert r.json()["roles"] == ["operator"]


def test_role_present_grants_access(client, make_token):
    token = make_token(roles=["qa_release"])
    r = client.get("/api/v1/_kernel/qa-release-check", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["allowed"] == "qa_release"


def test_role_absent_is_403(client, make_token):
    token = make_token(roles=["operator"])
    r = client.get("/api/v1/_kernel/qa-release-check", headers=_auth(token))
    assert r.status_code == 403


def test_human_only_rejects_service_account(client, make_token):
    # Service accounts carry a clientId claim → not human, even with the role.
    token = make_token(roles=["qa_release"], extra={"clientId": "agent-mesh"})
    r = client.get("/api/v1/_kernel/qa-release-check", headers=_auth(token))
    assert r.status_code == 403


def test_error_messages_do_not_leak_which_check(client, make_token):
    # 401 (no token) and 403 (wrong role) must use generic details.
    unauth = client.get("/api/v1/_kernel/qa-release-check")
    forbidden = client.get(
        "/api/v1/_kernel/qa-release-check",
        headers=_auth(make_token(roles=["operator"])),
    )
    assert unauth.status_code == 401
    assert forbidden.status_code == 403
    assert "role" not in forbidden.json()["detail"].lower()
