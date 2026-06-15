"""FastAPI application wiring for the security core.

Only the identity + audit kernel is mounted so far. Bounded contexts
(manufacturing, quality, …) will add their routers here later.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI

from .security import Principal, get_current_principal, require_role

app = FastAPI(title="Secure Global Chain API", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/me")
async def whoami(
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    """Any authenticated caller: echo identity (used to exercise auth)."""
    return {
        "sub": principal.sub,
        "email": principal.email,
        "name": principal.name,
        "roles": sorted(principal.roles),
    }


@app.get("/api/v1/_kernel/qa-release-check")
async def qa_release_check(
    principal: Principal = Depends(require_role("qa_release", human_only=True)),
) -> dict[str, str]:
    """Example consequential-role gate (human ``qa_release`` only)."""
    return {"sub": principal.sub, "allowed": "qa_release"}
