"""Manufacturing ORM models persist with the exact field names/enum values."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from sgc.models.enums import BatchStatus, MaterialKind, Sourcing, StatusToken, TaskKind
from sgc.models.manufacturing import (
    Batch,
    BatchStep,
    Equipment,
    IpcCheck,
    Line,
    Material,
    Product,
    Site,
    Supplier,
    Task,
)


@pytest.mark.asyncio
async def test_insert_full_manufacturing_graph(db_session):
    site = Site(name="Schaffhausen", cleanroom="CR4", gmp_status="GMP")
    product = Product(code="TRM", name="Guselkumab", modality="mAb")
    db_session.add_all([site, product])
    await db_session.flush()

    line = Line(site_id=site.id, name="Line B", stage="Filling", uptime_pct=98.7,
                status=StatusToken.pass_)
    supplier = Supplier(name="DS supplier", material="Guselkumab DS",
                        sourcing=Sourcing.dual, site_country="CH",
                        lead_time_days=30, status=StatusToken.pass_)
    db_session.add_all([line, supplier])
    await db_session.flush()

    material = Material(name="Guselkumab DS", kind=MaterialKind.ds, supplier_id=supplier.id)
    batch = Batch(code="TRM-2291", product_id=product.id, line_id=line.id,
                  stage="Filling", status=BatchStatus.inspection, yield_pct=98.7,
                  started_at=datetime.now(timezone.utc))
    equip = Equipment(name="Balance 12", kind="balance",
                      calibration_status=StatusToken.pass_)
    db_session.add_all([material, batch, equip])
    await db_session.flush()

    step = BatchStep(batch_id=batch.id, name="Compounding", sequence=1)
    ipc = IpcCheck(batch_id=batch.id, kind="weight", value=10.1, spec_low=9.5,
                   spec_high=10.5, result=StatusToken.pass_, at=datetime.now(timezone.utc))
    task = Task(title="Line clearance", kind=TaskKind.clearance,
                status=StatusToken.warn, batch_id=batch.id)
    db_session.add_all([step, ipc, task])
    await db_session.commit()

    loaded = (
        await db_session.execute(
            select(Batch)
            .where(Batch.code == "TRM-2291")
            .options(selectinload(Batch.steps), selectinload(Batch.ipc_checks),
                     selectinload(Batch.line), selectinload(Batch.product))
        )
    ).scalar_one()
    assert loaded.status is BatchStatus.inspection
    assert loaded.line.name == "Line B"
    assert loaded.product.code == "TRM"
    assert [s.name for s in loaded.steps] == ["Compounding"]
    assert loaded.ipc_checks[0].result is StatusToken.pass_


@pytest.mark.asyncio
async def test_enum_values_persist_as_handoff_strings(db_session):
    """The stored value strings must match DOMAIN_MODEL.md exactly."""
    batch = Batch(code="TRM-9001", status=BatchStatus.in_process)
    db_session.add(batch)
    await db_session.commit()

    # Read the raw stored string, not the Python enum.
    raw = await db_session.execute(
        select(Batch.__table__.c.status).where(Batch.__table__.c.code == "TRM-9001")
    )
    assert raw.scalar_one() == "In process"
    assert BatchStatus.released.value == "Released"
    assert TaskKind.sign_off.value == "Sign-off"
    assert MaterialKind.ds.value == "DS"
    assert StatusToken.pass_.value == "pass"
