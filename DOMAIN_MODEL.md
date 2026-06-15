# Domain model — Secure Global Chain

SQLAlchemy 2.0 (async, `Mapped[...]` style) + Alembic. Field names and enum values are taken
from the screens — keep them so the frontend binds with zero remapping. IDs below show the
**human business key** format; also give every table a UUID surrogate PK.

> Convention: every table has `id UUID pk`, `created_at`, `updated_at`, and (where it
> matters) `created_by`, `updated_by` FK → `users`. Lifecycle-bearing tables also carry a
> `status` enum and emit a domain event on transition (for Neo4j sync + audit).

---

## Enums (single source of truth)

```python
class BatchStatus(str, Enum):
    in_process = "In process"; hold = "Hold"; inspection = "Inspection"
    released = "Released"; quarantine = "Quarantine"; rejected = "Rejected"

class QualityState(str, Enum):
    compliant = "Compliant"; review = "Review"; quarantine = "Quarantine"
    verified = "Verified"; escalated = "Escalated"; watch = "Watch"

class Severity(str, Enum):
    critical = "Critical"; major = "Major"; minor = "Minor"

class RiskLevel(str, Enum):
    critical = "Critical"; high = "High"; watch = "Watch"

class DeviceState(str, Enum):
    provisioned = "Provisioned"; online = "Online"; transmitting = "Transmitting"
    offline = "Offline"; quarantined = "Quarantined"; decommissioned = "Decommissioned"

class FirmwareState(str, Enum):
    draft = "Draft"; signed = "Signed"; staged = "Staged"
    rolling = "Rolling"; deployed = "Deployed"; rolled_back = "Rolled back"

class StatusToken(str, Enum):   # the StatusDot/Badge vocabulary
    pass_ = "pass"; warn = "warn"; fail = "fail"; info = "info"; neutral = "neutral"
```

---

## Manufacturing context

```
suppliers          (id, name, material, sourcing[single|dual], site_country, lead_time_days, status)
materials          (id, name, kind[DS|excipient|component], supplier_id fk)
sites              (id, name 'Schaffhausen', cleanroom 'CR4', gmp_status)
lines              (id, site_id fk, name 'Line B', stage 'Filling', uptime_pct, status)
products           (id, code 'TRM', name 'Guselkumab', modality)
batches            (id, code 'TRM-2291', product_id fk, line_id fk, stage,
                    status BatchStatus, yield_pct, started_at, released_at, released_by fk)
batch_steps        (id, batch_id fk, name, sequence, signed_by fk, signed_at, record_url)
ipc_checks         (id, batch_id fk, kind 'weight', value, spec_low, spec_high, result StatusToken, at)
tasks              (id, assignee_id fk, title, kind[Clearance|Monitoring|IPC|Sign-off|Calibration],
                    due_at, status StatusToken, batch_id fk null)
equipment          (id, name 'Balance 12', kind, calibration_due, calibration_status)
```

## Quality & Compliance context

```
deviations         (id, code 'DEV-1182', title, severity Severity, line_id fk, batch_id fk null,
                    state QualityState, raised_by fk, raised_at, description)
capas              (id, code 'CAPA-0441', deviation_id fk, owner_id fk, due_at,
                    effectiveness_state, on_time_pct, status StatusToken)
compliance_items   (id, framework[GMP|GLP|GxP], area 'CR4', title, state StatusToken, evidence_url)
audit_findings     (id, audit_id fk, framework, severity Severity, status, remediation_due)
audits             (id, scope, framework, readiness_pct, scheduled_at, lead_id fk)
```

## Device Fleet context (NeuroSecure secure-MCU devices)

```
devices            (id, serial, model 'NeuroSecure', site_id fk, line_id fk null,
                    hw_identity_pubkey, state DeviceState, last_seen_at, firmware_id fk,
                    tamper_locked bool)
firmware_builds    (id, version 'v4.2.1', digest 'sha256:…', signed_by fk, signed_at,
                    state FirmwareState, release_notes, artifact_url)
firmware_rollouts  (id, firmware_id fk, cohort, devices_total, devices_done,
                    state FirmwareState, started_at, started_by fk)
device_attestations(id, device_id fk, firmware_id fk, measured_digest, verdict StatusToken, at)
provision_requests (id, device_serial, requested_by fk, approved_by fk null, status, at)
```
Device identity keys + firmware signing keys live in **Vault PKI**, not Postgres — store only
public keys / digests / references here. See `SECURITY.md`.

## Telemetry context (cold chain, biosignal, cleanroom)

```
sensor_streams     (id, device_id fk, kind[temp|particle|biosignal|humidity], unit, spec_low, spec_high)
readings           (stream_id fk, ts, value)            -- high-volume, partition by time
coldchain_lanes    (id, code 'SG→EU', origin, destination, spec_low 2, spec_high 8, status StatusToken)
shipments          (id, lane_id fk, batch_id fk, state[in_transit|delivered], departed_at, eta)
excursions         (id, lane_id fk, shipment_id fk, kind 'cold-chain', started_at, ended_at,
                    peak_value, severity Severity, disposition)
```
`readings` is the one table that wants time-series treatment (Timescale hypertable or
partitioning); everything else is ordinary relational.

## Intelligence context → **Neo4j**

Postgres entities above project into a graph. Node labels mirror the table; relationships are
the supply/manufacturing/compliance flow seen in `OperatorIntelMap`:

```
(:Supplier)-[:SUPPLIES]->(:Site)
(:Site)-[:RUNS]->(:Line)-[:PRODUCES]->(:Batch)
(:Batch)-[:TESTED_BY]->(:QCTest)
(:Batch)-[:STORED_IN]->(:ColdStore)-[:DISTRIBUTED_VIA]->(:Lane)-[:RELEASED_TO]->(:Market)
(:Batch)-[:HAS_DEVIATION]->(:Deviation)
(:Device)-[:MONITORS]->(:Line|:ColdStore)
(:Excursion)-[:AFFECTS]->(:Shipment)-[:CARRIES]->(:Batch)
```
Each node carries `{ id, label, category[supply|mfg|quality|compliance], status }`. Drive the
graph views and **chain-of-custody / blast-radius** queries from Cypher traversals. Keep nodes
thin; resolve full records from Postgres by `id`.

## Research & Evidence context

```
hypotheses         (id, title, posed_by fk, state[open|under_review|supported|refuted], domain)
evidence_packets   (id, hypothesis_id fk null, title, dataset_ref, method[frequentist|bayesian],
                    summary, generated_by, reviewed_by fk null, state)
evidence_results   (id, packet_id fk, statistic, value, ci_low, ci_high, p_value, posterior_ref)
validation_reports (id, code, scope, author_id fk, state[draft|in_review|approved],
                    signed_by fk null, signed_at)
datasets           (id, name, source, rows, schema_ref, lineage_ref)
```
Computation (pandas/numpy/scipy/PyMC) runs in Celery and writes results here — see
`AGENTS_AND_COMPUTE.md`. The **secure validation enclave** means evidence runs execute in an
isolated worker with no outbound network and Vault-scoped data access.

## Optimization, Economy, Decisions, Reviews

```
schedules          (id, line_id fk, horizon, objective, generated_by, state, solver_status)
schedule_slots     (id, schedule_id fk, batch_id fk, start_at, end_at, setup_minutes)
scenarios          (id, name, base_schedule_id fk, params jsonb, kpi_delta jsonb, created_by fk)
econ_indicators    (id, name, region, value, delta, as_of)          -- macro/finance layer
decisions          (id, title, context, options jsonb, recommended_idx,
                    decided_by fk null, decided_at null, rationale, state[open|decided])
reviews            (id, cadence[weekly|monthly|quarterly], scope, scheduled_at, chair_id fk, state)
review_items       (id, review_id fk, title, kind[decision|risk|metric], ref_id, disposition)
```
Decisions and reviews are where **AI assists, humans decide** is enforced: `recommended_idx`
can be agent-generated, but `decided_by` / `decided_at` must be a human + audited.

## Identity & Audit kernel

```
users              (id, keycloak_sub, email, display_name, roles[], site_id fk, active)
audit_events        (id, ts, actor_id fk, action, object_type, object_id, before jsonb,
                    after jsonb, prev_hash, hash)     -- append-only, hash-chained
agent_runs         (id, agent, graph_node, input_ref, output_ref, model 'ollama:…',
                    started_at, ended_at, status, proposed_action, human_disposition)
```
`audit_events.hash = sha256(prev_hash + canonical(event))` → tamper-evident chain. Never
UPDATE or DELETE this table. Audit-pack generation (a Celery job) exports a signed bundle.
