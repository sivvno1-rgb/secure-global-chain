"""DEV-ONLY auth: mint Keycloak-shaped tokens without standing up Keycloak.

Mounted only when ``SGC_DEV_AUTH=true`` (``settings.dev_auth_enabled``). Tokens
are HS256-signed with ``settings.dev_auth_secret`` and carry the same claims a
Keycloak access token would (``sub``, ``iss``, ``aud``, ``exp``,
``realm_access.roles``), so :func:`sgc.security.require_role` is satisfied
without any change to the auth logic. **Never enable in production.**
"""

from __future__ import annotations

import time

import jwt
from fastapi import APIRouter, HTTPException, Query

from .config import Settings, get_settings

router = APIRouter(prefix="/dev", tags=["dev-auth"])


def mint_dev_token(
    settings: Settings,
    *,
    sub: str,
    roles: list[str],
    email: str | None = None,
    name: str | None = None,
    service: bool = False,
    expires_in: int = 3600,
) -> str:
    now = int(time.time())
    claims: dict = {
        "sub": sub,
        "iss": settings.oidc_issuer,
        "aud": settings.oidc_audience,
        "iat": now,
        "exp": now + expires_in,
        "email": email or f"{sub}@dev.local",
        "name": name or sub,
        "preferred_username": sub,
        "realm_access": {"roles": roles},
    }
    if service:
        # Simulate a Keycloak service account → Principal.is_human == False,
        # so `human_only` routes reject it (useful for testing the human gate).
        claims["clientId"] = "dev-service"
    return jwt.encode(claims, settings.dev_auth_secret, algorithm="HS256")


@router.get("/login")
async def dev_login(
    roles: str = Query("operator", description="comma-separated realm roles"),
    sub: str = Query("dev-user"),
    service: bool = Query(False, description="mint a non-human service token"),
):
    """Mint a dev bearer token for the given role(s)."""
    settings = get_settings()
    if not settings.dev_auth_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    role_list = [r.strip() for r in roles.split(",") if r.strip()]
    token = mint_dev_token(
        settings, sub=sub, roles=role_list, service=service
    )
    return {
        "access_token": token,
        "token_type": "Bearer",
        "sub": sub,
        "roles": role_list,
        "is_human": not service,
        "usage": "send header  Authorization: Bearer <access_token>",
        "warning": "DEV ONLY — disabled when SGC_DEV_AUTH is not true.",
    }
