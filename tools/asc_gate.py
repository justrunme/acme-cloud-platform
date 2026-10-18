"""Agent Security Contract gate for the Acme platform agent (Chapter 12).

evaluate(...) decides ALLOW / BLOCK / REQUIRE_APPROVAL for every call in a tool-call trace
before execution. Order of checks per call (first failure wins):
  unavailable evaluator/policy store -> catalog digest pin -> gateway transport -> tool allowlist
  -> rate limits -> catalog input schema -> global deny patterns -> tool-specific constraints
  -> inference budget -> high-impact approval binding.
Trace verdict: any BLOCK => BLOCK; else any REQUIRE_APPROVAL => REQUIRE_APPROVAL; else ALLOW.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import fnmatch
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import jsonschema

from tools import budget
from tools.common import ROOT, load_doc, load_json, repo_path, sha256_file, sha256_obj

RANK = {"ALLOW": 0, "REQUIRE_APPROVAL": 1, "BLOCK": 2}
ACS = {"ALLOW": "ALLOW", "BLOCK": "DENY", "REQUIRE_APPROVAL": "ASK"}


class Unavailable(Exception):
    """Evaluator dependency unavailable. Always mapped to the policy's onUnavailable (BLOCK)."""


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def request_digest(agent: str, tool: str, args: dict, policy_version: str) -> str:
    return sha256_obj({"agent": agent, "tool": tool, "args": args, "policy_version": policy_version})


def load_trace(scenario: dict, root: Path) -> dict:
    spec = scenario["spec"]
    if "traceRef" in spec:
        return load_json(repo_path(root, spec["traceRef"]))
    return spec["trace"]


def _decision(verdict: str, code: str, detail: str) -> dict:
    return {"verdict": verdict, "reason_code": code, "reason": detail}


def _evaluate_call(call: dict, idx_tool: int, idx_total: int, ctx: dict) -> dict:
    policy, spec, catalog = ctx["policy"], ctx["policy"]["spec"], ctx["catalog"]
    tool = call.get("tool")
    args = call.get("args", {})

    if spec.get("requireGateway", True) and call.get("via", "gateway") != "gateway":
        return _decision("BLOCK", "no_gateway_envelope", "call bypassed the evaluating gateway; no envelope can exist")
    tool_def = next((t for t in catalog["tools"] if t["name"] == tool), None)
    if tool_def is None:
        return _decision("BLOCK", "tool_not_in_catalog", f"tool {tool!r} is not in the approved catalog")
    allowed = spec["agents"].get(ctx["agent"], {}).get("allowTools", [])
    if tool not in allowed:
        return _decision("BLOCK", "tool_not_allowed", f"agent {ctx['agent']!r} may not call {tool!r}")
    rl = spec.get("rateLimits", {})
    if idx_total > rl.get("maxCallsPerTrace", 0):
        return _decision("BLOCK", "rate_limit_exceeded", f"call {idx_total} exceeds maxCallsPerTrace={rl.get('maxCallsPerTrace')}")
    per_tool = rl.get("perTool", {}).get(tool)
    if per_tool is not None and idx_tool > per_tool:
        return _decision("BLOCK", "rate_limit_exceeded", f"{tool} call {idx_tool} exceeds perTool limit {per_tool}")

    errors = list(jsonschema.Draft202012Validator(tool_def["input_schema"]).iter_errors(args))
    if errors:
        return _decision("BLOCK", "argument_schema_violation", errors[0].message)

    for value in _strings(args):
        for pat in spec.get("globalDenyPatterns", []):
            if re.search(pat["regex"], value):
                return _decision("BLOCK", f"argument_denied:{pat['id']}", f"argument matches deny pattern {pat['id']}")

    rules = spec["tools"].get(tool, {})
    if "pathGlobs" in rules and not any(fnmatch.fnmatchcase(args["path"], g) for g in rules["pathGlobs"]):
        return _decision("BLOCK", "path_not_allowed", f"path {args['path']!r} outside {rules['pathGlobs']}")
    if "namespaces" in rules and args.get("namespace") not in rules["namespaces"]:
        return _decision("BLOCK", "namespace_not_allowed", f"namespace {args.get('namespace')!r} not in allowlist")
    if "applications" in rules and args.get("application") not in rules["applications"]:
        return _decision("BLOCK", "application_not_allowed", f"application {args.get('application')!r} not in allowlist")
    if "allowHosts" in rules:
        u = urlparse(args["url"])
        if u.scheme not in rules.get("allowSchemes", ["https"]) or u.hostname not in rules["allowHosts"]:
            return _decision("BLOCK", "host_not_allowed", f"url host {u.hostname!r} / scheme {u.scheme!r} not allowlisted")
    if "models" in rules and args.get("model") not in rules["models"]:
        return _decision("BLOCK", "model_not_allowed", f"model {args.get('model')!r} not allowlisted")

    if "budget" in rules:
        if ctx["budget_policy"] is None:
            raise Unavailable("budget policy unreadable")
        res = budget.decide(ctx["budget_policy"], rules["budget"]["team"], args["model"], args["max_tokens"], ctx["budget_snapshot"])
        if res["verdict"] != "ALLOW":
            return _decision(res["verdict"], res["reason_code"], f"inference budget: {res['reason_code']}")
        ctx["budget_snapshot"] = res["next_snapshot"]

    if rules.get("impact") == "high" and args.get("namespace") not in rules.get("approvalExemptNamespaces", []):
        digest = request_digest(ctx["agent"], tool, args, policy["metadata"]["version"])
        approval_id = call.get("approval_id")
        if not approval_id:
            return _decision("REQUIRE_APPROVAL", "approval_required", f"high-impact {tool}; bind approval to {digest}")
        record = ctx["approvals"].get(approval_id)
        if record is None:
            return _decision("BLOCK", "approval_unknown", f"approval {approval_id} not found in store")
        if record["request_digest"] != digest:
            return _decision("BLOCK", "approval_digest_mismatch", f"approval {approval_id} is bound to a different request")
        if _ts(record["expires_at"]) <= ctx["evaluated_at"]:
            return _decision("BLOCK", "approval_expired", f"approval {approval_id} expired at {record['expires_at']}")
        return _decision("ALLOW", "approved_binding_valid", f"approval {approval_id} matches request digest")
    return _decision("ALLOW", "within_contract", "call satisfies the contract")


def _strings(obj: Any):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _evaluate(scenario: dict, root: Path, policy_rel: str) -> dict:
    spec = scenario["spec"]
    faults = spec.get("context", {}).get("faults", {})
    if faults.get("policyStore") == "unavailable":
        raise Unavailable("policy store unavailable")
    if faults.get("evaluatorDelayMs"):
        time.sleep(faults["evaluatorDelayMs"] / 1000)
    policy = load_doc(repo_path(root, policy_rel))
    pspec = policy["spec"]
    catalog_rel = spec.get("catalogRef", pspec["catalog"]["ref"])
    catalog_digest = sha256_file(repo_path(root, catalog_rel))
    trace = load_trace(scenario, root)
    calls_out = []
    if catalog_digest != pspec["catalog"]["sha256"]:
        for c in trace["calls"]:
            calls_out.append(dict(id=c["id"], tool=c.get("tool"),
                                  **_decision("BLOCK", "catalog_digest_mismatch",
                                              f"runtime catalog {catalog_digest} != pinned {pspec['catalog']['sha256']}")))
    else:
        bctx = spec.get("context", {}).get("budgetStore")
        budget_policy_rel = next((t["budget"]["policyRef"] for t in pspec["tools"].values() if "budget" in t), None)
        ctx = {
            "policy": policy,
            "catalog": load_json(repo_path(root, catalog_rel)),
            "agent": trace["agent"],
            "approvals": {a["approval_id"]: a for a in load_json(repo_path(root, pspec["approvals"]["storeRef"]))["approvals"]},
            "evaluated_at": _ts(trace["evaluated_at"]),
            "budget_policy": load_doc(repo_path(root, budget_policy_rel)) if budget_policy_rel else None,
            "budget_snapshot": bctx,
        }
        per_tool: dict[str, int] = {}
        for n, c in enumerate(trace["calls"], start=1):
            per_tool[c.get("tool")] = per_tool.get(c.get("tool"), 0) + 1
            d = _evaluate_call(c, per_tool[c.get("tool")], n, ctx)
            calls_out.append({"id": c["id"], "tool": c.get("tool"),
                              "request_digest": request_digest(trace["agent"], c.get("tool"), c.get("args", {}), policy["metadata"]["version"]),
                              **d})
    worst = max(calls_out, key=lambda d: RANK[d["verdict"]])
    return {
        "verdict": worst["verdict"],
        "reason_code": worst["reason_code"],
        "reason": f"{worst['id']}: {worst['reason']}",
        "trace_id": trace["trace_id"],
        "evaluated_at": trace["evaluated_at"],
        "catalog_sha256": catalog_digest,
        "policy_version": policy["metadata"]["version"],
        "calls": calls_out,
    }


DEFAULT_POLICY = "agents/contracts/demo-agent.policy.yaml"


def evaluate(scenario: dict, root: Path = ROOT,
             policy_rel: str | None = None) -> dict:
    """Evaluate with a hard timeout.

    Timeout, missing dependency or evaluator error => BLOCK."""
    policy_rel = (policy_rel
                  or scenario["spec"].get("policyRef", DEFAULT_POLICY))
    timeout_ms = 1000
    try:
        pspec = load_doc(repo_path(root, policy_rel))["spec"]
        timeout_ms = int(pspec.get("evaluatorTimeoutMs", 1000))
    except Exception:
        pass
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    fut = pool.submit(_evaluate, scenario, root, policy_rel)
    try:
        result = fut.result(timeout=timeout_ms / 1000)
    except concurrent.futures.TimeoutError:
        result = _failclosed(scenario, root, "evaluator_timeout",
                             f"evaluator exceeded {timeout_ms} ms")
    except Unavailable as exc:
        result = _failclosed(scenario, root, "evaluator_unavailable",
                             str(exc))
    except Exception as exc:  # any evaluator error fails closed
        result = _failclosed(scenario, root, "evaluator_error",
                             f"{type(exc).__name__}: {exc}")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    result["policy_ref"] = policy_rel
    result["acs_disposition"] = ACS[result["verdict"]]
    return result


def _failclosed(scenario: dict, root: Path, code: str, detail: str) -> dict:
    trace = load_trace(scenario, root)
    return {
        "verdict": "BLOCK",
        "reason_code": code,
        "reason": f"onUnavailable=BLOCK: {detail}",
        "trace_id": trace.get("trace_id"),
        "evaluated_at": trace.get("evaluated_at"),
        "catalog_sha256": None,
        "policy_version": None,
        "calls": [{"id": c.get("id"), "tool": c.get("tool"), "verdict": "BLOCK", "reason_code": code, "reason": detail}
                  for c in trace.get("calls", [])],
    }


def evaluate_scenario_file(path: Path, root: Path = ROOT) -> dict:
    return evaluate(load_doc(path), root)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate one agent scenario, or print a request digest for approvals.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("evaluate")
    e.add_argument("scenario", type=Path)
    d = sub.add_parser("digest")
    d.add_argument("scenario", type=Path)
    d.add_argument("--call", required=True)
    args = ap.parse_args(argv)
    sc = load_doc(args.scenario)
    if args.cmd == "digest":
        trace = load_trace(sc, ROOT)
        policy = load_doc(ROOT / sc["spec"].get("policyRef", DEFAULT_POLICY))
        c = next(c for c in trace["calls"] if c["id"] == args.call)
        print(request_digest(trace["agent"], c["tool"], c["args"], policy["metadata"]["version"]))
        return 0
    r = evaluate(sc, ROOT)
    print(f"{r['verdict']}  {r['reason_code']}  {r['reason']}")
    return {"ALLOW": 0, "BLOCK": 1, "REQUIRE_APPROVAL": 2}[r["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
