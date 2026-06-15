"""Executive read-model builder seam (ARCHITECTURE.md §2).

Executive dashboards are **read-models** — projections over manufacturing,
quality, devices and telemetry. In production they are projection tables
refreshed by Celery beat per ``range``; here :class:`LiveReadModelBuilder`
computes them on demand from the system-of-record tables (always fresh, no live
fan-out beyond these aggregates). Swap to a projection-backed builder via the
``get_read_model_builder`` dependency.

All list endpoints honor ``?range=daily|weekly|monthly|yearly`` for windowed
metrics.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.devices import Device
from ..models.enums import (
    BatchStatus,
    DeviceState,
    QualityState,
    Severity,
    StatusToken,
)
from ..models.manufacturing import Batch, Line, Product, Supplier
from ..models.quality import ComplianceItem, Deviation
from ..models.telemetry import Excursion

RANGES = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=30),
    "yearly": timedelta(days=365),
}

# Quality states considered "open" (not closed out).
_OPEN_STATES = (
    QualityState.review,
    QualityState.escalated,
    QualityState.watch,
    QualityState.quarantine,
)


def window_cutoff(range_: str, *, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now - RANGES[range_]


class ReadModelBuilder(Protocol):
    async def overview(self, session: AsyncSession, *, range_: str) -> dict: ...
    async def risk(self, session: AsyncSession, *, range_: str) -> dict: ...
    async def portfolio(self, session: AsyncSession, *, range_: str) -> dict: ...


def _risk_level(critical: int, quarantined: int, open_dev: int, open_exc: int) -> str:
    if critical > 0 or quarantined > 0:
        return "Critical"
    if open_dev >= 5 or open_exc > 0:
        return "High"
    return "Watch"


class LiveReadModelBuilder:
    """Computes executive projections on demand from the system of record."""

    async def _count(self, session: AsyncSession, model, *filters) -> int:
        total = await session.scalar(
            select(func.count()).select_from(model).where(*filters)
        )
        return int(total or 0)

    async def _kpis(self, session: AsyncSession) -> dict:
        uptimes = (
            await session.execute(
                select(Line.uptime_pct).where(Line.uptime_pct.isnot(None))
            )
        ).scalars().all()
        line_uptime = round(sum(uptimes) / len(uptimes), 1) if uptimes else 0.0

        suppliers_total = await self._count(session, Supplier)
        suppliers_ok = await self._count(
            session, Supplier, Supplier.status == StatusToken.pass_
        )
        supply_on_time = (
            round(100.0 * suppliers_ok / suppliers_total, 1) if suppliers_total else 0.0
        )

        ci_total = await self._count(session, ComplianceItem)
        ci_ok = await self._count(
            session, ComplianceItem, ComplianceItem.state == StatusToken.pass_
        )
        compliance_score = round(100.0 * ci_ok / ci_total, 1) if ci_total else 100.0

        return {
            "line_uptime_pct": line_uptime,
            "supply_on_time_pct": supply_on_time,
            "compliance_score": compliance_score,
        }

    async def _risk(self, session: AsyncSession) -> dict:
        open_dev = await self._count(session, Deviation, Deviation.state.in_(_OPEN_STATES))
        critical = await self._count(
            session, Deviation,
            Deviation.state.in_(_OPEN_STATES), Deviation.severity == Severity.critical,
        )
        escalated = await self._count(
            session, Deviation, Deviation.state == QualityState.escalated
        )
        quarantined = await self._count(
            session, Device, Device.state == DeviceState.quarantined
        )
        open_exc = await self._count(session, Excursion, Excursion.ended_at.is_(None))
        return {
            "risk_level": _risk_level(critical, quarantined, open_dev, open_exc),
            "open_deviations": open_dev,
            "critical_deviations": critical,
            "escalated_deviations": escalated,
            "quarantined_devices": quarantined,
            "open_excursions": open_exc,
        }

    async def overview(self, session: AsyncSession, *, range_: str) -> dict:
        cutoff = window_cutoff(range_)
        batches_total = await self._count(session, Batch)
        in_process = await self._count(
            session, Batch, Batch.status == BatchStatus.in_process
        )
        released = await self._count(
            session, Batch,
            Batch.status == BatchStatus.released, Batch.released_at >= cutoff,
        )
        products = await self._count(session, Product)
        return {
            "range": range_,
            "kpis": await self._kpis(session),
            "portfolio": {
                "products": products,
                "batches_total": batches_total,
                "batches_in_process": in_process,
                "batches_released": released,
            },
            "risk": await self._risk(session),
        }

    async def risk(self, session: AsyncSession, *, range_: str) -> dict:
        risk = await self._risk(session)
        by_severity = {}
        for sev in Severity:
            by_severity[sev.value] = await self._count(
                session, Deviation,
                Deviation.state.in_(_OPEN_STATES), Deviation.severity == sev,
            )
        return {"range": range_, "by_severity": by_severity, **risk}

    async def portfolio(self, session: AsyncSession, *, range_: str) -> dict:
        cutoff = window_cutoff(range_)
        products = (await session.execute(select(Product).order_by(Product.code))).scalars().all()
        rows = []
        batches_total_all = 0
        released_all = 0
        for product in products:
            total = await self._count(session, Batch, Batch.product_id == product.id)
            released = await self._count(
                session, Batch,
                Batch.product_id == product.id,
                Batch.status == BatchStatus.released, Batch.released_at >= cutoff,
            )
            batches_total_all += total
            released_all += released
            rows.append({
                "code": product.code, "name": product.name,
                "batches_total": total, "batches_released": released,
            })
        return {
            "range": range_,
            "products": rows,
            "batches_total": batches_total_all,
            "batches_released": released_all,
        }


def get_read_model_builder() -> ReadModelBuilder:
    return LiveReadModelBuilder()
