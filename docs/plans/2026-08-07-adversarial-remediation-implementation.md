# Adversarial Review Remediation Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove every confirmed security, learning-integrity, state-continuity, storage-consistency, and release-gate defect from the adversarial review.

**Architecture:** Keep FastAPI/SQLAlchemy and Next.js as the single stack. Make question generation an idempotent mutation, persist resumable learning-session state on the server, make grading and scheduling conservative when model evidence is unavailable, and bind every stored blob to the backend that created it. Preserve the existing owner-scoped repository boundary and add fail-safe compensation instead of broad rewrites.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, PostgreSQL/pgvector, Pydantic, Next.js 16, React 19, TypeScript, pytest, Vitest, Playwright.

---

### Task 1: Close account-recovery and session-lifecycle vulnerabilities

**Files:**
- Modify: `src/refineq/config.py`
- Modify: `src/refineq/database/schema.py`
- Modify: `src/refineq/identity/service.py`
- Modify: `src/refineq/api/routers/auth.py`
- Modify: `infra/compose.yml`
- Modify: `.env.example`
- Test: `tests/integration/test_auth.py`

**Steps:**
1. Add failing tests proving reset tokens are hidden by default, unknown and existing accounts return the same public shape, and pre-reset JWTs are rejected after a password change.
2. Run the focused authentication tests and confirm the expected failures.
3. Default token exposure to false, add an explicit development-only opt-in, and compare JWT issue time with the user's credential-change time.
4. Run authentication tests and verify all pass.

### Task 2: Make question creation an idempotent mutation

**Files:**
- Modify: `src/refineq/api/limits.py`
- Modify: `src/refineq/api/routers/learning.py`
- Modify: `src/refineq/config.py`
- Modify: `src/refineq/learning/service.py`
- Modify: `apps/web/lib/api.ts`
- Test: `tests/integration/test_ai_practice.py`
- Test: `tests/unit/api/test_limits.py`
- Test: `apps/web/tests/contracts.test.ts`

**Steps:**
1. Add failing tests for POST-only question generation, read-only GET behavior, idempotent retries, and bounded question history.
2. Verify the new tests fail for the intended reasons.
3. Convert question generation to POST, cap persisted question history/saved references, and retain compatibility only as a non-mutating pending-question read. Do not add model quotas or commercial billing controls for this hackathon build.
4. Update the web client contract and verify focused backend/frontend tests pass.

### Task 3: Make fallback grading, plans, routing, and prompts trustworthy

**Files:**
- Modify: `src/refineq/learning/intelligence.py`
- Modify: `src/refineq/learning/planning.py`
- Modify: `src/refineq/workspaces/routing.py`
- Modify: `src/refineq/agent/context.py`
- Modify: `src/refineq/agent/service.py`
- Test: `tests/unit/learning/test_intelligence.py`
- Test: `tests/unit/learning/test_planning_and_evidence.py`
- Test: `tests/unit/workspaces/test_routing.py`
- Test: `tests/unit/agent/test_context.py`

**Steps:**
1. Add adversarial tests for keyword repetition, per-topic phase order, cross-product/operations-research/biological-growth routing, and goal prompt injection.
2. Confirm each regression test fails.
3. Make deterministic grading conservative and rubric-specific, advance activity phase per topic, use token-aware routing with ambiguity fallback, and keep user-controlled goal/plan/materials outside the fixed system policy.
4. Run focused unit tests and verify green.

### Task 4: Persist and restore the complete learning session

**Files:**
- Modify: `src/refineq/learning/service.py`
- Modify: `src/refineq/workspaces/service.py`
- Modify: `src/refineq/api/routers/learning.py`
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/components/learning-session-canvas.tsx`
- Modify: `apps/web/lib/session.ts`
- Test: `tests/integration/test_workspace_journey.py`
- Test: `apps/web/tests/components.test.tsx`
- Test: `apps/web/tests/contracts.test.ts`

**Steps:**
1. Add failing tests for pending-question/mode restoration, stable attempt IDs, draft preservation, topic title alignment, and navigation from Path/Progress to Today.
2. Verify failures.
3. Return pending question and latest result in snapshots, persist workspace/question draft metadata locally, reuse attempt/turn IDs until success, navigate before exposing generated work, and ignore stale async responses.
4. Run focused backend and frontend tests.

### Task 5: Give the contextual coach real, server-validated session context

**Files:**
- Modify: `src/refineq/agent/service.py`
- Modify: `src/refineq/api/routers/agent.py`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/components/session-coach.tsx`
- Test: `tests/integration/test_agent_chat.py`
- Test: `apps/web/tests/contracts.test.ts`

**Steps:**
1. Add failing tests proving the coach receives the server-owned pending question, learning mode, stage, and a bounded untrusted draft while rejecting cross-workspace question references.
2. Confirm failures.
3. Define a bounded context DTO, rehydrate trusted question data server-side, mark drafts untrusted, and reuse coach turn IDs across retries.
4. Verify focused tests pass.

### Task 6: Make review scheduling and plan completion real

**Files:**
- Modify: `src/refineq/learning/service.py`
- Modify: `src/refineq/learning/models.py`
- Modify: `apps/web/components/learning-session-canvas.tsx`
- Test: `tests/integration/test_learning_journey.py`
- Test: `apps/web/tests/components.test.tsx`

**Steps:**
1. Add failing tests that an answer links to and completes the active plan session and schedules a review from actual performance.
2. Confirm failures.
3. Persist review scheduling data in the same learning-state mutation and render only that server state.
4. Verify focused tests pass.

### Task 7: Bind material records to storage backends and make deletion recoverable

**Files:**
- Modify: `src/refineq/database/schema.py`
- Modify: `src/refineq/knowledge/index.py`
- Modify: `src/refineq/integrations/object_storage.py`
- Modify: `src/refineq/api/routers/materials.py`
- Modify: `src/refineq/workspaces/service.py`
- Test: `tests/integration/test_material_upload.py`
- Test: `tests/unit/integrations/test_object_storage.py`

**Steps:**
1. Add failing tests for local-to-S3 configuration changes, failed index deletion, and workspace deletion retries.
2. Confirm failures.
3. Persist a backend locator with each material, resolve reads/deletes through that locator, and delete metadata first with a recoverable tombstone/compensation path.
4. Verify focused tests pass on SQLite and PostgreSQL-compatible paths.

### Task 8: Restore release gates, security headers, localization, and regression coverage

**Files:**
- Modify: `infra/Caddyfile`
- Modify: `apps/web/tests/e2e/learning-journey.spec.ts`
- Modify: `src/refineq/learning/service.py`
- Modify: `apps/web/components/evidence-ledger.tsx`
- Format: `src/`, `tests/`, `scripts/`

**Steps:**
1. Add assertions for security headers and localized evidence; migrate the skipped legacy journey into active focused scenarios.
2. Verify the new assertions fail.
3. Add CSP/frame protection, store structured evidence copy, localize it in the client, and remove the broad E2E skip.
4. Run Ruff check/format, all Python tests, frontend tests/lint/build, secret scan, dependency audit, and E2E.

### Task 9: Final review and publish

**Files:**
- Review: all changed files

**Steps:**
1. Inspect `git diff --check`, `git status`, and the full staged diff for unrelated files or secrets.
2. Run the complete verification matrix again from a clean command invocation.
3. Commit with `QingJ01 <qingj1314@163.com>`.
4. Push the verified commit directly to `origin/main`, as explicitly requested.
5. Confirm the remote head and GitHub Actions status.
