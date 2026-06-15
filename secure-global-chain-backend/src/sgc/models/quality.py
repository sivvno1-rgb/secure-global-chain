"""Quality & Compliance context models (DOMAIN_MODEL.md §Quality & Compliance).

Field names and enum values are taken verbatim from the design handoff.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, UUIDType
from ._mixins import TimestampMixin
from .enums import Framework, QualityState, Severity, StatusToken, sa_enum


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)


class Deviation(Base, TimestampMixin):
    __tablename__ = "deviations"

    id: Mapped[uuid.UUID] = _pk()
    code: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[Severity] = mapped_column(sa_enum(Severity), nullable=False)
    line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("lines.id"), nullable=True
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("batches.id"), nullable=True
    )
    state: Mapped[QualityState] = mapped_column(
        sa_enum(QualityState), nullable=False, default=QualityState.review
    )
    raised_by: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id"), nullable=True
    )
    raised_at: Mapped[datetime | None] = mapped_column(nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Capa(Base, TimestampMixin):
    __tablename__ = "capas"

    id: Mapped[uuid.UUID] = _pk()
    code: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )
    deviation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("deviations.id"), nullable=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id"), nullable=True
    )
    due_at: Mapped[datetime | None] = mapped_column(nullable=True)
    effectiveness_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    on_time_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[StatusToken] = mapped_column(
        sa_enum(StatusToken), nullable=False, default=StatusToken.neutral
    )


class ComplianceItem(Base, TimestampMixin):
    __tablename__ = "compliance_items"

    id: Mapped[uuid.UUID] = _pk()
    framework: Mapped[Framework] = mapped_column(sa_enum(Framework), nullable=False)
    area: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[StatusToken] = mapped_column(
        sa_enum(StatusToken), nullable=False, default=StatusToken.neutral
    )
    evidence_url: Mapped[str | None] = mapped_column(String(512), nullable=True)


class Audit(Base, TimestampMixin):
    __tablename__ = "audits"

    id: Mapped[uuid.UUID] = _pk()
    scope: Mapped[str | None] = mapped_column(String(255), nullable=True)
    framework: Mapped[Framework] = mapped_column(sa_enum(Framework), nullable=False)
    readiness_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id"), nullable=True
    )


class AuditFinding(Base, TimestampMixin):
    __tablename__ = "audit_findings"

    id: Mapped[uuid.UUID] = _pk()
    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("audits.id"), nullable=False, index=True
    )
    framework: Mapped[Framework] = mapped_column(sa_enum(Framework), nullable=False)
    severity: Mapped[Severity] = mapped_column(sa_enum(Severity), nullable=False)
    status: Mapped[StatusToken] = mapped_column(
        sa_enum(StatusToken), nullable=False, default=StatusToken.neutral
    )
    remediation_due: Mapped[datetime | None] = mapped_column(nullable=True)
