"""Executive read-models API. Prefix ``/api/v1/executive``.

Read-only projections over the other centers. Honors
``?range=daily|weekly|monthly|yearly``. Restricted to executive/auditor roles.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..security import Principal, require_any_role
from .readmodel import RANGES, ReadModelBuilder, get_read_model_builder
from .schemas import ExecutiveOverview, PortfolioView, RiskView

router = APIRouter(prefix="/api/v1/executive", tags=["executive"])

# executive + auditor may read the dashboards.
_reader = require_any_role("executive", "auditor")


def _validate_range(range_: str) -> str:
    if range_ not in RANGES:
        raise HTTPException(
            status_code=422, detail=f"range must be one of {tuple(RANGES)}"
        )
    return range_


@router.get("/overview", response_model=ExecutiveOverview)
async def overview(
    range: str = Query("monthly"),
    builder: ReadModelBuilder = Depends(get_read_model_builder),
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(_reader),
):
    return await builder.overview(session, range_=_validate_range(range))


@router.get("/risk", response_model=RiskView)
async def risk(
    range: str = Query("monthly"),
    builder: ReadModelBuilder = Depends(get_read_model_builder),
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(_reader),
):
    return await builder.risk(session, range_=_validate_range(range))


@router.get("/portfolio", response_model=PortfolioView)
async def portfolio(
    range: str = Query("monthly"),
    builder: ReadModelBuilder = Depends(get_read_model_builder),
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(_reader),
):
    return await builder.portfolio(session, range_=_validate_range(range))
