#!/usr/bin/env bash
# Validate Acme evidence packages: JSON Schema (draft 2020-12), every sha256 digest
# recomputed from the referenced files, fail-closed cross-field rules, and for agent
# packages a re-run of the gate on the referenced scenario.
# Exits non-zero on any failure, including a missing jsonschema dependency.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec "${PYTHON:-python3}" -m tools.evidence validate --root "$ROOT" "$@"
