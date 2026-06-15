# Architecture — Secure Global Chain backend

## 1. Service topology (docker-compose)

```
                         ┌──────────────────────────────┐
   Frontend (existing) ──┤  FastAPI (ASGI, uvicorn)      │
   reads ui_kits screens │  - REST + WebSocket           │
                         │  - Pydantic v2 schemas        │
                         │  - OIDC/JWT auth middleware    │
                         └───────┬───────┬───────┬───────┘
                                 │       │       │
              ┌──────────────────┘       │       └──────────────────┐
              │                          │                          │
     ┌────────▼────────┐       ┌─────────▼────────┐       ┌─────────▼────────┐
     │ PostgreSQL      │       │ Neo4j            │       │ Redis            │
     │ system of record│       │ knowledge graph  │       │ cache · broker · │
     │ (SQLAlchemy)    │       │ chain of custody │       │ ws fan-out       │
     └─────────────────┘       └──────────────────┘       └────────┬─────────┘
                                                                    │ broker
                                                          ┌─────────▼─────────┐
                                                          │ Celery workers     │
                                                          │ - ingestion        │
                                                          │ - evidence/compute │
                                                          │ - optimization     │
                                                          │ - audit packs      │
                                                          │ - agent runs       │
                                                          └───┬────────────┬───┘
                                                              │            │
                                                    ┌─────────▼──┐   ┌─────▼──────┐
                                                    │ Ollama     │   │ Scientific │
                                                    │ local LLMs │   │ pandas/    │
                                                    │ (agents)   │   │ numpy/scipy│
                                                    └────────────┘   │ /PyMC      │
                                                                     └────────────┘
   Cross-cutting:
     Keycloak (OIDC issuer)  ·  Vault (secrets/PKI/signing)  ·  Audit log (append-only)
```

Everything runs under **Docker**. One `docker-compose.yml` brings up: `api`, `worker`
(Celery), `beat` (Celery scheduler), `postgres`, `neo4j`, `redis`, `keycloak`, `vault`,
`ollama`. The frontend is served separately and points at the `api` service.

## 2. Bounded contexts (one per center)

Build these as FastAPI routers / Python packages with their own SQLAlchemy models and
service layer. They share the identity + audit kernel.

| Context | Centers it serves | Primary stores |
|---|---|---|
| **identity** | login, RBAC, who-did-what | Keycloak + Postgres (user mirror) |
| **audit** | every consequential action, audit packs | Postgres (hash-chained) + object store |
| **manufacturing** | Mission, Operations | Postgres |
| **quality** | Quality & Compliance, Deviations, CAPA, Audit | Postgres |
| **devices** | NeuroSecure Device Fleet, firmware authority | Postgres + Vault PKI |
| **telemetry** | cold-chain, biosignal/cleanroom streams | Postgres (timescale-style) + Redis |
| **intelligence** | Intelligence map, Systems Map, chain of custody | **Neo4j** (+ Postgres refs) |
| **research** | Research enclave, evidence packets, hypotheses, validation reports | Postgres + scientific compute |
| **optimization** | Optimization (scheduling), Scenario Lab | Postgres + OR-Tools (Celery) |
| **economy** | Economic Policy / Finance layer | Postgres (+ external feeds) |
| **decisions** | Decision Center | Postgres |
| **reviews** | Executive Review Center (cadenced governance) | Postgres |
| **agents** | Autonomous agent mesh | LangGraph + Ollama (+ Postgres run log) |
| **incident** | Escalate / Incident Response | Postgres + notifications |
| **executive** | Executive Overview / Risk / Portfolio | **read-models** over the above |

The Executive center and most dashboards are **read-models**: don't query 12 tables live —
maintain projection tables (or materialized views) refreshed by Celery, so the dashboard
tiles render fast and consistently.

## 3. Postgres vs Neo4j — what goes where

- **Postgres is the system of record.** All entities, lifecycle state, signatures, audit,
  evidence metadata, schedules. Anything that needs ACID, history, or a regulator's eye.
- **Neo4j is the relationship/traversal layer.** Supplier → Material → Site → Line → Batch →
  QC → Cold store → Distribution → Market is naturally a graph (see `OperatorIntelMap`). Use
  it for: end-to-end traceability, chain of custody, impact/blast-radius ("what batches did
  this excursion touch?"), and the knowledge-graph topology views.
- Keep a **stable shared ID** on every node (the Postgres primary key / business key) so the
  two stores join cleanly. Neo4j holds the edges and a thin label cache; Postgres holds the
  full record. Sync via domain events on write (outbox pattern → Celery → Neo4j upsert).

## 4. Real-time

The screens are "telemetry-alive" — status dots pulse, devices ping when transmitting, live
signal feeds update. Implement:

- **WebSocket** endpoint per surface (e.g. `/ws/operations`, `/ws/fleet`, `/ws/intel`).
- Fan-out via **Redis pub/sub**: ingestion / agents / state changes publish events; the API
  process subscribes and pushes to connected clients.
- Coarse polling fallback for dashboards (`?range=daily|weekly|monthly|yearly` — the operator
  kit already drives a range selector; honor it server-side in the read-models).

## 5. Configuration & secrets

No secrets in env files in the repo. **Vault** issues: Postgres/Neo4j dynamic creds, the
device-fleet PKI (firmware signing + device identity), JWT validation keys (or validate
against Keycloak JWKS), and Ollama/model endpoints. FastAPI fetches them at boot via the
Vault API (AppRole auth). See `SECURITY.md`.
