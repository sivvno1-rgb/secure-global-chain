"""JWT validation against Keycloak (SECURITY.md §1, §4)."""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from sgc.security.jwt import TokenValidationError


def test_valid_token_returns_claims(validator, make_token):
    claims = validator.validate(make_token(roles=["operator", "quality"]))
    assert claims["sub"] == "user-sub-123"
    assert claims["realm_access"]["roles"] == ["operator", "quality"]


def test_expired_token_rejected(validator, make_token):
    with pytest.raises(TokenValidationError):
        validator.validate(make_token(expires_in=-10))


def test_wrong_audience_rejected(validator, make_token):
    with pytest.raises(TokenValidationError):
        validator.validate(make_token(audience="some-other-client"))


def test_wrong_issuer_rejected(validator, make_token):
    with pytest.raises(TokenValidationError):
        validator.validate(make_token(issuer="https://evil.test/realms/sgc"))


def test_bad_signature_rejected(validator, make_token):
    # Sign with a different key than the validator trusts.
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = make_token(sign_key=attacker_key)
    with pytest.raises(TokenValidationError):
        validator.validate(forged)


def test_missing_required_claim_rejected(validator, make_token):
    # Strip the audience entirely → "aud" required check fails.
    token = make_token(extra={"aud": None})
    with pytest.raises(TokenValidationError):
        validator.validate(token)


def test_garbage_token_rejected(validator):
    with pytest.raises(TokenValidationError):
        validator.validate("not-a-jwt")
