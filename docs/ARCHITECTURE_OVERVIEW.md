# Architecture Overview — Secure Global Chain

This document describes the system through three complementary lenses:

1. **[MBSE](#1-mbse--model-based-systems-engineering)** — Model-Based Systems
   Engineering: the canonical domain model, bounded contexts, and data topology.
2. **[Operations Research](#2-operations-research)** — the optimization and
   scientific-evidence compute engines.
3. **[Decision Architecture](#3-decision-architecture)** — how authority,
   proposals, human gating, and the audit trail fit together.

It complements the original [`design_handoff/ARCHITECTURE.md`](design_handoff/ARCHITECTURE.md)
(service topology) and [`DOMAIN_MODEL.md`](design_handoff/DOMAIN_MODEL.md)
(entities/fields). Where this doc and the handoff differ, the handoff is the
spec; this is the as-built map.

---

## 1. MBSE — Model-Based Systems Engineering

The platform is built model-first: one explicit, versioned domain model is the
single source of truth, and every surface (screens, APIs, read-models, graph) is
a *projection* of it. Field names, enum strings, and ID formats (`TRM-2291`,
`DEV-1182`, `v4.2.1`, `sha256:…`, status tokens `pass|warn|fail|info|neutral`)
are fixed in [`DOMAIN_MODEL.md`](design_handoff/DOMAIN_MODEL.md) and matched
exactly by code and frontend — no renaming across layers.

### 1.1 Bounded contexts (one per "center")

Each context is a Python package (`src/sgc/<context>/`) with its own SQLAlchemy
models, service layer, schemas, and router, sharing the identity + audit kernel.

| Context | Centers served | Primary store | Status |
|---|---|---|---|
| **security** (identity) | login, RBAC, who-did-what | Keycloak + Postgres mirror | ✅ |
| **audit** | every consequential action | Postgres (hash-chained) | ✅ |
| **manufacturing** | Mission, Operations | Postgres | ✅ |
| **quality** | Deviations, CAPA, Audits, Compliance | Postgres | ✅ |
| **devices** | NeuroSecure fleet, firmware authority | Postgres + Vault PKI | ✅ |
| **telemetry** | cold-chain, cleanroom/biosignal streams | Postgres + Redis | ✅ |
| **intelligence** | Systems Map, chain of custody | Neo4j (+ Postgres refs) | ✅ |
| **research** | evidence packets, hypotheses, validation | Postgres + SciPy/PyMC | ✅ |
| **optimization** | scheduling, Scenario Lab | Postgres + OR-Tools | ✅ |
| **agents** | advisory agent mesh | LangGraph + Ollama (+ run log) | ✅ |
| **executive** | Overview / Risk / Portfolio | read-models over the above | ✅ |
| **views** | per-screen backend-for-frontend | composes all of the above | ✅ |
| **decisions** | Decision Center | Postgres | 🔲 specced |
| **reviews** | Executive Review Center | Postgres | 🔲 specced |
| **economy** | Economic Policy / Finance layer | Postgres + feeds | 🔲 specced |
| **incident** | Escalate / Incident Response | Postgres + notifications | 🔲 specced |

🔲 = modeled in the handoff; the `views` layer scaffolds their routes returning
`{}` until the domain model lands.

### 1.2 System decomposition (logical view)

```
┌──────────────────────────── Presentation ────────────────────────────┐
│  Operator frontend (ui_kits)  ·  served at GET /  ·  /static/* assets  │
└───────────────────────────────────┬───────────────────────────────────┘
                                     │ view-models (read) + actions (write)
┌──────────────────────────── views BFF (read-only) ───────────────────┐
│  GET /api/v1/views/<key>  — 27 role-gated per-screen projections       │
│  composes context services; NO domain logic; NO audit events          │
└───────────────────────────────────┬───────────────────────────────────┘
┌─────────────────────────── Bounded contexts ─────────────────────────┐
│ manufacturing · quality · devices · telemetry · intelligence ·        │
│ research · optimization · agents · executive                          │
│   each: router → service → SQLAlchemy models                          │
└───────────────┬───────────────────────────────────┬───────────────────┘
┌──────── Kernel (cross-cutting) ────────┐  ┌──── Compute (Celery) ──────┐
│ security: JWT/JWKS, Principal, RBAC     │  │ ingest · evidence ·        │
│ audit:    append-only hash chain        │  │ optimize · agents · audit  │
└─────────────────────────────────────────┘  └────────────────────────────┘
```

### 1.3 Data topology — system of record vs. graph

A deliberate **two-store** split (handoff §3):

- **PostgreSQL = system of record.** All entities, lifecycle state, e-signatures,
  audit, evidence metadata, schedules. Anything needing ACID, history, or a
  regulator's eye. Accessed via async SQLAlchemy 2.0; schema evolved with Alembic
  (migrations `0001`–`0008`).
- **Neo4j = relationship/traversal layer.** The
  `Supplier → Material → Site → Line → Batch → QC → ColdStore → Distribution → Market`
  chain is naturally a graph. Used for end-to-end traceability, chain of custody,
  and **impact/blast-radius** ("which batches did this excursion touch?").
- **Shared business ID** on every node joins the two cleanly. Writes propagate via
  an **outbox → Celery → Neo4j upsert** (the dev build projects on demand via
  `intelligence/projector.py`; `neo4j_store.py` is the production Cypher seam).

### 1.4 Read-models & the BFF projection pattern

Dashboards must not fan out live queries across a dozen tables. Two layers apply
the projection pattern:

- **Executive read-models** (`executive/readmodel.py`): KPIs, portfolio counts,
  and a derived `risk_level`, computed on demand from aggregates and (in prod)
  refreshed by Celery beat per `?range=daily|weekly|monthly|yearly`.
- **`views` BFF** (`views/`): 27 per-screen view-models that *compose* existing
  context services into the exact shape each frontend screen renders. Strictly
  read-only — see [VIEWS_API.md](VIEWS_API.md).

### 1.5 Real-time

Status dots pulse and feeds update via **WebSocket + Redis pub/sub**: ingestion,
agents, and state changes publish events; the API subscribes and pushes to
clients. Dashboards have a coarse polling fallback honoring the `?range=` selector
server-side. (WS endpoints are the documented next increment.)

### 1.6 Traceability matrix (requirement → realization)

| Systems requirement | Realized by |
|---|---|
| Tamper-evident record of every consequential act | `audit/chain.py` + Postgres `UPDATE/DELETE`-blocking trigger |
| End-to-end batch traceability & blast-radius | Neo4j graph + `intelligence/{graph,projector}.py` |
| Fast, consistent dashboards | `executive` read-models + `views` BFF |
| Reproducible scientific evidence | `research/compute.py` (seed + lib versions + dataset hash) |
| Feasible, honest production schedules | `optimization/solver.py` (OR-Tools CP-SAT + `solver_status`) |
| No autonomous consequential action | propose-only agents + `human_only` role gates |

---

## 2. Operations Research

Two OR/compute engine families sit behind Celery, time-boxed and **advisory only**
([`AGENTS_AND_COMPUTE.md`](design_handoff/AGENTS_AND_COMPUTE.md)). They produce
numbers and options; humans choose.

### 2.1 Production scheduling (OR-Tools CP-SAT)

`optimization/solver.py` (`CpSatScheduleSolver`):

- **Decision variables:** per-batch interval variables on a line.
- **Constraints:** `AddNoOverlap` (a line runs one batch at a time); setup/horizon
  bounds from `lines`/`batches`/`schedules`.
- **Objective:** `AddMaxEquality(makespan, ends)` then `Minimize(makespan)`
  (sequencing to minimize completion time; extensible to throughput/tardiness).
- **Output:** `schedule_slots` (start/end offsets) + an **honest `solver_status`**
  ∈ `optimal | feasible | infeasible | timeout`, so the UI never implies false
  certainty. Solves are time-boxed.

```
POST /optimization/schedules  → solve (state="solved", advisory)
POST /optimization/schedules/{id}/commit → HUMAN (planner), audited
```

### 2.2 Scenario Lab (comparative what-if)

`POST /optimization/scenarios` re-solves with perturbed `scenarios.params` and
persists `kpi_delta` — a structured before/after for sensitivity analysis. The
base schedule is unchanged; a planner decides whether to act.

### 2.3 Scientific evidence (frequentist + Bayesian)

`research/compute.py` (`LocalEvidenceComputer`) — the platform's JASP heritage,
both schools:

- **Frequentist** (SciPy/pandas): t-tests, CIs, p-values (`ttest_1samp` + t-CI
  implemented; ANOVA/regression are the documented extensions).
- **Bayesian** (PyMC target; conjugate normal–normal posterior + credible
  interval implemented as the synchronous stand-in): posteriors, credible
  intervals, model comparison.
- **Persisted** as `evidence_results(statistic, value, ci_low, ci_high, p_value,
  posterior_ref)`.

OR doctrine enforced here:

- **Reproducible by mandate:** pinned seeds, recorded library versions, dataset
  hash + lineage on each packet — a regulator can re-run it.
- **No conclusion in code:** the task computes statistics; the interpretation
  (`supported`/`refuted`) is a **human disposition** on the hypothesis.
- **Enclave execution (prod):** the `evidence` Celery worker is locked down — no
  outbound internet, Vault-scoped dataset access; large artifacts go to object
  storage by reference.

### 2.4 Celery compute topology

```
Broker / backend: Redis
Queues:  ingest   → telemetry / lab files / feeds (high volume)
         evidence → SciPy/PyMC runs (CPU-heavy, isolated enclave)
         optimize → OR-Tools solves (CPU-heavy, time-boxed)
         agents   → LangGraph runs over Ollama (I/O + LLM latency)
         audit    → audit-pack export & signing (sensitive)
Beat:    refresh executive read-models · re-attest fleet ·
         cold-chain excursion sweeps · Neo4j reconciliation from outbox
```

---

## 3. Decision Architecture

The platform's spine is one invariant, enforced structurally rather than by
convention:

> **AI assists. Humans decide.**

### 3.1 Authority model

| Actor | May do | May NOT do |
|---|---|---|
| **Read clients / dashboards** | read view-models, projections | mutate anything |
| **Compute jobs (OR / evidence)** | compute options, statistics | choose, finalize, conclude |
| **Agents** | retrieve, summarize, write a *proposal* | release/sign/quarantine/decide/execute |
| **Humans (by role)** | the consequential action, via a gated route | bypass audit |

### 3.2 The propose → decide → audit loop

```
invoke agent ─▶ LangGraph nodes read (Neo4j + Postgres + evidence)
            ─▶ collect proposals ─▶ agent_run.status = "awaiting_human"
            ─▶ WS /ws/agents notifies a human
            ─▶ human accepts/rejects (disposition)         ── audited
            ─▶ to ACT, the human calls the center's HUMAN-GATED route
               (/release, /sign, /quarantine, /commit, /decide) ── audited
```

Crucially, **accepting a proposal is not execution.** `agents/service.py`
records the disposition with `"executed": False`; the human must still perform the
action through the gated route. There is *no code path* from the agent mesh to a
domain mutation. Tests assert that invoking or accepting a proposal never mutates
consequential state.

### 3.3 Structural enforcement

- **Consequential actions are explicit sub-resources**, not generic updates:
  `POST …/release`, `…/sign`, `…/quarantine`, `…/commit`, `…/decide`,
  `…/escalate`.
- **Role + human gate:** `require_role(role, human_only=True)` — service tokens
  are rejected even if they carry the role ([`SECURITY.md`](design_handoff/SECURITY.md) §1).
- **Idempotent:** consequential writes accept an `Idempotency-Key`.
- **Atomically audited:** every mutation writes an `audit_events` row *in the same
  transaction*; the response returns `X-Audit-Event-Id`.
- **Tamper-evident ledger:** `hash = sha256(prev_hash + canonical_json(event))`;
  `verify_chain()` validates the whole chain; a Postgres trigger blocks
  `UPDATE`/`DELETE` on the ledger.
- **Read/decide split at the edge:** the `views` BFF is read-only and writes no
  audit events; decisions flow only through gated routes (the frontend calls them
  via `SGCLive.act()`, surfacing `X-Audit-Event-Id`).

### 3.4 Governance surfaces

- **Decision Center** (`decisions`) — where open decisions are presented and a
  human disposition is recorded.
- **Executive Review Center** (`reviews`) — cadenced governance packets (decisions,
  risks, metrics) assembled by the *Review scribe* agent for human review.

These are specced; their `views` routes are scaffolded (returning `{}`) pending
their domain models. The *enforcement* (gating, audit, propose-only) is already
live across every implemented context.

### 3.5 Failure & safety posture

- **Honest uncertainty:** solvers surface `infeasible`/`timeout`; evidence reports
  CIs and p-values, never a verdict.
- **Quarantine on doubt:** unverifiable signed telemetry quarantines the device
  (`telemetry/ingest.py`); anomalies prompt a *proposed* quarantine, not an
  automatic one.
- **Least authority:** generic `401/403` messages never leak which role is
  missing; the evidence enclave has no outbound network.

---

## Appendix — where things live

| Concern | Path |
|---|---|
| App wiring, routers, `GET /`, `/static` | `src/sgc/main.py` |
| Identity / JWT / RBAC | `src/sgc/security/` |
| Hash-chained audit | `src/sgc/audit/chain.py`, `src/sgc/models/audit.py` |
| Domain models + enums | `src/sgc/models/` |
| OR-Tools scheduling | `src/sgc/optimization/solver.py` |
| Scientific evidence | `src/sgc/research/compute.py` |
| Agent mesh (propose-only) | `src/sgc/agents/mesh.py`, `src/sgc/agents/service.py` |
| Knowledge graph | `src/sgc/intelligence/{graph,projector,neo4j_store}.py` |
| Executive read-models | `src/sgc/executive/readmodel.py` |
| Views BFF (27 endpoints) | `src/sgc/views/` |
| Migrations | `alembic/versions/0001…0008` |
