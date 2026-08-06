# Implicit Learning Agent Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace visible projects with automatically routed personal learning workspaces and add material-grounded AI question generation and structured grading.

**Architecture:** Keep owner-scoped persistence, but make `workspace_id` the learning boundary and expose a resolver plus snapshot API. Add a strictly validated structured-model layer with deterministic fallbacks, then rebuild the browser flow around one persistent Agent entry point.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLite FTS5, OpenAI-compatible Chat Completions, Next.js 16, React 19, TypeScript, Pytest, Vitest, Playwright.

---

### Task 1: Workspace persistence and deterministic routing

**Files:**
- Create: `src/refineq/workspaces/models.py`
- Create: `src/refineq/workspaces/routing.py`
- Create: `src/refineq/storage/workspaces.py`
- Modify: `src/refineq/storage/json_store.py`
- Test: `tests/unit/workspaces/test_routing.py`
- Test: `tests/unit/storage/test_workspace_repository.py`

**Steps:**

1. Write failing tests proving records can be listed newest-first, same-subject intents reuse a workspace, unrelated subjects create a new workspace, and low-information input reuses the latest workspace.
2. Run `python -m pytest -q tests/unit/workspaces tests/unit/storage/test_workspace_repository.py` and verify failures refer to missing workspace modules.
3. Add strict Pydantic models (`LearningWorkspace`, `WorkspaceResolveRequest`, `WorkspaceRoute`) and owner-scoped repository methods `create`, `get`, `list`, `touch`.
4. Implement normalized token and subject-hint scoring with explicit confidence thresholds and no model dependency.
5. Re-run the focused tests and commit `feat: add implicit learning workspace routing`.

### Task 2: Workspace resolver and recovery API

**Files:**
- Create: `src/refineq/workspaces/service.py`
- Create: `src/refineq/api/routers/workspaces.py`
- Modify: `src/refineq/api/app.py`
- Modify: `src/refineq/learning/service.py`
- Modify: `src/refineq/knowledge/index.py`
- Test: `tests/integration/test_workspace_journey.py`

**Steps:**

1. Write an integration test that registers, resolves “高数极限”, resolves it again, resolves “英语四级”, lists two spaces, and restores a snapshot after creating learning evidence and material.
2. Verify the new test fails with 404 for `/workspaces/resolve`.
3. Implement `WorkspaceService.resolve/list/snapshot`; initialize new workspaces with inferred topic, a 30-day default horizon, and 45 daily minutes while preserving explicit request values.
4. Add `KnowledgeIndex.list_materials` and snapshot models for progress, plan, evidence and material records.
5. Wire the router and app state, run the integration test, then commit `feat: add workspace resolve and snapshot APIs`.

### Task 3: Structured model transport and per-user settings

**Files:**
- Create: `src/refineq/agent/structured.py`
- Modify: `src/refineq/agent/settings.py`
- Modify: `src/refineq/api/routers/settings.py`
- Modify: `src/refineq/agent/service.py`
- Test: `tests/unit/agent/test_structured.py`
- Test: `tests/integration/test_agent_chat.py`

**Steps:**

1. Write failing tests for fenced/plain JSON extraction, schema rejection, and owner-isolated model settings.
2. Verify focused tests fail against the current global repository.
3. Add a `StructuredModelTransport` protocol and OpenAI-compatible implementation that validates a supplied Pydantic response type.
4. Store settings below `users/{owner_id}/settings/model.json`; require owner ID on `load/public/save` and update chat/settings callers.
5. Run focused tests and commit `feat: isolate structured model settings per learner`.

### Task 4: Material-grounded AI question generation

**Files:**
- Create: `src/refineq/learning/intelligence.py`
- Modify: `src/refineq/learning/service.py`
- Modify: `src/refineq/learning/models.py`
- Modify: `src/refineq/api/routers/learning.py`
- Test: `tests/unit/learning/test_intelligence.py`
- Test: `tests/integration/test_ai_practice.py`

**Steps:**

1. Write failing tests asserting generated questions contain a private reference answer/rubric, expose only the public prompt/difficulty/citations, reject invented citations, and fall back deterministically without model settings.
2. Verify failures are caused by missing intelligence models/service.
3. Implement `GeneratedQuestion`, `RubricCriterion`, and `LearningIntelligenceService.generate_question` using retrieved workspace material plus mastery/difficulty state.
4. Persist the validated private grading payload in `pending_question`; never serialize it through `QuestionResponse`.
5. Run focused tests and commit `feat: generate grounded adaptive practice questions`.

### Task 5: Structured intelligent grading

**Files:**
- Modify: `src/refineq/learning/intelligence.py`
- Modify: `src/refineq/learning/service.py`
- Modify: `src/refineq/learning/models.py`
- Test: `tests/unit/learning/test_intelligence.py`
- Test: `tests/integration/test_ai_practice.py`

**Steps:**

1. Extend the failing integration test so a fake model returns score, strengths, gaps, misconceptions, feedback and citations; assert all fields persist in the attempt/evidence and update mastery/difficulty once.
2. Verify the test fails because the old substring grader does not return structured feedback.
3. Implement schema-validated grading, citation filtering, `score >= pass_score` correctness, and a deterministic rubric-aware fallback.
4. Preserve attempt idempotency so repeated submissions return the original grade without a second model call.
5. Run focused and learning regression tests, then commit `feat: add explainable AI answer grading`.

### Task 6: Single-Agent frontend with session recovery

**Files:**
- Create: `apps/web/components/learning-home.tsx`
- Create: `apps/web/lib/session.ts`
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/components/practice-card.tsx`
- Modify: `apps/web/components/material-dropzone.tsx`
- Modify: `apps/web/components/agent-panel.tsx`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/i18n.ts`
- Test: `apps/web/tests/contracts.test.ts`
- Test: `apps/web/tests/components.test.tsx`

**Steps:**

1. Write failing Vitest cases for token/workspace persistence, resolve/list/snapshot API contracts, Agent-first landing markup, and structured grading feedback.
2. Run `npm test` and verify the new tests fail for missing APIs/components.
3. Implement validated local storage helpers; restore `/auth/me`, workspace list and snapshot on boot; clear invalid sessions.
4. Replace `GoalWizard` with the Agent-first home and recent learning list. Keep workspace selection as a correction affordance, not a required setup step.
5. Update practice and material views to restore server state and display AI scoring details.
6. Run `npm test`, `npm run lint`, `npm run build`; commit `feat: make learning agent the primary workspace`.

### Task 7: Browser journey, migration and documentation

**Files:**
- Modify: `apps/web/tests/e2e/learning-journey.spec.ts`
- Create: `src/refineq/operations/workspace_migration.py`
- Create: `scripts/migrate_workspaces.py`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/operations.md`
- Test: `tests/operations/test_workspace_migration.py`
- Test: `tests/contract/test_repository_shape.py`

**Steps:**

1. Write failing migration tests from legacy `projects` records and a browser journey that registers, states an intent, uploads material, refreshes, restores the workspace, completes a graded answer, and sees feedback.
2. Verify each fails against the current implementation.
3. Implement backup-first idempotent workspace migration and update documentation/terminology.
4. Run `python -m ruff check src tests scripts`, `python -m pytest -q`, `python scripts/scan_secrets.py`, `npm test`, `npm run lint`, `npm run build`, and `npm run test:e2e`.
5. Build both Docker images in CI/local Docker when available, verify no tracked `project` UI naming remains, and commit `docs: document implicit learning workflow`.

### Task 8: Final integration

**Files:** all files changed above.

**Steps:**

1. Run `git diff --check`, inspect `git status`, and review the complete branch diff.
2. Re-run the full verification suite from a clean process.
3. Use `superpowers:requesting-code-review` if review agents are explicitly authorized; otherwise perform a local evidence-backed review.
4. Use `superpowers:finishing-a-development-branch` to integrate the verified branch into `main` without retaining obsolete worktree state.

