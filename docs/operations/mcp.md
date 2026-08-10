# MCP operations

The MCP endpoint is an account-bound evaluation simulation. The server binds every
request to one configured RefineQ account; clients do not send Bearer credentials.
Follow the complete [evaluation runbook](./mcp-evaluation.md) for configuration, the five-tool
flow, failure recovery, secret rotation, observability, and the independent HTTPS smoke test.

Protocol and client evidence is maintained separately in the
[compatibility record](./mcp-compatibility.md).
