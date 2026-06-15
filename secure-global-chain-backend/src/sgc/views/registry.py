"""Master registry of every view-model endpoint (FRONTEND_WIRING.md §7).

One :class:`ViewSpec` per row in the §7 table. The router (``router.py``) turns
each into a role-gated, read-only ``GET /api/v1/views/<key>``.

``availability``:

- ``live``      — composed from existing context services (``builder`` set).
- ``new-domain``— needs a backend model that doesn't exist yet; ``builder`` is
  ``None`` so the route returns ``{}`` and the frontend keeps its demo data.
- ``illustrative`` — a designed visualization with no operational source; also
  returns ``{}``.

Some rows are flagged ``live`` in §7 but their backing domain (decisions,
reviews, incidents, economy/finance indicators) is not modeled in this repo yet;
they carry ``builder=None`` (return ``{}``) until that context lands, while
staying flagged ``live`` here so the build order is visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from . import composed, service
from .schemas import MissionView, OperationsView, QualityView

Builder = Callable[[AsyncSession, str | None], Awaitable[dict]]


@dataclass(frozen=True)
class ViewSpec:
    key: str  # path after /api/v1/views/, may contain slashes (e.g. "ops/facility-map")
    role: str  # required realm role
    availability: str  # live | new-domain | illustrative
    builder: Builder | None = None  # None → route returns {}
    response_model: type[BaseModel] | None = None  # typed contract (§4–6) when known


# Order follows the §7 "build order (live first)".
REGISTRY: list[ViewSpec] = [
    # --- fully-specced live contracts (§4–6) ---------------------------------
    ViewSpec("mission", "operator", "live", service.build_mission, MissionView),
    ViewSpec("operations", "operator", "live", service.build_operations, OperationsView),
    ViewSpec("quality", "quality", "live", service.build_quality, QualityView),
    # --- other live rows (provisional shapes) --------------------------------
    ViewSpec("ops/facility-map", "operator", "live", composed.build_ops_facility_map),
    ViewSpec("optimization/schedule", "planner", "live", composed.build_optimization_schedule),
    ViewSpec("optimization/scenario", "planner", "live", composed.build_optimization_scenario),
    ViewSpec("agents", "operator", "live", composed.build_agents),
    ViewSpec("intel/globe", "operator", "live", composed.build_intel_globe),
    ViewSpec("intel/dependencies", "operator", "live", composed.build_intel_dependencies),
    ViewSpec("intel/hardware", "operator", "live", composed.build_intel_hardware),
    ViewSpec("intel/evidence", "operator", "live", composed.build_intel_evidence),
    ViewSpec("research/reports", "researcher", "live", composed.build_research_reports),
    ViewSpec("research/hypotheses", "researcher", "live", composed.build_research_hypotheses),
    ViewSpec("research/evidence", "researcher", "live", composed.build_research_evidence),
    ViewSpec("research/lockout", "researcher", "live", composed.build_research_lockout),
    # --- live in §7 but backing domain not modeled yet → {} ------------------
    ViewSpec("decisions", "operator", "live", None),
    ViewSpec("reviews", "executive", "live", None),
    ViewSpec("escalate", "operator", "live", None),
    ViewSpec("intel/economy", "executive", "live", None),
    ViewSpec("economy", "executive", "live", None),
    # --- new-domain (return {} until the model lands) ------------------------
    ViewSpec("ops/trade-ports", "operator", "new-domain", None),
    ViewSpec("intel/finance", "executive", "new-domain", None),
    ViewSpec("intel/security", "operator", "new-domain", None),
    ViewSpec("research/trust", "researcher", "new-domain", None),
    # --- illustrative (intentionally demo-only) ------------------------------
    ViewSpec("ops/peers", "operator", "illustrative", None),
    ViewSpec("intel/workforce", "operator", "illustrative", None),
    ViewSpec("intel/program", "operator", "illustrative", None),
]
