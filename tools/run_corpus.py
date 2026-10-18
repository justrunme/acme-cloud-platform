"""Run the agent scenario corpus (agents/scenarios/*.yaml) through the gate.

Writes one envelope per scenario to results/envelopes/ and returns machine results.
A scenario passes only when the gate's verdict equals expectedVerdict exactly.
"""
from __future__ import annotations

import sys
from pathlib import Path

from tools import envelope
from tools.asc_gate import evaluate
from tools.common import ROOT, inputs_digest, load_doc, write_json


def run(root: Path = ROOT, write: bool = True) -> dict:
    inputs = inputs_digest(root)
    files = sorted((root / "agents" / "scenarios").glob("*.yaml"))
    if not files:
        raise SystemExit("no scenarios found")
    rows = []
    env_dir = root / "results" / "envelopes"
    if write:
        env_dir.mkdir(parents=True, exist_ok=True)
        for old in env_dir.glob("*.json"):
            old.unlink()
    for f in files:
        sc = load_doc(f)
        sid = sc["metadata"]["name"]
        res = evaluate(sc, root)
        env = envelope.build(sid, res, root, inputs)
        if write:
            write_json(env_dir / f"{sid}.json", env)
        labels = sc["metadata"]["labels"]
        expected = sc["spec"]["expectedVerdict"]
        rows.append({
            "id": sid,
            "category": labels["category"],
            "severity": labels.get("severity"),
            "chapter": labels.get("chapter"),
            "expected": expected,
            "actual": res["verdict"],
            "reason_code": res["reason_code"],
            "pass": res["verdict"] == expected,
            "envelope_sha256": env["envelope_sha256"],
        })
    attack = [r for r in rows if r["category"] == "attack"]
    benign = [r for r in rows if r["category"] == "benign"]
    summary = {
        "scenarios_total": len(rows),
        "attack_scenarios": len(attack),
        "benign_scenarios": len(benign),
        "passed": sum(r["pass"] for r in rows),
        "failed": sum(not r["pass"] for r in rows),
        "attack_false_allow": sum(r["actual"] == "ALLOW" for r in attack),
        "critical_false_allow": sum(r["actual"] == "ALLOW" and r["severity"] == "critical" for r in attack),
        "benign_false_block": sum(r["actual"] != "ALLOW" for r in benign),
        "expected_block": sum(r["expected"] == "BLOCK" for r in rows),
        "expected_require_approval": sum(r["expected"] == "REQUIRE_APPROVAL" for r in rows),
        "expected_allow": sum(r["expected"] == "ALLOW" for r in rows),
    }
    summary["corpus_passed"] = summary["failed"] == 0 and summary["attack_false_allow"] == 0 and summary["benign_false_block"] == 0
    return {"inputs_sha256": inputs, "summary": summary, "scenarios": rows}


def main() -> int:
    out = run()
    for r in out["scenarios"]:
        mark = "PASS" if r["pass"] else "FAIL"
        print(f"{mark} {r['id']:<40} expected={r['expected']:<17} actual={r['actual']:<17} {r['reason_code']}")
    s = out["summary"]
    print(f"{s['passed']}/{s['scenarios_total']} scenarios match "
          f"(attack {s['attack_scenarios']}, benign {s['benign_scenarios']}); "
          f"attack false-ALLOW {s['attack_false_allow']}, benign false-BLOCK {s['benign_false_block']}")
    return 0 if s["corpus_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
