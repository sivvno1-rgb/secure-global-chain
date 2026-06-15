"""Async SQLAlchemy engine/session wiring and cross-dialect column types.

Production runs on PostgreSQL (asyncpg). The test suite runs the same models on
aiosqlite, so column types use ``with_variant`` to render the Postgres-native
type (UUID / JSONB) on Postgres while remaining portable on SQLite.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import JSON, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

# UUID surrogate PK type: native ``uuid`` on Postgres, CHAR(32) elsewhere.
UUIDType = Uuid(as_uuid=True)

# JSON document type: ``jsonb`` on Postgres, generic JSON elsewhere.
JSONType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url, future=True)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an async session."""
    async with get_sessionmaker()() as session:
        yield session
