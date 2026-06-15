"""View-model schemas. Field names are the exact contract the screens render
(FRONTEND_WIRING.md §4) — do not rename.
"""

from __future__ import annotations

from pydantic import BaseModel


class Headline(BaseModel):
    mission_pct: int
    critical_events: int


class Kpi(BaseModel):
    label: str
    v: str
    tone: str  # pass | warn | fail
    u: str | None = None  # unit; omitted when absent (response_model_exclude_none)


class MissionEvent(BaseModel):
    sev: str  # fail | warn
    c: str  # hex accent
    cat: str
    title: str
    desc: str
    impact: list[list[str]]  # [[label, value], …]
    action: str
    go: str  # target view id
    btn: str


class MissionView(BaseModel):
    headline: Headline
    kpis: list[Kpi]
    events: list[MissionEvent]
    facilities: list[list[str]]  # [name, detail, status]
    shipments: list[list[str]]  # [name, detail, status]
