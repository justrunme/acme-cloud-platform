"""Replayable case specimens modeled on public incidents (Part VI of the book).

Each cases/<id>/case.yaml is ILLUSTRATIVE: a small, fictional input shaped
after one public incident, with the source cited in the file. It is not a
reconstruction of the affected company's systems and makes no claim that a
check like this would have prevented the incident. The checks below decide
from the evidence present; anything missing is treated as unknown, and
unknown is not safe.

Run: python -m tools.check_cases  (exit 1 if any case disagrees with its
expected verdict).
"""
from __future__ import annotations

import sys
from pathlib import Path

from tools import asc_gate
from tools.check_restore import evaluate_rp
from tools.common import ROOT, load_doc, repo_path

RANK = {"ALLOW": 0, "REQUIRE_APPROVAL": 1, "BLOCK": 2}


def _verdict(problems: list[tuple[str, str]]) -> dict:
    if not problems:
        return {"verdict": "ALLOW", "reason_code": "within_contract",
                "problems": []}
    return {"verdict": "BLOCK", "reason_code": problems[0][0],
            "problems": [f"{c}: {d}" for c, d in problems]}


def check_restore(spec: dict, root: Path) -> dict:
    """A destructive data-plane step needs a PROVED restore."""
    contract = load_doc(repo_path(root, spec["contractRef"]))
    rp = evaluate_rp(spec["restorePoint"], contract)
    if rp["computed"] == "PROVED":
        return _verdict([])
    return _verdict([("restore_unproved", p) for p in rp["problems"]])


def check_fleet_parity(spec: dict, root: Path) -> dict:
    """Every target reports the expected build; rollback restores config."""
    want = spec["expectedArtifact"]
    problems = []
    for host in spec["targets"]:
        seen = spec["observed"].get(host)
        if seen is None:
            problems.append(("target_unobserved", f"{host}: no report"))
        elif seen != want:
            problems.append(("fleet_drift", f"{host}: {seen} != {want}"))
    rb = spec["rollback"]
    if spec.get("configChanges") and not rb.get("restoresConfig"):
        problems.append(("rollback_leaves_new_config",
                         "code reverts, flag stays set"))
    if not rb.get("rehearsed"):
        problems.append(("rollback_unproven", "no rollback rehearsal"))
    return _verdict(problems)


def check_capacity_removal(spec: dict, root: Path) -> dict:
    """Removal may not take a subsystem below its minimum, or go too fast."""
    problems, step = [], spec["limits"]["maxRemovePerStep"]
    for name, n in spec["request"]["remove"].items():
        sub = spec["subsystems"].get(name)
        if sub is None:
            problems.append(("subsystem_unknown", name))
            continue
        left = sub["current"] - n
        if left < sub["minimum"]:
            problems.append(("below_minimum_capacity",
                             f"{name}: {left} < minimum {sub['minimum']}"))
        if n > step:
            problems.append(("removal_too_fast", f"{name}: {n} > {step}"))
    extra = set(spec["request"]["remove"]) - set(spec["request"]["intended"])
    if extra:
        problems.append(("scope_exceeds_intent",
                         f"also removes {sorted(extra)}"))
    return _verdict(problems)


def check_content_contract(spec: dict, root: Path) -> dict:
    """Content may only use inputs the consumer supplies and tests cover."""
    supplied = spec["consumer"]["suppliedFields"]
    tested = set(spec["tests"]["nonWildcardFieldsCovered"])
    problems = []
    for inst in spec["instances"]:
        for idx in inst["nonWildcardFields"]:
            if idx >= supplied:
                problems.append(("field_beyond_supplied_inputs",
                                 f"{inst['id']}: field {idx} >= {supplied}"))
            elif idx not in tested:
                problems.append(("field_untested", f"{inst['id']}: {idx}"))
    rings = spec["rollout"]["rings"]
    if not rings or rings[0].get("scope") != "canary":
        problems.append(("no_canary_ring", "first ring is not a canary"))
    return _verdict(problems)


def check_recovery_path(spec: dict, root: Path) -> dict:
    """The gate's own self-test must pass, and some recovery path must
    survive the change."""
    problems = []
    if spec["auditTool"].get("selfTest") != "pass":
        problems.append(("audit_tool_unproven",
                         f"self-test: {spec['auditTool'].get('selfTest')}"))
    touched = set(spec["change"]["affects"])
    alive = [p["name"] for p in spec["recoveryPaths"]
             if not touched & set(p["dependsOn"])]
    if not alive:
        problems.append(("recovery_path_shares_fate",
                         "every access path depends on what changes"))
    return _verdict(problems)


def check_propagation(spec: dict, root: Path) -> dict:
    """Replicated data must pass the consumer's schema and roll out in
    stages to code paths that have already run."""
    problems = []
    for field in spec["consumer"]["requiredFields"]:
        if spec["record"].get(field) in (None, ""):
            problems.append(("data_fails_consumer_schema",
                             f"{field} is blank"))
    if spec["propagation"]["mode"] != "staged":
        problems.append(("unstaged_global_propagation",
                         spec["propagation"]["mode"]))
    path = spec["consumer"]["codePath"]
    if not (path.get("flagProtected") and path.get("exercisedInRollout")):
        problems.append(("code_path_unproven", path["name"]))
    return _verdict(problems)


def check_agent_trace(spec: dict, root: Path) -> dict:
    """Agent calls go through the real gate with a case-local contract."""
    scenario = {"spec": {"traceRef": spec["traceRef"]}}
    r = asc_gate.evaluate(scenario, root, spec["policyRef"])
    return {"verdict": r["verdict"], "reason_code": r["reason_code"],
            "problems": [f"{c['id']}: {c['reason_code']}"
                         for c in r["calls"] if c["verdict"] != "ALLOW"]}


CHECKS = {
    "restore": check_restore,
    "fleet-parity": check_fleet_parity,
    "capacity-removal": check_capacity_removal,
    "content-contract": check_content_contract,
    "recovery-path": check_recovery_path,
    "propagation": check_propagation,
    "agent-trace": check_agent_trace,
}


def run(root: Path = ROOT) -> list[dict]:
    rows = []
    for f in sorted((root / "cases").glob("*/case.yaml")):
        case = load_doc(f)
        spec = case["spec"]
        try:
            r = CHECKS[spec["check"]](spec["input"], root)
        except Exception as exc:  # a broken case fails closed
            r = {"verdict": "BLOCK", "reason_code": "case_error",
                 "problems": [f"{type(exc).__name__}: {exc}"]}
        exp = spec["expected"]
        ok = (case["metadata"].get("illustrative") is True
              and r["verdict"] == exp["verdict"]
              and r["reason_code"] == exp["reasonCode"])
        rows.append({"id": case["metadata"]["name"],
                     "modeledOn": case["metadata"]["modeledOn"]["incident"],
                     "pass": ok, **r})
    return rows


def main() -> int:
    rows = run()
    for r in rows:
        mark = "PASS" if r["pass"] else "FAIL"
        print(f"{mark} {r['id']}: {r['verdict']} {r['reason_code']}")
        for p in r["problems"]:
            print(f"       {p}")
    ok = sum(r["pass"] for r in rows)
    print(f"cases: {ok}/{len(rows)} match their expected verdict")
    return 0 if rows and ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
