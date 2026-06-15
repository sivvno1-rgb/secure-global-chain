"""CP-SAT schedule solver seam."""

from __future__ import annotations

from sgc.models.enums import SolverStatus
from sgc.optimization.solver import CpSatScheduleSolver, Job


def test_solver_sequences_without_overlap():
    solver = CpSatScheduleSolver()
    jobs = [
        Job(batch_id="A", duration_minutes=60),
        Job(batch_id="B", duration_minutes=90),
        Job(batch_id="C", duration_minutes=30),
    ]
    result = solver.solve(jobs, horizon_minutes=1000)
    assert result.status in (SolverStatus.optimal, SolverStatus.feasible)
    assert len(result.slots) == 3
    # No overlap: each slot starts at or after the previous end.
    ordered = sorted(result.slots, key=lambda s: s.start_at)
    for prev, nxt in zip(ordered, ordered[1:]):
        assert nxt.start_at >= prev.end_at
    # Minimal makespan for a single line == sum of durations.
    assert result.makespan == 180


def test_solver_reports_infeasible_when_horizon_too_small():
    solver = CpSatScheduleSolver()
    jobs = [Job(batch_id="A", duration_minutes=100), Job(batch_id="B", duration_minutes=100)]
    result = solver.solve(jobs, horizon_minutes=120)  # need 200, only 120
    assert result.status is SolverStatus.infeasible
    assert result.slots == []


def test_solver_handles_setup_minutes_and_empty():
    solver = CpSatScheduleSolver()
    res = solver.solve([Job(batch_id="A", duration_minutes=40, setup_minutes=20)], horizon_minutes=100)
    assert res.status in (SolverStatus.optimal, SolverStatus.feasible)
    assert res.makespan == 60  # 40 + 20 setup

    empty = solver.solve([], horizon_minutes=100)
    assert empty.status is SolverStatus.optimal
    assert empty.makespan == 0
