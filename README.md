# Handoff: Secure Global Chain — Backend Implementation

This package hands the **Secure Global Chain** design system to a developer working in
**Claude Code**, so the backend can be built to serve the existing frontend.

---

## What Secure Global Chain is

A systems-based intelligence platform for **pharmaceutical & advanced manufacturing**. It
harmonizes science, operations, manufacturing, quality, security, compliance, and executive
decision-making into one surface. Users never see the engines — they see **centers**:
Mission, Intelligence (knowledge graph), Research (evidence & validation), Economy,
Operations, Decisions, Reviews, Optimization, Agents, Escalate, Quality, Device Fleet,
Systems Map, Executive.

> **Operating principle: AI assists. Humans decide.** The system summarizes, retrieves, and
> navigates the graph; the conclusions — scientific, regulatory, clinical — stay with people.
> This is a hard constraint on the backend: agents **propose**, they never auto-approve a
> release, sign a record, or close a deviation. Every consequential action requires a
> human actor and is written to the audit trail.

---

## About the files in this bundle

The HTML/JSX in the design system (`ui_kits/`, `components/`, `slides/`, `guidelines/`) are
**design references created in HTML** — prototypes showing intended look and behavior, with
**realistic but hard-coded sample data**. They are **not** the production frontend and they
are **not** the backend. Your task is to **build the backend that produces the data these
screens currently fake**, in the stack below, and expose it over a clean API the real
frontend will consume.

The sample data in the JSX (batch `TRM-2291`, supplier "Guselkumab DS", `DEV-1182`,
firmware `v4.2.1`, `sha256:…`) is the **shape and vocabulary** your API should return — treat
it as the contract for field names, enums, and formats, not as seed data to ship.

**Fidelity: high.** Colors, type, spacing, copy, and status vocabulary are final. Do not
restyle. The backend must serve data that slots into these layouts unchanged.

---

## Target stack (as specified)

| Layer | Tech |
|---|---|
| API | **FastAPI** + **Pydantic v2** (schemas/validation) |
| Relational store | **PostgreSQL** via **SQLAlchemy 2.0** (async), migrations with **Alembic** |
| Graph store | **Neo4j** — knowledge graph, chain of custody, end-to-end traceability |
| Cache / broker / pub-sub | **Redis** (cache, rate limits, WebSocket fan-out, Celery broker) |
| Async work | **Celery** (ingestion, evidence runs, optimization, audit-pack generation) |
| Scientific compute | **pandas, numpy, scipy, PyMC**, JASP-style frequentist/Bayesian evidence |
| Optimization | OR-Tools (scheduling / scenario lab) — runs as Celery tasks |
| Agents | **LangGraph** (or a custom Python agent mesh) over **Ollama** local LLMs |
| Identity | **Keycloak** (OIDC) → **JWT** bearer tokens, RBAC via realm roles |
| Secrets | **HashiCorp Vault** (DB creds, signing keys, device PKI, Ollama/API keys) |
| Audit | Append-only **audit log** (hash-chained), every consequential action |
| Packaging | **Docker** / docker-compose for the whole mesh |

---

## How to use this with Claude Code

1. **Create the backend repo** and drop this whole folder into it (e.g. `docs/design_handoff/`).
   Also place `CLAUDE.md` at the **repo root** — it gives Claude Code persistent context.
2. Make the design system reachable so Claude Code can read the screens it's building for —
   either copy the `ui_kits/` folder in alongside, or keep both projects open.
3. Open Claude Code in the repo and start with scaffolding, e.g.:
   > *"Read `docs/design_handoff/`. Scaffold a FastAPI + async SQLAlchemy + Alembic project
   > with docker-compose for Postgres, Neo4j, Redis, Keycloak, Vault, and Ollama. Implement
   > the domain model in `DOMAIN_MODEL.md` as SQLAlchemy models + the first Alembic migration."*
4. Then build **center by center** (they map to bounded contexts — see `ARCHITECTURE.md`).
   Suggested order: Identity/Audit → Manufacturing core (Batches/Lines/Deviations) →
   Device Fleet → Intelligence graph → Research/Evidence → Optimization → Agents →
   Reviews/Decisions → Executive read-models.
5. Keep the **AI-assists-humans-decide** rule in front of every agent/automation task.

---

## Read these in order

| Doc | What it covers |
|---|---|
| `ARCHITECTURE.md` | Service topology, bounded contexts, how each center maps to the stack, real-time strategy |
| `DOMAIN_MODEL.md` | Postgres entities (SQLAlchemy), Neo4j graph schema, key enums & ID formats |
| `API_SURFACE.md` | REST/WebSocket endpoints grouped by center, derived from the screens |
| `AGENTS_AND_COMPUTE.md` | LangGraph agent mesh, Ollama, Celery jobs, scientific/evidence compute |
| `SECURITY.md` | Keycloak/OIDC, JWT, RBAC roles, Vault, device PKI & signed firmware, audit trail |
| `CLAUDE.md` | Drop at repo root — persistent build context & guardrails for Claude Code |

---

## Domain vocabulary (use these terms literally everywhere)

- **Verbs:** harmonize, trace, validate, attest, quarantine, escalate, sign, gate, provision.
- **Quality status:** Compliant · Review · Quarantine · Verified · Escalated · Watch.
- **Severity:** Critical / Major / Minor (deviations) · Critical / High / Watch (risk).
- **Batch lifecycle:** In process → Hold → Inspection → Released (or Quarantine / Rejected).
- **IDs (preserve formats):** batch `TRM-2291`, deviation `DEV-1182`, CAPA `CAPA-0441`,
  firmware `v4.2.1`, digests `sha256:9f3a…c0b1`, device serials, lanes `SG→EU`.
- Numbers are **specific and tabular** (`98.7%`, `1,284 / 1,310`); deltas carry direction.

This vocabulary is the source of truth for your enums, status fields, and API responses.
