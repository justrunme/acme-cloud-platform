"""Argo CD PreSync admission gate (cluster/README.md).

Runs as a PreSync hook Job. It fetches the change's evidence package from
the evidence store, validates it with the same code as `make validate`
(schema, every digest recomputed from the files baked into the image,
fail-closed rules), and records its decision back to the store.

Exit 0 only when the package is valid, the recorded verdict is ALLOW, and
the decision record was retained. Anything else exits 1, which fails the
hook and stops Argo CD before the Sync phase. Unknown is not safe: an
unreachable store, an unreadable package or a validator error is BLOCK.

Environment:
  ACME_CHANGE_ID       change being admitted, e.g. CHG-0042 (required)
  ACME_PACKAGE_PATH    store path (default evidence/<ACME_CHANGE_ID>.json)
  ACME_EVIDENCE_STORE  store base URL
                       (default http://evidence-store.acme-evidence.svc:8080)
  ACME_STORE_TIMEOUT   seconds per store request (default 3)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from tools.common import ROOT, canonical_json, load_json, sha256_bytes
from tools.evidence import SCHEMA_REL, ValidatorUnavailable, validate_package

MARKER = "ACME_GATE_DECISION"
DEFAULT_STORE = "http://evidence-store.acme-evidence.svc:8080"
STORE_ERRORS = (urllib.error.URLError, OSError, TimeoutError)


def _request(method: str, url: str, timeout: float,
             body: bytes | None = None) -> bytes:
    req = urllib.request.Request(
        url, data=body, method=method,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


def decide(change_id: str, store: str, package_path: str,
           timeout: float, root: Path = ROOT) -> dict:
    """Return the decision record. Never raises: every failure is BLOCK."""
    rec: dict = {
        "change": change_id, "package": package_path,
        "decision": "BLOCK", "reason": None, "errors": [],
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "gate_pod": os.environ.get("HOSTNAME"),
    }

    def done(decision: str, reason: str) -> dict:
        rec["decision"], rec["reason"] = decision, reason
        return rec

    try:
        raw = _request("GET", f"{store}/{package_path}", timeout)
    except STORE_ERRORS as exc:
        rec["errors"].append(f"evidence store unreachable: {exc}")
        return done("BLOCK", "evidence_store_unavailable")
    rec["package_sha256"] = sha256_bytes(raw)

    with tempfile.TemporaryDirectory() as tmp:
        pkg_file = Path(tmp) / "package.json"
        pkg_file.write_bytes(raw)
        try:
            schema = load_json(root / SCHEMA_REL)
            errs = validate_package(pkg_file, root, schema)
        except ValidatorUnavailable as exc:
            rec["errors"].append(str(exc))
            return done("BLOCK", "validator_unavailable")
        except Exception as exc:  # any evaluator error fails closed
            rec["errors"].append(f"validator error: {exc}")
            return done("BLOCK", "validator_error")
    if errs:
        rec["errors"].extend(errs)
        return done("BLOCK", "evidence_invalid")

    recorded = json.loads(raw).get("verdict", {}).get("decision")
    if recorded == "ALLOW":
        return done("ALLOW", "verdict_allow")
    if recorded == "REQUIRE_APPROVAL":
        # A hold, not a pass: approval binds to the request digest,
        # and only a re-evaluation can reach ALLOW.
        return done("REQUIRE_APPROVAL", "approval_required")
    return done("BLOCK", "verdict_block")


def retain(rec: dict, store: str, timeout: float) -> dict:
    """Write the record to the store. An unretained ALLOW becomes BLOCK."""
    digest = sha256_bytes(canonical_json(rec))[7:19]
    name = f"{rec['change']}-{digest}.json"
    try:
        _request("PUT", f"{store}/records/{name}", timeout,
                 canonical_json(rec))
        rec["record"] = f"records/{name}"
    except STORE_ERRORS as exc:
        rec["errors"].append(f"decision record not retained: {exc}")
        if rec["decision"] == "ALLOW":
            rec["decision"] = "BLOCK"
            rec["reason"] = "evidence_not_retained"
    return rec


def main() -> int:
    change_id = os.environ.get("ACME_CHANGE_ID", "").strip()
    if not change_id:
        rec = {"decision": "BLOCK", "reason": "no_change_id"}
        print(f"{MARKER} {json.dumps(rec)}")
        return 1
    store = os.environ.get("ACME_EVIDENCE_STORE", DEFAULT_STORE)
    store = store.rstrip("/")
    package_path = (os.environ.get("ACME_PACKAGE_PATH")
                    or f"evidence/{change_id}.json")
    timeout = float(os.environ.get("ACME_STORE_TIMEOUT", "3"))
    started = time.monotonic()
    rec = retain(decide(change_id, store, package_path, timeout),
                 store, timeout)
    # fetch + validate + retain, in milliseconds
    rec["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    print(f"{MARKER} {json.dumps(rec, sort_keys=True)}")
    return 0 if rec["decision"] == "ALLOW" else 1


if __name__ == "__main__":
    sys.exit(main())
