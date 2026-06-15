"""Shared fixtures: in-memory async DB and an RSA-backed JWT token factory."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable

import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from sgc.config import Settings
from sgc.db import Base
import sgc.models  # noqa: F401  (register tables on Base.metadata)

TEST_ISSUER = "https://keycloak.test/realms/sgc"
TEST_AUDIENCE = "secure-global-chain-api"
TEST_KID = "test-key-1"


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """A fresh in-memory SQLite database per test, with the kernel schema."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture(scope="session")
def rsa_keypair() -> tuple:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key, key.public_key()


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    return Settings(
        oidc_issuer=TEST_ISSUER,
        oidc_audience=TEST_AUDIENCE,
        oidc_jwks_url="https://keycloak.test/jwks",
    )


@pytest.fixture
def make_token(rsa_keypair) -> Callable[..., str]:
    """Factory producing signed RS256 access tokens with overridable claims."""
    private_key, _ = rsa_keypair

    def _make(
        *,
        sub: str = "user-sub-123",
        roles: list[str] | None = None,
        audience: str = TEST_AUDIENCE,
        issuer: str = TEST_ISSUER,
        expires_in: int = 300,
        email: str | None = "op@sgc.test",
        name: str | None = "Test Operator",
        extra: dict | None = None,
        sign_key=None,
    ) -> str:
        now = int(time.time())
        claims = {
            "sub": sub,
            "iss": issuer,
            "aud": audience,
            "iat": now,
            "exp": now + expires_in,
            "email": email,
            "name": name,
            "realm_access": {"roles": roles or []},
        }
        if extra:
            claims.update(extra)
        return jwt.encode(
            claims,
            sign_key or private_key,
            algorithm="RS256",
            headers={"kid": TEST_KID},
        )

    return _make


@pytest.fixture
def validator(test_settings, rsa_keypair):
    """JwtValidator wired to the test public key (no network)."""
    from sgc.security.jwt import JwtValidator

    _, public_key = rsa_keypair
    return JwtValidator(settings=test_settings, key_resolver=lambda token: public_key)
