"""Agent mesh seam (AGENTS_AND_COMPUTE.md §2).

The mesh is **advisory**. Each agent is read-only and its only output is a
*proposal* (``proposed_action``) — it cannot release a batch, sign firmware,
close a deviation, or decide. A human accepts a proposal via the relevant
center's human-gated route.

In production this is a LangGraph state graph over local Ollama models (no data
leaves the network). Here :class:`StubAgentMesh` produces deterministic proposals
synchronously so the flow is testable. Swap via the ``get_agent_mesh`` dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AgentDef:
    name: str
    job: str
    model: str


# The mesh catalogue (maps to centers). Models are local Ollama endpoints.
AGENTS: dict[str, AgentDef] = {
    "tracer": AgentDef(
        "tracer", "Walk the chain of custody; assemble traceability / blast-radius summaries",
        "ollama:llama3.1:8b"),
    "quality_analyst": AgentDef(
        "quality_analyst", "Triage deviations, draft CAPA suggestions, flag effectiveness risk",
        "ollama:llama3.1:8b"),
    "evidence_librarian": AgentDef(
        "evidence_librarian", "Retrieve datasets/packets, summarize stats; never assert conclusions",
        "ollama:llama3.1:8b"),
    "scheduler_advisor": AgentDef(
        "scheduler_advisor", "Read OR-Tools output, explain trade-offs, suggest scenario params",
        "ollama:llama3.1:8b"),
    "fleet_sentinel": AgentDef(
        "fleet_sentinel", "Watch device attestation/telemetry, propose quarantine on anomaly",
        "ollama:llama3.1:8b"),
    "review_scribe": AgentDef(
        "review_scribe", "Assemble cadenced review packets (decisions, risks, metrics)",
        "ollama:llama3.1:8b"),
}


@dataclass(frozen=True)
class AgentProposal:
    graph_node: str
    model: str
    output_ref: str
    proposed_action: dict


class AgentMesh(Protocol):
    def run(self, agent: AgentDef, *, input_ref: str | None, params: dict) -> AgentProposal: ...


class StubAgentMesh:
    """Deterministic, read-only proposal generator for dev/tests.

    Returns a *proposal* only. There is intentionally no code path from here to
    any domain mutation — the hard rule (agents propose, humans decide) is
    structural, not just policy.
    """

    def run(self, agent: AgentDef, *, input_ref: str | None, params: dict) -> AgentProposal:
        proposed_action = {
            "kind": f"{agent.name}_proposal",
            "summary": f"{agent.job} (proposal for {input_ref or 'context'})",
            "target": input_ref,
            "params": params,
            # Cites the records the proposal is grounded in (structured, not free text).
            "cites": params.get("cites", []),
            "requires_human": True,
        }
        output_ref = f"memory://agent/{agent.name}/{input_ref or 'context'}"
        return AgentProposal(
            graph_node="propose",
            model=agent.model,
            output_ref=output_ref,
            proposed_action=proposed_action,
        )


def get_agent_mesh() -> AgentMesh:
    return StubAgentMesh()
