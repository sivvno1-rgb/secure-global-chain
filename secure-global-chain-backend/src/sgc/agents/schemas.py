"""Pydantic v2 schemas for the Agent mesh context."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ..models.enums import AgentRunStatus


class AgentStatus(BaseModel):
    name: str
    job: str
    model: str
    last_run_at: datetime | None
    last_status: AgentRunStatus | None


class AgentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent: str
    graph_node: str | None
    input_ref: str | None
    output_ref: str | None
    model: str | None
    started_at: datetime | None
    ended_at: datetime | None
    status: AgentRunStatus
    proposed_action: dict | None
    human_disposition: str | None


class InvokeRequest(BaseModel):
    input_ref: str | None = None
    params: dict = {}


class DispositionRequest(BaseModel):
    disposition: str  # "accepted" | "rejected"
    note: str | None = None
