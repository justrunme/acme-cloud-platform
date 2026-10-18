"""Evaluate RestorePoint summaries against the Recovery Contract and compute StorageClass coverage.

Inputs are illustrative files of the fictional Acme estate; this checks the decision logic
(PROVED needs every contract clause covered by a passing assertion and RTO within the limit),
not a real restore.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from tools.common import ROOT, load_doc, load_json


def _ts(v: str) -> datetime:
    return datetime.fromisoformat(v.replace("Z", "+00:00"))


def evaluate_rp(summary: dict, contract: dict) -> dict:
    """PROVED only if every required clause has a passing assertion
    and the RTO is known and within the contract limit."""
    spec = contract["spec"]
    required = [k for k, v in spec["require"].items() if v == "required"]
    asserts = summary["assertions"]
    covered = {c for a in asserts if a.get("result") == "pass"
               for c in a.get("covers", [])}
    failed = [a["id"] for a in asserts if a.get("result") != "pass"]
    missing = [c for c in required if c not in covered]
    rto = summary.get("verdict", {}).get("rtoSeconds")
    rto_max = spec["limits"]["rto_seconds_max"]
    problems = []
    if missing:
        problems.append(f"clauses without passing assertion: {missing}")
    if failed:
        problems.append(f"failed assertions: {failed}")
    if rto is None:
        problems.append("rtoSeconds missing (unknown is not safe)")
    elif rto > rto_max:
        problems.append(f"rtoSeconds {rto} > {rto_max}")
    return {"computed": "UNPROVED" if problems else "PROVED",
            "problems": problems, "rtoSeconds": rto,
            "rtoSecondsMax": rto_max}


def run(root: Path = ROOT) -> dict:
    contract = load_doc(root / "restore/contracts/recovery-contract.yaml")
    rps = []
    for f in sorted((root / "restore").glob("RP-*/summary.json")):
        s = load_json(f)
        row = {"id": s["metadata"]["id"], "storageClass": s["scope"]["storageClass"],
               "recorded": s["verdict"]["decision"], "illustrative": s["metadata"].get("illustrative") is True}
        if s["metadata"].get("contractRef"):
            ev = evaluate_rp(s, contract)
            row.update(ev)
            row["pass"] = row["illustrative"] and ev["computed"] == row["recorded"]
        else:
            row["computed"] = "PASS" if all(a["result"] == "pass" for a in s["assertions"]) else "FAIL"
            row["pass"] = row["illustrative"] and row["computed"] == row["recorded"]
        rps.append(row)
    coverage = []
    for f in sorted((root / "infra/storage").glob("*.yaml")):
        sc = load_doc(f)["metadata"]["name"]
        proving = [r["id"] for r in rps if r["storageClass"] == sc and r["recorded"] in ("PASS", "PROVED")]
        coverage.append({"storageClass": sc, "passingRestorePoints": proving,
                         "dataPlaneChangeVerdict": "ALLOW-eligible" if proving else "BLOCK"})
    chg = load_json(root / "evidence/CHG-0042.json")
    target = next(c for c in coverage if c["storageClass"] == "fast-ssd-v2")
    consistent = target["dataPlaneChangeVerdict"] == "BLOCK" and chg["verdict"]["decision"] == "BLOCK"
    return {"restorePoints": rps, "storageClassCoverage": coverage,
            "chg0042": {"targetStorageClass": "fast-ssd-v2", "computed": target["dataPlaneChangeVerdict"],
                        "recorded": chg["verdict"]["decision"], "pass": consistent},
            "summary": {"passed": all(r["pass"] for r in rps) and consistent}}


def main() -> int:
    r = run()
    for rp in r["restorePoints"]:
        print(("PASS " if rp["pass"] else "FAIL ") + f"{rp['id']} storageClass={rp['storageClass']} recorded={rp['recorded']} computed={rp['computed']}")
    for c in r["storageClassCoverage"]:
        print(f"     coverage {c['storageClass']}: {c['passingRestorePoints'] or 'none'} -> {c['dataPlaneChangeVerdict']}")
    c = r["chg0042"]
    print(("PASS " if c["pass"] else "FAIL ") + f"CHG-0042 target {c['targetStorageClass']}: computed {c['computed']}, package {c['recorded']}")
    return 0 if r["summary"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
