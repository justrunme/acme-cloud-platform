"""Evidence envelopes for agent gate decisions: build and verify.

The envelope digest is an unkeyed integrity check over canonical fields. Anyone who can
rewrite the file can recompute it; trust envelopes produced by CI you control.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.common import ROOT, load_json, repo_path, sha256_file, sha256_obj

SCHEMA_VERSION = "acme.asc.envelope/v1"
REQUIRED = (
    "schema_version", "policy_ref", "policy_version", "policy_sha256", "catalog_sha256", "scenario_id",
    "trace_id", "verdict", "reason_code", "reason", "acs_disposition", "evaluated_at", "inputs_sha256",
    "envelope_sha256",
)
ACS = {"ALLOW": "ALLOW", "BLOCK": "DENY", "REQUIRE_APPROVAL": "ASK"}


def build(scenario_id: str, result: dict, root: Path, inputs_sha256: str) -> dict:
    env = {
        "schema_version": SCHEMA_VERSION,
        "policy_ref": result["policy_ref"],
        "policy_version": result["policy_version"],
        "policy_sha256": sha256_file(repo_path(root, result["policy_ref"])),
        "catalog_sha256": result["catalog_sha256"],
        "scenario_id": scenario_id,
        "trace_id": result["trace_id"],
        "verdict": result["verdict"],
        "reason_code": result["reason_code"],
        "reason": result["reason"],
        "acs_disposition": result["acs_disposition"],
        "evaluated_at": result["evaluated_at"],
        "calls": [{k: c.get(k) for k in ("id", "tool", "verdict", "reason_code", "request_digest")} for c in result["calls"]],
        "inputs_sha256": inputs_sha256,
    }
    env["envelope_sha256"] = sha256_obj(env)
    return env


def verify(env: dict, root: Path = ROOT) -> list[str]:
    errs = [f"missing field {k}" for k in REQUIRED if k not in env]
    if errs:
        return errs
    body = {k: v for k, v in env.items() if k != "envelope_sha256"}
    if sha256_obj(body) != env["envelope_sha256"]:
        errs.append("envelope_sha256 does not match canonical body (tampered)")
    if ACS.get(env["verdict"]) != env["acs_disposition"]:
        errs.append(f"acs_disposition {env['acs_disposition']} inconsistent with verdict {env['verdict']}")
    try:
        actual = sha256_file(repo_path(root, env["policy_ref"]))
    except (ValueError, FileNotFoundError):
        actual = None
    if actual != env["policy_sha256"]:
        errs.append("policy_sha256 does not match the policy file in this repository")
    return errs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify agent gate envelopes.")
    ap.add_argument("files", nargs="*", type=Path)
    args = ap.parse_args(argv)
    files = args.files or sorted((ROOT / "results" / "envelopes").glob("*.json"))
    if not files:
        print("ERROR no envelopes to verify", file=sys.stderr)
        return 2
    bad = 0
    for f in files:
        errs = verify(load_json(f))
        print(("OK   " if not errs else "FAIL ") + Path(f).name)
        for e in errs:
            print(f"  - {e}")
        bad += bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
