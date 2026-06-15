# Secure Global Chain

> **Pharma & advanced-manufacturing intelligence platform** — a system of record,
> knowledge graph, scientific/optimization compute mesh, and advisory agent layer
> behind a polished operator frontend.

[![tests](https://img.shields.io/badge/tests-169%20passing-brightgreen)](#testing)
[![python](https://img.shields.io/badge/python-3.11%2B-blue)](#)
[![api](https://img.shields.io/badge/api-FastAPI-009688)](#)
[![license](https://img.shields.io/badge/license-TBD-lightgrey)](#license)

---

## The one rule that overrides everything

> **AI assists. Humans decide.**
>
> Agents and jobs may *summarize, retrieve, compute, and propose*. They may
> **never** finalize a consequential action — releasing a batch, signing firmware
> or a validation report, closing a deviation, committing a schedule, or making a
> decision. Those require a **human actor** with the right role and are written to
> an append-only, hash-chained **audit trail**.

This rule is not a guideline; it is enforced structurally (see
[Decision Architecture](docs/ARCHITECTURE_OVERVIEW.md#3-decision-architecture)).

---

## What this is

A pharmaceutical manufacturing-intelligence backend that produces the live data a
rich operator frontend renders: mission health, manufacturing operations, quality
& compliance, a NeuroSecure device fleet, cold-chain telemetry, an intelligence
systems-map, a research/evidence enclave, production optimization, and an advisory
agent mesh — unified by identity, RBAC, and a tamper-evident audit ledger.

- **Postgres** is the system of record. **Neo4j** is the relationship/traversal
  layer (chain of custody, blast-radius). **Redis** is cache + broker + WebSocket
  fan-out. Heavy work runs on **Celery**.
- **OR-Tools** solves production schedules; **SciPy/NumPy/PyMC** produce
  reproducible statistical evidence; **LangGraph + Ollama** drive local, advisory
  agents.
- **Keycloak** issues identity (OIDC/JWT); **Vault** holds secrets and the
  device/firmware PKI.

## Architecture at a glance

```
                 ┌─────────────────────────────────────────────┐
   Frontend ────▶│  FastAPI (REST + WS)  ·  views BFF layer     │
  (ui_kits) ◀────│  Pydantic v2 contracts · OIDC/JWT · RBAC     │
                 └───┬───────────────┬───────────────┬─────────┘
                     │               │               │
            ┌────────▼──────┐ ┌──────▼───────┐ ┌─────▼─────────┐
            │ PostgreSQL    │ │   Neo4j      │ │     Redis     │
            │ system of     │ │ relationships│ │ cache·broker· │
            │ record (ACID) │ │ /traversal   │ │ ws fan-out    │
            └───────────────┘ └──────────────┘ └──────┬────────┘
              shared business ID ◀── outbox→Celery     │ broker
                                                ┌───────▼────────┐
                                                │ Celery workers │
                                                │ ingest·evidence│
                                                │ optimize·agents│
                                                └───┬────────┬───┘
                                              ┌─────▼──┐ ┌───▼────────┐
                                              │ Ollama │ │ SciPy/NumPy│
                                              │ (LLMs) │ │ /OR-Tools  │
                                              └────────┘ └────────────┘
   Cross-cutting: Keycloak (OIDC) · Vault (secrets/PKI) · hash-chained audit
```

Full treatment — through **MBSE**, **Operations Research**, and **Decision
Architecture** lenses — in **[docs/ARCHITECTURE_OVERVIEW.md](docs/ARCHITECTURE_OVERVIEW.md)**.

## Technology stack

| Layer | Tools |
|---|---|
| **API** | FastAPI · Uvicorn · Pydantic v2 · pydantic-settings |
| **Data** | PostgreSQL 16 (SQLAlchemy 2.0 async + asyncpg) · Neo4j 5 · Redis 7 · Alembic |
| **Compute** | Celery · OR-Tools (CP-SAT) · NumPy · SciPy · (PyMC) |
| **Agents** | LangGraph · Ollama (local LLMs) |
| **Identity / secrets** | Keycloak (OIDC) · PyJWT · HashiCorp Vault · cryptography |
| **Audit** | Append-only, SHA-256 hash-chained ledger (custom) |
| **Ops / test** | Docker · docker-compose · setuptools · pytest · pytest-asyncio · aiosqlite |

## Repository layout

```
secure-global-chain/
├── README.md                     ← you are here (project landing)
├── CONTRIBUTING.md               ← dev workflow + conventions
├── CLAUDE.md                     ← agent/contributor operating instructions
├── docs/
│   ├── ARCHITECTURE_OVERVIEW.md  ← MBSE / OR / decision architecture
│   ├── VIEWS_API.md              ← the 27 per-screen view-model endpoints
│   └── design_handoff/           ← original specs (source of truth)
│       ├── README.md  ARCHITECTURE.md  DOMAIN_MODEL.md  API_SURFACE.md
│       ├── AGENTS_AND_COMPUTE.md  SECURITY.md  FRONTEND_WIRING.md
└── secure-global-chain-backend/  ← the service (FastAPI app, see its README)
    ├── README.md                 ← backend quickstart + per-context status
    ├── Dockerfile  docker-compose.yml  Makefile  pyproject.toml
    ├── alembic/                  ← migrations (0001–0008)
    ├── src/sgc/                  ← bounded contexts + kernel + views BFF
    └── tests/                    ← 169 tests (SQLite, no live services)
```

## Quickstart

```bash
cd secure-global-chain-backend

# Full mesh (needs Docker registry access):
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python -m sgc.seed
curl http://localhost:8000/            # operator frontend (HTTP 200)
curl http://localhost:8000/health      # {"status":"ok"}

# Or local, no Docker (SQLite + dev auth):
python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
make seed-local
SGC_DATABASE_URL=sqlite+aiosqlite:///./demo.db make dev
```

See the **[backend README](secure-global-chain-backend/README.md)** for the full
guide (DEV auth tokens, per-context endpoints, seam-swapping for prod).

## Documentation index

| Document | What it covers |
|---|---|
| [docs/ARCHITECTURE_OVERVIEW.md](docs/ARCHITECTURE_OVERVIEW.md) | System design: MBSE, Operations Research, Decision Architecture |
| [docs/VIEWS_API.md](docs/VIEWS_API.md) | The backend-for-frontend `views` layer (27 endpoints) |
| [backend README](secure-global-chain-backend/README.md) | Run it, per-context status, endpoints, prod seams |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Branching, commits, conventions, testing |
| [docs/design_handoff/](docs/design_handoff/) | Original specs (domain model, API surface, security) |

## Status

Implemented and tested: identity+audit kernel · manufacturing · quality · devices
· telemetry · intelligence (graph) · research · optimization · agents · executive
read-models · the 27-route **views** BFF · operator frontend served at `/`.

Specced, not yet modeled: `decisions`, `reviews`, `economy`, `incident` contexts
(their view-model routes are scaffolded and return `{}` so the frontend keeps demo
data until the domains land).

## License

Not yet chosen — see [the license note](CONTRIBUTING.md#license). Until a `LICENSE`
file is added, all rights are reserved by the copyright holders.

## Testing

```bash
cd secure-global-chain-backend && pytest      # 169 tests, no live services needed
```
