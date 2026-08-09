# RefineQ maturity improvement log

## Cycle 1 — transport-independent rate-limit boundary

- Dimension: code structure and architecture clarity
- Result: PASS; material improvement and single focus independently confirmed
- Change: extracted `SlidingWindowRateLimiter` into `refineq.rate_limits`, rewired API and MCP
  consumers, and added an architecture contract forbidding `mcp -> api`
- Verification: focused regression set 20 passed; full Python suite 606 passed, 3 skipped; Ruff,
  format, and diff checks passed
- Independent score change: first accepted baseline, overall 91
- Review finding retained for the next architecture rotation: make the static boundary check aware
  of relative imports and nested MCP packages
- Files/logic now considered recently improved: shared rate-limit placement, API/MCP limiter import
  direction, and the direct MCP-to-API architecture boundary

## Cycle 2 — trusted mastery-subject journey

- Dimension: functional completeness
- Result: PASS; no P0/P1 findings and the independently reviewed overall score reached 96
- Change: replaced free-form topic-label trust inference with persisted server-owned
  `answer_key_subject` provenance, an exact material-topic registry, subject-bound grading
  snapshots, explicit legacy reauthorization, and transaction-time authority checks
- Grading boundary: generated free-text keys are coaching context only; deterministic fallback
  never updates mastery. The authoritative grader is isolated from generated keys and raw study
  materials, returns exact learner-answer evidence spans, and is checked for subject relevance,
  substance, prompt echo, and current snapshot provenance before BKT mutation
- Functional journey: composed library upload, attach, material analysis, targeted plan, grounded
  API question, structured grading, BKT update, and plan-session completion for the approved
  feedback-control path; compound-interest and natural definition-first subjects also verified
- Compatibility: short ASCII (`AI`, `ML`, `C++`), single Han, Japanese, and Korean subjects work;
  punctuation is treated as a token boundary and substring false positives such as `training -> AI`
  remain rejected
- Verification: focused gate 118 passed; full Python suite 648 passed, 3 skipped; frontend 205
  passed plus ESLint and Next build; Ruff, format, diff, MCP compatibility, and adversarial review
  passed
- Independent score change: overall 91 -> 96; maturity stop condition reached
- Non-blocking P2 follow-ups: persist an explicit provenance-kind enum and automate the already
  fault-injected subject-change concurrency barrier
- Files/logic now considered recently improved: learning subject authority, generated-question
  provenance, grading evidence authorization, material-targeted plan trust, and multilingual subject
  matching
