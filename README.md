# Acme Cloud Platform

Companion repository for the book **Prove It Before Production — Evidence-Driven Infrastructure
Engineering for Kubernetes and AI** by Andrey Lesnikov.

> **Acme is fictional.** Acme Cloud Platform is an invented estate used to make evidence, rehearsal and
> admission concrete. It is not a product and does not describe any real company's systems. Actors,
> timestamps, RTO values, logs, budgets, GPU quotas and commit identifiers in this repository are
> **illustrative**, and the files that carry them say so (`illustrative: true` or an `ILLUSTRATIVE`
> header). What *is* real: the sha256 digests, the validators, the agent gate, and the results they
> produce when you run them here.

## Central question

> What evidence do I have that this change is safe?

```text
CHANGE → RECONSTRUCT → REHEARSE → VERDICT → APPLY → VERIFY → EVIDENCE
                              └── BLOCK
```

Principle: **unknown is not safe** (fail closed).

## Quick start

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

make validate   # evidence packages: JSON Schema + every sha256 recomputed + fail-closed rules
make corpus     # agent security corpus through the gate (Chapter 12)
make policies   # inference budget and GPU admission policies against fixtures (Chapters 13-14)
make restore    # Recovery Contract decisions over RestorePoint files (Chapter 8)
make negative   # tampering and missing-field mutations that must be rejected
make test       # pytest
make results    # regenerate results/results.json and docs/EVIDENCE.md
make ci         # everything CI runs, including a drift check on generated files
```

Requires Python 3.10+ with the pinned packages in `requirements.txt`. `make validate` exits non-zero if
`jsonschema` is missing rather than degrading to a partial check.

Current numbers live only in [`docs/EVIDENCE.md`](docs/EVIDENCE.md), generated from
[`results/results.json`](results/results.json) by `make results`. CI regenerates both on every push and
pull request and fails if the committed copies differ. Results are bound to their inputs by
`inputs_sha256` (a digest over every input file); CI also uploads `results/run-metadata.json` with the
commit SHA and run id as a build artifact.

## What is executable and what is not

| Area | Executable here | Illustrative only |
| --- | --- | --- |
| Evidence packages (`evidence/`) | Schema, digest recomputation, fail-closed cross-field rules, gate re-run for agent packages | Actors, timestamps, `commitSha`, the change stories |
| Agent contracts (`agents/`) | Gate over every scenario, envelopes with real digests, approval binding to request digests, timeout → BLOCK | Traces are recorded fixtures, not a live MCP server |
| Inference budget (`policies/inference-budget.yaml`) | Schema and admission decisions on fixtures, including a unit-price rehearsal | Budgets, prices and traffic |
| GPU admission (`policies/gpu-admission.yaml`) | Schema and admission decisions on fixtures, autoscaler conflict detection | Pool size, class, quotas; no scheduling, no latency measurement |
| Restore (`restore/`) | PROVED/UNPROVED logic against the Recovery Contract, StorageClass coverage that explains CHG-0042's BLOCK | Logs, RTO values, row counts |
| Manifests (`apps/`, `infra/`) | Reviewed as text | No cluster runs in this repository |

## Evidence packages

| ID | Verdict | Chapter theme |
| --- | --- | --- |
| `CHG-0042` | BLOCK | PostgreSQL upgrade invalidates the tested restore path |
| `CHG-0043` | REQUIRE_APPROVAL | Agent attempts an unapproved production deploy |
| `CHG-0044` | ALLOW + PROVED | Restore drill meets the Recovery Contract |
| `CHG-0045` | BLOCK | Evidence store down → fail closed |

See [`evidence/README.md`](evidence/README.md) for what each digest covers.

## Layout

| Path | Role |
| --- | --- |
| `apps/` | Workload manifests (payments, orders, inference, agent) |
| `infra/` | PostgreSQL, ingress, storage |
| `graphs/` | Dependency / blast-radius inputs |
| `rehearsals/` | Pre-apply simulation scenarios |
| `evidence/` | Evidence packages (`CHG-*.json`) and schema |
| `policies/` | Fail-closed, evidence-plane, inference-budget and GPU-admission policies; schemas and fixtures |
| `restore/` | Recovery Contract and RestorePoints |
| `agents/` | Agent Security Contract, catalog, approvals, scenario corpus |
| `tools/` | Validators, gate, corpus runner, result generator |
| `scripts/` | `validate-evidence.sh` |
| `results/` | Generated `results.json` and retained envelopes |
| `docs/` | Generated `EVIDENCE.md`, chapter notes, vocabulary mapping |

## Chapter map

| Chapter | Entry points |
| --- | --- |
| 1 | `docs/ch01-green-is-not-safe.md`, `evidence/CHG-0042.json` |
| 2 | `docs/ch02-desired-vs-live.md`, `graphs/` |
| 3–6 | `graphs/`, `rehearsals/`, `evidence/schema/` |
| 7 | `policies/fail-closed.yaml` |
| 8 | `restore/`, `evidence/CHG-0044.json`, `make restore` |
| 9 | Rollback is discussed in the book; this repository has no rollback drill |
| 10 | `policies/evidence-system-availability.yaml`, `evidence/CHG-0045.json` |
| 11–12 | `agents/`, `evidence/CHG-0043.json`, `make corpus` |
| 13–14 | `policies/inference-budget.yaml`, `policies/gpu-admission.yaml`, `make policies` |
| 15–21 | Full pipeline, `make ci`, `docs/vocabulary-mapping.md` |

Related public reference implementations by the author: `architecture-rehearsal`,
`agent-security-contract`, `kanister-backup-restore`, `blastguard` (github.com/justrunme). Vocabulary
mapping: [`docs/vocabulary-mapping.md`](docs/vocabulary-mapping.md).

## License

Code and teaching files in this repository: [Apache License 2.0](LICENSE). The book text is not part of
this repository and is not covered by this license.
