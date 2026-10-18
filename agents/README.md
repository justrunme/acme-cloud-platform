# Agent security contracts (Part IV)

Executable companion for Chapters 11-14 of *Prove It Before Production*.

| Path | What it is |
| --- | --- |
| `contracts/demo-agent.policy.yaml` | Agent Security Contract for `platform-agent`: pinned catalog digest, tool allowlist, argument constraints, high-impact tools that need an approval bound to the request digest, rate limits, budget coupling, `onUnavailable: BLOCK` |
| `catalog/tools.json` | Approved tool catalog (digest pinned in the policy); `tools.poisoned.json` is the poisoning fixture |
| `approvals/approvals.json` | Illustrative approval store; each approval names one request digest |
| `scenarios/*.yaml` | The corpus: attack/misuse scenarios and benign scenarios, each with an expected verdict |
| `traces/CHG-0043-trace.json` | Trace behind evidence package `CHG-0043` |

The gate is `tools/asc_gate.py`; the runner is `tools/run_corpus.py`.

```bash
make corpus      # evaluate every scenario, write results/envelopes/*.json
make envelopes   # verify envelope digests and dispositions
python -m tools.asc_gate evaluate agents/scenarios/mcp_tool_poisoning.yaml
python -m tools.asc_gate digest agents/scenarios/unapproved_prod_deploy.yaml --call call-1
```

Current counts and per-scenario verdicts are in [`../docs/EVIDENCE.md`](../docs/EVIDENCE.md), generated
from `results/results.json`. Claims hold on this corpus only.

## Verdicts

| Verdict | Exit code (`asc_gate evaluate`) | ACS disposition |
| --- | --- | --- |
| ALLOW | 0 | ALLOW |
| BLOCK | 1 | DENY |
| REQUIRE_APPROVAL | 2 | ASK |

Trace verdict is the most restrictive call verdict. Evaluator timeout, unreadable policy, a dark budget
store or any evaluator error is BLOCK.

## Limits

The gate evaluates recorded, illustrative traces. It is not connected to a live MCP server, it is not an
OS sandbox, and it does not detect prompt injection inside a model. The "direct tool endpoint" rule is
modeled at the gate (`via: direct`) and as a NetworkPolicy manifest (`apps/agent/networkpolicy.yaml`)
that no cluster in this repository applies.
