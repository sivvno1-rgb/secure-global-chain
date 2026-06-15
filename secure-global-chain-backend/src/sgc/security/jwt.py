"""JWT access-token validation against Keycloak's JWKS.

Verifies signature (RS256, honoring ``kid`` rotation via JWKS), ``iss``, ``aud``,
and ``exp``. Anything else is rejected (SECURITY.md §1, §4). The signing-key
resolver is injectable so the validator can be unit-tested without network.
"""

from __future__ import annotations

from typing import Any, Callable

import jwt

from ..config import Settings, get_settings

# Resolve the verification key for a given token (reads its `kid` header).
SigningKeyResolver = Callable[[str], Any]


class TokenValidationError(Exception):
    """Raised for any invalid/expired/untrusted token. Mapped to HTTP 401."""


class _JWKSKeyResolver:
    """Default resolver: fetch + cache Keycloak JWKS, pick the key by ``kid``."""

    def __init__(self, jwks_url: str, ttl: int) -> None:
        # Imported lazily so unit tests never trigger a network client.
        from jwt import PyJWKClient

        self._client = PyJWKClient(jwks_url, cache_keys=True, lifespan=ttl)

    def __call__(self, token: str) -> Any:
        return self._client.get_signing_key_from_jwt(token).key


class JwtValidator:
    def __init__(
        self,
        settings: Settings | None = None,
        key_resolver: SigningKeyResolver | None = None,
        algorithms: tuple[str, ...] | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._key_resolver = key_resolver
        self._algorithms = (
            list(algorithms) if algorithms else list(self._settings.oidc_algorithms)
        )

    def _resolve_key(self, token: str) -> Any:
        if self._key_resolver is None:
            self._key_resolver = _JWKSKeyResolver(
                self._settings.oidc_jwks_url, self._settings.jwks_cache_ttl
            )
        return self._key_resolver(token)

    def validate(self, token: str) -> dict:
        """Return verified claims, or raise :class:`TokenValidationError`."""
        try:
            key = self._resolve_key(token)
            claims = jwt.decode(
                token,
                key,
                algorithms=self._algorithms,
                audience=self._settings.oidc_audience,
                issuer=self._settings.oidc_issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise TokenValidationError(str(exc)) from exc
        except Exception as exc:  # key resolution / JWKS failures → 401
            raise TokenValidationError(f"key resolution failed: {exc}") from exc
        return claims
