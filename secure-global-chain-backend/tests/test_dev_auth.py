"""DEV-ONLY auth: minted tokens satisfy require_role; endpoint is off by default."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sgc.config import Settings
from sgc.devauth import mint_dev_token
from sgc.security.jwt import JwtValidator, TokenValidationError
from sgc.security.principal import Principal


def _dev_settings() -> Settings:
    return Settings(
        dev_auth_enabled=True,
        dev_auth_secret="unit-test-secret",
        oidc_issuer="https://keycloak.test/realms/sgc",
        oidc_audience="secure-global-chain-api",
    )


def _dev_validator(settings: Settings) -> JwtValidator:
    return JwtValidator(
        settings=settings,
        key_resolver=lambda _t: settings.dev_auth_secret,
        algorithms=("HS256",),
    )


def test_minted_token_validates_and_carries_roles():
    s = _dev_settings()
    token = mint_dev_token(s, sub="olivia", roles=["qa_release", "quality"])
    claims = _dev_validator(s).validate(token)
    principal = Principal.from_claims(claims)
    assert principal.sub == "olivia"
    assert principal.is_human is True
    assert principal.has_role("qa_release")  # require_role would pass


def test_service_token_is_not_human():
    s = _dev_settings()
    token = mint_dev_token(s, sub="agent", roles=["qa_release"], service=True)
    principal = Principal.from_claims(_dev_validator(s).validate(token))
    assert principal.is_human is False  # human_only routes reject it


def test_token_rejected_under_wrong_secret():
    s = _dev_settings()
    token = mint_dev_token(s, sub="x", roles=["operator"])
    attacker = Settings(
        dev_auth_enabled=True, dev_auth_secret="WRONG",
        oidc_issuer=s.oidc_issuer, oidc_audience=s.oidc_audience,
    )
    import pytest

    with pytest.raises(TokenValidationError):
        _dev_validator(attacker).validate(token)


def test_dev_login_absent_when_disabled():
    # The app is imported with default settings (dev auth OFF) → route not mounted.
    from sgc.main import app

    with TestClient(app) as client:
        assert client.get("/dev/login").status_code == 404
