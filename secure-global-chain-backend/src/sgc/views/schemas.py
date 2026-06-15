"""View-model schemas. Field names are the exact contract the screens render
(FRONTEND_WIRING.md §4–6) — do not rename.

Fields that a backend can only fill incrementally are optional; the router uses
``response_model_exclude_none`` so any field the builder omits is dropped and the
frontend keeps its built-in demo value (FRONTEND_WIRING.md §4 note).
"""

from __future__ import annotations

from pydantic import BaseModel


# --- mission (§4) --------------------------------------------------------------
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


# --- operations (§6) -----------------------------------------------------------
class OpsTask(BaseModel):
    id: str
    t: str
    st: str  # done | now | todo
    kind: str
    due: str | None = None


class OpsDevice(BaseModel):
    id: str
    loc: str
    st: str  # pass | warn | fail
    live: bool


class OpsEnv(BaseModel):
    k: str
    v: str
    ok: bool
    u: str | None = None


class OpsBatch(BaseModel):
    code: str
    stage: str | None = None
    completion: int | None = None


class OperationsView(BaseModel):
    # All optional: a field the builder can't compose is omitted so the screen
    # falls back to demo for it.
    tasks: list[OpsTask] | None = None
    devices: list[OpsDevice] | None = None
    env: list[OpsEnv] | None = None
    batch: OpsBatch | None = None


# --- quality (§5) --------------------------------------------------------------
class QcStatus(BaseModel):
    v: str  # pass | warn | fail | info
    t: str  # human label


class QcChange(BaseModel):
    id: str
    t: str
    st: QcStatus
    type: str | None = None
    owner: str | None = None
    due: str | None = None


class QcImprovement(BaseModel):
    t: str
    st: QcStatus
    method: str | None = None
    impact: str | None = None


class QcAgent(BaseModel):
    t: str
    m: str | None = None
    act: str | None = None


class QualityView(BaseModel):
    kpis: list[Kpi] | None = None
    changes: list[QcChange] | None = None
    reviews: list[list] | None = None  # [doc, dueDate, status]
    docs: list[list] | None = None  # [label, pct]
    ci: list[QcImprovement] | None = None
    agents: list[QcAgent] | None = None
