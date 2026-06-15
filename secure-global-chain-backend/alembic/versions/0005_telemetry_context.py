"""telemetry & cold-chain context

Creates sensor_streams, readings, coldchain_lanes, shipments, excursions per
DOMAIN_MODEL.md (exact field names and enum value strings). ``readings`` is the
high-volume time-series table (a Timescale hypertable in production). Targets
PostgreSQL.

Revision ID: 0005_telemetry_context
Revises: 0004_devices_context
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from sgc.models.enums import Severity, ShipmentState, StatusToken, StreamKind, sa_enum

# revision identifiers, used by Alembic.
revision: str = "0005_telemetry_context"
down_revision: Union[str, None] = "0004_devices_context"
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
        "sensor_streams",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("device_id", _uuid(), nullable=False),
        sa.Column("kind", sa_enum(StreamKind), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("spec_low", sa.Float(), nullable=True),
        sa.Column("spec_high", sa.Float(), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sensor_streams_device_id", "sensor_streams", ["device_id"], unique=False
    )

    op.create_table(
        "readings",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("stream_id", _uuid(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["stream_id"], ["sensor_streams.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_readings_stream_ts", "readings", ["stream_id", "ts"], unique=False)

    op.create_table(
        "coldchain_lanes",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("origin", sa.String(length=64), nullable=True),
        sa.Column("destination", sa.String(length=64), nullable=True),
        sa.Column("spec_low", sa.Float(), nullable=True),
        sa.Column("spec_high", sa.Float(), nullable=True),
        sa.Column("status", sa_enum(StatusToken), nullable=False),
        *_ts_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(
        "ix_coldchain_lanes_code", "coldchain_lanes", ["code"], unique=True
    )

    op.create_table(
        "shipments",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("lane_id", _uuid(), nullable=True),
        sa.Column("batch_id", _uuid(), nullable=True),
        sa.Column("state", sa_enum(ShipmentState), nullable=False),
        sa.Column("departed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("eta", sa.DateTime(timezone=True), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["lane_id"], ["coldchain_lanes.id"]),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "excursions",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("lane_id", _uuid(), nullable=True),
        sa.Column("shipment_id", _uuid(), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("peak_value", sa.Float(), nullable=True),
        sa.Column("severity", sa_enum(Severity), nullable=False),
        sa.Column("disposition", sa.String(length=255), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(["lane_id"], ["coldchain_lanes.id"]),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("excursions")
    op.drop_table("shipments")
    op.drop_index("ix_coldchain_lanes_code", table_name="coldchain_lanes")
    op.drop_table("coldchain_lanes")
    op.drop_index("ix_readings_stream_ts", table_name="readings")
    op.drop_table("readings")
    op.drop_index("ix_sensor_streams_device_id", table_name="sensor_streams")
    op.drop_table("sensor_streams")
