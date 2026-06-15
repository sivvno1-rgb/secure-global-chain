"""Pydantic v2 schemas for the Executive read-models."""

from __future__ import annotations

from pydantic import BaseModel


class KpiTiles(BaseModel):
    line_uptime_pct: float
    supply_on_time_pct: float
    compliance_score: float


class PortfolioSummary(BaseModel):
    products: int
    batches_total: int
    batches_in_process: int
    batches_released: int


class RiskSummary(BaseModel):
    risk_level: str
    open_deviations: int
    critical_deviations: int
    escalated_deviations: int
    quarantined_devices: int
    open_excursions: int


class ExecutiveOverview(BaseModel):
    range: str
    kpis: KpiTiles
    portfolio: PortfolioSummary
    risk: RiskSummary


class RiskView(BaseModel):
    range: str
    risk_level: str
    open_deviations: int
    critical_deviations: int
    escalated_deviations: int
    quarantined_devices: int
    open_excursions: int
    by_severity: dict[str, int]


class ProductLine(BaseModel):
    code: str
    name: str
    batches_total: int
    batches_released: int


class PortfolioView(BaseModel):
    range: str
    products: list[ProductLine]
    batches_total: int
    batches_released: int
