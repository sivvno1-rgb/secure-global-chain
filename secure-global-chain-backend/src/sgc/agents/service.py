"""Agent mesh service layer.

Invoke runs an agent and records a *proposal* (status ``awaiting_human``). It
performs no consequential action. The human disposition (accept/reject) is the
only audited event here; accepting does **not** execute anything — the human
still acts via the relevant center's human-gated route.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import AuditPayload, append_audit_event
from ..errors import ConflictError, NotFoundError
from ..models.agents import AgentRun
from ..models.audit import AuditEvent
from ..models.enums import AgentRunStatus
from ..models.user import User
from .mesh import AGENTS, AgentMesh

_VALID_DISPOSITIONS = {"accepted", "rejected"}


async def list_agents(session: AsyncSession) -> list[dict]:
    """Mesh status: each catalogued agent + its last run."""
    out = []
    for name, definition in AGENTS.items():
        last = (
            await session.execute(
                select(AgentRun)
                .where(AgentRun.agent == name)
                .order_by(AgentRun.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        out.append({
            "name": name,
            "job": definition.job,
            "model": definition.model,
            "last_run_at": last.started_at if last else None,
            "last_status": last.status if last else None,
        })
    return out


async def list_runs(
    session: AsyncSession, *, agent: str | None = None
) -> list[AgentRun]:
    filters = []
    if agent is not None:
        filters.append(AgentRun.agent == agent)
    result = await session.execute(
        select(AgentRun).where(*filters).order_by(AgentRun.started_at.desc())
    )
    return list(result.scalars())


async def invoke_agent(
    session: AsyncSession,
    *,
    agent: str,
    mesh: AgentMesh,
    input_ref: str | None,
    params: dict,
) -> AgentRun:
    """Kick an agent run; record the proposal awaiting human disposition."""
    definition = AGENTS.get(agent)
    if definition is None:
        raise NotFoundError(f"Unknown agent {agent}")

    run = AgentRun(
        agent=agent,
        input_ref=input_ref,
        status=AgentRunStatus.running,
        started_at=datetime.now(timezone.utc),
    )
    session.add(run)
    await session.flush()

    try:
        proposal = mesh.run(definition, input_ref=input_ref, params=params)
    except Exception as exc:
        run.status = AgentRunStatus.failed
        run.ended_at = datetime.now(timezone.utc)
        run.output_ref = f"error: {exc}"
        return run

    run.graph_node = proposal.graph_node
    run.model = proposal.model
    run.output_ref = proposal.output_ref
    run.proposed_action = proposal.proposed_action
    # The run waits for a human — it never self-finalizes.
    run.status = AgentRunStatus.awaiting_human
    run.ended_at = datetime.now(timezone.utc)
    return run


async def disposition_run(
    session: AsyncSession,
    run_id: uuid.UUID,
    actor: User,
    *,
    disposition: str,
    note: str | None = None,
) -> tuple[AgentRun, AuditEvent]:
    """Human accepts/rejects a proposal (audited). Records the decision only —
    it does not perform the proposed consequential action."""
    if disposition not in _VALID_DISPOSITIONS:
        raise ConflictError("disposition must be 'accepted' or 'rejected'")

    run = await session.get(AgentRun, run_id)
    if run is None:
        raise NotFoundError(f"Agent run {run_id} not found")
    if run.human_disposition is not None:
        raise ConflictError("Agent run already dispositioned")
    if run.status != AgentRunStatus.awaiting_human:
        raise ConflictError(f"Agent run is {run.status.value}; not awaiting a human")

    run.human_disposition = disposition
    run.status = (
        AgentRunStatus.accepted if disposition == "accepted" else AgentRunStatus.rejected
    )

    event = await append_audit_event(
        session,
        AuditPayload(
            actor_id=actor.id,
            action="disposition",
            object_type="agent_run",
            object_id=str(run.id),
            after={
                "agent": run.agent,
                "disposition": disposition,
                "note": note,
                # Recorded for the trail: acceptance is not execution.
                "executed": False,
            },
        ),
    )
    return run, event
