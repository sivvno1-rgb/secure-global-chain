"""agent mesh context

Creates agent_runs per DOMAIN_MODEL.md. Agents propose only; proposed_action is
data, human_disposition records the human accept/reject. Targets PostgreSQL.

Revision ID: 0008_agents_context
Revises: 0007_optimization_context
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from sgc.models.enums import AgentRunStatus, sa_enum

# revision identifiers, used by Alembic.
revision: str = "0008_agents_context"
down_revision: Union[str, None] = "0007_optimization_context"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent", sa.String(length=64), nullable=False),
        sa.Column("graph_node", sa.String(length=64), nullable=True),
        sa.Column("input_ref", sa.String(length=255), nullable=True),
        sa.Column("output_ref", sa.String(length=255), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa_enum(AgentRunStatus), nullable=False),
        sa.Column("proposed_action", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("human_disposition", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_runs_agent", "agent_runs", ["agent"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_agent_runs_agent", table_name="agent_runs")
    op.drop_table("agent_runs")
