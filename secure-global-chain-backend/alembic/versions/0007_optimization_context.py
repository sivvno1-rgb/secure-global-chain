"""optimization & scenario lab context

Creates schedules, schedule_slots, scenarios per DOMAIN_MODEL.md (exact field
names and enum value strings). Targets PostgreSQL.

Revision ID: 0007_optimization_context
Revises: 0006_research_context
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from sgc.models.enums import ScheduleState, SolverStatus, sa_enum

# revision identifiers, used by Alembic.
revision: str = "0007_optimization_context"
down_revision: Union[str, None] = "0006_research_context"
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
        "schedules",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("line_id", _uuid(), nullable=True),
        sa.Column("horizon", sa.Integer(), nullable=True),
        sa.Column("objective", sa.String(length=128), nullable=True),
        sa.Column("generated_by", sa.String(length=128), nullable=True),
        sa.Column("state", sa_enum(ScheduleState), nullable=False),
        sa.Column("solver_status", sa_enum(SolverStatus), nullable=True),
        sa.Column("committed_by", _uuid(), nullable=True),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["line_id"], ["lines.id"]),
        sa.ForeignKeyConstraint(["committed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "schedule_slots",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("schedule_id", _uuid(), nullable=False),
        sa.Column("batch_id", _uuid(), nullable=True),
        sa.Column("start_at", sa.Integer(), nullable=True),
        sa.Column("end_at", sa.Integer(), nullable=True),
        sa.Column("setup_minutes", sa.Integer(), nullable=False),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["schedule_id"], ["schedules.id"]),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_schedule_slots_schedule_id", "schedule_slots", ["schedule_id"], unique=False
    )

    op.create_table(
        "scenarios",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("base_schedule_id", _uuid(), nullable=True),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("kpi_delta", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", _uuid(), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["base_schedule_id"], ["schedules.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("scenarios")
    op.drop_index("ix_schedule_slots_schedule_id", table_name="schedule_slots")
    op.drop_table("schedule_slots")
    op.drop_table("schedules")
