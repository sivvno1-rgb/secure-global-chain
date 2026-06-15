"""Scheduling solver seam (AGENTS_AND_COMPUTE.md §4).

A single-line (single-machine) sequencing problem: place jobs with given
durations and setup times on one line without overlap, within the horizon,
minimizing makespan. CP-SAT (OR-Tools) solves it; solves are time-boxed and
return an honest ``solver_status`` (optimal/feasible/infeasible/timeout).

In production this runs in the locked-down Celery ``optimize`` queue. Here
:class:`CpSatScheduleSolver` runs synchronously so the flow is testable. The
solver is **advisory** — a human commits a schedule. Swap via the
``get_schedule_solver`` dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ortools.sat.python import cp_model

from ..models.enums import SolverStatus

# Default solve time box (seconds).
DEFAULT_TIME_LIMIT = 5.0


@dataclass(frozen=True)
class Job:
    batch_id: str | None
    duration_minutes: int
    setup_minutes: int = 0


@dataclass(frozen=True)
class SolvedSlot:
    batch_id: str | None
    start_at: int  # minute offset from horizon start
    end_at: int
    setup_minutes: int


@dataclass
class SolveResult:
    status: SolverStatus
    slots: list[SolvedSlot] = field(default_factory=list)
    makespan: int | None = None


class ScheduleSolver(Protocol):
    def solve(
        self, jobs: list[Job], *, horizon_minutes: int, time_limit: float = DEFAULT_TIME_LIMIT
    ) -> SolveResult: ...


_STATUS_MAP = {
    cp_model.OPTIMAL: SolverStatus.optimal,
    cp_model.FEASIBLE: SolverStatus.feasible,
    cp_model.INFEASIBLE: SolverStatus.infeasible,
}


class CpSatScheduleSolver:
    """OR-Tools CP-SAT single-line scheduler (minimize makespan)."""

    def solve(
        self,
        jobs: list[Job],
        *,
        horizon_minutes: int,
        time_limit: float = DEFAULT_TIME_LIMIT,
    ) -> SolveResult:
        if not jobs:
            return SolveResult(status=SolverStatus.optimal, slots=[], makespan=0)

        model = cp_model.CpModel()
        horizon = int(horizon_minutes)
        starts, ends, intervals = [], [], []
        for i, job in enumerate(jobs):
            length = int(job.duration_minutes) + int(job.setup_minutes)
            start = model.NewIntVar(0, horizon, f"start_{i}")
            end = model.NewIntVar(0, horizon, f"end_{i}")
            interval = model.NewIntervalVar(start, length, end, f"iv_{i}")
            starts.append(start)
            ends.append(end)
            intervals.append(interval)

        model.AddNoOverlap(intervals)
        makespan = model.NewIntVar(0, horizon, "makespan")
        model.AddMaxEquality(makespan, ends)
        model.Minimize(makespan)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit)
        status = solver.Solve(model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            slots = []
            for i, job in enumerate(jobs):
                slots.append(SolvedSlot(
                    batch_id=job.batch_id,
                    start_at=int(solver.Value(starts[i])),
                    end_at=int(solver.Value(ends[i])),
                    setup_minutes=job.setup_minutes,
                ))
            slots.sort(key=lambda s: s.start_at)
            return SolveResult(
                status=_STATUS_MAP[status],
                slots=slots,
                makespan=int(solver.Value(makespan)),
            )
        if status == cp_model.INFEASIBLE:
            return SolveResult(status=SolverStatus.infeasible)
        return SolveResult(status=SolverStatus.timeout)


def get_schedule_solver() -> ScheduleSolver:
    return CpSatScheduleSolver()
