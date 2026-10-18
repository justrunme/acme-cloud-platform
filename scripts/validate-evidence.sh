#!/usr/bin/env bash
# Validate Acme evidence packages against the JSON Schema (stdlib Python).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCHEMA="$ROOT/evidence/schema/evidence-package.schema.json"

if [[ ! -f "$SCHEMA" ]]; then
  echo "schema not found: $SCHEMA" >&2
  exit 1
fi

shopt -s nullglob
packages=("$ROOT"/evidence/CHG-*.json)
if [[ ${#packages[@]} -eq 0 ]]; then
  echo "no evidence packages found under evidence/CHG-*.json" >&2
  exit 1
fi

python3 - "$SCHEMA" "${packages[@]}" <<'PY'
import json, sys
from pathlib import Path

schema_path = Path(sys.argv[1])
packages = [Path(p) for p in sys.argv[2:]]

try:
    import jsonschema
except ImportError:
    jsonschema = None

schema = json.loads(schema_path.read_text())
errors = 0

def check_required(doc, path="$"):
    """Minimal required-field check when jsonschema is unavailable."""
    required = schema.get("required", [])
    missing = [k for k in required if k not in doc]
    if missing:
        return [f"{path}: missing keys {missing}"]
    problems = []
    meta = doc.get("metadata") or {}
    for k in ("id", "createdAt", "actor"):
        if k not in meta:
            problems.append(f"{path}.metadata: missing {k}")
    verdict = doc.get("verdict") or {}
    if verdict.get("decision") not in ("ALLOW", "BLOCK", "REQUIRE_APPROVAL"):
        problems.append(f"{path}.verdict.decision: invalid or missing")
    return problems

for pkg in packages:
    doc = json.loads(pkg.read_text())
    if jsonschema is not None:
        validator = jsonschema.Draft202012Validator(schema)
        errs = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
        if errs:
            errors += 1
            print(f"FAIL {pkg.name}")
            for e in errs:
                loc = ".".join(str(x) for x in e.path) or "$"
                print(f"  - {loc}: {e.message}")
        else:
            print(f"OK   {pkg.name}  verdict={doc['verdict']['decision']}")
    else:
        problems = check_required(doc)
        if problems:
            errors += 1
            print(f"FAIL {pkg.name} (install jsonschema for full validation)")
            for p in problems:
                print(f"  - {p}")
        else:
            print(f"OK   {pkg.name}  verdict={doc['verdict']['decision']}  (basic check; pip install jsonschema for full)")

sys.exit(1 if errors else 0)
PY
