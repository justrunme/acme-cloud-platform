"""Inference budget admission (Chapter 13).

A pure function over a policy and a usage snapshot.
"""
from __future__ import annotations

from typing import Any


def decide(policy: dict, team: str, model: str, requested_tokens: int,
           snapshot: dict | None) -> dict[str, Any]:
    spec = policy["spec"]
    adm = spec["admission"]
    budget = next((b for b in spec["budgets"] if b["team"] == team), None)
    if budget is None:
        return {"verdict": adm["whenTeamUnknown"],
                "reason_code": "budget_team_unknown"}
    status = (snapshot or {}).get("status")
    if status not in ("available", "unavailable"):
        return {"verdict": adm["whenBudgetUnknown"],
                "reason_code": "budget_unknown"}
    if status == "unavailable":
        return {"verdict": adm["whenBudgetStoreDown"],
                "reason_code": "budget_store_down"}
    age = snapshot.get("ageSeconds")
    if age is None or age > spec["freshnessSecondsMax"]:
        return {"verdict": adm["whenSnapshotStale"],
                "reason_code": "budget_snapshot_stale"}
    price = spec["models"].get(model, {}).get("costPerMillionTokensUsd")
    if price is None:
        return {"verdict": adm["whenBudgetUnknown"],
                "reason_code": "budget_model_price_unknown"}
    used_tokens = int(snapshot.get("usedTokens", 0))
    used_usd = float(snapshot.get("usedUsd", 0.0))
    cost = requested_tokens * price / 1_000_000
    over_tokens = used_tokens + requested_tokens > budget["dailyTokens"]
    over_usd = used_usd + cost > budget["dailyUsd"] + 1e-9
    if over_tokens or over_usd:
        return {
            "verdict": adm["whenBudgetExceeded"],
            "reason_code": "budget_exceeded",
            "remaining_tokens": max(budget["dailyTokens"] - used_tokens, 0),
        }
    return {
        "verdict": "ALLOW",
        "reason_code": "within_budget",
        "next_snapshot": dict(snapshot,
                              usedTokens=used_tokens + requested_tokens,
                              usedUsd=round(used_usd + cost, 6)),
    }
