"""FastAPI auth dependencies: current principal and ``require_role``.

Per SECURITY.md §4: 401 = missing/invalid token, 403 = authenticated but lacks
the role. Messages are intentionally generic — never leak which check failed.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .jwt import JwtValidator, TokenValidationError
from .principal import Principal

_bearer = HTTPBearer(auto_error=False)


@lru_cache
def get_jwt_validator() -> JwtValidator:
    """Process-wide validator (caches JWKS keys). Overridable in tests."""
    return JwtValidator()


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    validator: JwtValidator = Depends(get_jwt_validator),
) -> Principal:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = validator.validate(credentials.credentials)
    except TokenValidationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Principal.from_claims(claims)


async def require_human(
    principal: Principal = Depends(get_current_principal),
) -> Principal:
    """Authenticated **human** actor (rejects service/agent tokens).

    Used where any human may act but no service identity may — e.g. dispositioning
    an agent proposal (SECURITY.md §1; AI assists, humans decide).
    """
    if not principal.is_human:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
        )
    return principal


def require_role(
    role: str, *, human_only: bool = False
) -> Callable[..., "Principal"]:
    """Dependency factory enforcing a realm role.

    Set ``human_only=True`` for consequential actions (release, sign, provision,
    decide, escalate): service tokens are rejected even if they carry the role
    (SECURITY.md §1).
    """
    return require_any_role(role, human_only=human_only)


def require_any_role(
    *roles: str, human_only: bool = False
) -> Callable[..., "Principal"]:
    """Like :func:`require_role` but grants access if the caller has *any* role.

    Used where the handoff allows more than one role (e.g. operators *or* quality
    may raise deviations).
    """
    allowed = frozenset(roles)

    async def _dependency(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        if human_only and not principal.is_human:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
            )
        if allowed.isdisjoint(principal.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
            )
        return principal

    return _dependency
