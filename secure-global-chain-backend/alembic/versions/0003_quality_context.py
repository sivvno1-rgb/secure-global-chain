"""quality & compliance context

Creates deviations, capas, compliance_items, audits, audit_findings per
DOMAIN_MODEL.md (exact field names and enum value strings). Targets PostgreSQL.

Revision ID: 0003_quality_context
Revises: 0002_manufacturing_context
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from sgc.models.enums import (
    Framework,
    QualityState,
    Severity,
    StatusToken,
    sa_enum,
)

# revision identifiers, used by Alembic.
revision: str = "0003_quality_context"
down_revision: Union[str, None] = "0002_manufacturing_context"
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
        "deviations",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("severity", sa_enum(Severity), nullable=False),
        sa.Column("line_id", _uuid(), nullable=True),
        sa.Column("batch_id", _uuid(), nullable=True),
        sa.Column("state", sa_enum(QualityState), nullable=False),
        sa.Column("raised_by", _uuid(), nullable=True),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["line_id"], ["lines.id"]),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"]),
        sa.ForeignKeyConstraint(["raised_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_deviations_code", "deviations", ["code"], unique=True)

    op.create_table(
        "capas",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("deviation_id", _uuid(), nullable=True),
        sa.Column("owner_id", _uuid(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effectiveness_state", sa.String(length=64), nullable=True),
        sa.Column("on_time_pct", sa.Float(), nullable=True),
        sa.Column("status", sa_enum(StatusToken), nullable=False),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["deviation_id"], ["deviations.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_capas_code", "capas", ["code"], unique=True)

    op.create_table(
        "compliance_items",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("framework", sa_enum(Framework), nullable=False),
        sa.Column("area", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("state", sa_enum(StatusToken), nullable=False),
        sa.Column("evidence_url", sa.String(length=512), nullable=True),
        *_ts_columns(),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "audits",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("scope", sa.String(length=255), nullable=True),
        sa.Column("framework", sa_enum(Framework), nullable=False),
        sa.Column("readiness_pct", sa.Float(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lead_id", _uuid(), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["lead_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "audit_findings",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("audit_id", _uuid(), nullable=False),
        sa.Column("framework", sa_enum(Framework), nullable=False),
        sa.Column("severity", sa_enum(Severity), nullable=False),
        sa.Column("status", sa_enum(StatusToken), nullable=False),
        sa.Column("remediation_due", sa.DateTime(timezone=True), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["audit_id"], ["audits.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_findings_audit_id", "audit_findings", ["audit_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_audit_findings_audit_id", table_name="audit_findings")
    op.drop_table("audit_findings")
    op.drop_table("audits")
    op.drop_table("compliance_items")
    op.drop_index("ix_capas_code", table_name="capas")
    op.drop_table("capas")
    op.drop_index("ix_deviations_code", table_name="deviations")
    op.drop_table("deviations")
