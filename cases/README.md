# Case specimens modeled on public incidents

Part VI of *Prove It Before Production* reads seven public incidents through
the book's model. Each directory here holds one small, replayable specimen for
one of those chapters. Run them with `make cases`; `tests/test_cases.py` also
checks that every check returns ALLOW once the missing evidence is supplied,
so none of them blocks unconditionally.

What these files are:

- **Illustrative.** Hosts, counts, digests, table names and timestamps are
  invented for teaching. Only the shape of the failure follows the cited
  public report.
- **Not reconstructions.** They do not describe the affected company's
  systems, and they make no claim that a check like this would have prevented
  the incident. The companies' own reports, linked in each `case.yaml`, are
  the authority on what happened.
- **Executable.** Each `case.yaml` names a check in `tools/check_cases.py`
  (the agent cases use the real `tools/asc_gate.py` with a case-local
  contract in `agent-2025/`) and the verdict it must produce.

| Case | Modeled on | Check | Expected |
| --- | --- | --- | --- |
| `gitlab-2017-restore` | GitLab.com database outage, January 2017 | `restore` | BLOCK `restore_unproved` |
| `knight-2012-fleet-parity` | Knight Capital, August 2012 (SEC order) | `fleet-parity` | BLOCK `fleet_drift` |
| `s3-2017-capacity-removal` | Amazon S3 us-east-1, February 2017 | `capacity-removal` | BLOCK `below_minimum_capacity` |
| `crowdstrike-2024-content-contract` | CrowdStrike Channel File 291, July 2024 | `content-contract` | BLOCK `field_beyond_supplied_inputs` |
| `facebook-2021-recovery-path` | Facebook backbone outage, October 2021 | `recovery-path` | BLOCK `audit_tool_unproven` |
| `gcp-2025-propagation` | Google Cloud Service Control, June 2025 | `propagation` | BLOCK `data_fails_consumer_schema` |
| `agent-2025-freeze` | Replit agent, July 2025 (public statements) | `agent-trace` | BLOCK `tool_not_allowed` |
| `agent-2025-no-freeze` | Replit agent, July 2025 (public statements) | `agent-trace` | REQUIRE_APPROVAL `approval_required` |

These cases are deliberately kept out of the agent scenario corpus
(`agents/scenarios/`), whose counts the book cites.
