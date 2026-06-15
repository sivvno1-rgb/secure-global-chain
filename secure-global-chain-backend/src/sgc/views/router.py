"""Backend-for-frontend view-models. Prefix ``/api/v1/views``.

Read-only, role-gated projections the operator screens consume directly
(FRONTEND_WIRING.md §2/§7). No audit events — consequential actions still use
the existing gated routes (the frontend calls those via ``SGCLive.act()``).

Every key in the §7 master registry gets exactly one route here; the route table
is generated from :data:`sgc.views.registry.REGISTRY` so role-gating stays
consistent and new screens are added by appending one row there.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..security import Principal, require_role
from .registry import REGISTRY, ViewSpec

router = APIRouter(prefix="/api/v1/views", tags=["views"])


def _make_endpoint(spec: ViewSpec):
    """Build the handler for one view. Captures ``spec`` per route."""

    async def endpoint(
        range: str | None = Query(None, description="daily|weekly|monthly|yearly (reserved)"),
        session: AsyncSession = Depends(get_session),
        _: Principal = Depends(require_role(spec.role)),
    ) -> dict:
        # new-domain / illustrative / not-yet-composed rows: the frontend falls
        # back to its built-in demo data when the body is empty.
        if spec.builder is None:
            return {}
        return await spec.builder(session, range)

    return endpoint


for _spec in REGISTRY:
    router.add_api_route(
        f"/{_spec.key}",
        _make_endpoint(_spec),
        methods=["GET"],
        response_model=_spec.response_model,
        response_model_exclude_none=True,
        name=f"view_{_spec.key.replace('/', '_').replace('-', '_')}",
        summary=f"{_spec.key} view-model ({_spec.availability})",
    )
