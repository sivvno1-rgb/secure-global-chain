"""Application settings.

Secrets are intended to come from Vault at boot in production (see
``docs/design_handoff/SECURITY.md`` §2); for local/dev they fall back to
environment variables. No secret values are committed to the repo.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SGC_", env_file=".env", extra="ignore"
    )

    # --- Database ---------------------------------------------------------
    # Async SQLAlchemy URL. Postgres in prod; tests override with aiosqlite.
    database_url: str = Field(
        default="postgresql+asyncpg://sgc:sgc@localhost:5432/sgc",
    )

    # --- Identity / Keycloak (OIDC) --------------------------------------
    # The OIDC issuer (Keycloak realm URL). Tokens must carry this `iss`.
    oidc_issuer: str = Field(default="https://keycloak.local/realms/sgc")
    # JWKS endpoint used to validate token signatures (honors `kid` rotation).
    oidc_jwks_url: str = Field(
        default="https://keycloak.local/realms/sgc/protocol/openid-connect/certs"
    )
    # Expected audience claim on access tokens.
    oidc_audience: str = Field(default="secure-global-chain-api")
    # Allowed signing algorithms. Keycloak default is RS256.
    oidc_algorithms: tuple[str, ...] = ("RS256",)
    # How long to cache JWKS keys (seconds).
    jwks_cache_ttl: int = Field(default=3600)

    # --- DEV-ONLY auth (must be False in production) ----------------------
    # When enabled, the API validates HS256 tokens signed with `dev_auth_secret`
    # instead of Keycloak JWKS, and mounts GET /dev/login to mint them. This lets
    # you explore locally without Keycloak. require_role() is unchanged.
    dev_auth_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("SGC_DEV_AUTH", "SGC_DEV_AUTH_ENABLED"),
    )
    dev_auth_secret: str = Field(default="dev-insecure-secret-change-me-0123456789")

    # --- Infrastructure endpoints (compose service names in Docker) -------
    redis_url: str = Field(default="redis://localhost:6379/0")
    celery_broker_url: str | None = Field(default=None)
    celery_result_backend: str | None = Field(default=None)
    neo4j_uri: str = Field(default="bolt://localhost:7687")
    ollama_url: str = Field(default="http://localhost:11434")
    vault_addr: str = Field(default="http://localhost:8200")

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
