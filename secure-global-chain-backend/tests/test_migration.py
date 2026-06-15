"""The Alembic kernel migration is well-formed and renders valid Postgres DDL.

We don't have a live Postgres here, so we render the migration **offline**
(``alembic upgrade head --sql``) against the postgresql dialect and assert the
expected DDL is emitted — including the append-only trigger.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    BACKEND_ROOT / "alembic" / "versions" / "0001_identity_audit_kernel.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("kernel_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_metadata_is_well_formed():
    m = _load_migration()
    assert m.revision == "0001_identity_audit_kernel"
    assert m.down_revision is None
    assert callable(m.upgrade)
    assert callable(m.downgrade)


def test_offline_sql_renders_expected_postgres_ddl():
    env = dict(os.environ)
    # Offline mode does not connect; the URL only selects the dialect.
    env["SGC_DATABASE_URL"] = "postgresql+asyncpg://u:p@localhost:5432/sgc"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=str(BACKEND_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    sql = result.stdout.lower()
    # Kernel (0001)
    assert "create table users" in sql
    assert "create table audit_events" in sql
    assert "jsonb" in sql
    assert "uuid" in sql
    assert "audit_events_no_update_delete" in sql
    assert "before update or delete on audit_events" in sql
    # Manufacturing (0002)
    for table in ("suppliers", "materials", "sites", "lines", "products",
                  "batches", "batch_steps", "ipc_checks", "tasks", "equipment"):
        assert f"create table {table}" in sql, f"missing CREATE TABLE {table}"
    # Quality (0003)
    for table in ("deviations", "capas", "compliance_items", "audits",
                  "audit_findings"):
        assert f"create table {table}" in sql, f"missing CREATE TABLE {table}"
    # Devices (0004)
    for table in ("firmware_builds", "devices", "firmware_rollouts",
                  "device_attestations", "provision_requests"):
        assert f"create table {table}" in sql, f"missing CREATE TABLE {table}"
    # Telemetry (0005)
    for table in ("sensor_streams", "readings", "coldchain_lanes", "shipments",
                  "excursions"):
        assert f"create table {table}" in sql, f"missing CREATE TABLE {table}"
    # Enum values are enforced via CHECK constraints (native_enum=False).
    assert "in process" in sql  # BatchStatus value string in a CHECK
    assert "released_by" in sql
