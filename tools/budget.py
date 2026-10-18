"""Inference budget admission (Chapter 13). Pure function over a policy and a usage snapshot."""
from __future__ import annotations

from typing import Any


def decide(policy: dict, team: str, model: str, requested_tokens: int, snapshot: dict | None) -> dict[str, Any]:
    spec = policy["spec"]
    adm = spec["admission"]
    budget = next((b for b in spec["budgets"] if b["team"] == team), None)
    if budget is None:
        return {"verdict": adm["whenTeamUnknown"], "reason_code": "budget_team_unknown"}
    if not snapshot or snapshot.get("status") not in ("available", "unavailable"):
        return {"verdict": adm["whenBudgetUnknown"], "reason_code": "budget_unknown"}
    if snapshot["status"] == "unavailable":
        return {"verdict": adm["whenBudgetStoreDown"], "reason_code": "budget_store_down"}
    if "ageSeconds" not in snapshot or snapshot["ageSeconds"] > spec["freshnessSecondsMax"]:
        return {"verdict": adm["whenSnapshotStale"], "reason_code": "budget_snapshot_stale"}
    price = spec["models"].get(model, {}).get("costPerMillionTokensUsd")
    if price is None:
        return {"verdict": adm["whenBudgetUnknown"], "reason_code": "budget_model_price_unknown"}
    used_tokens = int(snapshot.get("usedTokens", 0))
    used_usd = float(snapshot.get("usedUsd", 0.0))
    cost = requested_tokens * price / 1_000_000
    if used_tokens + requested_tokens > budget["dailyTokens"] or used_usd + cost > budget["dailyUsd"] + 1e-9:
        return {
            "verdict": adm["whenBudgetExceeded"],
            "reason_code": "budget_exceeded",
            "remaining_tokens": max(budget["dailyTokens"] - used_tokens, 0),
        }
    return {
        "verdict": "ALLOW",
        "reason_code": "within_budget",
        "next_snapshot": dict(snapshot, usedTokens=used_tokens + requested_tokens, usedUsd=round(used_usd + cost, 6)),
    }
