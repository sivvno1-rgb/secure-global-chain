"""Append-only, hash-chained audit ledger (SECURITY.md §5)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from sgc.audit import (
    GENESIS_HASH,
    AuditPayload,
    append_audit_event,
    canonical_json,
    compute_hash,
    verify_chain,
)
from sgc.models.audit import AuditEvent


async def _append(session, **kw) -> AuditEvent:
    event = await append_audit_event(session, AuditPayload(**kw))
    await session.commit()
    return event


@pytest.mark.asyncio
async def test_first_event_links_to_genesis(db_session):
    event = await _append(
        db_session, action="release", object_type="batch", object_id="TRM-2291"
    )
    assert event.prev_hash == GENESIS_HASH
    assert len(event.hash) == 64


@pytest.mark.asyncio
async def test_hash_matches_documented_formula(db_session):
    event = await _append(
        db_session,
        action="sign",
        object_type="firmware",
        object_id="v4.2.1",
        after={"digest": "sha256:9f3a"},
    )
    expected = compute_hash(
        event.prev_hash,
        canonical_json(
            ts=event.ts,
            actor_id=event.actor_id,
            action=event.action,
            object_type=event.object_type,
            object_id=event.object_id,
            before=event.before,
            after=event.after,
        ),
    )
    assert event.hash == expected


@pytest.mark.asyncio
async def test_each_event_chains_to_previous(db_session):
    e1 = await _append(db_session, action="raise", object_type="deviation", object_id="DEV-1182")
    e2 = await _append(db_session, action="escalate", object_type="deviation", object_id="DEV-1182")
    e3 = await _append(db_session, action="release", object_type="batch", object_id="TRM-2291")
    assert e2.prev_hash == e1.hash
    assert e3.prev_hash == e2.hash
    assert e1.seq < e2.seq < e3.seq


@pytest.mark.asyncio
async def test_verify_chain_passes_for_intact_ledger(db_session):
    for i in range(5):
        await _append(db_session, action="provision", object_type="device", object_id=f"DEV-{i}")
    assert await verify_chain(db_session) is True


@pytest.mark.asyncio
async def test_tampering_breaks_verification(db_session):
    await _append(db_session, action="release", object_type="batch", object_id="TRM-2291")
    await _append(db_session, action="quarantine", object_type="batch", object_id="TRM-2292")
    assert await verify_chain(db_session) is True

    # Simulate an attacker editing a stored row (bypassing the app API).
    target = (
        await db_session.execute(select(AuditEvent).order_by(AuditEvent.seq.asc()))
    ).scalars().first()
    target.after = {"tampered": True}
    await db_session.commit()

    assert await verify_chain(db_session) is False


def test_canonical_json_is_stable_and_sorted():
    from datetime import datetime, timezone

    a = canonical_json(
        ts=datetime(2026, 6, 15, tzinfo=timezone.utc),
        actor_id=None,
        action="x",
        object_type="batch",
        object_id="TRM-1",
        before=None,
        after={"b": 2, "a": 1},
    )
    # Top-level keys are sorted: "action" before "object_type".
    assert a.index('"action"') < a.index('"object_type"')
    # Nested keys are sorted and there is no insignificant whitespace.
    assert '"a":1,"b":2' in a
    assert ", " not in a
    # Deterministic: same inputs → identical output.
    assert a == canonical_json(
        ts=datetime(2026, 6, 15, tzinfo=timezone.utc),
        actor_id=None,
        action="x",
        object_type="batch",
        object_id="TRM-1",
        before=None,
        after={"a": 1, "b": 2},
    )
