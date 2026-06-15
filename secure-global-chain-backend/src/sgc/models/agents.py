"""Agent mesh run log (DOMAIN_MODEL.md §Identity & Audit kernel).

Every LangGraph/Ollama run is logged here. Agents **propose** only — the
``proposed_action`` is data, never executed by the agent; a human accepts via the
relevant center's human-gated route, recorded as ``human_disposition`` + audit.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, JSONType, UUIDType
from ._mixins import TimestampMixin
from .enums import AgentRunStatus, sa_enum


class AgentRun(Base, TimestampMixin):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=uuid.uuid4
    )
    agent: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    graph_node: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    output_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[AgentRunStatus] = mapped_column(
        sa_enum(AgentRunStatus), nullable=False, default=AgentRunStatus.running
    )
    # The proposal (read-only output). Never an executed action.
    proposed_action: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    # "accepted" | "rejected" once a human decides.
    human_disposition: Mapped[str | None] = mapped_column(String(32), nullable=True)
