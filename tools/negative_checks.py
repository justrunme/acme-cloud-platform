"""Negative checks: each mutation of a scratch copy of the repository MUST be rejected.

A check passes only when the validator, envelope verifier, or gate refuses the mutated input.
Results feed results/results.json; tests/test_negative.py runs the same checks under pytest.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

from tools import envelope as envmod
from tools.asc_gate import evaluate
from tools.common import ROOT, load_doc, load_json, write_json
from tools.evidence import SCHEMA_REL, seal, validate_package

COPY_DIRS = ("agents", "apps", "evidence", "graphs", "infra", "policies", "rehearsals", "restore", "tools", "scripts")


def scratch_copy() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="acme-neg-"))
    for d in COPY_DIRS:
        shutil.copytree(ROOT / d, tmp / d, ignore=shutil.ignore_patterns("__pycache__"))
    return tmp


def _pkg_errors(root: Path, pkg_id: str) -> list[str]:
    return validate_package(root / f"evidence/{pkg_id}.json", root, load_json(root / SCHEMA_REL))


def _edit_pkg(root: Path, pkg_id: str, fn: Callable[[dict], None], reseal: bool = False) -> None:
    p = root / f"evidence/{pkg_id}.json"
    d = load_json(p)
    fn(d)
    if reseal:
        d = seal(d, root)
    write_json(p, d)


# Each check mutates `root` and returns the rejection messages (empty list == NOT rejected == failure).
def tampered_artifact(root: Path) -> list[str]:
    with open(root / "graphs/payments-postgres.yaml", "a", encoding="utf-8") as f:
        f.write("# silent edit\n")
    return _pkg_errors(root, "CHG-0042")


def tampered_package_field(root: Path) -> list[str]:
    _edit_pkg(root, "CHG-0042", lambda d: d["verdict"].__setitem__("reason", "Looks fine."))
    return _pkg_errors(root, "CHG-0042")


def missing_required_field(root: Path) -> list[str]:
    _edit_pkg(root, "CHG-0042", lambda d: d["verdict"].pop("policySha256"))
    return _pkg_errors(root, "CHG-0042")


def malformed_digest(root: Path) -> list[str]:
    _edit_pkg(root, "CHG-0044", lambda d: d["evidence"]["artifacts"][0].__setitem__("sha256", "sha256:demo-not-real"))
    return _pkg_errors(root, "CHG-0044")


def missing_artifact_file(root: Path) -> list[str]:
    (root / "restore/RP-0017/summary.json").unlink()
    return _pkg_errors(root, "CHG-0042")


def artifact_path_escapes_repo(root: Path) -> list[str]:
    _edit_pkg(root, "CHG-0045", lambda d: d["evidence"]["artifacts"][0].__setitem__("path", "../../etc/passwd"))
    return _pkg_errors(root, "CHG-0045")


def inconclusive_marked_allow(root: Path) -> list[str]:
    def f(d):
        d["verdict"]["decision"] = "ALLOW"
        d["verdict"].pop("rehearsalDecision", None)
    _edit_pkg(root, "CHG-0045", f, reseal=True)  # digests valid; only the fail-closed rule can catch it
    return _pkg_errors(root, "CHG-0045")


def agent_package_contradicts_gate(root: Path) -> list[str]:
    def f(d):
        d["verdict"]["decision"] = "BLOCK"
        d["verdict"]["acsDisposition"] = "DENY"
    _edit_pkg(root, "CHG-0043", f, reseal=True)
    return _pkg_errors(root, "CHG-0043")


def jsonschema_unavailable(root: Path) -> list[str]:
    env = dict(os.environ, ACME_SIMULATE_MISSING_JSONSCHEMA="1")
    p = subprocess.run([sys.executable, "-m", "tools.evidence", "validate", "--root", str(root)],
                       cwd=root, env=env, capture_output=True, text=True)
    return [f"exit {p.returncode}: {p.stderr.strip()}"] if p.returncode != 0 else []


def tampered_envelope(root: Path) -> list[str]:
    env = _fresh_envelope(root, "unapproved_prod_deploy")
    env["verdict"] = "ALLOW"
    env["acs_disposition"] = "ALLOW"
    return envmod.verify(env, root)


def envelope_disposition_inconsistent(root: Path) -> list[str]:
    from tools.common import sha256_obj
    env = _fresh_envelope(root, "unapproved_prod_deploy")
    env["acs_disposition"] = "ALLOW"
    env["envelope_sha256"] = sha256_obj({k: v for k, v in env.items() if k != "envelope_sha256"})
    return envmod.verify(env, root)


def envelope_missing_field(root: Path) -> list[str]:
    env = _fresh_envelope(root, "read_workspace_file")
    env.pop("policy_sha256")
    return envmod.verify(env, root)


def catalog_pin_drift_fails_closed(root: Path) -> list[str]:
    p = root / "agents/catalog/tools.json"
    cat = load_json(p)
    cat["tools"][0]["description"] += " "
    write_json(p, cat)
    res = evaluate(load_doc(root / "agents/scenarios/read_workspace_file.yaml"), root)
    return [f"{res['verdict']} {res['reason_code']}"] if res["verdict"] == "BLOCK" else []


def corrupt_policy_fails_closed(root: Path) -> list[str]:
    (root / "agents/contracts/demo-agent.policy.yaml").write_text("spec: [unclosed\n", encoding="utf-8")
    res = evaluate(load_doc(root / "agents/scenarios/inventory_read.yaml"), root)
    return [f"{res['verdict']} {res['reason_code']}"] if res["verdict"] == "BLOCK" else []


def _fresh_envelope(root: Path, sid: str) -> dict:
    res = evaluate(load_doc(root / f"agents/scenarios/{sid}.yaml"), root)
    return envmod.build(sid, res, root, "sha256:" + "0" * 64)


CHECKS: list[tuple[str, str, Callable[[Path], list[str]]]] = [
    ("tampered_artifact", "An artifact file changes after sealing; its recorded sha256 must no longer verify", tampered_artifact),
    ("tampered_package_field", "A package field is edited without resealing; envelopeSha256 must fail", tampered_package_field),
    ("missing_required_field", "verdict.policySha256 removed; schema must reject", missing_required_field),
    ("malformed_digest", "A placeholder digest (sha256:demo-...) must fail the schema", malformed_digest),
    ("missing_artifact_file", "A referenced artifact is deleted; validation must fail", missing_artifact_file),
    ("artifact_path_escapes_repo", "Artifact path ../../etc/passwd must be refused", artifact_path_escapes_repo),
    ("inconclusive_marked_allow", "Correctly sealed package with inconclusive rehearsal but ALLOW must fail the fail-closed rule", inconclusive_marked_allow),
    ("agent_package_contradicts_gate", "Agent package whose verdict differs from the gate re-run must fail", agent_package_contradicts_gate),
    ("jsonschema_unavailable", "Without jsonschema the validator must exit non-zero, not degrade to OK", jsonschema_unavailable),
    ("tampered_envelope", "Envelope verdict edited from REQUIRE_APPROVAL to ALLOW; verify must fail", tampered_envelope),
    ("envelope_disposition_inconsistent", "Resealed envelope with ACS disposition inconsistent with verdict must fail", envelope_disposition_inconsistent),
    ("envelope_missing_field", "Envelope without policy_sha256 must fail verify", envelope_missing_field),
    ("catalog_pin_drift_fails_closed", "One byte of catalog drift turns a benign call into BLOCK", catalog_pin_drift_fails_closed),
    ("corrupt_policy_fails_closed", "Unparseable policy makes the gate BLOCK, not ALLOW", corrupt_policy_fails_closed),
]


def run_one(name: str) -> dict:
    _, desc, fn = next(c for c in CHECKS if c[0] == name)
    root = scratch_copy()
    try:
        msgs = fn(root)
    except Exception as exc:  # an exception is not a rejection; it is a broken check
        msgs = []
        desc = f"{desc} (check raised {type(exc).__name__}: {exc})"
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return {"id": name, "description": desc, "expected": "rejected", "observed": "rejected" if msgs else "accepted",
            "pass": bool(msgs), "first_message": msgs[0] if msgs else None}


def run() -> dict:
    rows = [run_one(n) for n, _, _ in CHECKS]
    return {"checks": rows, "summary": {"total": len(rows), "passed": sum(r["pass"] for r in rows),
                                        "all_rejected": all(r["pass"] for r in rows)}}


def main() -> int:
    r = run()
    for c in r["checks"]:
        print(("PASS " if c["pass"] else "FAIL ") + f"{c['id']:<36} {c['first_message']}")
    print(f"{r['summary']['passed']}/{r['summary']['total']} negative checks rejected as expected")
    return 0 if r["summary"]["all_rejected"] else 1


if __name__ == "__main__":
    sys.exit(main())
