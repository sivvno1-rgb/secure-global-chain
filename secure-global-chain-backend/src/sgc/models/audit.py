"""``audit_events`` — append-only, hash-chained ledger.

Every consequential/mutating action writes one row, in the same transaction as
the change (SECURITY.md §5). Rows are never UPDATEd or DELETEd:

    hash = sha256(prev_hash + canonical_json(event_content))

``seq`` is a monotonically increasing ordering key. The domain model lists the
content columns; ``seq`` is added as the deterministic chain order (UUID PKs and
wall-clock ``ts`` are not reliable orderings under concurrency).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, JSONType, UUIDType

# Seed prev_hash for the first event in the chain (genesis).
GENESIS_HASH = "0" * 64


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=uuid.uuid4
    )
    # Deterministic chain ordering; assigned by the append helper in the same
    # transaction as the hash link. The unique constraint guards concurrency.
    seq: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # The human (or constrained service) actor. Consequential actions require a
    # human actor; that policy is enforced at the route layer.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    object_type: Mapped[str] = mapped_column(String(128), nullable=False)
    # Business key of the affected record (e.g. "TRM-2291"), or None.
    object_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    before: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
