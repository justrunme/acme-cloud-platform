"""GPU admission decisions (Chapter 14). Pure functions over a policy and a quota snapshot."""
from __future__ import annotations


def decide(policy: dict, request: dict, snapshot: dict | None, policy_engine: str = "up") -> dict:
    spec = policy["spec"]
    adm = spec["admission"]
    if policy_engine != "up":
        return {"verdict": adm["whenPolicyEngineDown"], "reason_code": "policy_engine_down"}
    tenant = next((t for t in spec["tenants"] if t["name"] == request.get("tenant")), None)
    if tenant is None:
        return {"verdict": adm["whenTenantUnknown"], "reason_code": "tenant_unknown"}
    if not snapshot or snapshot.get("status") != "available":
        return {"verdict": adm["whenQuotaUnknown"], "reason_code": "quota_unknown"}
    cluster = next((c for c in spec["clusters"] if c["name"] == request.get("cluster", spec["clusters"][0]["name"])), None)
    if cluster is None or request.get("gpuClass") not in cluster["gpuClasses"]:
        return {"verdict": adm["whenClassUnavailable"], "reason_code": "gpu_class_unavailable"}
    gpus = int(request["gpus"])
    used_by_tenant = int(snapshot.get("tenantAllocated", {}).get(tenant["name"], 0))
    if used_by_tenant + gpus > tenant["maxGpus"]:
        return {"verdict": "BLOCK", "reason_code": "tenant_quota_exceeded"}
    if int(snapshot.get("poolAllocated", 0)) + gpus > cluster["totalGpus"]:
        return {"verdict": adm["whenFairnessCheckInconclusive"], "reason_code": "pool_capacity_exceeded"}
    if request.get("initiator") == "agent":
        return {"verdict": adm["agentInitiatedMutation"], "reason_code": "agent_initiated_gpu_mutation"}
    return {"verdict": "ALLOW", "reason_code": "within_quota"}


AUTOSCALERS = ("HorizontalPodAutoscaler", "ScaledObject")


def autoscaler_conflicts(manifests: list[dict]) -> list[str]:
    """Return workloads controlled by more than one autoscaler
    (HPA and/or KEDA ScaledObject)."""
    seen: dict[str, int] = {}
    for m in manifests:
        if m.get("kind") not in AUTOSCALERS:
            continue
        ref = m.get("spec", {}).get("scaleTargetRef", {})
        ns = m.get("metadata", {}).get("namespace", "default")
        key = f"{ns}/{ref.get('kind', 'Deployment')}/{ref.get('name')}"
        seen[key] = seen.get(key, 0) + 1
    return sorted(k for k, n in seen.items() if n > 1)
