#!/usr/bin/env bash
# Run the Acme admission gate on a real kind cluster with Argo CD (cluster/README.md).
#   1. create a kind cluster            4. start the evidence store
#   2. build and load the gate image    5. sync every scenario in cluster/scenarios.yaml
#   3. install Argo CD                  6. write results/cluster/kind-e2e.json
# Argo CD pulls the manifests from REPO_URL at REVISION, so REVISION must be pushed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CLUSTER="${CLUSTER:-acme-e2e}"
KIND_NODE_IMAGE="${KIND_NODE_IMAGE:-kindest/node:v1.31.0}"
ARGOCD_VERSION="${ARGOCD_VERSION:-v2.13.3}"
REPO_URL="${REPO_URL:-https://github.com/justrunme/acme-cloud-platform.git}"
REVISION="${REVISION:-$(git rev-parse HEAD)}"
PYTHON="${PYTHON:-python3}"
KEEP_CLUSTER="${KEEP_CLUSTER:-0}"

log() { printf '==> %s\n' "$*"; }

if ! kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
  log "kind cluster $CLUSTER ($KIND_NODE_IMAGE)"
  kind create cluster --name "$CLUSTER" --image "$KIND_NODE_IMAGE" --config cluster/kind-config.yaml --wait 120s
fi
kubectl config use-context "kind-$CLUSTER" >/dev/null
[[ "$KEEP_CLUSTER" == 1 ]] || trap 'kind delete cluster --name "$CLUSTER" >/dev/null 2>&1 || true' EXIT

log "gate image acme-gate:e2e"
docker build -q -t acme-gate:e2e -f cluster/Dockerfile . >/dev/null
kind load docker-image acme-gate:e2e --name "$CLUSTER"

log "Argo CD $ARGOCD_VERSION"
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f - >/dev/null
kubectl apply -n argocd --server-side --force-conflicts \
  -f "https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/install.yaml" >/dev/null
kubectl -n argocd rollout status statefulset/argocd-application-controller --timeout=300s
for d in argocd-repo-server argocd-server argocd-redis; do
  kubectl -n argocd rollout status "deployment/$d" --timeout=300s
done

log "evidence store"
kubectl apply -f cluster/platform/evidence-store.yaml >/dev/null
kubectl -n acme-evidence rollout status deployment/evidence-store --timeout=120s

log "scenarios at $REVISION"
"$PYTHON" -m tools.kind_e2e --repo "$REPO_URL" --revision "$REVISION"
