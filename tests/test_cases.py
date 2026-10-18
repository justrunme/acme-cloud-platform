"""Case specimens (cases/): each expected verdict holds, and the same check
returns ALLOW once the missing evidence is supplied, so no check blocks
unconditionally."""
import copy

import pytest

from tools import check_cases
from tools.common import ROOT, load_doc


def _case(name):
    return load_doc(ROOT / "cases" / name / "case.yaml")["spec"]


def test_all_cases_match_expected():
    rows = check_cases.run()
    assert len(rows) == 8
    assert all(r["pass"] for r in rows), [r for r in rows if not r["pass"]]


def _fixed(name):
    spec = copy.deepcopy(_case(name))
    i = spec["input"]
    if name == "gitlab-2017-restore":
        clauses = ["artifact_integrity", "isolated_restore", "application_ready",
                   "data_verification", "cross_component_consistency"]
        i["restorePoint"] = {"assertions": [{"id": "R1", "result": "pass",
                                             "covers": clauses}],
                             "verdict": {"rtoSeconds": 900}}
    elif name == "knight-2012-fleet-parity":
        i["observed"]["srv-8"] = i["expectedArtifact"]
        i["rollback"] = {"revertsCode": True, "restoresConfig": True,
                         "rehearsed": True}
    elif name == "s3-2017-capacity-removal":
        i["request"]["remove"] = dict(i["request"]["intended"])
    elif name == "crowdstrike-2024-content-contract":
        i["instances"][1]["nonWildcardFields"] = [0, 1]
        i["rollout"]["rings"] = [{"scope": "canary"}, {"scope": "all-hosts"}]
    elif name == "facebook-2021-recovery-path":
        i["auditTool"]["selfTest"] = "pass"
        i["recoveryPaths"].append({"name": "independent-oob",
                                   "dependsOn": ["separate-carrier"]})
    elif name == "gcp-2025-propagation":
        i["record"].update(limit="1000", scope="project")
        i["propagation"]["mode"] = "staged"
        i["consumer"]["codePath"].update(flagProtected=True,
                                         exercisedInRollout=True)
    return spec


@pytest.mark.parametrize("name", [
    "gitlab-2017-restore", "knight-2012-fleet-parity",
    "s3-2017-capacity-removal", "crowdstrike-2024-content-contract",
    "facebook-2021-recovery-path", "gcp-2025-propagation"])
def test_supplying_the_evidence_allows(name):
    spec = _fixed(name)
    r = check_cases.CHECKS[spec["check"]](spec["input"], ROOT)
    assert r["verdict"] == "ALLOW", r


def test_agent_dev_write_is_exempt():
    spec = _case("agent-2025-no-freeze")
    from tools import asc_gate
    trace = load_doc(ROOT / spec["input"]["traceRef"])
    trace["calls"][1]["args"]["namespace"] = "dev"
    r = asc_gate.evaluate({"spec": {"trace": trace}}, ROOT,
                          spec["input"]["policyRef"])
    assert r["verdict"] == "ALLOW", r
