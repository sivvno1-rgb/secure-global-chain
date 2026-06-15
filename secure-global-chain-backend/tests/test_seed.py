"""The demo seed populates every context and is idempotent."""

from __future__ import annotations

import pytest

from sgc.seed import seed


@pytest.mark.asyncio
async def test_seed_populates_all_contexts(db_session):
    counts = await seed(db_session)
    # representative coverage across contexts
    assert counts["batches"] == 12
    assert counts["lines"] == 3
    assert counts["deviations"] == 3
    assert counts["devices"] == 7
    assert counts["firmware_builds"] == 2
    assert counts["excursions"] == 2
    assert counts["agent_runs"] == 3
    assert counts["users"] == 6


@pytest.mark.asyncio
async def test_seed_is_idempotent(db_session):
    first = await seed(db_session)
    second = await seed(db_session)
    assert first == second  # re-running changes nothing
