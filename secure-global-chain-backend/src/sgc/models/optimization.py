"""Optimization & Scenario Lab models (DOMAIN_MODEL.md §Optimization).

Schedules are solved by OR-Tools (Celery ``optimize`` queue). The solver is
**advisory** — a human commits a schedule (AGENTS_AND_COMPUTE.md §4).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base, JSONType, UUIDType
from ._mixins import TimestampMixin
from .enums import ScheduleState, SolverStatus, sa_enum


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)


class Schedule(Base, TimestampMixin):
    __tablename__ = "schedules"

    id: Mapped[uuid.UUID] = _pk()
    line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("lines.id"), nullable=True
    )
    # Planning horizon in minutes.
    horizon: Mapped[int | None] = mapped_column(Integer, nullable=True)
    objective: Mapped[str | None] = mapped_column(String(128), nullable=True)
    generated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    state: Mapped[ScheduleState] = mapped_column(
        sa_enum(ScheduleState), nullable=False, default=ScheduleState.draft
    )
    solver_status: Mapped[SolverStatus | None] = mapped_column(
        sa_enum(SolverStatus), nullable=True
    )
    committed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id"), nullable=True
    )
    committed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    slots: Mapped[list["ScheduleSlot"]] = relationship(
        back_populates="schedule",
        order_by="ScheduleSlot.start_at",
        cascade="all, delete-orphan",
    )


class ScheduleSlot(Base, TimestampMixin):
    __tablename__ = "schedule_slots"

    id: Mapped[uuid.UUID] = _pk()
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("schedules.id"), nullable=False, index=True
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("batches.id"), nullable=True
    )
    start_at: Mapped[int | None] = mapped_column(Integer, nullable=True)  # minute offset
    end_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    setup_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    schedule: Mapped["Schedule"] = relationship(back_populates="slots")


class Scenario(Base, TimestampMixin):
    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("schedules.id"), nullable=True
    )
    params: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    kpi_delta: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id"), nullable=True
    )
