# API surface — Secure Global Chain

REST under `/api/v1`, JSON, Pydantic v2 schemas. WebSocket under `/ws`. Every mutating route
requires a valid JWT and writes an `audit_event`. List endpoints accept
`?range=daily|weekly|monthly|yearly` (dashboards), `?page`/`?limit`, and relevant filters.
Responses use the **exact field names / enum strings** from `DOMAIN_MODEL.md`.

Conventions:
- `GET` collection → `{ items: [...], total, page }`
- Status fields serialize as the StatusDot/Badge token (`pass|warn|fail|info|neutral`) or the
  domain enum string, matching what the screen renders.
- Consequential verbs are **explicit sub-resources**, not generic PATCH:
  `POST …/release`, `…/quarantine`, `…/sign`, `…/escalate`, `…/provision`, `…/approve`.

---

## Mission / Operations (manufacturing context)

```
GET  /api/v1/mission/summary?range=            → KPI tiles (supply on-time, line uptime, compliance score)
GET  /api/v1/lines                             → lines with stage, uptime, status
GET  /api/v1/batches?line=&status=             → batch table (code, line, stage, status, yield)
GET  /api/v1/batches/{code}                    → full batch + steps + IPC checks
POST /api/v1/batches/{code}/release            → human-only; → audit; → graph event
POST /api/v1/batches/{code}/quarantine
POST /api/v1/batches/{code}/steps/{id}/sign    → e-signature; → audit
GET  /api/v1/tasks?assignee=me&window=today    → operator task list
POST /api/v1/tasks/{id}/complete
GET  /api/v1/compliance/area?framework=        → GMP/GLP items for the operator's area
WS   /ws/operations                            → live signals, IPC results, task changes
```

## Quality & Compliance

```
GET  /api/v1/deviations?severity=&state=
POST /api/v1/deviations                        → raise (code DEV-####); → audit
POST /api/v1/deviations/{code}/escalate
GET  /api/v1/capas?status=
POST /api/v1/capas/{code}/effectiveness        → record check result
GET  /api/v1/audits  ·  GET /api/v1/audits/{id}/findings
POST /api/v1/audit-packs                       → enqueue Celery job → signed bundle
GET  /api/v1/audit-packs/{id}                  → status + download URL when ready
```

## Device Fleet (NeuroSecure)

```
GET  /api/v1/devices?state=&site=              → fleet table (serial, state, firmware, last seen)
GET  /api/v1/devices/{serial}                  → device detail + attestation history + streams
POST /api/v1/devices/provision                 → request; approval is human-gated
POST /api/v1/devices/{serial}/quarantine
GET  /api/v1/firmware                          → builds (version, digest, state)
POST /api/v1/firmware/{version}/sign           → Vault-signed; human-only; → audit
POST /api/v1/firmware/{version}/rollouts       → start staged rollout
GET  /api/v1/firmware/rollouts/{id}            → progress (devices_done/total)
WS   /ws/fleet                                 → device ping / state / attestation events
```

## Telemetry & Cold chain

```
GET  /api/v1/streams/{device}/readings?from=&to=&kind=
GET  /api/v1/coldchain/lanes                   → lanes with spec + status
GET  /api/v1/coldchain/excursions?lane=&open=
POST /api/v1/coldchain/excursions/{id}/disposition
WS   /ws/telemetry                             → live readings (throttled / downsampled)
```

## Intelligence / Systems Map (Neo4j)

```
GET  /api/v1/intel/graph?filter=supply|mfg|quality|compliance   → nodes + edges for the map
GET  /api/v1/intel/node/{id}                   → node detail + signal + connection count
GET  /api/v1/intel/trace/{batchCode}           → end-to-end chain of custody (Cypher path)
GET  /api/v1/intel/impact/{nodeId}             → blast radius ("what does this affect")
GET  /api/v1/intel/signals?range=              → live signal feed (fail/warn/pass items)
```

## Research & Evidence

```
GET  /api/v1/research/hypotheses?state=
POST /api/v1/research/hypotheses
GET  /api/v1/research/evidence/{id}            → packet + results (stat, CI, p, posterior ref)
POST /api/v1/research/evidence                 → enqueue evidence run (method=frequentist|bayesian)
GET  /api/v1/research/validation-reports
POST /api/v1/research/validation-reports/{id}/sign   → human approval; → audit
```

## Optimization & Scenario Lab

```
POST /api/v1/optimization/schedules            → enqueue OR-Tools solve (Celery)
GET  /api/v1/optimization/schedules/{id}       → slots + solver_status
POST /api/v1/optimization/scenarios            → what-if over a base schedule
GET  /api/v1/optimization/scenarios/{id}       → KPI deltas
```

## Decisions, Reviews, Economy, Escalate, Executive

```
GET  /api/v1/decisions?state=open
POST /api/v1/decisions/{id}/decide             → human-only: option + rationale; → audit
GET  /api/v1/reviews?cadence=                  → cadenced governance items
POST /api/v1/reviews/{id}/items/{itemId}/disposition
GET  /api/v1/economy/indicators?region=        → macro/finance layer
POST /api/v1/incidents/escalate                → open incident, notify, → audit
GET  /api/v1/incidents?state=open
GET  /api/v1/executive/overview?range=         → read-model: portfolio, risk, KPIs
GET  /api/v1/executive/risk    ·  GET /api/v1/executive/portfolio
```

## Agents (mesh)

```
GET  /api/v1/agents                            → mesh status (agent, state, last run, model)
GET  /api/v1/agents/runs?agent=                → run log with proposed_action + human_disposition
POST /api/v1/agents/{agent}/invoke             → kick a LangGraph run (returns run id)
POST /api/v1/agents/runs/{id}/disposition      → human accepts/rejects a proposal; → audit
WS   /ws/agents                                → run progress / proposals awaiting human
```
**No agent endpoint ever finalizes a consequential action.** Agents produce *proposals*
attached to a run; a human accepts via the relevant center's human-gated route above.

---

## Cross-cutting response contract

- **Auth:** `Authorization: Bearer <JWT>` (Keycloak). 401 unauth, 403 missing role.
- **Errors:** RFC-9457 problem+json `{ type, title, status, detail, instance }`.
- **Audit:** mutating responses include `X-Audit-Event-Id` header.
- **Idempotency:** consequential POSTs accept `Idempotency-Key` (stored in Redis).
- **Pagination/sort/filter:** consistent query params across collections.
