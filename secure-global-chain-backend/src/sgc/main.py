"""FastAPI application wiring for the security core.

Only the identity + audit kernel is mounted so far. Bounded contexts
(manufacturing, quality, …) will add their routers here later.
"""

from __future__ import annotations

import logging

from fastapi import Depends, FastAPI

from .agents import router as agents_router
from .config import get_settings
from .devices import router as devices_router
from .errors import install_error_handlers
from .executive import router as executive_router
from .intelligence import router as intelligence_router
from .manufacturing import router as manufacturing_router
from .optimization import router as optimization_router
from .quality import router as quality_router
from .research import router as research_router
from .security import Principal, get_current_principal, require_role
from .telemetry import router as telemetry_router
from .views import router as views_router

logger = logging.getLogger("sgc")

app = FastAPI(title="Secure Global Chain API", version="0.1.0")
install_error_handlers(app)
app.include_router(manufacturing_router)
app.include_router(quality_router)
app.include_router(devices_router)
app.include_router(telemetry_router)
app.include_router(intelligence_router)
app.include_router(research_router)
app.include_router(optimization_router)
app.include_router(agents_router)
app.include_router(executive_router)
app.include_router(views_router)

# DEV-ONLY: mount /dev/login when dev auth is enabled (never in production).
if get_settings().dev_auth_enabled:
    from .devauth import router as dev_auth_router

    app.include_router(dev_auth_router)
    logger.warning(
        "SGC_DEV_AUTH is ENABLED — /dev/login mints local tokens and JWTs are "
        "validated with the dev secret, NOT Keycloak. Do not use in production."
    )


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
