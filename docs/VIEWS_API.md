# Views API — backend-for-frontend read-models

The `views` layer (`src/sgc/views/`) is a **backend-for-frontend (BFF)**: one
role-gated, read-only endpoint per operator screen, returning the exact shape that
screen renders. It *composes* existing context services — it duplicates no domain
logic and writes **no audit events**. Consequential actions still go through the
gated context routes (`/release`, `/sign`, …), which the frontend calls directly.

This implements [`design_handoff/FRONTEND_WIRING.md`](design_handoff/FRONTEND_WIRING.md)
§2 and the §7 master registry.

## How it works

```
GET /api/v1/views/<key>?range=daily|weekly|monthly|yearly
    → role-gated (require_role) read-model JSON
```

- The route table is **generated from a single registry** (`views/registry.py`),
  so role-gating stays consistent and a new screen is one row.
- Each builder returns **only the fields it can compose** and omits the rest; the
  frontend keeps its built-in demo value for anything absent
  (`response_model_exclude_none`).
- **Availability** classifies each row:
  - `live` — composable from existing services today.
  - `new-domain` — needs a model that doesn't exist yet → returns `{}`.
  - `illustrative` — a designed visualization with no operational source → `{}`.

## Endpoint registry (27)

| Key | Role | Availability | Composes from |
|---|---|---|---|
| `mission` | operator | **live** | manufacturing + quality + telemetry + devices |
| `operations` | operator | **live** | manufacturing (tasks, batch, env, devices) |
| `quality` | quality | **live** | quality (compliance, CAPA, audits) + agents |
| `ops/facility-map` | operator | **live** | sites + lines health |
| `optimization/schedule` | planner | **live** | optimization schedules + slots |
| `optimization/scenario` | planner | **live** | optimization scenarios |
| `agents` | operator | **live** | agent mesh + runs |
| `intel/globe` | operator | **live** | sites + devices + signals |
| `intel/dependencies` | operator | **live** | intel graph (nodes + edges) |
| `intel/hardware` | operator | **live** | telemetry + devices |
| `intel/evidence` | operator | **live** | research evidence packets |
| `research/reports` | researcher | **live** | validation reports |
| `research/hypotheses` | researcher | **live** | hypotheses |
| `research/evidence` | researcher | **live** | evidence packets |
| `research/lockout` | researcher | **live** | agent runs + audit chain |
| `decisions` | operator | live¹ | decisions (domain not yet modeled) |
| `reviews` | executive | live¹ | reviews (domain not yet modeled) |
| `escalate` | operator | live¹ | incidents (domain not yet modeled) |
| `intel/economy` | executive | live¹ | economy indicators (not yet modeled) |
| `economy` | executive | live¹ | economy indicators (not yet modeled) |
| `ops/trade-ports` | operator | new-domain | logistics/lanes (not modeled) |
| `intel/finance` | executive | new-domain | finance/cost model (not modeled) |
| `intel/security` | operator | new-domain | audit + attestation derivation |
| `research/trust` | researcher | new-domain | trust/attestation model |
| `ops/peers` | operator | illustrative | — |
| `intel/workforce` | operator | illustrative | — |
| `intel/program` | operator | illustrative | — |

¹ Flagged `live` in the §7 build order, but the backing domain isn't modeled in
this repo yet, so the route currently returns `{}` and the frontend uses demo data.

## Authored contracts

Three screens have authored JSON contracts; the rest return provisional composed
shapes (the frontend author owns the final shapes as each screen is wired).

### `GET /api/v1/views/mission` (operator)
Headline chips, 6 KPI tiles, ranked event list, facility + shipment status.
```jsonc
{
  "headline": { "mission_pct": 92, "critical_events": 2 },
  "kpis": [ { "label": "Mission health", "v": "92", "u": "%", "tone": "pass" }, … ],  // exactly 6, in order
  "events": [ { "sev": "fail", "c": "#b5341f", "cat": "...", "title": "...",
               "desc": "...", "impact": [["Schedule","11% slip"]],
               "action": "...", "go": "escalate", "btn": "Open incident" } ],
  "facilities": [ ["Schaffhausen", "Particle drift · Line B", "fail"] ],  // [name, detail, status]
  "shipments":  [ ["Guselkumab DS", "Customs review · +6d", "warn"] ]
}
```

### `GET /api/v1/views/operations` (operator)
Shift task queue, assigned devices, cleanroom readings, active batch.
```jsonc
{
  "tasks":   [ { "id": "t2", "t": "Environmental check", "due": "09:00", "st": "now", "kind": "Monitoring" } ], // st ∈ done|now|todo
  "devices": [ { "id": "SGC-NS-04127", "loc": "CR4 · EEG", "st": "pass", "live": true } ],                      // st ∈ pass|warn|fail
  "env":     [ { "k": "Particle 0.5µm", "v": "2,140", "u": "/m³", "ok": true } ],
  "batch":   { "code": "TRM-2291", "stage": "Filling", "completion": 62 }
}
```

### `GET /api/v1/views/quality` (quality)
KPI tiles, change controls, periodic reviews, doc/training progress, continuous
improvement, agent drafts. Only the tiles with a real source are emitted (e.g.
compliance → "SOX on-time", CAPAs → "Open CAPAs", audits → "Audit readiness", plus
agent drafts); change-control / periodic-review / training fields are omitted until
those domains are modeled.
```jsonc
{
  "kpis":   [ { "label": "Open CAPAs", "v": "9", "tone": "warn" }, … ],
  "agents": [ { "t": "Drafted CC-0431 requalification plan", "m": "Awaiting human disposition", "act": "Review" } ]
}
```

Full contracts and field-by-field composition notes live in
[`design_handoff/FRONTEND_WIRING.md`](design_handoff/FRONTEND_WIRING.md) §4–7.

## Guarantees (enforced by tests)

`tests/test_views_registry.py` + `tests/test_views_mission.py` assert, for the
whole registry:

- right role → `200`; wrong role → `403`; no token → `401`;
- `new-domain` / `illustrative` routes return `{}`;
- the §5/§6 contracts match their authored shape;
- exactly one route per key (27, no duplicates);
- hitting every view writes **no** audit events (reads only).
