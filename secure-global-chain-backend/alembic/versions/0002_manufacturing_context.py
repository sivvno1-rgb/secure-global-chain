"""manufacturing context

Creates the manufacturing tables (suppliers, materials, sites, lines, products,
batches, batch_steps, ipc_checks, tasks, equipment) per DOMAIN_MODEL.md, with
the field names and enum values taken verbatim from the design handoff. Targets
PostgreSQL (UUID PKs); enums are stored as VARCHAR + CHECK for portability.

Revision ID: 0002_manufacturing_context
Revises: 0001_identity_audit_kernel
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from sgc.models.enums import (
    BatchStatus,
    MaterialKind,
    Sourcing,
    StatusToken,
    TaskKind,
    sa_enum,
)

# revision identifiers, used by Alembic.
revision: str = "0002_manufacturing_context"
down_revision: Union[str, None] = "0001_identity_audit_kernel"
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
        "suppliers",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("material", sa.String(length=255), nullable=True),
        sa.Column("sourcing", sa_enum(Sourcing), nullable=False),
        sa.Column("site_country", sa.String(length=128), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("status", sa_enum(StatusToken), nullable=False),
        *_ts_columns(),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "materials",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa_enum(MaterialKind), nullable=False),
        sa.Column("supplier_id", _uuid(), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "sites",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("cleanroom", sa.String(length=64), nullable=True),
        sa.Column("gmp_status", sa.String(length=64), nullable=True),
        *_ts_columns(),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "lines",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("site_id", _uuid(), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=True),
        sa.Column("uptime_pct", sa.Float(), nullable=True),
        sa.Column("status", sa_enum(StatusToken), nullable=False),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "products",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("modality", sa.String(length=128), nullable=True),
        *_ts_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "batches",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("product_id", _uuid(), nullable=True),
        sa.Column("line_id", _uuid(), nullable=True),
        sa.Column("stage", sa.String(length=64), nullable=True),
        sa.Column("status", sa_enum(BatchStatus), nullable=False),
        sa.Column("yield_pct", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_by", _uuid(), nullable=True),
        sa.Column("created_by", _uuid(), nullable=True),
        sa.Column("updated_by", _uuid(), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["line_id"], ["lines.id"]),
        sa.ForeignKeyConstraint(["released_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_batches_code", "batches", ["code"], unique=True)

    op.create_table(
        "batch_steps",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("batch_id", _uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("signed_by", _uuid(), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("record_url", sa.String(length=512), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"]),
        sa.ForeignKeyConstraint(["signed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_batch_steps_batch_id", "batch_steps", ["batch_id"], unique=False
    )

    op.create_table(
        "ipc_checks",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("batch_id", _uuid(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("spec_low", sa.Float(), nullable=True),
        sa.Column("spec_high", sa.Float(), nullable=True),
        sa.Column("result", sa_enum(StatusToken), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ipc_checks_batch_id", "ipc_checks", ["batch_id"], unique=False
    )

    op.create_table(
        "tasks",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("assignee_id", _uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("kind", sa_enum(TaskKind), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa_enum(StatusToken), nullable=False),
        sa.Column("batch_id", _uuid(), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_assignee_id", "tasks", ["assignee_id"], unique=False)

    op.create_table(
        "equipment",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=True),
        sa.Column("calibration_due", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calibration_status", sa_enum(StatusToken), nullable=False),
        *_ts_columns(),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("equipment")
    op.drop_index("ix_tasks_assignee_id", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_ipc_checks_batch_id", table_name="ipc_checks")
    op.drop_table("ipc_checks")
    op.drop_index("ix_batch_steps_batch_id", table_name="batch_steps")
    op.drop_table("batch_steps")
    op.drop_index("ix_batches_code", table_name="batches")
    op.drop_table("batches")
    op.drop_table("products")
    op.drop_table("lines")
    op.drop_table("sites")
    op.drop_table("materials")
    op.drop_table("suppliers")
