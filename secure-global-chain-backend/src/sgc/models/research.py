"""Research & Evidence context models (DOMAIN_MODEL.md §Research & Evidence).

Computation (frequentist scipy / Bayesian) runs in Celery and writes results
here. The interpretation (supported/refuted) is a human disposition — never set
by code (AGENTS_AND_COMPUTE.md §3).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base, UUIDType
from ._mixins import TimestampMixin
from .enums import (
    EvidenceMethod,
    EvidenceState,
    HypothesisState,
    ValidationReportState,
    sa_enum,
)


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)


class Hypothesis(Base, TimestampMixin):
    __tablename__ = "hypotheses"

    id: Mapped[uuid.UUID] = _pk()
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    posed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id"), nullable=True
    )
    state: Mapped[HypothesisState] = mapped_column(
        sa_enum(HypothesisState), nullable=False, default=HypothesisState.open
    )
    domain: Mapped[str | None] = mapped_column(String(128), nullable=True)


class EvidencePacket(Base, TimestampMixin):
    __tablename__ = "evidence_packets"

    id: Mapped[uuid.UUID] = _pk()
    hypothesis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("hypotheses.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    method: Mapped[EvidenceMethod] = mapped_column(
        sa_enum(EvidenceMethod), nullable=False
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id"), nullable=True
    )
    state: Mapped[EvidenceState] = mapped_column(
        sa_enum(EvidenceState), nullable=False, default=EvidenceState.pending
    )

    results: Mapped[list["EvidenceResult"]] = relationship(
        back_populates="packet", cascade="all, delete-orphan"
    )


class EvidenceResult(Base, TimestampMixin):
    __tablename__ = "evidence_results"

    id: Mapped[uuid.UUID] = _pk()
    packet_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("evidence_packets.id"), nullable=False, index=True
    )
    statistic: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    ci_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    ci_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    p_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    posterior_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)

    packet: Mapped["EvidencePacket"] = relationship(back_populates="results")


class ValidationReport(Base, TimestampMixin):
    __tablename__ = "validation_reports"

    id: Mapped[uuid.UUID] = _pk()
    code: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )
    scope: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id"), nullable=True
    )
    state: Mapped[ValidationReportState] = mapped_column(
        sa_enum(ValidationReportState), nullable=False,
        default=ValidationReportState.draft,
    )
    signed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id"), nullable=True
    )
    signed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Dataset(Base, TimestampMixin):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schema_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lineage_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
