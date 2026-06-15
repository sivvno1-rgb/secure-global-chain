"""Backend-for-frontend view-models. Prefix ``/api/v1/views``.

Read-only, role-gated projections the operator screens consume directly
(FRONTEND_WIRING.md). No audit events — consequential actions still use the
existing gated routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..security import Principal, require_role
from . import service
from .schemas import MissionView

router = APIRouter(prefix="/api/v1/views", tags=["views"])


@router.get("/mission", response_model=MissionView, response_model_exclude_none=True)
async def mission(
    range: str | None = Query(None, description="daily|weekly|monthly|yearly (reserved)"),
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role("operator")),
) -> dict:
    """Mission Control view-model (§4): headline, 6 KPIs, ranked events,
    facility and shipment status."""
    return await service.build_mission(session)
