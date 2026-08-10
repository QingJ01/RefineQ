# MCP Phase A compatibility record

Last verified locally: 2026-08-10.

## Locked protocol and SDK

- Official Python SDK: `mcp==2.0.0`, locked with hashes in both runtime lock files.
- Preferred protocol: `2026-07-28`, negotiated with `server/discover`.
- Compatibility path: the pinned SDK also accepts the prior stable `2025-11-25`
  initialization flow.
- Transport: stateless Streamable HTTP at exactly `/mcp`.
- Exposed capabilities: Tools only. The server intentionally does not advertise Tasks,
  Elicitation, Resources, Prompts, logging, or subscriptions.

## Evidence captured in the repository

- An official in-memory SDK client discovers exactly five tools and validates every output
  schema.
- A real Streamable HTTP wire test exercises `server/discover`, DNS-rebinding Host checks,
  and the exact `/mcp` path.
- `scripts/mcp_smoke.py` is an independent official SDK client that executes the full public
  flow through HTTP(S), validates every structured result against its advertised output schema,
  verifies the search → task → grade citation chain, rejects incomplete loops, and can require
  either the AI or deterministic fallback generation-and-grading path.
- Caddy preserves `/mcp`, disables response buffering for streaming, and bounds the request
  body.

No public HTTPS hostname, MCP Inspector session, or organizer-specific competition client was
available in this repository environment, so those compatibility claims remain explicitly
unverified. Before enabling the endpoint for an evaluation, run the smoke script against the
final HTTPS hostname, run both `--require-mode ai` and `--require-mode fallback` drills, verify
the five-tool flow in MCP Inspector and the target client, and retain those outputs with the
release record. A local or in-memory pass is not evidence that DNS, TLS, or the public reverse
proxy is configured correctly.
