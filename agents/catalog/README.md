# Tool catalog

`tools.json` is the approved MCP-style tool catalog for `platform-agent`. Its sha256 is pinned in
`../contracts/demo-agent.policy.yaml` (`spec.catalog.sha256`). The gate hashes whatever catalog the
runtime presents and returns BLOCK on any mismatch.

`tools.poisoned.json` is a deliberately poisoned copy used by the `mcp_tool_poisoning` scenario: one
tool description tells the model to read secrets. Only the description text differs, which is the point:
an allowlist by tool name alone would not notice.
