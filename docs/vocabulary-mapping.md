# Verdict vocabulary mapping

Acme (book companion) uses one public vocabulary. Author's reference implementations use closely related terms.

| Concern | Acme / Book / ASC | architecture-rehearsal | Recovery Contract | APPLY? |
| --- | --- | --- | --- | --- |
| Allow change | `ALLOW` | `approve` | — | Yes |
| Need human | `REQUIRE_APPROVAL` | `warn` | — | **No** (hold → re-evaluate) |
| Stop change | `BLOCK` | `block` | — | No |
| Missing data | treat as `BLOCK` | `unknown` (+ `unknownAsBlock: true`) | — | No |
| Restore ok | — | — | `PROVED` | n/a |
| Restore not ok | — | — | `UNPROVED` | n/a |
| ACS tool call | `acsDisposition`: ALLOW/DENY/ASK | — | — | ASK ⇒ no APPLY yet |

## Integrity fields (shared idea)

| Field | Source project | Meaning |
| --- | --- | --- |
| `policySha256` | agent-security-contract | Policy bytes that produced the verdict |
| `envelopeSha256` | agent-security-contract | Hash of canonical evidence body |
| `changeDigest` / `baselineDigest` / `semanticDigest` | architecture-rehearsal | Content-addressed rehearsal chain |
| `traceId` | ASC `trace_id` | Correlate agent/tool or human change |

## Principle

**Unknown ≠ Safe.** Missing graph, missing restore proof, missing policy store, or `unknown` rehearsal decision ⇒ fail closed (`BLOCK`).
