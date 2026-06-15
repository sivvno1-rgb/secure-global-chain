"""identity + audit kernel

Creates the shared identity (``users``) and the append-only, hash-chained
``audit_events`` ledger (SECURITY.md §1, §5). Targets PostgreSQL: UUID PKs,
JSONB documents, an IDENTITY ordering column, and a trigger that blocks
UPDATE/DELETE on the audit ledger so append-only is enforced in the database,
not just the application.

Revision ID: 0001_identity_audit_kernel
Revises:
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_identity_audit_kernel"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_APPEND_ONLY_FN = """
CREATE OR REPLACE FUNCTION audit_events_block_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only: % is not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""

_APPEND_ONLY_TRIGGER = """
CREATE TRIGGER audit_events_no_update_delete
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION audit_events_block_mutation();
"""


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("keycloak_sub", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column(
            "roles",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("keycloak_sub"),
    )
    op.create_index(
        "ix_users_keycloak_sub", "users", ["keycloak_sub"], unique=True
    )

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        # Assigned by the application in the same transaction as the hash link
        # (see sgc.audit.chain.append_audit_event); unique guards concurrency.
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("object_type", sa.String(length=128), nullable=False),
        sa.Column("object_id", sa.String(length=255), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.UniqueConstraint("seq"),
        sa.UniqueConstraint("hash"),
    )
    op.create_index(
        "ix_audit_events_actor_id", "audit_events", ["actor_id"], unique=False
    )

    # Enforce append-only at the database level.
    op.execute(_APPEND_ONLY_FN)
    op.execute(_APPEND_ONLY_TRIGGER)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS audit_events_no_update_delete ON audit_events"
    )
    op.execute("DROP FUNCTION IF EXISTS audit_events_block_mutation()")
    op.drop_index("ix_audit_events_actor_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_users_keycloak_sub", table_name="users")
    op.drop_table("users")
