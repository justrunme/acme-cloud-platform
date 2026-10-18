from tools import run_corpus
from tools.asc_gate import evaluate, request_digest
from tools.common import ROOT, load_doc, load_json


def test_corpus_matches_expectations_without_writing():
    out = run_corpus.run(ROOT, write=False)
    s = out["summary"]
    failed = [r for r in out["scenarios"] if not r["pass"]]
    assert not failed, failed
    assert s["attack_false_allow"] == 0
    assert s["benign_false_block"] == 0


def test_every_chapter12_category_is_present():
    ids = {p.stem for p in (ROOT / "agents/scenarios").glob("*.yaml")}
    for required in (
        "unapproved_prod_deploy", "mcp_tool_poisoning", "argument_injection", "path_traversal",
        "cross_namespace_mutate", "approval_replay_different_digest", "rate_limit_fanout",
        "direct_tool_endpoint_no_gateway", "inference_fanout_budget_exhausted",
        "read_workspace_file", "inventory_read", "sandbox_apply_low_risk", "approved_prod_deploy_valid_binding",
    ):
        assert required in ids


def test_approvals_bind_to_real_request_digests():
    store = load_json(ROOT / "agents/approvals/approvals.json")["approvals"]
    policy = load_doc(ROOT / "agents/contracts/demo-agent.policy.yaml")
    sc = load_doc(ROOT / "agents/scenarios/approved_prod_deploy_valid_binding.yaml")
    call = sc["spec"]["trace"]["calls"][0]
    digest = request_digest("platform-agent", call["tool"], call["args"], policy["metadata"]["version"])
    assert any(a["request_digest"] == digest for a in store)


def test_removing_approval_turns_allow_into_require_approval():
    sc = load_doc(ROOT / "agents/scenarios/approved_prod_deploy_valid_binding.yaml")
    sc["spec"]["trace"]["calls"][0].pop("approval_id")
    assert evaluate(sc, ROOT)["verdict"] == "REQUIRE_APPROVAL"
