# CLAUDE.md — Secure Global Chain backend

> Place this file at the **root of the backend repo**. Claude Code reads it on every session.
> Full specs live in `docs/design_handoff/` (this handoff package). Read them before building.

## What this project is

The backend for **Secure Global Chain** — a pharma & advanced-manufacturing intelligence
platform. A polished frontend already exists (HTML/JSX design system in `ui_kits/`). Your job
is to build the services that produce the data those screens currently fake, and expose it
over a clean API.

## The one rule that overrides everything

**AI assists. Humans decide.** Agents and jobs may *summarize, retrieve, compute, and
propose*. They must **never** finalize a consequential action — releasing a batch, signing
firmware or a validation report, closing a deviation, or making a decision. Those require a
human actor with the right role and are written to the audit trail. If a task seems to ask an
agent to auto-approve something, stop and flag it.

## Stack (do not substitute without asking)

FastAPI · Pydantic v2 · PostgreSQL + SQLAlchemy 2.0 (async) + Alembic · Neo4j (knowledge
graph / chain of custody) · Redis (cache, broker, WS fan-out) · Celery · pandas/numpy/scipy/PyMC
+ OR-Tools (scientific & optimization compute) · LangGraph + Ollama (advisory agent mesh) ·
Keycloak (OIDC) + JWT · Vault (secrets + device/firmware PKI) · append-only hash-chained audit ·
Docker / docker-compose for everything.

## Architecture in one breath

- **Postgres = system of record.** **Neo4j = relationships/traversal** (trace, blast-radius).
  Keep a shared business ID on both; sync via an outbox → Celery → Neo4j upsert.
- One **bounded context per center**: identity, audit, manufacturing, quality, devices,
  telemetry, intelligence, research, optimization, economy, decisions, reviews, agents,
  incident, executive (read-models). See `docs/design_handoff/ARCHITECTURE.md`.
- Dashboards/Executive are **read-models** refreshed by Celery beat — don't fan out live
  queries across a dozen tables.
- Real-time via **WebSocket + Redis pub/sub**; honor `?range=daily|weekly|monthly|yearly`.

## Conventions

- Field names, enum strings, and ID formats come from `docs/design_handoff/DOMAIN_MODEL.md`
  and match the frontend exactly (`TRM-2291`, `DEV-1182`, `v4.2.1`, `sha256:…`, status tokens
  `pass|warn|fail|info|neutral`). Don't rename them.
- Consequential actions are explicit sub-resources (`POST …/release`, `…/sign`, `…/quarantine`,
  `…/decide`), human-gated by role, audited, idempotent (`Idempotency-Key`).
- Every mutation writes an `audit_events` row in the same transaction (hash-chained).
- Secrets only from Vault (AppRole); validate JWTs against Keycloak JWKS. Nothing secret in env.
- Errors as RFC-9457 problem+json. Tests for every endpoint + every human-gating rule.

## Build order (suggested)

1. docker-compose: postgres, neo4j, redis, keycloak, vault, ollama, api, worker, beat.
2. Identity + audit kernel (JWT validation, RBAC dependency, hash-chained audit).
3. Manufacturing core: lines, batches, steps, IPC, tasks (+ release/sign, audited).
4. Quality: deviations, CAPA, audits, audit packs.
5. Device fleet: devices, firmware sign/rollout, attestations (Vault PKI).
6. Telemetry + cold chain ingestion (signed) → Redis → WS.
7. Intelligence: Postgres→Neo4j sync; trace / impact / graph endpoints.
8. Research/evidence (enclave Celery worker); optimization (OR-Tools).
9. Agents (LangGraph/Ollama) — proposals only.
10. Decisions, reviews, economy, incident; executive read-models.

## Docs index (`docs/design_handoff/`)

`README.md` · `ARCHITECTURE.md` · `DOMAIN_MODEL.md` · `API_SURFACE.md` ·
`AGENTS_AND_COMPUTE.md` · `SECURITY.md`
