"""Evidence package digests, sealing and fail-closed validation.

Digest rules (all values are "sha256:<64 hex>"):
  change.changeDigest            canonical JSON of `change` without `changeDigest`
  reconstruction.baselineDigest  bytes of the file named by reconstruction.graphRef
  rehearsal.semanticDigest       bytes of the file named by rehearsal.scenarioRef (if present)
  verdict.policySha256           bytes of the file named by verdict.policyRef
  evidence.artifacts[].sha256    bytes of each artifact file
  evidence.envelopeSha256        canonical JSON of the whole package without evidence.envelopeSha256
"""
from __future__ import annotations

import argparse
import copy
import os
import sys
from pathlib import Path
from typing import Any

from tools.common import ROOT, load_json, repo_path, sha256_file, sha256_obj, write_json

SCHEMA_REL = "evidence/schema/evidence-package.schema.json"

ACS_FOR_VERDICT = {"ALLOW": "ALLOW", "BLOCK": "DENY", "REQUIRE_APPROVAL": "ASK"}
REHEARSAL_TO_VERDICT = {"approve": "ALLOW", "warn": "REQUIRE_APPROVAL", "block": "BLOCK", "unknown": "BLOCK"}


class ValidatorUnavailable(RuntimeError):
    """Raised when full validation cannot run. Callers must treat this as failure."""


def _load_jsonschema():
    if os.environ.get("ACME_SIMULATE_MISSING_JSONSCHEMA") == "1":  # used by negative tests only
        raise ValidatorUnavailable("jsonschema import disabled (ACME_SIMULATE_MISSING_JSONSCHEMA=1)")
    try:
        import jsonschema  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ValidatorUnavailable(
            "jsonschema is not installed; refusing to report packages as valid (pip install -r requirements.txt)"
        ) from exc
    return jsonschema


def _file_digest(root: Path, rel: str) -> str | None:
    try:
        p = repo_path(root, rel)
    except ValueError:
        return None
    return sha256_file(p) if p.is_file() else None


def expected_digests(pkg: dict, root: Path) -> dict[str, str | None]:
    """Return {json-path: expected digest or None if the source is missing}."""
    out: dict[str, str | None] = {}
    change = {k: v for k, v in pkg.get("change", {}).items() if k != "changeDigest"}
    out["change.changeDigest"] = sha256_obj(change)
    rec = pkg.get("reconstruction", {})
    if "graphRef" in rec:
        out["reconstruction.baselineDigest"] = _file_digest(root, rec["graphRef"])
    reh = pkg.get("rehearsal", {})
    if "scenarioRef" in reh:
        out["rehearsal.semanticDigest"] = _file_digest(root, reh["scenarioRef"])
    ver = pkg.get("verdict", {})
    if "policyRef" in ver:
        out["verdict.policySha256"] = _file_digest(root, ver["policyRef"])
    for i, art in enumerate(pkg.get("evidence", {}).get("artifacts", [])):
        out[f"evidence.artifacts[{i}].sha256"] = _file_digest(root, art.get("path", ""))
    return out


def envelope_digest(pkg: dict) -> str:
    body = copy.deepcopy(pkg)
    body.get("evidence", {}).pop("envelopeSha256", None)
    return sha256_obj(body)


def _get(pkg: dict, dotted: str) -> Any:
    cur: Any = pkg
    for part in dotted.replace("]", "").split("."):
        if "[" in part:
            name, idx = part.split("[")
            cur = cur.get(name, []) if isinstance(cur, dict) else []
            cur = cur[int(idx)] if isinstance(cur, list) and int(idx) < len(cur) else None
        else:
            cur = cur.get(part) if isinstance(cur, dict) else None
        if cur is None:
            return None
    return cur


def _set(pkg: dict, dotted: str, value: str) -> None:
    parts = dotted.replace("]", "").split(".")
    cur: Any = pkg
    for part in parts[:-1]:
        if "[" in part:
            name, idx = part.split("[")
            cur = cur[name][int(idx)]
        else:
            cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def seal(pkg: dict, root: Path) -> dict:
    """Recompute every digest from the files in the repository. Missing sources raise."""
    pkg = copy.deepcopy(pkg)
    for path, digest in expected_digests(pkg, root).items():
        if digest is None:
            raise FileNotFoundError(f"{pkg.get('metadata', {}).get('id')}: source for {path} does not exist")
        _set(pkg, path, digest)
    pkg.setdefault("evidence", {})["envelopeSha256"] = envelope_digest(pkg)
    return pkg


def semantic_errors(pkg: dict) -> list[str]:
    """Fail-closed cross-field rules that JSON Schema cannot express."""
    errs: list[str] = []
    ver = pkg.get("verdict", {})
    reh = pkg.get("rehearsal", {})
    rec = pkg.get("reconstruction", {})
    decision = ver.get("decision")
    if decision == "ALLOW":
        if reh.get("result") != "pass":
            errs.append("verdict.decision ALLOW requires rehearsal.result=pass")
        if rec.get("unknowns"):
            errs.append("verdict.decision ALLOW with non-empty reconstruction.unknowns (unknown is not safe)")
        if reh.get("kind") == "restore" and ver.get("recoveryVerdict") != "PROVED":
            errs.append("restore change may be ALLOW only with recoveryVerdict=PROVED")
    if reh.get("result") == "inconclusive" and decision != "BLOCK":
        errs.append("rehearsal.result=inconclusive must map to BLOCK")
    if ver.get("recoveryVerdict") == "UNPROVED" and decision == "ALLOW":
        errs.append("recoveryVerdict=UNPROVED cannot be ALLOW")
    raw = ver.get("rehearsalDecision")
    if raw is not None and REHEARSAL_TO_VERDICT.get(raw) != decision:
        errs.append(f"rehearsalDecision={raw} maps to {REHEARSAL_TO_VERDICT.get(raw)}, not {decision}")
    acs = ver.get("acsDisposition")
    if acs is not None and ACS_FOR_VERDICT.get(decision) != acs:
        errs.append(f"acsDisposition={acs} inconsistent with decision={decision}")
    if pkg.get("metadata", {}).get("illustrative") is not True:
        errs.append("metadata.illustrative must be true: every package in this companion is a fictional teaching scenario")
    return errs


def agent_cross_check(pkg: dict, root: Path) -> list[str]:
    """For agent packages, re-run the gate on the referenced scenario and compare verdicts."""
    reh = pkg.get("rehearsal", {})
    if reh.get("kind") != "agent" or "scenarioRef" not in reh:
        return []
    from tools.asc_gate import evaluate_scenario_file

    try:
        result = evaluate_scenario_file(repo_path(root, reh["scenarioRef"]), root)
    except Exception as exc:  # fail closed: an evaluator error is a validation failure
        return [f"agent scenario could not be evaluated: {exc}"]
    decision = pkg.get("verdict", {}).get("decision")
    if result["verdict"] != decision:
        return [f"gate evaluates {reh['scenarioRef']} to {result['verdict']}, package claims {decision}"]
    return []


def validate_package(path: Path, root: Path, schema: dict) -> list[str]:
    jsonschema = _load_jsonschema()
    try:
        pkg = load_json(path)
    except Exception as exc:
        return [f"unreadable JSON: {exc}"]
    errs: list[str] = []
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    for e in sorted(validator.iter_errors(pkg), key=lambda e: list(map(str, e.path))):
        loc = ".".join(str(x) for x in e.path) or "$"
        errs.append(f"schema {loc}: {e.message}")
    if errs:
        return errs  # do not compute digests over a structurally invalid package
    for dotted, expected in expected_digests(pkg, root).items():
        actual = _get(pkg, dotted)
        if expected is None:
            errs.append(f"digest {dotted}: referenced file is missing or outside the repository")
        elif actual != expected:
            errs.append(f"digest {dotted}: recorded {actual} != computed {expected}")
    env = pkg["evidence"]["envelopeSha256"]
    if env != envelope_digest(pkg):
        errs.append(f"digest evidence.envelopeSha256: recorded {env} != computed {envelope_digest(pkg)}")
    errs.extend(semantic_errors(pkg))
    if not errs:
        errs.extend(agent_cross_check(pkg, root))
    return errs


def validate_all(root: Path = ROOT, files: list[Path] | None = None) -> list[dict]:
    schema = load_json(root / SCHEMA_REL)
    _load_jsonschema()
    files = files or sorted((root / "evidence").glob("CHG-*.json"))
    if not files:
        raise ValidatorUnavailable("no evidence packages found under evidence/CHG-*.json")
    report = []
    for f in files:
        errs = validate_package(f, root, schema)
        decision = None
        try:
            decision = load_json(f).get("verdict", {}).get("decision")
        except Exception:
            pass
        report.append({"file": Path(f).name, "ok": not errs, "decision": decision, "errors": errs})
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--root", type=Path, default=ROOT)
    v.add_argument("files", nargs="*", type=Path)
    s = sub.add_parser("seal", help="recompute digests in place (authoring only)")
    s.add_argument("--root", type=Path, default=ROOT)
    s.add_argument("files", nargs="*", type=Path)
    args = ap.parse_args(argv)

    if args.cmd == "seal":
        files = args.files or sorted((args.root / "evidence").glob("CHG-*.json"))
        for f in files:
            write_json(f, seal(load_json(f), args.root))
            print(f"sealed {Path(f).name}")
        return 0

    try:
        report = validate_all(args.root, args.files or None)
    except ValidatorUnavailable as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2
    failed = 0
    for r in report:
        if r["ok"]:
            print(f"OK   {r['file']}  verdict={r['decision']}  schema+digests+rules")
        else:
            failed += 1
            print(f"FAIL {r['file']}")
            for e in r["errors"]:
                print(f"  - {e}")
    print(f"{len(report) - failed}/{len(report)} evidence packages valid")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
