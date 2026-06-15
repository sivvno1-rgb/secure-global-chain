# secure-global-chain-backend

Backend service for the **Secure Global Chain** platform. Built per the design
handoff in [`docs/design_handoff/`](../docs/design_handoff/) (read those docs
first — `SECURITY.md`, `DOMAIN_MODEL.md`, `API_SURFACE.md`, `ARCHITECTURE.md`).

> **Operating principle: AI assists. Humans decide.** Agents *propose*; every
> consequential action (release, sign, provision, decide, escalate) requires a
> human actor and is written to the audit trail.

## Status

| Context | State |
|---|---|
| **Security core** — identity + audit kernel | ✅ implemented |
| **manufacturing** — Mission / Operations | ✅ implemented |
| **quality** — Deviations / CAPA / Audits | ✅ implemented |
| **devices** — NeuroSecure fleet / firmware | ✅ implemented |
| **telemetry** — cold chain / streams | ✅ implemented |
| **intelligence** — Systems Map / graph | ✅ implemented |
| **research** — evidence / validation | ✅ implemented |
| **optimization** — scheduling / scenario lab | ✅ implemented |
| **agents** — advisory mesh (proposals only) | ✅ implemented |
| **executive** — read-models (overview/risk/portfolio) | ✅ implemented |

## Run the full mesh (Docker)

`docker-compose.yml` brings up the whole stack from `CLAUDE.md` step 1: `postgres`,
`neo4j`, `redis`, `keycloak`, `vault`, `ollama`, `api`, `worker` (Celery), `beat`
(Celery scheduler).

```bash
cd secure-global-chain-backend
docker compose up -d --build

# Wait for the API to report healthy, then:
curl http://localhost:8000/health        # -> {"status":"ok"}

# Apply the database schema (one-off, after postgres is healthy):
docker compose exec api alembic upgrade head

# Tail logs / tear down
docker compose logs -f api
docker compose down            # add -v to also drop the data volumes
```

Exposed ports: API `8000`, Postgres `5432`, Neo4j `7474`/`7687`, Redis `6379`,
Keycloak `8080`, Vault `8200`, Ollama `11434`.

### Demo data (`make seed`)

`src/sgc/seed.py` loads idempotent demo data across every context — 3 lines, 12
batches in various states, open deviations + CAPAs, a 7-device fleet with
firmware + a rollout, cold-chain lanes with excursions, a schedule, evidence, and
a few agent runs. Re-running never duplicates (entities keyed by code/serial/etc.).

```bash
make migrate    # docker compose exec api alembic upgrade head
make seed       # docker compose exec api python -m sgc.seed
```

### Explore without Keycloak (DEV auth)

Set `SGC_DEV_AUTH=true` (already on in `docker-compose.yml`) to mount `GET
/dev/login`, which mints a Keycloak-shaped **HS256** token signed with
`SGC_DEV_AUTH_SECRET`. In this mode the API validates that token instead of
Keycloak JWKS — **`require_role()` is unchanged**, just satisfiable locally.
**Never enable in production** (default is off; a startup warning logs when on).

```bash
# mint a token for one or more roles
TOKEN=$(curl -s "http://localhost:8000/dev/login?roles=qa_release&sub=quinn" | jq -r .access_token)

# use it like any bearer token
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/batches

# ?service=true mints a non-human token (rejected by human_only routes)
```

**Explore with no Docker at all** (local SQLite):

```bash
make seed-local             # SGC_DATABASE_URL=sqlite+aiosqlite:///./demo.db, creates tables + seeds
SGC_DATABASE_URL=sqlite+aiosqlite:///./demo.db make dev   # uvicorn with SGC_DEV_AUTH=true
# then /dev/login + curl as above against http://localhost:8000
```

The `api`/`worker`/`beat` services share one image (`Dockerfile`) and are wired to
the other services by name via `SGC_*` env vars (see the `x-api-env` anchor in the
compose file). **Keycloak and Vault run in dev mode with throwaway credentials —
not for production.** `/health` is dependency-free, so it is reachable as soon as
the `api` container starts (before migrations / Keycloak realm setup).

> Validated here via `docker compose config` and by running the `api` command
> (`uvicorn sgc.main:app`) directly — `/health` returns `{"status":"ok"}`. A live
> `docker compose up` must be run in an environment with Docker Hub access (this
> CI sandbox blocks container-registry downloads).

### Executive read-models context

Read-only projections over the other centers per `ARCHITECTURE.md` §2.
**No new Postgres tables.**

- Endpoints: `GET /executive/overview`, `GET /executive/risk`,
  `GET /executive/portfolio` — all honor `?range=daily|weekly|monthly|yearly`
  and are restricted to `executive`/`auditor`.
- **Read-model seam** (`sgc/executive/readmodel.py`): `LiveReadModelBuilder`
  computes the projections on demand from manufacturing/quality/devices/telemetry
  aggregates (KPIs, portfolio counts, risk roll-up with a derived `risk_level`).
- Deferred: projection tables refreshed by Celery beat per range (the seam swaps
  to a projection-backed builder via `get_read_model_builder`).

### Agent mesh context

Model (`agent_runs`), migration (`0008`), and the API per `DOMAIN_MODEL.md` /
`API_SURFACE.md` / `AGENTS_AND_COMPUTE.md`. **The one rule: agents propose,
humans decide.**

- Endpoints: `GET /agents` (mesh status), `GET /agents/runs` (filter `agent`),
  `POST /agents/{agent}/invoke` (returns a run with a proposal),
  `POST /agents/runs/{id}/disposition` (human accept/reject → audit).
- **Mesh seam** (`sgc/agents/mesh.py`): six catalogued agents (tracer, quality
  analyst, evidence librarian, scheduler advisor, fleet sentinel, review scribe)
  over local Ollama models. `StubAgentMesh` produces deterministic, read-only
  proposals; the LangGraph-over-Ollama orchestrator is the prod target (swap via
  `get_agent_mesh`).
- **Hard rule enforced structurally**: an agent's only output is a
  `proposed_action` with `status=awaiting_human`; there is no code path from the
  mesh to a domain mutation. Disposition requires a **human** (`require_human` —
  service tokens rejected) and is audited; **accepting records the decision, it
  does not execute** — the human still acts via the center's human-gated route.
  Tests assert invoking/accepting never mutates consequential state.
- Deferred: the LangGraph/Ollama runtime and `WS /ws/agents`.

### Optimization & Scenario Lab context

Models, migration (`0007`), the API, and a real OR-Tools solve per
`DOMAIN_MODEL.md` / `API_SURFACE.md` / `AGENTS_AND_COMPUTE.md`:

- Tables: `schedules, schedule_slots, scenarios`.
- Endpoints: `POST /optimization/schedules` (solve), `GET …/schedules/{id}`,
  `POST …/schedules/{id}/commit`, `POST /optimization/scenarios` (what-if),
  `GET …/scenarios/{id}`.
- **Solver seam** (`sgc/optimization/solver.py`): `CpSatScheduleSolver` runs an
  OR-Tools **CP-SAT** single-line sequencing solve (no overlap, minimize
  makespan), time-boxed, returning honest `solver_status`
  (`optimal|feasible|infeasible|timeout`). Runs synchronously here; the Celery
  `optimize` queue is the prod target (swap via `get_schedule_solver`).
- **Advisory + human-gated**: a solve only *proposes* (`state=solved`); a person
  commits via `POST …/schedules/{id}/commit` — `planner`, audited
  (`X-Audit-Event-Id`). Scenarios re-solve perturbed params and persist
  `kpi_delta`.
- Deferred: the Celery `optimize` worker (time-boxed solves, progress over WS).

### Research & Evidence context

Models, migration (`0006`), the API, and real evidence compute per
`DOMAIN_MODEL.md` / `API_SURFACE.md` / `AGENTS_AND_COMPUTE.md`:

- Tables: `hypotheses, evidence_packets, evidence_results, validation_reports,
  datasets`.
- Endpoints: `GET/POST /research/hypotheses`, `GET /research/evidence/{id}`,
  `POST /research/evidence` (run), `GET/POST /research/validation-reports`,
  `POST /research/validation-reports/{code}/sign`.
- **Compute seam** (`sgc/research/compute.py`): `LocalEvidenceComputer` runs
  **frequentist** (scipy `ttest_1samp` + t-CI) and **Bayesian** (conjugate
  normal-normal posterior + credible interval) synchronously; reproducible
  (pinned seed, recorded lib versions + dataset hash). **No verdict in code** —
  the run computes statistics only; supported/refuted stays a human disposition.
- **Human-gated, audited**: `POST /research/validation-reports/{code}/sign` —
  `qa_release` e-signature (`X-Audit-Event-Id`).
- Deferred: the enclave Celery `evidence` worker (no outbound network, Vault-
  scoped data) and the PyMC Bayesian path — the seam runs synchronously for now.

### Intelligence / Systems Map context (graph)

Graph-backed per `ARCHITECTURE.md` §3 (Postgres = system of record, graph =
relationship/traversal). **No new Postgres tables.**

- Endpoints: `GET /intel/graph` (filter `supply|mfg|quality|compliance`),
  `GET /intel/node/{id}` (detail + connection count + signal),
  `GET /intel/trace/{batchCode}` (chain of custody), `GET /intel/impact/{nodeId}`
  (blast radius), `GET /intel/signals` (live fail/warn/pass feed).
- **GraphStore seam** (`sgc/intelligence/graph.py`): `InMemoryGraphStore` backs
  dev/tests, projected from Postgres by `projector.py` (the same upsert logic the
  production outbox→Celery→Neo4j sync runs). A `Neo4jGraphStore` Cypher skeleton
  (`neo4j_store.py`) is the production target — swap via the `get_graph_store`
  dependency.
- Deferred: the live Neo4j server + `neo4j` driver, and the outbox table + Celery
  sync worker (the dev path projects on demand instead).

### Telemetry & cold-chain context

Models, migration (`0005`), and the API per `DOMAIN_MODEL.md` / `API_SURFACE.md`:

- Tables: `sensor_streams, readings, coldchain_lanes, shipments, excursions`
  (`readings` is the high-volume time-series table — Timescale hypertable target).
- Reads: `GET /streams/{device}/readings` (filter `from`/`to`/`kind`),
  `GET /coldchain/lanes`, `GET /coldchain/excursions` (filter `lane`/`open`).
- **Human-gated, audited**: `POST /coldchain/excursions/{id}/disposition` —
  `quality`.
- **Signed-ingestion seam** (`sgc/telemetry/ingest.py`): device telemetry is
  signed with the Vault-issued device identity key; `ingest_signed_reading`
  verifies it, writes the reading, and **quarantines** the device on signature
  failure. `LocalDevTelemetryVerifier` stands in for dev/tests; swap via the
  `get_telemetry_verifier` dependency.
- Deferred: live `WS /ws/telemetry` (Redis pub/sub fan-out) and the Celery
  `ingest` worker that drives `ingest_signed_reading`.

### Device Fleet context

Models, migration (`0004`), and the API per `DOMAIN_MODEL.md` / `API_SURFACE.md`:

- Tables: `firmware_builds, devices, firmware_rollouts, device_attestations,
  provision_requests`.
- Reads: `GET /devices` (filter `state`/`site`), `GET /devices/{serial}`
  (+ attestation history), `GET /firmware`, `GET /firmware/rollouts/{id}`.
- **Human-gated, audited** transitions (role + human actor, audit row in the same
  transaction, `X-Audit-Event-Id`):
  - `POST /devices/provision` — request (`operator`/`fleet_admin`)
  - `POST /devices/provision-requests/{id}/approve` — `fleet_admin` (creates the device)
  - `POST /devices/{serial}/quarantine` — `fleet_admin`
  - `POST /firmware/{version}/sign` — `fleet_admin` (Vault-signed)
  - `POST /firmware/{version}/rollouts` — `fleet_admin` (requires signed firmware)
- **PKI seam** (`sgc/devices/pki.py`): firmware signing + device identity keys
  belong in **Vault PKI** (SECURITY.md §2-3). A deterministic `LocalDevSigner` /
  `LocalDevIdentityProvider` stands in for local/dev/tests; swap by overriding
  the `get_firmware_signer` / `get_device_identity_provider` dependencies.

### Quality & Compliance context

Models, migration (`0003`), and the API per `DOMAIN_MODEL.md` / `API_SURFACE.md`:

- Tables: `deviations, capas, compliance_items, audits, audit_findings`.
- Reads: `GET /deviations`, `GET /capas`, `GET /audits`,
  `GET /audits/{id}/findings`, `GET /compliance/area`.
- **Human-gated, audited** transitions (role + human actor, audit row in the same
  transaction, `X-Audit-Event-Id` on the response):
  - `POST /deviations` — raise (`operator` or `quality`), auto-codes `DEV-####`
  - `POST /deviations/{code}/escalate` — `quality`
  - `POST /capas/{code}/effectiveness` — `quality`
- Deferred: `POST /audit-packs` (needs the Celery + object store + Vault signing
  step; no table in the domain model yet).

### Manufacturing context

Models, migration (`0002`), and the Mission/Operations API per `DOMAIN_MODEL.md`
and `API_SURFACE.md` (exact field names / enum strings):

- Tables: `suppliers, materials, sites, lines, products, batches, batch_steps,
  ipc_checks, tasks, equipment`.
- Endpoints: `GET /mission/summary`, `GET /lines`, `GET /batches`,
  `GET /batches/{code}`, `GET /tasks`, `POST /tasks/{id}/complete`, and the
  human-gated consequential routes below.
- **Human-gated, audited transitions** (each requires the role + a human actor
  via `require_role(..., human_only=True)` and writes an `audit_events` row in
  the same transaction; the response carries `X-Audit-Event-Id`):
  - `POST /batches/{code}/release` — `qa_release`
  - `POST /batches/{code}/quarantine` — `quality`
  - `POST /batches/{code}/steps/{id}/sign` — `operator` (e-signature)

## Security core (what's here now)

Implements the identity + audit kernel from `SECURITY.md` §1, §4, §5:

- **JWT validation against Keycloak** (`sgc/security/jwt.py`) — verifies
  signature (RS256, JWKS `kid` rotation), `iss`, `aud`, `exp`; rejects anything
  else. The signing-key resolver is injectable for testing.
- **`require_role()` RBAC dependency** (`sgc/security/deps.py`) — realm-role
  gate; `401` for missing/invalid token, `403` for insufficient role (generic
  messages — never leaks which). `human_only=True` rejects service tokens on
  consequential routes.
- **Append-only, hash-chained `audit_events`** (`sgc/audit/chain.py`,
  `sgc/models/audit.py`) — `hash = sha256(prev_hash + canonical_json(event))`,
  plus a `users` mirror and the first Alembic migration. The migration also
  installs a Postgres trigger blocking `UPDATE`/`DELETE` on the ledger.

## Layout

```
secure-global-chain-backend/
├── pyproject.toml
├── alembic.ini
├── .env.example
├── alembic/
│   ├── env.py                 # async Alembic environment
│   └── versions/0001_identity_audit_kernel.py
├── src/sgc/
│   ├── config.py              # settings (Vault in prod; env for dev)
│   ├── db.py                  # async engine/session + cross-dialect types
│   ├── main.py                # FastAPI app (kernel routes only so far)
│   ├── models/                # users, audit_events
│   ├── security/              # JWT validation, Principal, require_role
│   └── audit/                 # hash-chain build + verify
└── tests/                     # JWT, RBAC, audit-chain, migration
```

## Develop

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

# Tests (SQLite in-memory; no external services needed)
pytest

# Apply migrations to Postgres
export SGC_DATABASE_URL=postgresql+asyncpg://sgc:sgc@localhost:5432/sgc
alembic upgrade head

# Run the API
uvicorn sgc.main:app --reload
```

### Testing notes

Tests run on `aiosqlite` so they need no live Postgres, Keycloak, or Vault. JWT
tests generate an RSA keypair and sign tokens locally; the Alembic migration is
validated by rendering its Postgres DDL **offline** (`alembic upgrade head --sql`).
The migration itself targets PostgreSQL (UUID, JSONB, append-only trigger).
