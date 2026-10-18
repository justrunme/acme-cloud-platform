"""Validate Chapter 12-14 policies against JSON Schema and evaluate admission fixtures.

This is policy evaluation over fixtures. It does not schedule pods, call an inference
gateway, or measure latency.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import jsonschema

from tools import budget, gpu
from tools.common import ROOT, load_doc, load_json, sha256_file

SCHEMAS = {
    "policies/inference-budget.yaml": "policies/schema/inference-budget.schema.json",
    "policies/gpu-admission.yaml": "policies/schema/gpu-admission.schema.json",
    "agents/contracts/demo-agent.policy.yaml": "policies/schema/agent-security-contract.schema.json",
}


def schema_checks(root: Path) -> list[dict]:
    out = []
    for doc_rel, schema_rel in SCHEMAS.items():
        doc = load_doc(root / doc_rel)
        errs = [e.message for e in jsonschema.Draft202012Validator(load_json(root / schema_rel)).iter_errors(doc)]
        if doc_rel.startswith("agents/"):
            pinned = doc["spec"]["catalog"]["sha256"]
            actual = sha256_file(root / doc["spec"]["catalog"]["ref"])
            if pinned != actual:
                errs.append(f"catalog pin {pinned} != approved catalog {actual}")
        out.append({"policy": doc_rel, "ok": not errs, "errors": errs, "sha256": sha256_file(root / doc_rel)})
    return out


def _price_rehearsal(policy: dict, fx: dict) -> dict:
    def blocks(pol):
        teams = []
        for t in fx["traffic"]:
            snap = {"status": "available", "usedTokens": 0, "usedUsd": 0.0, "ageSeconds": 0}
            if budget.decide(pol, t["team"], t["model"], t["tokens"], snap)["verdict"] != "ALLOW":
                teams.append(t["team"])
        return teams
    proposed = copy.deepcopy(policy)
    proposed["spec"]["models"][fx["change"]["model"]]["costPerMillionTokensUsd"] = fx["change"]["costPerMillionTokensUsd"]
    cur, new = blocks(policy), blocks(proposed)
    actual = {"current": {"block": len(cur)}, "proposed": {"block": len(new), "blockedTeams": sorted(new)}}
    return {"actual": actual, "pass": actual == fx["expected"]}


def fixture_checks(root: Path) -> list[dict]:
    bpol = load_doc(root / "policies/inference-budget.yaml")
    gpol = load_doc(root / "policies/gpu-admission.yaml")
    out = []
    for f in sorted((root / "policies/fixtures/budget").glob("*.yaml")):
        fx = load_doc(f)
        if fx.get("kind") == "price-rehearsal":
            r = _price_rehearsal(bpol, fx)
            out.append({"id": fx["id"], "area": "inference-budget", "chapter": fx["chapter"], "expected": fx["expected"],
                        "actual": r["actual"], "pass": r["pass"]})
            continue
        q = fx["request"]
        d = budget.decide(bpol, q["team"], q["model"], q["tokens"], fx.get("snapshot"))
        out.append({"id": fx["id"], "area": "inference-budget", "chapter": fx["chapter"], "expected": fx["expected"],
                    "actual": d["verdict"], "reason_code": d["reason_code"], "pass": d["verdict"] == fx["expected"]})
    for f in sorted((root / "policies/fixtures/gpu").glob("*.yaml")):
        fx = load_doc(f)
        if fx.get("kind") == "autoscaler-check":
            conflicts = gpu.autoscaler_conflicts(fx["manifests"])
            verdict = gpol["spec"]["admission"]["whenAutoscalerConflict"] if conflicts else "ALLOW"
            reason = "autoscaler_conflict" if conflicts else "single_autoscaler"
        else:
            d = gpu.decide(gpol, fx["request"], fx.get("snapshot"), fx.get("policyEngine", "up"))
            verdict, reason = d["verdict"], d["reason_code"]
        out.append({"id": fx["id"], "area": "gpu-admission", "chapter": fx["chapter"], "expected": fx["expected"],
                    "actual": verdict, "reason_code": reason, "pass": verdict == fx["expected"]})
    return out


def run(root: Path = ROOT) -> dict:
    schemas = schema_checks(root)
    fixtures = fixture_checks(root)
    return {
        "schemas": schemas,
        "fixtures": fixtures,
        "summary": {
            "policies_valid": sum(s["ok"] for s in schemas),
            "policies_total": len(schemas),
            "budget_fixtures": sum(f["area"] == "inference-budget" for f in fixtures),
            "gpu_fixtures": sum(f["area"] == "gpu-admission" for f in fixtures),
            "fixtures_passed": sum(f["pass"] for f in fixtures),
            "fixtures_total": len(fixtures),
            "passed": all(s["ok"] for s in schemas) and all(f["pass"] for f in fixtures),
        },
    }


def main() -> int:
    r = run()
    for s in r["schemas"]:
        print(("OK   " if s["ok"] else "FAIL ") + f"schema {s['policy']}")
        for e in s["errors"]:
            print(f"  - {e}")
    for f in r["fixtures"]:
        print(("PASS " if f["pass"] else "FAIL ") + f"{f['id']:<40} expected={f['expected']} actual={f['actual']}")
    s = r["summary"]
    print(f"{s['policies_valid']}/{s['policies_total']} policies valid; {s['fixtures_passed']}/{s['fixtures_total']} fixtures match")
    return 0 if s["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
