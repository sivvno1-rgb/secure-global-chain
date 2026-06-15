"""Graph-store dependency.

Dev/test default: build an in-memory store projected from the current Postgres
state on each request (always consistent, no stale sync). Swap to the Neo4j
adapter — which is kept pre-synced by the outbox→Celery worker — by overriding
this dependency.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from .graph import GraphStore, InMemoryGraphStore
from .projector import project_from_postgres


async def get_graph_store(
    session: AsyncSession = Depends(get_session),
) -> GraphStore:
    store = InMemoryGraphStore()
    await project_from_postgres(session, store)
    return store
