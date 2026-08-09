# Home Agent Dispatch Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with test-first checkpoints.

**Goal:** Turn the learning home composer into a deterministic supervisor that can complete bounded one-shot learning questions, route across workspaces, preview ambiguous workspace creation, and safely confirm medium-risk plan edits without persisting conversational content.

**Architecture:** Add an isolated `refineq.home` domain. Deterministic policy owns scope, strong/ambiguous long-term signals, explicit navigation, candidate ordering, and all write boundaries. Structured model calls are split into a five-second classifier and a fifteen-second answer generator; the latter receives no workspace state. Existing workspace and learning services remain the only mutation authorities. Home events and action receipts are content-free, owner-scoped records.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy, HMAC-SHA256, pytest; Next.js 15, React 19, TypeScript, Vitest, Playwright.

---

## Task 1: Deterministic policy and typed protocol

**Files:**
- Create: `src/refineq/home/__init__.py`
- Create: `src/refineq/home/models.py`
- Create: `src/refineq/home/policy.py`
- Test: `tests/unit/home/test_policy.py`
- Test: `tests/unit/home/test_models.py`
- Create: `tests/fixtures/home_dispatch_eval.json`

1. Write table-driven failing tests for explicit workspace commands, cross-space scheduling, evaluation requests, strong versus ambiguous new-workspace signals, direct-answer allow/deny boundaries, prompt injection, real-time/high-risk scope, duplicate names, and the eight-candidate limit.
2. Define strict Pydantic request/result union members, workspace summaries/targets/proposals, action previews, clarification options, and confirmation receipts.
3. Implement a pure `HomeRoutingPolicy` whose hard decisions cannot be upgraded or downgraded by model output.
4. Add a bilingual synthetic eval fixture and verify the rule baseline against it.
5. Run `python -m pytest tests/unit/home -q` and commit.

## Task 2: Read-only workspace preview and batch dispatch projections

**Files:**
- Modify: `src/refineq/storage/sql_store.py`
- Modify: `src/refineq/storage/learning.py`
- Modify: `src/refineq/knowledge/index.py`
- Modify: `src/refineq/workspaces/service.py`
- Test: `tests/unit/storage/test_sql_store.py`
- Test: `tests/integration/test_home_dispatch.py`

1. Write failing tests proving preview does not touch/create records and an eight-workspace summary load has a bounded database-read count.
2. Add owner-scoped record batch reads and batched material-status counts.
3. Split `WorkspaceService.resolve` into read-only `preview_resolution` and idempotent/stale-safe `commit_resolution`, keeping `/workspaces/resolve` compatible.
4. Build dispatch summaries by feeding projected plan/material/mastery fields into the existing `select_next_action` function, never by looping through `WorkspaceService.next_action`.
5. Run targeted storage/workspace/home integration tests and commit.

## Task 3: Model isolation, signed tokens, events, and home service

**Files:**
- Create: `src/refineq/home/intelligence.py`
- Create: `src/refineq/home/tokens.py`
- Create: `src/refineq/home/events.py`
- Create: `src/refineq/home/service.py`
- Test: `tests/unit/home/test_intelligence.py`
- Test: `tests/unit/home/test_tokens.py`
- Test: `tests/unit/home/test_events.py`
- Test: `tests/integration/test_home_dispatch.py`

1. Write failing tests for 500-character classifier isolation, answer-generator workspace isolation, model timeout fallback, unconfigured-model recovery, owner binding, expiry/tamper checks, no-content event serialization, direct-answer non-mutation, stale versions, and idempotent confirmation.
2. Implement separate structured classifier/answer transports and schemas. Validate model workspace IDs against the server candidate set.
3. Implement HMAC confirmation and continuation tokens backed by a persistent server key; bind owner, operation, target, proposal hash, state version/hash, expiry, and nonce.
4. Implement content-free home events and minimal action receipts. Event failures are best-effort and never fail the user result.
5. Implement dispatch orchestration for all six result kinds, deterministic cross-space ranking, strong-signal direct creation, ambiguous creation preview, reschedule/duration previews, and confirmed mutations through existing domain services.
6. Run all home unit/integration tests and commit.

## Task 4: API wiring and independent admin metrics

**Files:**
- Create: `src/refineq/api/routers/home.py`
- Modify: `src/refineq/api/app.py`
- Modify: `src/refineq/api/routers/admin.py`
- Modify: `src/refineq/operations/admin.py`
- Test: `tests/integration/test_home_dispatch.py`
- Test: `tests/integration/test_admin_auth.py`

1. Write failing API tests for request bounds, auth, owner isolation, dispatch/confirm contracts, unknown tools, model degradation, and metrics independence.
2. Wire classifier timeout `5s/0 retries`, answer timeout `15s/1 retry`, signer, repositories, service, and router into the app factory with injectable test transports.
3. Expose `POST /home/dispatch`, `POST /home/actions/confirm`, and an admin-only home-dispatch metrics endpoint that never contributes to learning metrics.
4. Run API and admin integration tests and commit.

## Task 5: Frontend single-result state machine and six cards

**Files:**
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/components/learning-home.tsx`
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/lib/i18n.ts`
- Modify: `apps/web/app/styles.css`
- Test: `apps/web/tests/contracts.test.ts`
- Test: `apps/web/tests/learning-home-direction.test.tsx`
- Test: `apps/web/tests/components.test.tsx`

1. Write failing contract and component tests for all six card types, one latest result, Enter/Shift+Enter, explicit-command-only auto-navigation, confirmation, retry/input retention, out-of-scope recovery, and stale response guards.
2. Add discriminated TypeScript result contracts and API methods accepting abort signals.
3. Replace `onResolve` with a local-memory dispatch state machine. New requests abort old ones and validate both auth token and request ID before applying results.
4. Render one accessible result card with a single primary action, optional secondary actions, proposal editing, manual recovery, model-unconfigured paths, and no browser/session storage.
5. Add responsive styles with 44px targets, focus transfer, `aria-live`, and reduced-motion behavior.
6. Run frontend unit tests and commit.

## Task 6: End-to-end migration, documentation, and full verification

**Files:**
- Modify: `apps/web/tests/e2e/learning-journey.spec.ts`
- Create: `docs/product/home-agent-dispatch.md`
- Modify: relevant operations/API documentation if contracts are listed there

1. Migrate the original one-sentence journey to an unambiguous time-constrained signal.
2. Add ambiguous preview/confirm and direct-answer-stays-home/refresh-clears E2E journeys.
3. Document product behavior, deterministic boundaries, data lifecycle, operator configuration, metrics, and recovery semantics.
4. Run `python -m pytest`, `python -m ruff check src tests`, frontend tests, ESLint, production build, and the relevant Playwright suite.
5. Inspect the complete diff for privacy, ownership, race, idempotency, mobile, and accessibility regressions; fix and rerun affected checks.
6. Request independent sub-agent review, address every high-confidence finding, rerun the full verification suite, and commit the final fixes.
7. Push the feature branch, create a ready PR, wait for checks, merge to `main`, and verify the remote main SHA and clean worktree.
