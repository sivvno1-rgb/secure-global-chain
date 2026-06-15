"""Quality models persist with the exact handoff field names / enum strings."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from sgc.models.enums import Framework, QualityState, Severity, StatusToken
from sgc.models.quality import Audit, AuditFinding, Capa, ComplianceItem, Deviation


@pytest.mark.asyncio
async def test_quality_graph_inserts(db_session):
    dev = Deviation(code="DEV-1182", title="Drift", severity=Severity.major,
                    state=QualityState.review)
    db_session.add(dev)
    await db_session.flush()
    capa = Capa(code="CAPA-0441", deviation_id=dev.id, status=StatusToken.warn)
    audit = Audit(scope="CR4", framework=Framework.gxp, readiness_pct=90.0)
    db_session.add_all([capa, audit])
    await db_session.flush()
    finding = AuditFinding(audit_id=audit.id, framework=Framework.gxp,
                           severity=Severity.minor, status=StatusToken.warn)
    ci = ComplianceItem(framework=Framework.gmp, area="CR4", title="Gowning",
                        state=StatusToken.pass_)
    db_session.add_all([finding, ci])
    await db_session.commit()

    loaded = (
        await db_session.execute(select(Deviation).where(Deviation.code == "DEV-1182"))
    ).scalar_one()
    assert loaded.severity is Severity.major
    assert loaded.state is QualityState.review


@pytest.mark.asyncio
async def test_enum_value_strings(db_session):
    dev = Deviation(code="DEV-2000", title="t", severity=Severity.critical,
                    state=QualityState.escalated)
    db_session.add(dev)
    await db_session.commit()
    raw_state = await db_session.execute(
        select(Deviation.__table__.c.state).where(
            Deviation.__table__.c.code == "DEV-2000"
        )
    )
    assert raw_state.scalar_one() == "Escalated"
    assert Severity.critical.value == "Critical"
    assert QualityState.compliant.value == "Compliant"
    assert Framework.gxp.value == "GxP"
