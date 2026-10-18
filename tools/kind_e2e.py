"""Drive the kind + Argo CD e2e scenarios and write results/cluster/kind-e2e.json.

Expects a cluster prepared by cluster/e2e.sh (Argo CD installed, gate image loaded, evidence store
running). Every scenario creates one Argo CD Application from the repository at --revision, waits
for the sync operation to finish, then reads the gate's decision from the hook Job log and checks
whether the change object was applied. Exits non-zero if any scenario differs from its expectation.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

from tools.common import ROOT, load_yaml, write_json
from tools.presync_gate import MARKER

OUT = ROOT / "results" / "cluster" / "kind-e2e.json"
STORE_NS, STORE = "acme-evidence", "evidence-store"


def kubectl(*args: str, check: bool = True, stdin: str | None = None) -> str:
    proc = subprocess.run(["kubectl", *args], input=stdin, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"kubectl {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def application(name: str, path: str, repo: str, revision: str, auto: bool) -> dict:
    spec: dict = {
        "project": "default",
        "source": {"repoURL": repo, "targetRevision": revision, "path": path},
        "destination": {"server": "https://kubernetes.default.svc", "namespace": name},
        "syncPolicy": {"syncOptions": ["CreateNamespace=true"]},
    }
    if auto:
        spec["syncPolicy"]["automated"] = {}
    return {"apiVersion": "argoproj.io/v1alpha1", "kind": "Application",
            "metadata": {"name": name, "namespace": "argocd"}, "spec": spec}


def get_app(name: str) -> dict:
    return json.loads(kubectl("get", "application", name, "-n", "argocd", "-o", "json"))


def set_store(up: bool) -> None:
    kubectl("scale", f"deployment/{STORE}", "-n", STORE_NS, f"--replicas={1 if up else 0}")
    if up:
        kubectl("rollout", "status", f"deployment/{STORE}", "-n", STORE_NS, "--timeout=120s")
    else:
        kubectl("wait", "--for=delete", "pod", "-l", f"app={STORE}", "-n", STORE_NS, "--timeout=120s", check=False)


def wait_operation(name: str, timeout: int) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        op = get_app(name).get("status", {}).get("operationState", {})
        if op.get("phase") in ("Succeeded", "Failed", "Error"):
            return op
        time.sleep(2)
    raise TimeoutError(f"{name}: sync operation did not finish in {timeout}s")


def gate_decision(ns: str) -> dict | None:
    logs = kubectl("logs", "job/acme-presync-gate", "-n", ns, check=False)
    for line in logs.splitlines():
        if line.startswith(MARKER + " "):
            return json.loads(line[len(MARKER) + 1:])
    return None


def run_scenario(sc: dict, repo: str, revision: str, timeout: int) -> dict:
    name = f"e2e-{sc['id']}"
    store_up = sc["store"] == "up"
    if not store_up:
        set_store(False)
    try:
        app = application(name, sc["path"], repo, revision, auto=sc["trigger"] == "auto")
        kubectl("apply", "-f", "-", stdin=json.dumps(app))
        if sc["trigger"] == "manual":
            for _ in range(60):  # wait until Argo CD has compared the source, as a person would
                if get_app(name).get("status", {}).get("sync", {}).get("status") in ("OutOfSync", "Synced"):
                    break
                time.sleep(2)
            op = {"operation": {"initiatedBy": {"username": "e2e-manual-sync"},
                                "sync": {"revision": revision, "syncOptions": ["CreateNamespace=true"]}}}
            kubectl("patch", "application", name, "-n", "argocd", "--type", "merge", "-p", json.dumps(op))
        op = wait_operation(name, timeout)
    finally:
        if not store_up:
            set_store(True)
    gate = gate_decision(name) or {}
    applied = bool(kubectl("get", "configmap", "applied-change", "-n", name, "--ignore-not-found", "-o", "name",
                           check=False).strip())
    exp = sc["expect"]
    row = {
        "id": sc["id"], "path": sc["path"], "store": sc["store"], "trigger": sc["trigger"],
        "expected": exp,
        "gate_decision": gate.get("decision"), "gate_reason": gate.get("reason"),
        "gate_elapsed_ms": gate.get("elapsed_ms"), "gate_errors": gate.get("errors", []),
        "record": gate.get("record"),
        "sync_phase": op.get("phase"), "sync_message": op.get("message"),
        "sync_started": op.get("startedAt"), "sync_finished": op.get("finishedAt"),
        "applied": applied,
    }
    row["ok"] = (row["gate_decision"] == exp["decision"] and row["gate_reason"] == exp["reason"]
                 and applied == exp["applied"]
                 and row["sync_phase"] == ("Succeeded" if exp["applied"] else "Failed"))
    return row


def setup_facts() -> dict:
    ver = json.loads(kubectl("version", "-o", "json"))
    argocd = kubectl("get", "deployment", "argocd-server", "-n", "argocd",
                     "-o", "jsonpath={.spec.template.spec.containers[0].image}")
    kind = subprocess.run(["kind", "version"], capture_output=True, text=True).stdout.strip()
    return {
        "kubernetes": ver.get("serverVersion", {}).get("gitVersion"),
        "kind": kind, "argocd_image": argocd,
        "nodes": len(json.loads(kubectl("get", "nodes", "-o", "json"))["items"]),
        "runner": os.environ.get("ImageOS") or platform.platform(),
        "cpus": os.cpu_count(),
    }


def retained_records() -> list[str]:
    raw = kubectl("get", "--raw", f"/api/v1/namespaces/{STORE_NS}/services/{STORE}:8080/proxy/records", check=False)
    try:
        return json.loads(raw)
    except ValueError:
        return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--revision", required=True)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)

    scenarios = load_yaml(ROOT / "cluster" / "scenarios.yaml")["scenarios"]
    rows = []
    for sc in scenarios:
        row = run_scenario(sc, args.repo, args.revision, args.timeout)
        rows.append(row)
        print(f"{'OK  ' if row['ok'] else 'FAIL'} {row['id']:<26} gate={row['gate_decision']}/{row['gate_reason']} "
              f"sync={row['sync_phase']} applied={row['applied']} gate_ms={row['gate_elapsed_ms']}", flush=True)
    records = retained_records()
    passed = sum(r["ok"] for r in rows)
    result = {
        "schema_version": "acme.cluster-e2e/v1",
        "illustrative_estate": True,
        "note": "Results of running cluster/e2e.sh on the setup below. They hold on this setup only: one kind "
                "node, a stand-in ConfigMap as the change, and an in-memory evidence store.",
        "revision": args.revision,
        "repo": args.repo,
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_url": (f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/"
                    f"{os.environ['GITHUB_RUN_ID']}") if os.environ.get("GITHUB_RUN_ID") else None,
        "setup": setup_facts(),
        "scenarios": rows,
        "retained_records": records,
        "summary": {
            "scenarios": len(rows), "passed": passed,
            "blocked_or_held": sum(r["gate_decision"] in ("BLOCK", "REQUIRE_APPROVAL") for r in rows),
            "applied_without_allow": sum(r["applied"] and r["gate_decision"] != "ALLOW" for r in rows),
            "allowed_and_applied": sum(r["applied"] and r["gate_decision"] == "ALLOW" for r in rows),
            "records_retained": len(records),
            "gate_elapsed_ms_max": max((r["gate_elapsed_ms"] or 0) for r in rows),
            "all_passed": passed == len(rows),
        },
    }
    write_json(args.out, result)
    print(f"{passed}/{len(rows)} scenarios as expected; wrote {args.out}")
    return 0 if result["summary"]["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
