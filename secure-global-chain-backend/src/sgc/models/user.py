"""User mirror.

Keycloak is the source of truth for credentials and roles; we mirror users into
Postgres so ``created_by`` / ``signed_by`` / ``decided_by`` FKs have referential
integrity (SECURITY.md §1). ``keycloak_sub`` is the JWT ``sub`` claim.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, JSONType, UUIDType


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=uuid.uuid4
    )
    # Maps to the JWT `sub` claim; Keycloak remains the credential authority.
    keycloak_sub: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Cached copy of Keycloak realm roles for reference/joins (not authoritative).
    roles: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    # FK to sites lands with the manufacturing context; nullable surrogate for now.
    site_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
