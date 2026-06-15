"""device fleet context

Creates firmware_builds, devices, firmware_rollouts, device_attestations,
provision_requests per DOMAIN_MODEL.md (exact field names and enum value
strings). Device identity keys and firmware signing keys live in Vault PKI — only
public keys, digests and references are stored here. Targets PostgreSQL.

Revision ID: 0004_devices_context
Revises: 0003_quality_context
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from sgc.models.enums import DeviceState, FirmwareState, StatusToken, sa_enum

# revision identifiers, used by Alembic.
revision: str = "0004_devices_context"
down_revision: Union[str, None] = "0003_quality_context"
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
        "firmware_builds",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("digest", sa.String(length=128), nullable=True),
        sa.Column("signed_by", _uuid(), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state", sa_enum(FirmwareState), nullable=False),
        sa.Column("release_notes", sa.Text(), nullable=True),
        sa.Column("artifact_url", sa.String(length=512), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["signed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version"),
    )
    op.create_index(
        "ix_firmware_builds_version", "firmware_builds", ["version"], unique=True
    )

    op.create_table(
        "devices",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("serial", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("site_id", _uuid(), nullable=True),
        sa.Column("line_id", _uuid(), nullable=True),
        sa.Column("hw_identity_pubkey", sa.Text(), nullable=True),
        sa.Column("state", sa_enum(DeviceState), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("firmware_id", _uuid(), nullable=True),
        sa.Column("tamper_locked", sa.Boolean(), nullable=False),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.ForeignKeyConstraint(["line_id"], ["lines.id"]),
        sa.ForeignKeyConstraint(["firmware_id"], ["firmware_builds.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("serial"),
    )
    op.create_index("ix_devices_serial", "devices", ["serial"], unique=True)

    op.create_table(
        "firmware_rollouts",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("firmware_id", _uuid(), nullable=False),
        sa.Column("cohort", sa.String(length=128), nullable=True),
        sa.Column("devices_total", sa.Integer(), nullable=False),
        sa.Column("devices_done", sa.Integer(), nullable=False),
        sa.Column("state", sa_enum(FirmwareState), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_by", _uuid(), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["firmware_id"], ["firmware_builds.id"]),
        sa.ForeignKeyConstraint(["started_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_firmware_rollouts_firmware_id",
        "firmware_rollouts",
        ["firmware_id"],
        unique=False,
    )

    op.create_table(
        "device_attestations",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("device_id", _uuid(), nullable=False),
        sa.Column("firmware_id", _uuid(), nullable=True),
        sa.Column("measured_digest", sa.String(length=128), nullable=True),
        sa.Column("verdict", sa_enum(StatusToken), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.ForeignKeyConstraint(["firmware_id"], ["firmware_builds.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_device_attestations_device_id",
        "device_attestations",
        ["device_id"],
        unique=False,
    )

    op.create_table(
        "provision_requests",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("device_serial", sa.String(length=64), nullable=False),
        sa.Column("requested_by", _uuid(), nullable=True),
        sa.Column("approved_by", _uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("provision_requests")
    op.drop_index("ix_device_attestations_device_id", table_name="device_attestations")
    op.drop_table("device_attestations")
    op.drop_index("ix_firmware_rollouts_firmware_id", table_name="firmware_rollouts")
    op.drop_table("firmware_rollouts")
    op.drop_index("ix_devices_serial", table_name="devices")
    op.drop_table("devices")
    op.drop_index("ix_firmware_builds_version", table_name="firmware_builds")
    op.drop_table("firmware_builds")
