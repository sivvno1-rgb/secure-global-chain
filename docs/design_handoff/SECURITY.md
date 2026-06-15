# Security — Secure Global Chain

Zero-trust posture: **Keycloak** issues identity, **Vault** holds every secret and the device
PKI, **JWT** carries claims to the API, and an append-only **audit trail** records every
consequential action. The platform's promise — *AI assists, humans decide* — is enforced
here, not just in UI copy.

---

## 1. Identity — Keycloak (OIDC)

- Keycloak is the **OIDC issuer**. The frontend does the auth-code+PKCE flow; the API
  validates the resulting **JWT** access token.
- FastAPI validates tokens against Keycloak's **JWKS** (cache keys, honor `kid` rotation).
  Verify `iss`, `aud`, `exp`, signature. Reject anything else.
- Mirror users into Postgres `users` (`keycloak_sub` ↔ `id`) for FK integrity on
  `created_by` / `signed_by` / `decided_by`, but Keycloak remains the source of truth for
  credentials and roles.

### RBAC roles (realm roles → enforced per route)

| Role | Can |
|---|---|
| `operator` | View/act on own lines: tasks, IPC, raise deviations |
| `quality` | Deviations, CAPA, audits, audit packs |
| `qa_release` | **Sign** batch release, sign validation reports (e-signature) |
| `fleet_admin` | Provision/quarantine devices, **sign** firmware, start rollouts |
| `scientist` | Hypotheses, evidence runs, validation report authoring |
| `planner` | Run optimization / scenarios |
| `executive` | Decisions, reviews, executive read-models |
| `auditor` | Read-everything + audit packs; no mutations |
| `admin` | User/role/config management |

Enforce with a FastAPI dependency (`require_role("qa_release")`). Consequential routes
(release, sign, provision, decide, escalate) require the specific role **and** a human actor —
no service token may invoke them. Agents run under a constrained service identity that holds
**no** consequential roles.

---

## 2. Secrets & PKI — Vault

Nothing sensitive in env files or the repo. Vault provides:

- **Dynamic DB credentials** for Postgres and Neo4j (short TTL, rotated).
- **Device PKI** (Vault PKI secrets engine): issues/holds device identity certs and the
  **firmware signing key**. Postgres stores only public keys, digests, and references.
- **JWT validation material** (or validate against Keycloak JWKS directly).
- **Ollama / model + external feed endpoints and keys.**
- FastAPI and Celery workers authenticate to Vault via **AppRole** at boot and fetch leases;
  the enclave (`evidence`) worker gets a tightly scoped policy (dataset paths only).

---

## 3. Device identity & signed firmware

The NeuroSecure device story is a security feature, not a metadata field:

- Each device has a **hardware identity** keypair; telemetry and attestations are **signed**.
  The ingestion worker verifies signatures and **quarantines** devices that fail.
- **Firmware is signed in Vault.** `POST /firmware/{version}/sign` is human-gated (`fleet_admin`),
  produces a `sha256:` digest + signature, and is audited. Devices verify the signature before
  applying; `device_attestations` records measured-vs-expected digest.
- Rollouts are staged and reversible (`firmware_rollouts.state` includes `rolled_back`).

---

## 4. JWT contract

```
Authorization: Bearer <access_token>
claims: sub (→ users.keycloak_sub), realm_access.roles[], email, name, exp, iss, aud
```
- Short-lived access tokens; refresh via Keycloak. API is **stateless** — no server sessions.
- 401 = missing/invalid token; 403 = authenticated but lacks role. Never leak which.
- Optional step-up auth (re-authentication) before the most consequential actions
  (batch release, firmware sign) — Keycloak ACR / `max_age`.

---

## 5. Audit trail (append-only, hash-chained)

- Every mutating action writes one `audit_events` row **in the same transaction** as the
  change (outbox/transactional). Capture `actor_id, action, object_type, object_id,
  before, after`.
- **Hash chain:** `hash = sha256(prev_hash + canonical_json(event))`. Tamper-evident; never
  UPDATE/DELETE. Periodically anchor the latest hash (sign with a Vault key) for non-repudiation.
- **Audit packs:** a Celery `audit` task exports a scoped, signed bundle (records + evidence +
  chain segment) for inspectors — surfaced by `POST /audit-packs`.
- E-signatures (release, firmware sign, report sign, decisions) are first-class audit events
  with the signer identity and, where required, a reason/meaning string (21 CFR Part 11 style).

---

## 6. Transport & hardening (baseline)

- TLS everywhere; HSTS at the edge. Internal services on a private Docker network.
- Rate limiting + `Idempotency-Key` (Redis) on mutating routes.
- Strict CORS allow-list for the frontend origin only.
- Input validation via Pydantic at the boundary; parameterized queries / the ORM only.
- Secrets rotation via Vault leases; no long-lived static credentials.
- PII / regulated data: encrypt at rest (DB + object store), least-privilege Vault policies.
