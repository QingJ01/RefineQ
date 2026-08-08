# Learning Workspace Navigation And Layout Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make route ownership, learning-space isolation, and wide-screen layout clear and reliable across the RefineQ learning experience.

**Architecture:** The Next.js route determines whether the learner sees the personal home or a workspace. Session storage retains identity and convenience state only. The existing workspace component remains the shared data controller while navigation becomes canonical `<Link>` routes and the page layouts adopt one responsive workspace frame.

**Tech Stack:** Next.js 16 App Router, React 19, TypeScript, Vitest, CSS, Lucide React.

---

### Task 1: Make routes the only view-state authority

**Files:**
- Modify: `apps/web/lib/session.ts`
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/tests/learning-session.test.ts`
- Modify: `apps/web/tests/contracts.test.ts`

**Step 1: Write the failing tests**

- Assert persisted sessions no longer contain a `home` flag.
- Assert the root component does not restore a workspace from saved view state.
- Assert logout replaces the current location with `/`.
- Assert unavailable route workspaces redirect to `/`.

**Step 2: Run tests to verify RED**

Run: `npm test -- --run tests/learning-session.test.ts tests/contracts.test.ts`

Expected: failures referencing the legacy `home` field and missing canonical redirect behavior.

**Step 3: Implement route-owned restoration**

- Remove `home` from `LearningSession`.
- On `/`, restore authentication and workspace list only.
- On `/learn/:workspaceId/:section`, restore exactly the URL workspace.
- Replace invalid workspace and logout routes with `/`.
- Keep the last workspace identifier only as convenience metadata.

**Step 4: Run tests to verify GREEN**

Run: `npm test -- --run tests/learning-session.test.ts tests/contracts.test.ts`

Expected: all selected tests pass.

### Task 2: Clarify home, space, and section navigation

**Files:**
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/lib/i18n.ts`
- Modify: `apps/web/tests/contracts.test.ts`
- Modify: `apps/web/tests/components.test.tsx`

**Step 1: Write the failing tests**

- Assert the workspace shell has an explicit home link.
- Assert a current-space switcher links to the workspace list.
- Assert every section link is generated through `learningPath(workspace.id, section)`.
- Assert the current workspace title appears before local section navigation.

**Step 2: Run tests to verify RED**

Run: `npm test -- --run tests/contracts.test.ts tests/components.test.tsx`

Expected: failures for missing navigation landmarks and link structure.

**Step 3: Implement the sidebar hierarchy**

- Use Next.js `Link` for route navigation.
- Add explicit learning-home and current-space controls.
- Move the current workspace summary above local navigation.
- Preserve admin, language, and logout actions.
- Add locale keys in Chinese and English.

**Step 4: Run tests to verify GREEN**

Run: `npm test -- --run tests/contracts.test.ts tests/components.test.tsx`

Expected: all selected tests pass.

### Task 3: Recompose wide-screen learning pages

**Files:**
- Modify: `apps/web/components/learning-session-canvas.tsx`
- Modify: `apps/web/app/styles.css`
- Modify: `apps/web/tests/components.test.tsx`
- Modify: `apps/web/tests/contracts.test.ts`

**Step 1: Write the failing tests**

- Assert feedback renders meaningful empty states.
- Assert today no longer uses a viewport-forced minimum height.
- Assert the workspace frame expands beyond the legacy 1200/1240px limits.
- Assert progress becomes a two-column desktop composition with a single-column breakpoint.

**Step 2: Run tests to verify RED**

Run: `npm test -- --run tests/components.test.tsx tests/contracts.test.ts`

Expected: failures for missing empty feedback text and legacy layout declarations.

**Step 3: Implement the responsive layout**

- Widen the shared workspace frame with controlled responsive padding.
- Use a flexible content/rail grid for today without forced viewport height.
- Bound feedback text and compact empty feedback surfaces.
- Place mastery and evidence side by side on wide screens.
- Collapse layouts at medium and mobile breakpoints.

**Step 4: Run tests to verify GREEN**

Run: `npm test -- --run tests/components.test.tsx tests/contracts.test.ts`

Expected: all selected tests pass.

### Task 4: Full verification and local handoff

**Files:**
- Verify: `apps/web/`
- Verify: repository root

**Step 1: Run frontend verification**

Run: `npm test -- --run && npm run lint && npm run build`

Expected: tests, lint, and production build pass.

**Step 2: Run backend regression tests**

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Expected: all non-environment-skipped tests pass.

**Step 3: Restart local services and probe live routes**

- Confirm `/`, `/learn/refineq-demo/today`, `/learn/refineq-demo/progress`, and API authentication return success.
- Do not run Playwright or control a browser until the user chooses the browser.

**Step 4: Review the final diff and commit**

- Confirm no payment, model-allowance, or commercial control files changed.
- Confirm git identity is `QingJ01 <qingj1314@163.com>`.
- Commit only the scoped design, routing, layout, and tests.
