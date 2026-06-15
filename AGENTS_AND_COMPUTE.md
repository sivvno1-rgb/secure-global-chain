# Agents & scientific compute — Secure Global Chain

Two engine families sit behind Celery: the **agent mesh** (LangGraph + Ollama) and the
**scientific/evidence + optimization** compute (pandas/numpy/scipy/PyMC, OR-Tools). Both are
**advisory**. They surface proposals; humans decide.

---

## 1. Celery topology

```
Broker / result backend: Redis
Queues:
  ingest      → device telemetry, lab files, external feeds (high volume, fast)
  evidence    → pandas/scipy/PyMC runs (CPU-heavy, isolated enclave worker)
  optimize    → OR-Tools schedule / scenario solves (CPU-heavy, time-boxed)
  agents      → LangGraph runs that call Ollama (I/O + LLM latency)
  audit       → audit-pack export & signing (low volume, sensitive)
Beat schedules:
  - refresh executive read-models (per range)
  - re-attest device fleet
  - cold-chain excursion sweeps
  - graph (Neo4j) reconciliation from the Postgres outbox
```

Workers are separate Docker services so the **enclave** (`evidence`) worker can be locked
down: no outbound internet, Vault-scoped dataset access only, results written back over the
broker. Time-box long solves and stream progress over Redis → WebSocket.

---

## 2. Agent mesh (LangGraph over Ollama)

Model the mesh as a **LangGraph** state graph (or an equivalent custom Python orchestration).
Each node is a focused agent; the graph state carries the task, retrieved context, and a
growing list of **proposals**.

Suggested agents (map to centers):

| Agent | Job (read-only + propose) |
|---|---|
| **Tracer** | Walk the Neo4j chain of custody; assemble traceability / blast-radius summaries |
| **Quality analyst** | Triage deviations, draft CAPA suggestions, flag effectiveness risk |
| **Evidence librarian** | Retrieve datasets/packets, summarize stats, never assert conclusions |
| **Scheduler advisor** | Read OR-Tools output, explain trade-offs, suggest scenario params |
| **Fleet sentinel** | Watch device attestation/telemetry, propose quarantine on anomaly |
| **Review scribe** | Assemble cadenced review packets (decisions, risks, metrics) |

Hard rules for every agent:
- **Tools are read-mostly.** The only "write" an agent may perform is creating a *proposal*
  (`agent_runs.proposed_action`) and posting non-destructive notes. It cannot release a
  batch, sign firmware, close a deviation, or decide.
- **Local inference only via Ollama** (e.g. a small instruct model). No data leaves the
  network. Model name + endpoint come from Vault, recorded on each `agent_run`.
- **Every run is logged** to `agent_runs` with input/output refs, model, and the human
  disposition once a person accepts/rejects. This is part of the audit story.
- **Grounding:** agents retrieve from Neo4j + Postgres + evidence store; prompts must cite
  the records used. Prefer structured tool calls over free generation.

Run lifecycle:
```
invoke → LangGraph executes nodes → proposals collected → run = "awaiting_human"
       → WS /ws/agents notifies → human accepts via a human-gated center route
       → disposition written back → audit_event
```

---

## 3. Scientific / evidence compute

Evidence packets (see `DOMAIN_MODEL.md → research`) are produced by Celery `evidence` tasks.
Support both schools (the platform's JASP heritage):

- **Frequentist** (pandas + scipy.stats): t-tests, ANOVA, regression, CIs, p-values.
- **Bayesian** (PyMC): posterior estimation, credible intervals, model comparison.
- numpy for the array math; pandas for dataset wrangling; persist:
  `evidence_results(statistic, value, ci_low, ci_high, p_value, posterior_ref)`.

Principles:
- **Reproducible:** pin seeds, record library versions + dataset hash on the packet
  (`dataset_ref` + lineage). A regulator must be able to re-run it.
- **No conclusions in code.** The task computes statistics; the *interpretation* ("supported /
  refuted") is a human disposition on the hypothesis. Agents may summarize numbers, not rule.
- **Enclave execution:** runs in the locked-down worker; large artifacts (traces, posterior
  samples) go to object storage, referenced by URL, not inlined.

---

## 4. Optimization (OR-Tools)

- `optimize` queue solves production **schedules** (CP-SAT / routing as appropriate):
  objective + constraints from `schedules` / `lines` / `batches`; output `schedule_slots`.
- **Scenario Lab** = re-solve with perturbed `scenarios.params`; persist `kpi_delta`.
- Time-box solves; return `solver_status` (optimal / feasible / infeasible / timeout) so the
  UI can show honest state. Solver is advisory — a human commits a schedule.

---

## 5. Ingestion

- Device telemetry arrives signed (device identity from Vault PKI). The `ingest` worker
  verifies the signature, rejects/ quarantines on failure, writes `readings`, and publishes a
  live event to Redis → WebSocket. Out-of-spec readings raise excursions / signals.
- Lab and external (economic) feeds land as datasets with recorded lineage.
