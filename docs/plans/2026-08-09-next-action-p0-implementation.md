# NextAction P0 Complete Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the revised adversarial review into shipped product behavior: a material-gated, deterministic next action; one primary task on Today; one source of truth for plan constraints; consistent mobile agendas; and internally computable learning-loop metrics.

**Architecture:** Keep decision policy deterministic and server-owned. A pure learning-domain selector receives a versioned workspace snapshot, indexed-material availability, the evaluation time, and the learner's current UTC offset; `WorkspaceService` supplies those inputs and exposes the result through the workspace snapshot and a refresh endpoint. Journey events remain owner/workspace scoped in a separate bounded event record so analytics cannot change learning-domain versions or break a committed user flow; an admin-only read model computes windowed aggregates without a third-party analytics SDK.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy-backed atomic JSON records, Next.js 16, React 19, TypeScript, Vitest, pytest.

---

### Task 1: Deterministic `NextAction` domain policy

**Files:**
- Create: `src/refineq/learning/next_action.py`
- Modify: `src/refineq/workspaces/service.py`
- Modify: `src/refineq/api/routers/workspaces.py`
- Test: `tests/unit/learning/test_next_action.py`
- Test: `tests/integration/test_workspace_journey.py`

**Step 1: Write failing table-driven tests**

Cover these ordered cases with a fixed evaluation time and UTC offset:

1. no indexed material → `upload_material`, regardless of due reviews or plan sessions;
2. indexed material + due review → `start_review`;
3. indexed material + local-today session → `start_session`;
4. indexed material + remaining minutes above deadline capacity → `repair_pace`;
5. indexed material + no higher-ranked candidate → weakest-topic `start_practice`;
6. identical inputs → identical action, target, reason code, evidence references, and stable id.

Run: `python -m pytest tests/unit/learning/test_next_action.py -v`

Expected: FAIL because `refineq.learning.next_action` does not exist.

**Step 2: Implement the minimal pure selector**

Add immutable Pydantic models for `NextAction` and alternatives. Include `id`, `workspace_id`, `version`, `expires_at`, `action_type`, `trigger`, `reason_code`, `reason`, `preconditions`, `evidence_refs`, `expected_outcome`, `target_id`, `topic_id`, `minutes`, `alternatives`, `risk_level`, and `approval_mode`. Use a stable hash of workspace/version/action/target for the id. Treat only `status == "indexed"` materials as searchable.

**Step 3: Expose the decision**

Add `WorkspaceService.next_action(...)`, include `next_action` in `WorkspaceSnapshot`, and add `GET /workspaces/{workspace_id}/next-action?timezone_offset_minutes=...`. The snapshot endpoint accepts the same bounded offset.

Run: `python -m pytest tests/unit/learning/test_next_action.py tests/integration/test_workspace_journey.py -v`

Expected: PASS.

### Task 2: Enforce the material boundary for new workspace questions

**Files:**
- Modify: `src/refineq/workspaces/service.py`
- Modify: `src/refineq/api/routers/learning.py`
- Test: `tests/integration/test_learning_journey.py`
- Test: `tests/integration/test_ai_practice.py`

**Step 1: Write the failing contract test**

Create a workspace without materials and POST a new workspace question. Assert `409`, code `material_required`, and that no pending generic question is stored. Upload an indexed material and assert the same request path can then create a material-grounded task. Keep legacy `/projects/.../learning/question` behavior unchanged.

Run: `python -m pytest tests/integration/test_learning_journey.py -k material_required -v`

Expected: FAIL because the endpoint currently returns a fallback question.

**Step 2: Implement the guard**

Add an owner-scoped `WorkspaceMaterialRequiredError` and `WorkspaceService.require_searchable_material`. Call it only from the workspace question creation endpoint before model or fallback work begins. After retrieval, enforce a second invariant: the generated workspace question must be material-grounded and carry real sources; otherwise return `material_insufficient` without storing a generic question. This closes irrelevant-material and check/delete race windows.

**Step 3: Update fixtures that intentionally exercise later workspace-question behavior**

Give those scenarios an indexed material instead of weakening the production invariant.

Run: `python -m pytest tests/integration/test_ai_practice.py tests/integration/test_learning_journey.py tests/integration/test_workspace_journey.py -v`

Expected: PASS.

### Task 3: Render one primary action on Today

**Files:**
- Create: `apps/web/components/next-action-card.tsx`
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/hooks/use-workspace-state.ts`
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/components/initial-diagnostic.tsx`
- Modify: `apps/web/app/styles.css`
- Test: `apps/web/tests/components.test.tsx`
- Test: `apps/web/tests/contracts.test.ts`

**Step 1: Write failing rendering and API tests**

Assert that:

- an upload action renders one primary upload CTA and no practice-start CTA;
- a due-review action invokes the referenced review;
- a scheduled action invokes the referenced plan session;
- pace risk opens Plan;
- weakest-topic practice starts the referenced grounded practice;
- the initial diagnostic is a collapsed secondary calibration and is omitted once `attempt_count > 0`;
- `ApiClient` sends the browser UTC offset when loading and refreshing the decision.

Run: `npm test -- components.test.tsx contracts.test.ts`

Expected: FAIL because the component and contracts do not exist.

**Step 2: Implement the Today state machine**

When there is no active question/result, render `NextActionCard` instead of the full session canvas. Render the session canvas only for an active practice/reflection. Keep ReviewQueue and coach affordances secondary. Refresh `NextAction` after upload, diagnostic, answer, plan changes, and session changes.

**Step 3: Demote diagnosis visually and behaviorally**

Render `InitialDiagnostic` as a collapsed `<details>` section and only when both diagnostic and attempt counts are zero. It must never compete as another primary card.

Run: `npm test -- components.test.tsx contracts.test.ts`

Expected: PASS.

### Task 4: Make structured plan constraints authoritative

**Files:**
- Modify: `src/refineq/workspaces/models.py`
- Modify: `src/refineq/storage/workspaces.py`
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/components/plan-settings.tsx`
- Modify: `apps/web/components/study-workspace.tsx`
- Test: `tests/integration/test_workspace_journey.py`
- Test: `apps/web/tests/components.test.tsx`

**Step 1: Write failing persistence and UI tests**

Assert that a workspace permanently retains `original_goal` while plan updates synchronize the current goal, date, and daily minutes. The UI must label original text as historical input that no longer controls scheduling and show the current date/minutes from structured plan fields in one summary.

Run: `python -m pytest tests/integration/test_workspace_journey.py -k original_goal -v`

Run: `npm test -- components.test.tsx`

Expected: FAIL because `original_goal` and the current-constraint summary do not exist.

**Step 2: Implement backward-compatible persistence**

Add optional `original_goal` with a validation fallback to `goal` for existing records; set it at workspace creation and never mutate it during plan updates.

**Step 3: Implement the UI truth hierarchy**

Operational headers use `plan.goal`/`progress.goal`. Plan settings show current structured constraints prominently and the original text in a clearly historical, read-only disclosure. Free text never supplies the displayed current date or minute budget.

Run both targeted suites; expected PASS.

### Task 5: Reuse the mobile agenda strategy

**Files:**
- Modify: `apps/web/components/global-calendar.tsx`
- Modify: `apps/web/app/styles.css`
- Test: `apps/web/tests/contracts.test.ts`
- Test: `apps/web/tests/components.test.tsx`

**Step 1: Write the failing responsive contract**

Assert that the `≤700px` rule groups workspace and global calendars into the same single-column agenda selectors, hides weekday headings and blank/outside cells, removes the global `min-width: 720px`, and preserves 44×44 targets. Assert global mobile rows include workspace, topic, status, time, and minutes.

Run: `npm test -- contracts.test.ts components.test.tsx`

Expected: FAIL on the existing horizontal-scroll rule.

**Step 2: Implement shared responsive CSS and markup**

Keep seven-column desktop layouts untouched. Add explicit empty/outside hooks to global days and reuse the existing plan-calendar mobile row treatment rather than creating a third calendar pattern.

Run the targeted tests; expected PASS.

### Task 6: Record the internal learning timeline and compute the north star

**Files:**
- Modify: `src/refineq/learning/service.py`
- Modify: `src/refineq/workspaces/service.py`
- Modify: `src/refineq/api/routers/materials.py`
- Modify: `src/refineq/api/routers/learning.py`
- Modify: `src/refineq/operations/admin.py`
- Modify: `src/refineq/api/routers/admin.py`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/components/study-workspace.tsx`
- Test: `tests/unit/learning/test_learning_events.py`
- Test: `tests/integration/test_learning_journey.py`
- Test: `tests/integration/test_admin_auth.py`

**Step 1: Write failing event and metric tests**

Cover idempotent, bounded events for `intent_submitted`, `workspace_ready`, `workspace_opened`, `material_searchable`, `question_started`, `grounded_grade_created`, and validated `grounded_grade_shown`. A shown event must reference an owner-scoped, material-grounded attempt. Compute:

- unique weekly active learners;
- unique learners completing a grounded closed loop;
- closed-loop weekly completion rate;
- first intent-to-grounded-grade P50/P90;
- revisit-open-to-next-question P50/P90.

Run: `python -m pytest tests/unit/learning/test_learning_events.py tests/integration/test_learning_journey.py tests/integration/test_admin_auth.py -v`

Expected: FAIL because the event timeline and metric endpoint do not exist.

**Step 2: Implement atomic event recording**

Store a bounded, idempotent event array in a separate owner/workspace journey record. Product analytics must not advance the learning-domain version, invalidate in-flight model work, or turn an already committed resolve/upload/question/grade/snapshot into a user-visible failure. Add a narrow authenticated endpoint for the client to mark a grade as shown; validate the attempt and its grounding before recording.

**Step 3: Implement the admin-only metric read model**

Add `GET /admin/metrics/learning?starts_at=...&ends_at=...`. Scan owner-scoped journey event records through the operations service, aggregate in Python for SQLite/PostgreSQL parity, and return counts, rates, and percentile durations. Use window-neutral names such as `active_learners`; a weekly north-star query is a caller-supplied seven-day window. Do not call a third-party analytics service.

Run the targeted tests; expected PASS.

### Task 7: Documentation and full verification

**Files:**
- Modify: `docs/product/08-adversarial-experience-agentization-review.md`
- Modify: relevant API/operating docs if contracts change

**Step 1: Mark shipped scope and exact metric definitions**

Document event semantics, the material gate, UTC-offset behavior, and the distinction between internal retention proxies and unavailable external mastery truth.

**Step 2: Run full verification**

Run:

```powershell
python -m pytest
python -m ruff check .
npm test
npm run lint
npm run build
```

Expected: all commands exit 0; PostgreSQL-only tests may remain explicitly skipped.

**Step 3: Independent review and integration**

Request a sub-agent review of the complete diff against this plan and the revised adversarial review. Reproduce and fix every valid blocking/important finding with a failing test first. Re-run the full verification, merge the feature branch into `main`, and push `origin/main` using `QingJ01 <qingj1314@163.com>`.
