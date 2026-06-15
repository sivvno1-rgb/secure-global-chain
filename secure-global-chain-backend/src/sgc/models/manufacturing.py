"""Manufacturing context models (DOMAIN_MODEL.md §Manufacturing).

Field names and enum values are taken verbatim from the design handoff so the
frontend binds with zero remapping.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base, UUIDType
from ._mixins import TimestampMixin
from .enums import (
    BatchStatus,
    MaterialKind,
    Sourcing,
    StatusToken,
    TaskKind,
    sa_enum,
)


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)


class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    material: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sourcing: Mapped[Sourcing] = mapped_column(sa_enum(Sourcing), nullable=False)
    site_country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[StatusToken] = mapped_column(
        sa_enum(StatusToken), nullable=False, default=StatusToken.neutral
    )


class Material(Base, TimestampMixin):
    __tablename__ = "materials"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[MaterialKind] = mapped_column(sa_enum(MaterialKind), nullable=False)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("suppliers.id"), nullable=True
    )


class Site(Base, TimestampMixin):
    __tablename__ = "sites"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cleanroom: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gmp_status: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Line(Base, TimestampMixin):
    __tablename__ = "lines"

    id: Mapped[uuid.UUID] = _pk()
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("sites.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uptime_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[StatusToken] = mapped_column(
        sa_enum(StatusToken), nullable=False, default=StatusToken.neutral
    )

    site: Mapped["Site | None"] = relationship()


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = _pk()
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    modality: Mapped[str | None] = mapped_column(String(128), nullable=True)


class Batch(Base, TimestampMixin):
    __tablename__ = "batches"

    id: Mapped[uuid.UUID] = _pk()
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("products.id"), nullable=True
    )
    line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("lines.id"), nullable=True
    )
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[BatchStatus] = mapped_column(
        sa_enum(BatchStatus), nullable=False, default=BatchStatus.in_process
    )
    yield_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(nullable=True)
    released_by: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id"), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id"), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id"), nullable=True
    )

    product: Mapped["Product | None"] = relationship()
    line: Mapped["Line | None"] = relationship()
    steps: Mapped[list["BatchStep"]] = relationship(
        back_populates="batch",
        order_by="BatchStep.sequence",
        cascade="all, delete-orphan",
    )
    ipc_checks: Mapped[list["IpcCheck"]] = relationship(
        back_populates="batch",
        order_by="IpcCheck.at",
        cascade="all, delete-orphan",
    )


class BatchStep(Base, TimestampMixin):
    __tablename__ = "batch_steps"

    id: Mapped[uuid.UUID] = _pk()
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("batches.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id"), nullable=True
    )
    signed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    record_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    batch: Mapped["Batch"] = relationship(back_populates="steps")


class IpcCheck(Base, TimestampMixin):
    __tablename__ = "ipc_checks"

    id: Mapped[uuid.UUID] = _pk()
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("batches.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    spec_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    spec_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    result: Mapped[StatusToken] = mapped_column(
        sa_enum(StatusToken), nullable=False, default=StatusToken.neutral
    )
    at: Mapped[datetime | None] = mapped_column(nullable=True)

    batch: Mapped["Batch"] = relationship(back_populates="ipc_checks")


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = _pk()
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[TaskKind] = mapped_column(sa_enum(TaskKind), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[StatusToken] = mapped_column(
        sa_enum(StatusToken), nullable=False, default=StatusToken.neutral
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("batches.id"), nullable=True
    )


class Equipment(Base, TimestampMixin):
    __tablename__ = "equipment"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    calibration_due: Mapped[datetime | None] = mapped_column(nullable=True)
    calibration_status: Mapped[StatusToken] = mapped_column(
        sa_enum(StatusToken), nullable=False, default=StatusToken.neutral
    )
