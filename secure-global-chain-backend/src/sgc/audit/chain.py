"""Hash-chain construction and verification for ``audit_events``.

The chain is tamper-evident: each event's ``hash`` commits to the previous
event's ``hash`` plus a canonical serialization of the event content. Re-hashing
the table in order must reproduce every stored ``hash``; any edit breaks the link.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit import GENESIS_HASH, AuditEvent


@dataclass(frozen=True)
class AuditPayload:
    """The content of one audit event, before it is chained and persisted."""

    action: str
    object_type: str
    object_id: str | None = None
    actor_id: uuid.UUID | None = None
    before: dict | None = None
    after: dict | None = None


def _serialize_ts(ts: datetime) -> str:
    """Deterministic UTC ISO-8601 with explicit offset (microsecond precision)."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).isoformat()


def canonical_json(
    *,
    ts: datetime,
    actor_id: uuid.UUID | None,
    action: str,
    object_type: str,
    object_id: str | None,
    before: dict | None,
    after: dict | None,
) -> str:
    """Canonical JSON of the event content used as the hash preimage.

    Stable across runs: sorted keys, no insignificant whitespace, UTC timestamp,
    UUIDs as strings. ``prev_hash`` is *not* included here — it is prepended
    separately in :func:`compute_hash` (``sha256(prev_hash + canonical_json)``).
    """
    content = {
        "ts": _serialize_ts(ts),
        "actor_id": str(actor_id) if actor_id is not None else None,
        "action": action,
        "object_type": object_type,
        "object_id": object_id,
        "before": before,
        "after": after,
    }
    return json.dumps(
        content, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def compute_hash(prev_hash: str, payload_canonical: str) -> str:
    """``sha256(prev_hash + canonical_json(event))`` as lowercase hex."""
    return hashlib.sha256(
        (prev_hash + payload_canonical).encode("utf-8")
    ).hexdigest()


async def _latest_link(session: AsyncSession) -> tuple[int, str]:
    """``(seq, hash)`` of the most recent event, or the genesis seed if empty."""
    result = await session.execute(
        select(AuditEvent.seq, AuditEvent.hash)
        .order_by(AuditEvent.seq.desc())
        .limit(1)
    )
    last = result.first()
    if last is None:
        return 0, GENESIS_HASH
    return last.seq, last.hash


async def append_audit_event(
    session: AsyncSession, payload: AuditPayload
) -> AuditEvent:
    """Append one event to the chain.

    Must run inside the same transaction as the change it records. The caller
    commits. Returns the persisted :class:`AuditEvent` (with ``hash`` set).
    """
    prev_seq, prev_hash = await _latest_link(session)
    ts = datetime.now(timezone.utc)
    payload_canonical = canonical_json(
        ts=ts,
        actor_id=payload.actor_id,
        action=payload.action,
        object_type=payload.object_type,
        object_id=payload.object_id,
        before=payload.before,
        after=payload.after,
    )
    event = AuditEvent(
        seq=prev_seq + 1,
        ts=ts,
        actor_id=payload.actor_id,
        action=payload.action,
        object_type=payload.object_type,
        object_id=payload.object_id,
        before=payload.before,
        after=payload.after,
        prev_hash=prev_hash,
        hash=compute_hash(prev_hash, payload_canonical),
    )
    session.add(event)
    # Assign seq/ts defaults without ending the caller's transaction.
    await session.flush()
    return event


async def verify_chain(session: AsyncSession) -> bool:
    """Recompute the whole chain in order; return True iff every link holds."""
    result = await session.execute(
        select(AuditEvent).order_by(AuditEvent.seq.asc())
    )
    prev_hash = GENESIS_HASH
    for event in result.scalars():
        if event.prev_hash != prev_hash:
            return False
        expected = compute_hash(
            prev_hash,
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
        if event.hash != expected:
            return False
        prev_hash = event.hash
    return True
