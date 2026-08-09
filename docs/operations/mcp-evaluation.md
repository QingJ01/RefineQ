# RefineQ MCP evaluation endpoint

This endpoint is a deliberately small product-evaluation surface. It operates only on one
resettable simulation owner and never reads or updates real learner mastery.

## Enable it safely

The endpoint is disabled by default. Set all of the following in the deployment secret store,
not in source control:

```text
REFINEQ_MCP_ENABLED=true
REFINEQ_MCP_EVALUATION_SECRET=<at least 32 random characters>
REFINEQ_MCP_ALLOWED_HOSTS=learn.example.com
```

Keep the default five-minute run TTL unless the evaluator genuinely needs more time. Rotate
the bearer secret after an evaluation window. Startup fails closed when MCP is enabled without
a strong secret or Host allowlist.

The public URL is `https://<host>/mcp`. Authentication is accepted only as:

```text
Authorization: Bearer <evaluation secret>
```

Query parameters and cookies are ignored. Do not place the secret in a URL, shell history,
client configuration committed to Git, screenshots, or support logs.

## Tool flow

1. `refineq_begin_demo(client_run_key)` resets and leases the simulation. Reusing the same key
   during an active run returns the same opaque run token.
2. `refineq_get_learning_context(run_id)` reads the bounded baseline without creating events or
   changing a record version.
3. `refineq_search_materials(run_id, query, limit)` returns clipped excerpts and citation IDs.
4. `refineq_get_practice_task(run_id, request_id, ...)` returns one material-grounded task.
5. `refineq_submit_answer(..., attempt_id, expected_state_version)` grades once, changes only
   sandbox mastery, completes the run, and remains replayable for the idempotency retention
   window.

The evaluation task requests an exact three-field JSON answer derived from the fixed cited
example. This narrow response contract lets the deterministic fallback verify typed values and
fail closed instead of awarding mastery from prompt echoes, prose filler, or keyword stuffing.

Use a new `client_run_key` for a second run. Only one run may be seeding or active globally;
other callers receive `demo_busy`. Expired or completed runs reject further reads and writes,
except an exact replay of a completed answer submission.

Every reset binds a private run fence to the learning record. Model results are revalidated
against that fence and the durable lease immediately before commit, so an expired or superseded
run cannot write into its successor. Public question IDs are also bound to the run and are not
accepted by later runs. The sandbox uses a fixed logical study date for its plan projection;
wall-clock time is used only for leases, retention, and operational timestamps. This makes the
initial public context reproducible across runs without weakening TTL enforcement.

Terminal run and idempotency rows are retained for the configured idempotency window and then
removed. Each new run generation has a fresh random nonce inside its server-derived token, so
reusing a client key after retention cannot make an old run token valid again.

The fixed material is maintained by the server. Phase A has no material upload, plan mutation,
coach, prompt, resource, task, or user OAuth surface.

When the platform model integration is configured and healthy, question generation and optional
grading feedback use that integration with a 15-second request timeout. The server-owned typed
validator remains authoritative for pass/fail and mastery evidence in every mode. Any model error
or timeout falls back to the server-authored deterministic question/key and feedback. Embedding
calls use a separate four-second MCP budget and degrade to lexical retrieval. Returned `mode`,
`grading_mode`, and `retrieval_mode` always report the path that produced the question and
feedback.

## Observability

The API keeps bounded, content-free counters, response sizes, and P50/P95/P99 latency samples in
`app.state.mcp_telemetry`; it also counts result modes, stable error codes, protocol versions,
anonymous client classes, and idempotency replays. Normal service logs contain only the tool,
outcome, stable error code, duration, correlation ID, and exception type. Neither telemetry nor
logs retain bearer/run tokens, client keys, owner IDs, emails, prompts, answers, or material text.
Metrics are process-local and reset on restart, so production deployments should export the
snapshot through their existing private monitoring integration rather than adding it to the MCP
tool surface.

## Stable error handling

Tool failures set MCP `isError=true` and return a structured `error` with a stable code,
retryability, optional retry delay, and next action. Common codes are `invalid_input`,
`unauthorized`, `rate_limited`, `demo_busy`, `run_not_found`, `run_expired`, `run_completed`,
`idempotency_conflict`, `state_conflict`, `material_required`, and `internal_error`.
Internal exception messages, bearer tokens, learner answers, and material contents are not
written to operational logs.

## Public smoke test

From a trusted machine with the pinned dependencies installed:

```powershell
$env:REFINEQ_MCP_URL = "https://learn.example.com/mcp"
$env:REFINEQ_MCP_EVALUATION_SECRET = "<secret from the deployment secret store>"
python scripts/mcp_smoke.py --require-mode ai
Remove-Item Env:REFINEQ_MCP_EVALUATION_SECRET
```

Success requires five exact tools, output-schema-valid structured content for every response,
at least one material search result, a non-empty search → task → grade citation chain, material
grounding, a passing grade, a sandbox mastery change, final status `completed`, exact idempotency
replays, and a clean second-run reset. The script exits non-zero if any criterion is false and
does not print the bearer or run token.

Before release, perform a separate fallback drill by temporarily disabling the sandbox model
integration in a controlled deployment and running:

```powershell
python scripts/mcp_smoke.py --require-mode fallback
```

Restore the intended model configuration afterward and repeat the AI drill. Neither local drill
replaces final-host HTTPS, MCP Inspector, and organizer-client verification.

## Disable and rotate

Set `REFINEQ_MCP_ENABLED=false` and redeploy. Caddy will still forward `/mcp`, but the API has no
matching route and returns 404. Rotate the old bearer secret, then remove it from the runtime
environment. Existing hashed run and idempotency rows contain no recoverable raw token and age
out according to their retention policy.
