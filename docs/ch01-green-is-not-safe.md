# Chapter 1 companion — Green is not safe

Mirror of the book’s opening example. Full prose: `../../drafts/ch01-production-is-a-terrible-test-environment.md`.

## Naive path

```text
PR: Upgrade PostgreSQL 15 → 16 for payments
terraform plan → CI green → policy pass → staging ok → merge → GitOps sync
```

## Evidence path (CHG-0042)

```text
change
  → reconstruct (graphs/payments-postgres.yaml)
  → rehearse (rehearsals/CHG-0042-postgres-upgrade.yaml)
  → verdict BLOCK
  → evidence/CHG-0042.json retained
```

```text
payments
   ↓
postgres
   ↓
PVC
   ↓
StorageClass fast-ssd-v1  →  proposed fast-ssd-v2
BLOCK
Reason:
StorageClass migration would invalidate
the tested recovery path (RP-0017).
Evidence:
evidence/CHG-0042.json
```

## Principle

**Unknown ≠ Safe.** Missing restore proof on the *target* configuration is not a warning—it is a stop.
