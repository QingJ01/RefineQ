# Final Demo Remediation Design

The release fix keeps the existing MCP and Agent boundaries intact while making their success
semantics honest under disconnects and concurrent browser tabs. For MCP, the bearer gateway will
cache exactly the ASGI messages it consumes while inspecting the request body, replay those messages
once, and then delegate subsequent reads to the original `receive`. This preserves partial-body and
disconnect events without changing authentication, rate limiting, or the downstream MCP server.

For Agent practice adjustments, three approaches were considered. Comparing only the returned topic
and difficulty in the browser would detect some no-ops but would leave the server race intact. An
action-specific execution endpoint would be the strongest long-term abstraction, but it duplicates
the existing question-generation API immediately before the demo submission. The selected approach
adds the learning record version observed when the deterministic proposal is created. The browser
echoes that version when applying the proposal, and `LearningService.next_question` checks it while
holding the existing question-generation lock. Idempotent replays are checked first, so a successfully
applied action remains safely retryable; a first execution against changed state fails with HTTP 409
instead of returning an unrelated pending question with HTTP 200.

The browser test will exercise the visible coach flow with a non-null `adjust_practice` proposal and
verify the action request, replacement question, and applied state. The material-search control will
receive a localized accessible name plus a stable `name` and non-auth autocomplete hint. Deployment
uses the repository's existing Docker Compose topology, preserving the server `.env` and volumes;
post-deploy checks cover readiness, public HTTPS, security headers, the learner page, and MCP routing.
