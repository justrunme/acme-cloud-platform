# Kind + Argo CD e2e

This directory runs the Acme admission gate where the book says it belongs: as an Argo CD **PreSync
hook**, in front of every sync, on a real Kubernetes cluster. It is small on purpose. Each change is a
ConfigMap called `applied-change`; if that object exists after a sync, the change was applied.

```bash
./cluster/e2e.sh                 # kind + Argo CD + evidence store + all scenarios
KEEP_CLUSTER=1 ./cluster/e2e.sh  # keep the cluster afterwards for inspection
```

Needs Docker, `kind`, `kubectl`, Python with `requirements.txt`, and network access to GitHub: Argo CD
pulls the manifests from `REPO_URL` at `REVISION` (default: `HEAD`, which must be pushed). CI runs the
same script in the `kind-e2e` job and uploads `results/cluster/kind-e2e.json`.

The committed `results/cluster/kind-e2e.json` is the artifact of CI run
[39139548905](https://github.com/justrunme/acme-cloud-platform/actions/runs/39139548905) on `main` at
`98478c6`; `docs/EVIDENCE.md` renders it. Later runs upload their own artifact and do not overwrite it.

## Pieces

| Path | Role |
| --- | --- |
| `Dockerfile` | One image with this repository and its pinned dependencies, used by the gate and the store |
| `platform/evidence-store.yaml` | `evidence-store` in `acme-evidence`: serves packages, retains decision records on a PVC |
| `gate/base/presync-gate.yaml` | The PreSync hook Job running `tools/presync_gate.py` |
| `gate/base/change.yaml` | The stand-in for the change under review |
| `changes/<id>/` | Kustomize overlays that point the gate at one change |
| `fixtures/CHG-0042-edited-to-allow.json` | CHG-0042 with its verdict edited to ALLOW after sealing |
| `scenarios.yaml` | Scenarios, the store state during each sync, and the expected outcome |

## What the gate does

1. Fetches the package from the store. Unreachable store: **BLOCK** (`evidence_store_unavailable`).
2. Validates it with the same code as `make validate`: schema, every digest recomputed from the files
   in the image, fail-closed rules. Any error: **BLOCK** (`evidence_invalid`).
3. Reads the recorded verdict. Only ALLOW exits 0; REQUIRE_APPROVAL is a hold, not a pass.
4. Writes a decision record to the store. An ALLOW whose record cannot be retained becomes **BLOCK**.

A failed PreSync hook fails the sync operation, and Argo CD applies nothing from the Sync phase. The
manual-sync scenario sends the same sync operation the Argo CD UI and CLI send, so the path engineers
use by hand meets the same hook.

## What this does not show

- One node, no real workload, no real database. The ConfigMap stands in for the StatefulSet change.
- The store has no authentication, replication or retention policy.
- Anyone with permission to edit the Application or delete the hook can still bypass it. Closing that
  needs RBAC and an admission controller, which this e2e does not configure.
- Timings come from one run on one runner and are not benchmarks.
