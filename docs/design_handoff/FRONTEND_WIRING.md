# Frontend wiring — live data for every screen

This document defines how the operator frontend (`ui_kits/operator/`) consumes
live data from the FastAPI backend, and the exact **view-model contract** each
screen needs. It is the bridge between two data models that were designed
separately:

- the **frontend** renders a rich, narrative product model (mission health,
  ranked events, facility/shipment status, …);
- the **backend** stores normalized domain data (batches, deviations, devices, …).

We reconcile them with **per-screen read-model endpoints** (a backend-for-frontend
layer) — the same projection pattern the executive context already uses.

---

## 1. The integration pattern (frontend — already in place)

`ui_kits/operator/live-data.js` is loaded before the screens and exposes:

```js
window.SGCLive            // store: auth, fetch, cache, act(), refresh()
window.useLive('<key>')   // React hook → view-model object, or null
```

Each screen reads its view-model and falls back to its built-in demo data, so
the app is always usable (offline → demo, online → live):

```js
const live = window.useLive('mission');
const kpis = live?.kpis ?? DEMO_KPIS;
```

- **Auth:** `live-data.js` mints a dev token via `GET /dev/login?roles=<role>`
  (gated by `SGC_DEV_AUTH`; swap to real Keycloak later). Role comes from
  `?role=` or `localStorage`.
- **Base URL:** same-origin by default (works when the backend serves the app);
  override with `?api=https://host` (backend must allow CORS).
- **Actions:** `SGCLive.act('/api/v1/.../release', body)` POSTs a consequential
  action and returns the parsed body + `X-Audit-Event-Id`. After an action,
  call `SGCLive.refresh('<key>')`.

**Mission Control is already wired** as the reference implementation — copy its
shape for the rest.

---

## 2. The backend contract (to build in the repo)

For each screen `<key>`, implement:

```
GET /api/v1/views/<key>?range=        → role-gated read-model, JSON below
```

- Put these under a new `views` router (`src/sgc/views/`), composing existing
  context services — **do not** duplicate domain logic; aggregate it.
- Role-gate with the existing `require_role()` (operator/quality/exec as noted).
- These are **reads** — no new audit events. Consequential actions still go
  through the existing gated routes (`/release`, `/sign`, …); the frontend calls
  those directly via `SGCLive.act()`.
- Return the **exact field names** below — the screens render them as-is.

---

## 3. Screen inventory

| Key | Screen (component) | Role | Status | Composes |
|-----|--------------------|------|--------|----------|
| `mission` | Mission Control (`MissionControl`) | operator | **contract ready ✅ / frontend wired ✅** | manufacturing + quality + telemetry + devices |
| `operations` | Operations (`OpsSection`) | operator | to spec | manufacturing (lines, batches, IPC, tasks) |
| `quality` | Quality & Compliance (`QualityCompliance`) | quality | to spec | quality (deviations, CAPA, audits, reviews) |
| `intelligence` | Intelligence / Systems Map (`IntelSection`) | operator | to spec | intelligence (graph, trace, signals) |
| `research` | Research enclave (`ResearchSection`) | researcher | to spec | research (hypotheses, evidence, reports) |
| `optimization` | Optimization / Scenario Lab (`OptSection`) | planner | to spec | optimization (schedules, scenarios) |
| `decisions` | Decision Center (`OpDecision`) | operator | to spec | decisions + cross-context proposals |
| `reviews` | Executive Review Center (`ReviewCenter`) | executive | to spec | reviews (cadenced governance) |
| `agents` | Agent Mesh (`OpAgents`) | operator | to spec | agents (mesh, runs, proposals) |
| `escalate` | Incident Response (`OpEscalate`) | operator | to spec | incidents |
| `economy` | Economic Policy Layer (`EconomicLayer`) | executive | to spec | economy indicators |

Sub-tabs inside Intelligence / Research / Operations / Optimization can either be
folded into the parent view-model or fetched as `views/<key>/<tab>` — decide per
screen as we wire them.

> The remaining contracts are authored screen-by-screen as we wire each one (the
> exact shapes are read off each component's current demo data, which lives here
> in the design system, not in the backend repo). Mission below is the template.

---

## 4. Contract — `mission`  → `GET /api/v1/views/mission`

Renders Mission Control: headline chips, the 6 KPI tiles, the ranked event list,
and the facility / shipment status tiles.

```jsonc
{
  "headline": {
    "mission_pct": 92,            // int — composite health, drives "Mission 92%"
    "critical_events": 2          // int — count of sev=="fail" events
  },
  "kpis": [                       // exactly these 6, in order; tone ∈ pass|warn|fail
    { "label": "Mission health",     "v": "92",     "u": "%",    "tone": "pass" },
    { "label": "Active risks",       "v": "4",                   "tone": "fail" },
    { "label": "Pending decisions",  "v": "4",                   "tone": "warn" },
    { "label": "Facilities healthy", "v": "15",     "u": "/ 18", "tone": "pass" },
    { "label": "Shipments delayed",  "v": "2",                   "tone": "warn" },
    { "label": "Value at risk",      "v": "$23.8M",              "tone": "fail" }
  ],
  "events": [                     // ranked by impact; sev ∈ fail|warn; c = hex accent
    {
      "sev": "fail",
      "c": "#b5341f",
      "cat": "Supply disruption",
      "title": "Guselkumab DS held in Swiss customs",
      "desc": "Single-source TREMFYA drug substance delayed +6 days — batch hold risk within 48 hours.",
      "impact": [["Schedule","11% slip"],["Exposure","$0.9M/wk"],["Facilities","3"]],
      "action": "Escalate + activate procurement",
      "go": "escalate",           // target view id for the button
      "btn": "Open incident"
    }
    // …more events
  ],
  "facilities": [                 // [name, detail, status]; status ∈ pass|warn|fail
    ["Schaffhausen", "Particle drift · Line B", "fail"],
    ["Singapore",    "ERLEADA lot hold",        "warn"],
    ["Cork",         "DS customs hold",          "warn"]
  ],
  "shipments": [                  // [name, detail, status]
    ["Guselkumab DS", "Customs review · +6d",   "warn"],
    ["Lane Cork→CH",  "Cold-chain excursion",    "warn"],
    ["Polysorbate 80","In transit · on time",    "pass"]
  ]
}
```

**How the backend should populate it (compose, don't invent):**

- `kpis[1] Active risks` ← count of open critical/major items across
  `deviations(state=open)` + `coldchain/excursions(open)` + agent proposals pending.
- `kpis[2] Pending decisions` ← open decisions + agent runs awaiting disposition.
- `kpis[3] Facilities healthy` ← sites with no open critical signal / total sites.
- `kpis[4] Shipments delayed` ← cold-chain lanes in excursion / delayed transit.
- `kpis[5] Value at risk` ← sum of `value` on quarantined/at-risk batches (or a
  configured estimate); format as `$X.YM`.
- `events` ← top-N ranked union of: open critical deviations, cold-chain
  excursions, quality holds (quarantined batches), capacity bottlenecks from the
  optimizer. Map each to `{sev,cat,title,desc,impact,action,go,btn}`.
- `facilities` / `shipments` ← site health roll-up and lane/transit status.
- `mission_pct` ← weighted composite (e.g. compliance, uptime, on-time, open-risk
  penalty). Pick a formula and keep it stable.

When any field is absent the frontend keeps its demo value, so the endpoint can
ship incrementally (start with `kpis` + `headline`, add `events` next, etc.).
