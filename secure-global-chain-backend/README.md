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
| devices, telemetry, intelligence, research, optimization, agents, executive | ⬜ pending |

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
