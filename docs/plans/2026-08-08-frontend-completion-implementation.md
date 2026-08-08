# RefineQ Frontend Completion Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn every item in the 2026-08-08 frontend audit into a tested, production-usable learner or administrator capability.

**Architecture:** Deliver owner-scoped vertical slices through the existing FastAPI service/repository boundary and the Next.js same-origin API client. Reuse existing learning records for workspace-local projections, SQL tables for queryable account/operations data, and the established RefineQ component/tokens system for UI.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy, SQLite/PostgreSQL, Next.js 16, React 19, TypeScript, Vitest, Playwright.

---

### Task 1: Localized API errors and capability status

**Files:**
- Create: `apps/web/lib/error-messages.ts`
- Modify: `apps/web/lib/i18n.ts`
- Modify: `apps/web/components/auth-panel.tsx`
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/components/session-coach.tsx`
- Test: `apps/web/tests/error-messages.test.ts`
- Test: `apps/web/tests/components.test.tsx`

**Step 1: Write failing tests**

Add assertions that `invalid_credentials`, `model_not_configured`, `material_quota`, and unknown errors render locale-appropriate copy, and that the coach exposes `onConfigure` only to administrators.

```ts
expect(localizeApiError(new ApiError(401, "invalid_credentials", "Invalid"), "zh"))
  .toBe("邮箱或密码错误");
expect(screen.getByTestId("coach-configure-model")).toBeTruthy();
```

**Step 2: Verify RED**

Run: `npm test -- error-messages.test.ts components.test.tsx`
Expected: FAIL because the mapper and recovery action do not exist.

**Step 3: Implement minimal behavior**

Create a typed error-code dictionary with a safe unknown fallback. Route all learner and auth API errors through it. Extend `SessionCoach` with `modelConfigured`, `isAdmin`, `onConfigure`, and an explicit deterministic-fallback message.

**Step 4: Verify GREEN**

Run the focused tests, then `npm test`.

**Step 5: Commit**

Commit: `fix: localize errors and expose agent recovery`

### Task 2: Mount the complete workspace Agent

**Files:**
- Modify: `apps/web/components/agent-panel.tsx`
- Modify: `apps/web/components/learning-session-canvas.tsx`
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/app/styles.css`
- Modify: `apps/web/lib/types.ts`
- Test: `apps/web/tests/components.test.tsx`
- Test: `apps/web/tests/contracts.test.ts`

**Step 1: Write failing tests**

Render a workspace and assert that conversation history, new conversation, retry, source drawer, and model setup state are reachable from the Today experience.

**Step 2: Verify RED**

Run: `npm test -- components.test.tsx contracts.test.ts`
Expected: FAIL because `AgentPanel` is not mounted by a production component.

**Step 3: Implement minimal behavior**

Mount `AgentPanel` as a collapsible full-coach surface linked from `SessionCoach`. Pass workspace ID, role, locale, and settings navigation. Keep the compact coach for in-step questions, but make session history visible and persistent via existing APIs.

**Step 4: Verify GREEN and commit**

Run focused tests and commit `feat: connect workspace agent history`.

### Task 3: Enforce inspectable learning provenance

**Files:**
- Modify: `src/refineq/learning/service.py`
- Modify: `src/refineq/learning/intelligence.py`
- Modify: `src/refineq/learning/models.py`
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/components/learning-session-canvas.tsx`
- Modify: `apps/web/components/source-drawer.tsx`
- Test: `tests/integration/test_ai_practice.py`
- Test: `tests/integration/test_learning_journey.py`
- Test: `apps/web/tests/components.test.tsx`

**Step 1: Write failing tests**

Test two cases: retrieved material produces `grounding="material"` plus sources; no retrieval produces `grounding="general"` and copy that does not claim uploaded evidence.

```python
assert question.grounding == "material"
assert question.sources
assert all(source.material_id for source in question.sources)
```

**Step 2: Verify RED**

Run the two focused Python tests and confirm the missing field/claim failure.

**Step 3: Implement minimal behavior**

Add a grounding discriminator to public questions and answer results. Filter sources through the current retrieval result only. Generate generic fallback wording when sources are empty. Render the badge and source action in both practice and feedback.

**Step 4: Verify GREEN and commit**

Run Python and frontend focused tests. Commit `feat: make practice provenance explicit`.

### Task 4: Replace the false workspace switcher

**Files:**
- Create: `apps/web/components/workspace-switcher.tsx`
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/app/styles.css`
- Test: `apps/web/tests/components.test.tsx`
- Test: `apps/web/tests/e2e/learning-journey.spec.ts`

**Step 1: Write a failing interaction test**

Assert that activating `workspace-switcher` opens a menu, selecting another workspace navigates directly to its Today route, and Escape restores focus.

**Step 2: Verify RED**

Run the component test and confirm the existing Link navigates home.

**Step 3: Implement minimal behavior**

Use a button with `aria-haspopup="menu"`, roving focus, workspace progress summaries, an explicit “all spaces” link, and direct route navigation.

**Step 4: Verify GREEN and commit**

Commit `fix: implement real workspace switching`.

### Task 5: Editable and regenerable learning plans

**Files:**
- Modify: `src/refineq/learning/service.py`
- Modify: `src/refineq/api/routers/learning.py`
- Modify: `src/refineq/workspaces/service.py`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/lib/types.ts`
- Create: `apps/web/components/plan-settings.tsx`
- Modify: `apps/web/components/plan-timeline.tsx`
- Modify: `apps/web/components/study-workspace.tsx`
- Test: `tests/integration/test_workspace_journey.py`
- Test: `tests/unit/learning/test_planning_and_evidence.py`
- Test: `apps/web/tests/components.test.tsx`
- Test: `apps/web/tests/contracts.test.ts`

**Step 1: Write failing backend tests**

Define `PlanUpdateRequest(goal, exam_at, daily_minutes, topic_order, regenerate)` and assert an owner can atomically update it, sessions are regenerated only when requested, completed sessions are preserved when possible, and another owner receives 404.

**Step 2: Verify RED**

Run the focused Python tests.

**Step 3: Implement backend and verify GREEN**

Add `PUT /workspaces/{id}/learning/plan`, validate timezone/minutes/topic membership, update workspace goal when changed, rebuild the plan through `build_study_plan`, and return the new `StudyPlan`.

**Step 4: Write failing frontend tests**

Assert editing, validation, cancel, save, and regenerate confirmation behavior.

**Step 5: Implement UI and verify GREEN**

Add a settings panel above the timeline with date, minutes, topic ordering, reason copy, and a destructive regeneration confirmation.

**Step 6: Commit**

Commit `feat: add editable adaptive plans`.

### Task 6: Feedback actions, review queue, and progress analytics

**Files:**
- Modify: `src/refineq/learning/service.py`
- Modify: `src/refineq/api/routers/learning.py`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/lib/types.ts`
- Create: `apps/web/components/review-queue.tsx`
- Create: `apps/web/components/progress-topic-detail.tsx`
- Modify: `apps/web/components/learning-session-canvas.tsx`
- Modify: `apps/web/components/progress-insights.tsx`
- Modify: `apps/web/components/evidence-ledger.tsx`
- Test: `tests/integration/test_learning_journey.py`
- Test: `apps/web/tests/components.test.tsx`

**Step 1: Write failing tests**

Specify `GET /workspaces/{id}/learning/insights` returning mastery history, error counts, due reviews, and rubric details from attempts/evidence. Test ownership and stable ordering.

**Step 2: Verify RED, implement backend, verify GREEN**

Project existing attempt/evidence/review data; do not duplicate it.

**Step 3: Write failing UI tests**

Assert rubric/source inspection, retry same question, add learner note/appeal, due-review start, topic drill-down, and empty states.

**Step 4: Implement UI and verify GREEN**

Use accessible details/dialog patterns and route due reviews back to Today with the topic selected.

**Step 5: Commit**

Commit `feat: complete feedback and review loop`.

### Task 7: Account and security center

**Files:**
- Modify: `src/refineq/identity/models.py`
- Modify: `src/refineq/identity/service.py`
- Modify: `src/refineq/api/routers/auth.py`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/lib/types.ts`
- Create: `apps/web/components/account-center.tsx`
- Create: `apps/web/app/account/page.tsx`
- Modify: `apps/web/components/study-workspace.tsx`
- Test: `tests/integration/test_auth.py`
- Test: `apps/web/tests/components.test.tsx`
- Test: `apps/web/tests/contracts.test.ts`

**Step 1: Write failing backend tests**

Cover profile update, current-password-gated password change, export, logout-all/session version invalidation, and fail-safe account deletion. Confirm another user cannot access exported data.

**Step 2: Verify RED and implement backend**

Add `/auth/profile`, `/auth/password`, `/auth/export`, `/auth/sessions`, and `/auth/account`. Hash passwords with the existing service and revoke tokens through a persisted session version.

**Step 3: Write failing frontend tests and implement UI**

Build one account route with profile, security, export, and danger-zone sections. Require typed confirmation for account deletion.

**Step 4: Verify and commit**

Commit `feat: add account and security controls`.

### Task 8: Material metadata and bulk organization

**Files:**
- Modify: `src/refineq/database/schema.py`
- Modify: `src/refineq/knowledge/index.py`
- Modify: `src/refineq/api/routers/materials.py`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/components/material-dropzone.tsx`
- Test: `tests/integration/test_material_upload.py`
- Test: `tests/unit/knowledge/test_index.py`
- Test: `apps/web/tests/components.test.tsx`

**Step 1: Write failing tests**

Cover title/tags update, status/tag filters, sort order, selected bulk deletion, ownership, and cleanup of chunks/object storage.

**Step 2: Verify RED and implement backend**

Store title/tags in the material record, add validated PATCH and bulk-delete endpoints, and extend list query parameters. Keep writes and storage cleanup fail-safe.

**Step 3: Write failing UI tests and implement**

Add selection, search/filter toolbar, sort, editable metadata, processing details, and bulk confirmation.

**Step 4: Verify and commit**

Commit `feat: add scalable material organization`.

### Task 9: Mobile navigation and readability

**Files:**
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/components/learning-session-canvas.tsx`
- Modify: `apps/web/app/styles.css`
- Test: `apps/web/tests/components.test.tsx`
- Test: `apps/web/tests/e2e/learning-journey.spec.ts`

**Step 1: Write failing tests**

Assert a visible mobile section title, context shortcuts, 44px interactive targets, sticky task action, keyboard focus restoration, and no horizontal overflow at 390px.

**Step 2: Verify RED and implement**

Preserve desktop design while adding mobile-only labels/shortcuts and raising secondary type to at least 12px in task-critical surfaces.

**Step 3: Verify and commit**

Commit `fix: improve mobile task navigation`.

### Task 10: Administrator operations control plane

**Files:**
- Modify: `src/refineq/operations/admin.py`
- Modify: `src/refineq/operations/backup.py`
- Modify: `src/refineq/api/routers/admin.py`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/components/admin-console.tsx`
- Modify: `apps/web/lib/admin-routes.ts`
- Create: `apps/web/app/admin/operations/page.tsx`
- Test: `tests/integration/test_admin_auth.py`
- Test: `tests/operations/test_backup.py`
- Test: `apps/web/tests/components.test.tsx`
- Test: `apps/web/tests/contracts.test.ts`

**Step 1: Write failing backend tests**

Cover paginated users/quota summaries, material/index job status, audit-log pagination, backup creation/listing, restore validation, admin authorization, traversal rejection, and audit entries.

**Step 2: Verify RED and implement backend**

Reuse the existing SQL audit table and backup service. Expose only validated IDs, never arbitrary paths. Require explicit confirmation tokens for restore.

**Step 3: Write failing UI tests and implement**

Add Users, Activity, Jobs, and Backup sections with empty/loading/error states and guarded destructive controls.

**Step 4: Verify and commit**

Commit `feat: add admin operations console`.

### Task 11: Refactor the workspace state boundary

**Files:**
- Create: `apps/web/hooks/use-learning-auth.ts`
- Create: `apps/web/hooks/use-workspace-state.ts`
- Create: `apps/web/hooks/use-practice-state.ts`
- Create: `apps/web/hooks/use-agent-state.ts`
- Modify: `apps/web/components/study-workspace.tsx`
- Test: `apps/web/tests/contracts.test.ts`
- Test: `apps/web/tests/components.test.tsx`

**Step 1: Add characterization tests**

Protect restore, route notice, draft persistence, request idempotency, upload state, and logout behavior before moving code.

**Step 2: Verify tests pass against current behavior**

This is a refactor prerequisite rather than a new behavior RED; new hook APIs receive their own failing unit tests before creation.

**Step 3: Extract one hook at a time**

Move logic without changing rendering, run focused tests after every extraction, and keep only orchestration in `StudyWorkspace`.

**Step 4: Commit**

Commit `refactor: split workspace state domains`.

### Task 12: Full verification and browser acceptance

**Files:**
- Modify: `apps/web/tests/e2e/learning-journey.spec.ts`
- Modify: `docs/architecture.md`
- Modify: `docs/operations.md`
- Modify: `README.md`

**Step 1: Extend the isolated E2E journey**

Cover real switching, agent history, sourced practice, plan edit, retry/review, account settings, material bulk actions, mobile shortcuts, admin users/audit/jobs, backup creation, localized errors, and 404 recovery.

**Step 2: Run complete verification**

```powershell
& 'D:\project\personal agent\.venv\Scripts\python.exe' -m pytest -q
& 'D:\project\personal agent\.venv\Scripts\python.exe' -m ruff check src tests scripts
& 'D:\project\personal agent\.venv\Scripts\python.exe' scripts/scan_secrets.py
Set-Location apps/web
npm test
npm run lint
npm run build
npm run test:e2e
```

Expected: all commands exit 0; Playwright retains no failure artifacts.

**Step 3: Perform screenshot QA**

Capture desktop and mobile states for every flow in an isolated `REFINEQ_DATA_ROOT`. Inspect navigation, overflow, focus, empty/error/success states, evidence visibility, and destructive confirmations.

**Step 4: Update documentation and commit**

Document APIs, operating controls, backup/restore safety, and learner workflows. Commit `docs: document completed product flows`.
