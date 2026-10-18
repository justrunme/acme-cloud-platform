# Evidence packages

`CHG-*.json` are evidence packages for the book's fictional Acme changes. Each declares
`metadata.illustrative: true`: actors, timestamps, `commitSha` and the scenarios are teaching material.
The digests are not: every one is a real sha256 that `scripts/validate-evidence.sh` recomputes.

| Field | sha256 over |
| --- | --- |
| `change.changeDigest` | canonical JSON of `change` without `changeDigest` |
| `reconstruction.baselineDigest` | bytes of the file named by `reconstruction.graphRef` |
| `rehearsal.semanticDigest` | bytes of the file named by `rehearsal.scenarioRef` |
| `verdict.policySha256` | bytes of the file named by `verdict.policyRef` |
| `evidence.artifacts[].sha256` | bytes of each artifact |
| `evidence.envelopeSha256` | canonical JSON of the whole package without `evidence.envelopeSha256` |

Canonical JSON: keys sorted, separators `,` and `:`, UTF-8, no ASCII escaping.

The validator fails (non-zero exit) when the schema does not match, any digest differs, a referenced
file is missing or outside the repository, a fail-closed rule is broken (for example an inconclusive
rehearsal marked ALLOW), an agent package disagrees with a fresh gate run, or `jsonschema` is not
installed. `make negative` proves each of those failure paths.

These digests are unkeyed integrity checks, not signatures: anyone who can rewrite a file can reseal it.
Trust packages produced by CI you control. After editing an input on purpose, reseal with
`python -m tools.evidence seal` and review the diff.
