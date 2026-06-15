"""research & evidence context

Creates hypotheses, evidence_packets, evidence_results, validation_reports,
datasets per DOMAIN_MODEL.md (exact field names and enum value strings). Targets
PostgreSQL.

Revision ID: 0006_research_context
Revises: 0005_telemetry_context
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from sgc.models.enums import (
    EvidenceMethod,
    EvidenceState,
    HypothesisState,
    ValidationReportState,
    sa_enum,
)

# revision identifiers, used by Alembic.
revision: str = "0006_research_context"
down_revision: Union[str, None] = "0005_telemetry_context"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid():
    return postgresql.UUID(as_uuid=True)


def _ts_columns():
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def upgrade() -> None:
    op.create_table(
        "hypotheses",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("posed_by", _uuid(), nullable=True),
        sa.Column("state", sa_enum(HypothesisState), nullable=False),
        sa.Column("domain", sa.String(length=128), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["posed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "evidence_packets",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("hypothesis_id", _uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("dataset_ref", sa.String(length=255), nullable=True),
        sa.Column("method", sa_enum(EvidenceMethod), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("generated_by", sa.String(length=128), nullable=True),
        sa.Column("reviewed_by", _uuid(), nullable=True),
        sa.Column("state", sa_enum(EvidenceState), nullable=False),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["hypothesis_id"], ["hypotheses.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "evidence_results",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("packet_id", _uuid(), nullable=False),
        sa.Column("statistic", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("ci_low", sa.Float(), nullable=True),
        sa.Column("ci_high", sa.Float(), nullable=True),
        sa.Column("p_value", sa.Float(), nullable=True),
        sa.Column("posterior_ref", sa.String(length=255), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["packet_id"], ["evidence_packets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evidence_results_packet_id", "evidence_results", ["packet_id"], unique=False
    )

    op.create_table(
        "validation_reports",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=255), nullable=True),
        sa.Column("author_id", _uuid(), nullable=True),
        sa.Column("state", sa_enum(ValidationReportState), nullable=False),
        sa.Column("signed_by", _uuid(), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["signed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(
        "ix_validation_reports_code", "validation_reports", ["code"], unique=True
    )

    op.create_table(
        "datasets",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("rows", sa.Integer(), nullable=True),
        sa.Column("schema_ref", sa.String(length=255), nullable=True),
        sa.Column("lineage_ref", sa.String(length=255), nullable=True),
        *_ts_columns(),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("datasets")
    op.drop_index("ix_validation_reports_code", table_name="validation_reports")
    op.drop_table("validation_reports")
    op.drop_index("ix_evidence_results_packet_id", table_name="evidence_results")
    op.drop_table("evidence_results")
    op.drop_table("evidence_packets")
    op.drop_table("hypotheses")
