# Contributing — Secure Global Chain

Thanks for working on Secure Global Chain. This guide covers the workflow and the
conventions that keep the codebase consistent and auditable.

## The one rule

> **AI assists. Humans decide.** Never add a code path that lets an agent or a job
> finalize a consequential action (release, sign, quarantine, commit, decide,
> escalate). Those are human-gated and audited. If a task seems to ask for
> auto-approval, stop and flag it.

## Project setup

```bash
cd secure-global-chain-backend
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest                         # 169 tests, SQLite — no live services needed
```

To run the app locally without Docker/Keycloak:

```bash
make seed-local
SGC_DATABASE_URL=sqlite+aiosqlite:///./demo.db make dev   # DEV auth on
```

## Architecture & where code goes

- One **bounded context per center** under `src/sgc/<context>/`, each with
  `models` (in `src/sgc/models/`), `service.py`, `schemas.py`, `router.py`.
- **Read-models / per-screen data** belong in `src/sgc/views/` (the BFF) — compose
  context services, don't duplicate domain logic, write no audit events.
- See [docs/ARCHITECTURE_OVERVIEW.md](docs/ARCHITECTURE_OVERVIEW.md) and
  [docs/design_handoff/](docs/design_handoff/) before adding a context.

## Conventions

- **Stack is fixed** (don't substitute without asking): FastAPI, Pydantic v2,
  SQLAlchemy 2.0 async + Alembic, PostgreSQL, Neo4j, Redis, Celery,
  NumPy/SciPy/PyMC + OR-Tools, LangGraph + Ollama, Keycloak, Vault.
- **Names come from the domain model.** Field names, enum strings, and ID formats
  (`TRM-2291`, `DEV-1182`, `v4.2.1`, `sha256:…`, status tokens
  `pass|warn|fail|info|neutral`) match `DOMAIN_MODEL.md` and the frontend exactly.
  Don't rename them.
- **Consequential actions** are explicit sub-resources (`POST …/release`,
  `…/sign`, `…/quarantine`, `…/commit`, `…/decide`), gated by
  `require_role(..., human_only=True)`, idempotent (`Idempotency-Key`), and write
  an `audit_events` row **in the same transaction** (returning `X-Audit-Event-Id`).
- **Secrets only from Vault** (AppRole) in prod; validate JWTs against Keycloak
  JWKS. Nothing secret in env or the repo.
- **Errors** are RFC-9457 problem+json.
- **Tests** for every endpoint and every human-gating rule.

## Database changes

- Add an Alembic migration in `alembic/versions/` (sequential: `0009_…`).
- Migrations target PostgreSQL (UUID, JSONB, append-only audit trigger); tests run
  on `aiosqlite` via cross-dialect types in `db.py`.

```bash
export SGC_DATABASE_URL=postgresql+asyncpg://sgc:sgc@localhost:5432/sgc
alembic upgrade head
alembic upgrade head --sql      # render DDL offline (used in tests)
```

## Testing

```bash
pytest                          # all
pytest tests/test_views_registry.py -q
```

- No live Postgres/Keycloak/Vault needed — SQLite + locally-signed RSA tokens.
- Add a test alongside every new endpoint and every role gate.

## Git workflow

- Branch from the default branch; never commit directly to it.
- Clear, descriptive commit messages (imperative subject + a short body
  explaining *why*).
- Don't open a PR unless asked; keep changes scoped.

## License

This project does **not yet have a license**. Until a `LICENSE` file is added at
the repo root, all rights are reserved and external contributions can't be
redistributed. If you maintain this repo, pick a license (e.g. Apache-2.0 or MIT
for permissive, or a proprietary notice) and add the `LICENSE` file + a header
policy. Open an issue to decide.
