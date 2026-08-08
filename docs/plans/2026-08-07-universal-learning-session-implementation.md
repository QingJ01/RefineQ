# Universal Learning Session Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the fragmented subject-and-quiz workflow with one domain-neutral capability-learning session that connects goals, sources, learning methods, practice artifacts, AI feedback, and follow-up review.

**Architecture:** Preserve the current FastAPI, repository, and Next.js boundaries. Generalize the existing question pipeline into a mode-aware learning task without migrating stored records, then compose the existing plan, material, grading, and agent capabilities into a new session canvas. Keep legacy question fields and URLs compatible while replacing the learner-facing information architecture with Today, Learning Path, Library, and Progress.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, pytest, Next.js 16, React 19, TypeScript, Vitest, Playwright, existing Lucide icon system.

---

### Task 1: Generalize the learning-task contract

**Files:**
- Modify: `src/refineq/learning/models.py`
- Modify: `src/refineq/learning/intelligence.py`
- Modify: `src/refineq/learning/service.py`
- Modify: `src/refineq/api/routers/learning.py`
- Test: `tests/unit/learning/test_intelligence.py`
- Test: `tests/integration/test_ai_practice.py`

**Steps:**
1. Add failing tests that request `concept`, `case`, `project`, and `exam` modes and assert that the selected mode survives the generated task and public response.
2. Run the focused tests and confirm they fail because mode selection is not implemented.
3. Add a strict `LearningMode` value, mode-aware prompt instructions, and backwards-compatible defaults for stored questions.
4. Thread the `mode` query through both project and workspace learning routes.
5. Run the focused unit and integration tests until green.

### Task 2: Define the frontend session model

**Files:**
- Create: `apps/web/lib/learning-session.ts`
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/api.ts`
- Test: `apps/web/tests/learning-session.test.ts`
- Test: `apps/web/tests/contracts.test.ts`

**Steps:**
1. Add failing tests for session phases, active-step derivation, domain-neutral mode labels, current topic selection, and source summaries.
2. Run Vitest and confirm the missing module/contract failures.
3. Implement pure session-view-model helpers and extend the API request/response types with `learningMode`.
4. Run the focused tests until green.

### Task 3: Build the selected Today session canvas

**Files:**
- Create: `apps/web/components/learning-session-canvas.tsx`
- Create: `apps/web/components/session-coach.tsx`
- Modify: `apps/web/components/study-workspace.tsx`
- Add: `apps/web/public/assets/refineq-coach-avatar.png`
- Test: `apps/web/tests/components.test.tsx`

**Steps:**
1. Add failing render tests for the four-stage session, learning-method selector, contextual sources, task answer flow, inline grading result, and contextual coach suggestions.
2. Run the component tests and confirm they fail for missing session components.
3. Implement the canvas using the selected mockup proportions: dominant learning surface, narrow context rail, one primary action, and the generated coach asset.
4. Reuse the existing question, grading, material, and agent API handlers; do not duplicate persistence logic.
5. Run component tests until green.

### Task 4: Replace the learner-facing information architecture

**Files:**
- Modify: `apps/web/lib/learning-routes.ts`
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/components/plan-timeline.tsx`
- Modify: `apps/web/components/progress-insights.tsx`
- Modify: `apps/web/components/evidence-ledger.tsx`
- Modify: `apps/web/lib/i18n.ts`
- Test: `apps/web/tests/contracts.test.ts`
- Test: `apps/web/tests/components.test.tsx`

**Steps:**
1. Add failing tests for `today`, `path`, `materials`, and `progress`, including legacy-route normalization.
2. Run focused tests and confirm the new routes and labels fail.
3. Move the weekly plan out of Today into Learning Path, combine mastery and evidence under Progress, and remove the standalone Agent destination.
4. Replace exam-only labels with capability, output, activity, feedback, and review language while preserving bilingual support.
5. Keep stable aliases for old `/evidence` and `/coach` URLs so saved links do not become dead ends.
6. Run focused frontend tests until green.

### Task 5: Match the selected visual target responsively

**Files:**
- Modify: `apps/web/app/styles.css`
- Modify: `apps/web/components/material-dropzone.tsx`
- Modify: `apps/web/components/plan-timeline.tsx`
- Modify: `apps/web/components/progress-insights.tsx`

**Steps:**
1. Add or update DOM assertions for the major layout regions and accessible controls.
2. Implement the 1440 x 1024 desktop composition, shared tokens, spacing, type hierarchy, stepper, answer workspace, and right context rail.
3. Add responsive behavior for tablet and 390 x 844 mobile without hiding labels from assistive technology.
4. Keep upload, path editing, task answering, source drawers, and coach inputs operational across breakpoints.
5. Run lint, Vitest, and the Next.js build.

### Task 6: Update and run the complete learner journey

**Files:**
- Modify: `apps/web/tests/e2e/learning-journey.spec.ts`

**Steps:**
1. Update the E2E journey to create a non-academic capability goal, open Learning Path, upload source material, choose a learning method, complete a task, inspect inline feedback, confirm Progress, and use the contextual coach.
2. Run Playwright and confirm the old-flow assertions fail before finishing the UI changes.
3. Complete the minimum implementation needed for the new flow.
4. Run Python tests, Ruff, frontend tests, ESLint, Next.js build, and Playwright.

### Task 7: Visual comparison and blocking design QA

**Files:**
- Create: `design-qa.md`
- Save evidence under: `C:/Users/QingJ/.codex/visualizations/2026/08/05/019fd1da-993a-7040-82d4-830cf70f321b/refineq-universal-session/`

**Steps:**
1. Start the verified local app and capture the Today session at 1440 x 1024 in the same interaction state as the selected visual target.
2. Create a combined source-and-implementation comparison image and inspect it directly.
3. Record P0-P3 findings in `design-qa.md`; keep `final result: blocked` while any P0-P2 item remains.
4. Fix P0-P2 issues and repeat the same-state capture and comparison.
5. Set `final result: passed` only after the visual, interaction, console, responsive, and automated-test gates pass.
