# Complete Frontend Interactions Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn RefineQ's current one-way learning MVP into a complete, recoverable interaction loop across workspaces, plans, practice, materials, Agent chat, authentication, administration, routing, i18n, and accessibility.

**Architecture:** Keep the FastAPI and Next.js stack. Add small owner-scoped resource endpoints to existing repositories, make browser URLs and server data the durable state, and keep transient UI state local to focused components. Reuse the current RefineQ visual system while adding interaction layers, drawers, status rows, confirmations, and live feedback.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, repository-backed SQLite/PostgreSQL storage, Next.js 16 App Router, React 19, TypeScript, Vitest, Playwright.

---

### Task 1: Durable interaction contracts

**Files:**
- Modify: `src/refineq/workspaces/models.py`
- Modify: `src/refineq/workspaces/service.py`
- Modify: `src/refineq/storage/workspaces.py`
- Modify: `src/refineq/learning/service.py`
- Modify: `src/refineq/storage/learning.py`
- Test: `tests/integration/test_workspace_journey.py`
- Test: `tests/integration/test_learning_journey.py`

**Steps:**
1. Add failing tests for workspace update/archive/delete and owner isolation.
2. Run focused tests and confirm the missing endpoints/repository methods fail.
3. Implement owner-scoped lifecycle methods and API schemas.
4. Add failing tests for plan-session complete/defer and persisted progress.
5. Implement plan task mutation without changing the generated plan contract.
6. Run focused tests until green.

### Task 2: Material management contracts

**Files:**
- Modify: `src/refineq/api/routers/materials.py`
- Modify: `src/refineq/knowledge/index.py`
- Modify: `src/refineq/storage/sql_store.py`
- Test: `tests/integration/test_material_upload.py`

**Steps:**
1. Add failing tests for list/search/detail/download/delete, invalid ownership, and missing material errors.
2. Verify failures come from missing routes.
3. Implement owner/workspace-scoped material operations and safe original-file responses.
4. Run the material integration suite until green.

### Task 3: Agent sessions and cancellation-ready API

**Files:**
- Modify: `src/refineq/api/routers/agent.py`
- Modify: `src/refineq/agent/service.py`
- Modify: `src/refineq/storage/sessions.py`
- Test: `tests/integration/test_agent_chat.py`

**Steps:**
1. Add failing tests for session list, transcript retrieval, deletion/new conversation, workspace isolation, and newest-first ordering.
2. Verify the routes fail before implementation.
3. Add immutable public session/message response models and owner-scoped service methods.
4. Implement the routes and run focused tests until green.

### Task 4: Password recovery

**Files:**
- Modify: `src/refineq/api/routers/auth.py`
- Modify: `src/refineq/auth.py`
- Modify: `src/refineq/storage/sql_store.py`
- Test: `tests/integration/test_auth.py`

**Steps:**
1. Add failing tests for non-enumerating reset requests, one-time expiry-bound tokens, password update, and token reuse rejection.
2. Verify the new tests fail for missing behavior.
3. Implement hashed reset-token persistence and reset endpoints.
4. Run authentication tests until green.

### Task 5: Frontend state, URL, locale, and routing feedback

**Files:**
- Create: `apps/web/app/learn/[workspaceId]/[section]/page.tsx`
- Create: `apps/web/components/learning-route.tsx`
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/components/learning-home.tsx`
- Modify: `apps/web/lib/session.ts`
- Modify: `apps/web/lib/i18n.ts`
- Modify: `apps/web/lib/api.ts`
- Test: `apps/web/tests/contracts.test.ts`
- Test: `apps/web/tests/components.test.tsx`

**Steps:**
1. Add failing tests for valid section parsing, locale persistence, route-result projection, active navigation semantics, and functional recent-learning navigation.
2. Run Vitest and confirm expected failures.
3. Implement durable learning URLs, independent request states, route decision UI, correction actions, and locale synchronization.
4. Run focused frontend tests until green.

### Task 6: Practice, plans, progress, and evidence

**Files:**
- Modify: `apps/web/components/practice-card.tsx`
- Modify: `apps/web/components/plan-timeline.tsx`
- Modify: `apps/web/components/evidence-ledger.tsx`
- Create: `apps/web/components/source-drawer.tsx`
- Create: `apps/web/components/progress-insights.tsx`
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/view-models.ts`
- Test: `apps/web/tests/components.test.tsx`

**Steps:**
1. Add failing semantic tests for difficulty, generation/grading mode, source disclosure, plan task actions, topic mastery, recommendation, and evidence details.
2. Verify the tests fail for missing UI.
3. Implement the components using existing design tokens and API data.
4. Run component tests until green.

### Task 7: Material interaction UI

**Files:**
- Modify: `apps/web/components/material-dropzone.tsx`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/lib/upload-flow.ts`
- Modify: `apps/web/app/styles.css`
- Test: `apps/web/tests/components.test.tsx`
- Test: `apps/web/tests/contracts.test.ts`

**Steps:**
1. Add failing tests for drag/drop state, file validation, queue projection, retry/cancel, search, detail/download/delete, and real status labels.
2. Verify the tests fail.
3. Implement the upload queue and material management interactions.
4. Run frontend tests until green.

### Task 8: Durable Agent UI

**Files:**
- Modify: `apps/web/components/agent-panel.tsx`
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/app/styles.css`
- Test: `apps/web/tests/components.test.tsx`

**Steps:**
1. Add failing tests for optimistic user messages, loading status, stop, copy, retry, new conversation, history restoration, and source details.
2. Verify the tests fail.
3. Implement lifted session state, AbortController propagation, session history, message actions, and source drawer.
4. Run component tests until green.

### Task 9: Safe administration and complete authentication UI

**Files:**
- Modify: `apps/web/components/admin-console.tsx`
- Modify: `apps/web/components/auth-panel.tsx`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/app/styles.css`
- Test: `apps/web/tests/components.test.tsx`
- Test: `apps/web/tests/e2e/learning-journey.spec.ts`

**Steps:**
1. Add failing tests for dirty state, navigation warning, saved-only testing, save-and-test, stable success feedback, load-error lockout, password reveal, autocomplete, rule hints, and reset flow.
2. Verify failures.
3. Implement the protected admin form workflow and recovery UI.
4. Run frontend tests until green.

### Task 10: Accessibility and end-to-end verification

**Files:**
- Modify: `apps/web/app/layout.tsx`
- Modify: `apps/web/app/styles.css`
- Modify: `apps/web/tests/e2e/learning-journey.spec.ts`

**Steps:**
1. Add Playwright assertions for URLs/history, keyboard focus, live regions, mobile accessible names, destructive confirmations, and state recovery.
2. Run Playwright and confirm new assertions expose missing behavior.
3. Complete accessibility, responsive, and focus-management fixes.
4. Run `python -m pytest -q`, `npm test`, `npm run lint`, `npm run build`, and `npm run test:e2e`.
5. Capture and inspect desktop/mobile screenshots from the current run.
6. Audit every item in the design document against code and runtime evidence.
