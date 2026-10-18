# Acme Cloud Platform

Companion estate for **Prove It Before Production** (Andrey Lesnikov).

One small Kubernetes platform. Many unpleasant changes. Every meaningful change leaves evidence.

```text
Kubernetes
├── payments
├── orders
├── postgres
├── ingress
├── AI agent
└── inference service
```

## Central question

> What evidence do I have that this change is safe?

## Verifiable Infrastructure Model

```text
Observe → Reconstruct → Simulate → Decide → Prove
```

Operational pipeline:

```text
CHANGE → RECONSTRUCT → REHEARSE → VERDICT → APPLY → VERIFY → EVIDENCE
                              └── BLOCK
```

Principle: **Unknown ≠ Safe** (fail closed).

## Signature example — CHG-0042

Engineer wants to upgrade PostgreSQL for `payments`.

Naive path: `terraform plan` → green → deploy  

Evidence path: change → reconstruct dependencies → rehearse → verdict  

Result: **BLOCK** — StorageClass migration would invalidate the tested recovery path.  
Artifact: [`evidence/CHG-0042.json`](./evidence/CHG-0042.json)

## Layout

| Path | Role |
| --- | --- |
| `apps/` | Workload manifests (payments, orders, inference, agent) |
| `infra/` | Postgres, ingress, storage, cluster baselines |
| `graphs/` | Dependency / blast-radius inputs |
| `rehearsals/` | Pre-apply simulation scenarios |
| `evidence/` | Change evidence packages (`CHG-*.json`) + schema |
| `policies/` | Fail-closed rules |
| `restore/` | RestorePoint drills (Chapter 8) |
| `agents/` | Agent/MCP security contracts (Part IV) |
| `docs/` | Chapter ↔ repo map |
| `scripts/` | Validate evidence packages |

## Quick start

```bash
# Validate all evidence packages against the schema
./scripts/validate-evidence.sh

# Show the Chapter 1 blocked change
cat evidence/CHG-0042.json
```

Requires: `python3` (stdlib only for validation).

## Evidence packages

| ID | Verdict | Chapter theme |
| --- | --- | --- |
| `CHG-0042` | BLOCK | Postgres upgrade invalidates restore path |
| `CHG-0043` | REQUIRE_APPROVAL | Agent unapproved prod deploy |
| `CHG-0044` | ALLOW + PROVED | Restore drill meets Recovery Contract |
| `CHG-0045` | BLOCK | Evidence store down → fail closed |

```bash
./scripts/validate-evidence.sh
```

## Chapter map

| Chapter | Repo entry |
| --- | --- |
| 1 | `docs/ch01-green-is-not-safe.md`, `evidence/CHG-0042.json` |
| 2 | `docs/ch02-desired-vs-live.md`, `graphs/` |
| 3–6 | `graphs/`, `rehearsals/`, `evidence/schema/` |
| 7 | `policies/fail-closed.yaml` |
| 8 | `restore/`, `evidence/CHG-0044.json` |
| 9 | GitOps rollback rehearsals (extend) |
| 10 | `policies/evidence-system-availability.yaml`, `evidence/CHG-0045.json` |
| 11–12 | `agents/`, `evidence/CHG-0043.json` |
| 13–14 | `policies/inference-budget.yaml`, `policies/gpu-admission.yaml` |
| 15 | Full pipeline + vocabulary mapping |

## Status

Companion estate for the full first draft. Manifests + evidence packages are reviewable; Kind e2e can deepen chapter by chapter. Vocabulary aligned with `architecture-rehearsal`, `agent-security-contract`, and Recovery Contract — see `docs/vocabulary-mapping.md`.
