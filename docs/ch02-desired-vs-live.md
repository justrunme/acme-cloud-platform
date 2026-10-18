# Chapter 2 companion — Desired vs live

Acme often has three stories about the same system:

| Layer | Where it lives | Example lie |
| --- | --- | --- |
| Desired (Git) | `apps/`, `infra/` | Manifest says `postgres:15.8` and `fast-ssd-v1` |
| Rendered / reconciled | GitOps live objects | Synced & Healthy according to the controller |
| Observed | Runtime APIs, PVC status, backups | Actual binding, restore tooling path, hidden owners |

When these diverge, green sync is still possible.

## Exercise

1. Read `infra/postgres/statefulset.yaml` (desired).
2. Read `graphs/payments-postgres.yaml` (reconstructed dependencies).
3. Read `restore/RP-0017/summary.json` (observed recovery assumptions).
4. Open `evidence/CHG-0042.json` and see how the lie becomes a BLOCK.

Further reading: TwinOps three-way drift (desired / rendered / observed) on `justrunme/twinops-control-plane`.
