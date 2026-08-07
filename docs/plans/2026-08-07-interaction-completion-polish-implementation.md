# Interaction Completion Polish Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete RefineQ's remaining practice, source, confirmation, material, Agent, administration, and page-state interactions without changing its architecture or visual identity.

**Architecture:** Extend the owner-scoped learning record with question sequence/history and saved-question references, expose only public question data, and keep targeted practice generation behind the existing workspace learning routes. Add focused React interaction primitives and region-level busy state while preserving the current Next.js route structure and CSS system.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLite/PostgreSQL repository abstraction, Next.js 16 App Router, React 19, TypeScript, Vitest, Playwright.

---

### Task 1: Public grounded-practice contract

**Files:**
- Modify: `src/refineq/learning/service.py`
- Modify: `src/refineq/api/routers/learning.py`
- Modify: `tests/integration/test_ai_practice.py`
- Modify: `tests/integration/test_learning_journey.py`

**Steps:**
1. Add failing tests that request a chosen topic/difficulty, replace a pending question, receive unique IDs, and receive public source records without an expected answer.
2. Run the focused tests and confirm failures are caused by missing query parameters and response fields.
3. Add sequence-backed question generation, topic/difficulty validation, replace semantics, and public source projection.
4. Re-run the focused tests until green and commit.

### Task 2: Durable saved questions

**Files:**
- Modify: `src/refineq/learning/service.py`
- Modify: `src/refineq/api/routers/learning.py`
- Modify: `src/refineq/workspaces/service.py`
- Modify: `tests/integration/test_learning_journey.py`
- Modify: `tests/integration/test_workspace_journey.py`

**Steps:**
1. Add failing tests for save, unsave, list, snapshot restoration, unknown question rejection, and owner isolation.
2. Verify the endpoint and snapshot assertions fail.
3. Store private question history and saved timestamps inside each learning record; expose immutable public saved-question models.
4. Run focused tests until green and commit.

### Task 3: Practice UI and learning entry points

**Files:**
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/lib/i18n.ts`
- Modify: `apps/web/components/practice-card.tsx`
- Modify: `apps/web/components/plan-timeline.tsx`
- Modify: `apps/web/components/progress-insights.tsx`
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/tests/components.test.tsx`
- Modify: `apps/web/tests/contracts.test.ts`

**Steps:**
1. Add failing component and API tests for adaptive/1–5 difficulty, skip, same-topic practice, save/unsave, source disclosure, plan start, recommendation start, and independent busy state.
2. Run Vitest and verify expected failures.
3. Implement the API client and state flow, then render the controls using the current visual tokens.
4. Run frontend tests until green and commit.

### Task 4: Accessible confirmation and inline editing

**Files:**
- Create: `apps/web/components/confirm-dialog.tsx`
- Modify: `apps/web/components/learning-home.tsx`
- Modify: `apps/web/components/material-dropzone.tsx`
- Modify: `apps/web/components/agent-panel.tsx`
- Modify: `apps/web/components/admin-console.tsx`
- Modify: `apps/web/tests/components.test.tsx`
- Modify: `apps/web/tests/contracts.test.ts`

**Steps:**
1. Add failing tests proving no application action relies on `window.prompt` or application-navigation `window.confirm`, and proving the shared dialog has accessible semantics.
2. Confirm the tests fail against current components.
3. Add the reusable dialog, inline workspace rename, destructive confirmations, and custom unsaved-navigation confirmation while retaining `beforeunload` for browser closure.
4. Run frontend tests until green and commit.

### Task 5: Materials, Agent, and disclosure polish

**Files:**
- Modify: `apps/web/components/material-dropzone.tsx`
- Modify: `apps/web/components/agent-panel.tsx`
- Modify: `apps/web/components/source-drawer.tsx`
- Modify: `apps/web/lib/i18n.ts`
- Modify: `apps/web/app/styles.css`
- Modify: `apps/web/tests/components.test.tsx`

**Steps:**
1. Add failing tests for search empty/clear, metadata disclosure, queue cleanup, deletion progress, suggested prompts, localized model status, source empty state, and dialog focus behavior.
2. Verify the focused tests fail.
3. Implement the missing states and accessibility behavior without adding dependencies.
4. Run frontend tests until green and commit.

### Task 6: Route-level loading and recovery pages

**Files:**
- Create: `apps/web/app/loading.tsx`
- Create: `apps/web/app/error.tsx`
- Create: `apps/web/app/not-found.tsx`
- Modify: `apps/web/app/layout.tsx`
- Modify: `apps/web/app/styles.css`
- Modify: `apps/web/tests/contracts.test.ts`

**Steps:**
1. Add failing contract tests for loading, error, and not-found routes plus complete metadata.
2. Verify failures.
3. Implement branded, responsive recovery states and metadata.
4. Run frontend tests, lint, and build until green; commit.

### Task 7: End-to-end verification and delivery

**Files:**
- Modify: `apps/web/tests/e2e/learning-journey.spec.ts`

**Steps:**
1. Add Playwright coverage for selected difficulty, unique skipped question, source drawer, saved-question restoration, plan/recommendation practice, custom destructive confirmation, and custom admin navigation guard.
2. Run the new scenarios and fix only failures reproduced by the tests.
3. Run `python -m pytest -q`, `python -m ruff check src tests`, `npm test`, `npm run lint`, `npm run build`, and `npm run test:e2e`.
4. Inspect desktop/mobile screenshots, run secret/legacy-name and `git diff --check` audits, commit the final test updates, and push `main`.
