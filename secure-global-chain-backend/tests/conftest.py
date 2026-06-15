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


@pytest_asyncio.fixture
async def mfg(tmp_path, validator):
    """Seeded manufacturing DB + an ASGI HTTP client, sharing one event loop.

    Yields ``(client, sessionmaker, refs)``. The app's ``get_session`` and JWT
    validator are overridden; a file-backed SQLite DB holds the seed data.
    """
    from datetime import datetime, timezone

    from httpx import ASGITransport, AsyncClient

    import sgc.models as models
    from sgc.db import get_session
    from sgc.main import app
    from sgc.models.enums import BatchStatus, Sourcing, StatusToken, TaskKind
    from sgc.security.deps import get_jwt_validator

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'mfg.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    now = datetime.now(timezone.utc)
    refs: dict = {}
    async with maker() as s:
        seed_user = models.User(
            keycloak_sub="seed-user",
            email="seed@sgc.test",
            display_name="Seed Operator",
            roles=["operator"],
        )
        site = models.Site(name="Schaffhausen", cleanroom="CR4", gmp_status="GMP")
        product = models.Product(code="TRM", name="Guselkumab", modality="mAb")
        s.add_all([seed_user, site, product])
        await s.flush()

        line = models.Line(
            site_id=site.id,
            name="Line B",
            stage="Filling",
            uptime_pct=98.7,
            status=StatusToken.pass_,
        )
        supplier = models.Supplier(
            name="Guselkumab DS supplier",
            material="Guselkumab DS",
            sourcing=Sourcing.dual,
            site_country="CH",
            lead_time_days=30,
            status=StatusToken.pass_,
        )
        s.add_all([line, supplier])
        await s.flush()

        b1 = models.Batch(
            code="TRM-2291",
            product_id=product.id,
            line_id=line.id,
            stage="Filling",
            status=BatchStatus.inspection,
            yield_pct=98.7,
            started_at=now,
        )
        b2 = models.Batch(
            code="TRM-2292",
            product_id=product.id,
            line_id=line.id,
            stage="Released",
            status=BatchStatus.released,
            yield_pct=97.4,
            started_at=now,
        )
        s.add_all([b1, b2])
        await s.flush()

        step1 = models.BatchStep(batch_id=b1.id, name="Compounding", sequence=1)
        step2 = models.BatchStep(
            batch_id=b1.id,
            name="Filling",
            sequence=2,
            signed_by=seed_user.id,
            signed_at=now,
        )
        ipc = models.IpcCheck(
            batch_id=b1.id,
            kind="weight",
            value=10.1,
            spec_low=9.5,
            spec_high=10.5,
            result=StatusToken.pass_,
            at=now,
        )
        task = models.Task(
            title="Line clearance", kind=TaskKind.clearance, status=StatusToken.warn
        )
        s.add_all([step1, step2, ipc, task])
        await s.commit()
        refs.update(
            batch="TRM-2291",
            released_batch="TRM-2292",
            unsigned_step=step1.id,
            signed_step=step2.id,
            line_id=line.id,
        )

    async def _get_session():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = _get_session
    app.dependency_overrides[get_jwt_validator] = lambda: validator

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, maker, refs

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def fleet(tmp_path, validator):
    """Seeded device fleet DB + an ASGI client. Yields ``(client, sessionmaker, refs)``."""
    from datetime import datetime, timezone

    from httpx import ASGITransport, AsyncClient

    import sgc.models as models
    from sgc.db import get_session
    from sgc.main import app
    from sgc.models.enums import DeviceState, FirmwareState, StatusToken
    from sgc.security.deps import get_jwt_validator

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'fleet.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    now = datetime.now(timezone.utc)
    refs: dict = {}
    async with maker() as s:
        fw_draft = models.FirmwareBuild(
            version="v4.2.1", state=FirmwareState.draft, artifact_url="s3://fw/v4.2.1"
        )
        fw_signed = models.FirmwareBuild(
            version="v4.1.0", state=FirmwareState.signed, digest="sha256:abc123"
        )
        s.add_all([fw_draft, fw_signed])
        await s.flush()

        dev_online = models.Device(
            serial="DEV-1182", model="NeuroSecure", state=DeviceState.online,
            hw_identity_pubkey="dev-pub:seed", last_seen_at=now, firmware_id=fw_signed.id,
        )
        s.add(dev_online)
        await s.flush()
        att = models.DeviceAttestation(
            device_id=dev_online.id, firmware_id=fw_signed.id,
            measured_digest="sha256:abc123", verdict=StatusToken.pass_, at=now,
        )
        pending = models.ProvisionRequest(
            device_serial="DEV-2000", status="pending", at=now
        )
        s.add_all([att, pending])
        await s.commit()
        refs.update(
            device="DEV-1182",
            draft_firmware="v4.2.1",
            signed_firmware="v4.1.0",
            pending_request=pending.id,
        )

    async def _get_session():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = _get_session
    app.dependency_overrides[get_jwt_validator] = lambda: validator

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, maker, refs

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def qual(tmp_path, validator):
    """Seeded quality DB + an ASGI client. Yields ``(client, sessionmaker, refs)``."""
    from datetime import datetime, timezone

    from httpx import ASGITransport, AsyncClient

    import sgc.models as models
    from sgc.db import get_session
    from sgc.main import app
    from sgc.models.enums import (
        BatchStatus,
        Framework,
        QualityState,
        Severity,
        StatusToken,
    )
    from sgc.security.deps import get_jwt_validator

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'qual.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    now = datetime.now(timezone.utc)
    refs: dict = {}
    async with maker() as s:
        site = models.Site(name="Schaffhausen", cleanroom="CR4")
        s.add(site)
        await s.flush()
        line = models.Line(site_id=site.id, name="Line B", status=StatusToken.pass_)
        s.add(line)
        await s.flush()
        batch = models.Batch(code="TRM-2291", line_id=line.id, status=BatchStatus.hold)
        s.add(batch)
        await s.flush()

        dev = models.Deviation(
            code="DEV-1000",
            title="Fill weight drift",
            severity=Severity.major,
            line_id=line.id,
            batch_id=batch.id,
            state=QualityState.review,
            raised_at=now,
        )
        dev_escalated = models.Deviation(
            code="DEV-1001",
            title="Environmental excursion",
            severity=Severity.critical,
            state=QualityState.escalated,
            raised_at=now,
        )
        capa = models.Capa(
            code="CAPA-0001", deviation_id=None, status=StatusToken.warn
        )
        audit = models.Audit(scope="CR4 annual", framework=Framework.gmp, readiness_pct=82.0)
        s.add_all([dev, dev_escalated, capa, audit])
        await s.flush()
        finding = models.AuditFinding(
            audit_id=audit.id,
            framework=Framework.gmp,
            severity=Severity.minor,
            status=StatusToken.warn,
        )
        ci_gmp = models.ComplianceItem(
            framework=Framework.gmp, area="CR4", title="Gowning log", state=StatusToken.pass_
        )
        ci_glp = models.ComplianceItem(
            framework=Framework.glp, area="Lab 2", title="Balance calibration", state=StatusToken.warn
        )
        s.add_all([finding, ci_gmp, ci_glp])
        await s.commit()
        refs.update(
            deviation="DEV-1000",
            escalated_deviation="DEV-1001",
            capa="CAPA-0001",
            audit_id=audit.id,
            line_id=line.id,
        )

    async def _get_session():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = _get_session
    app.dependency_overrides[get_jwt_validator] = lambda: validator

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, maker, refs

    app.dependency_overrides.clear()
    await engine.dispose()
