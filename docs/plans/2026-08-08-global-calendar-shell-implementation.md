# Global Calendar and Unified Sidebar Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an owner-scoped cross-workspace calendar and make authenticated routes share one left-sidebar/right-content application shell.

**Architecture:** A new backend calendar service projects bounded task ranges from owner-scoped workspace plans without returning full snapshots. A reusable client-side sidebar receives already-authorized user/workspace data and contextual navigation; the new `/calendar` route renders a read-only aggregate and deep-links each task back to its owning workspace calendar.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQL-backed record repositories, Next.js 16, React 19, TypeScript, Vitest, Playwright-compatible browser verification.

---

### Task 1: Calendar domain projection

**Files:**
- Create: `src/refineq/calendar/__init__.py`
- Create: `src/refineq/calendar/models.py`
- Create: `src/refineq/calendar/service.py`
- Create: `tests/unit/calendar/test_calendar_service.py`

**Step 1: Write the failing tests**

Cover owner-scoped aggregation from multiple workspaces, `[starts_at, ends_at)` filtering, stable ordering, topic labels, archived exclusion/inclusion, missing plans, naive datetimes, reversed ranges, and ranges longer than 370 days.

**Step 2: Run tests to verify RED**

Run: `python -m pytest tests/unit/calendar/test_calendar_service.py -q`

Expected: FAIL because `refineq.calendar` does not exist.

**Step 3: Implement the minimal domain service**

Create frozen Pydantic `CalendarTask` and `CalendarResponse` models. Implement `CalendarService.list_tasks(owner_id, starts_at, ends_at, include_archived=False)` using only `WorkspaceRepository.list(owner_id, ...)` and `LearningRepository.get(owner_id, workspace.id)`. Validate aware timestamps and a maximum 370-day half-open range before reading records.

**Step 4: Run tests to verify GREEN**

Run: `python -m pytest tests/unit/calendar/test_calendar_service.py -q`

Expected: PASS.

**Step 5: Commit**

Commit message: `feat: add owner-scoped calendar projection`

### Task 2: Authenticated calendar API

**Files:**
- Create: `src/refineq/api/routers/calendar.py`
- Modify: `src/refineq/api/app.py`
- Create: `tests/integration/test_calendar.py`

**Step 1: Write the failing API tests**

Create two users and multiple workspaces. Assert `GET /calendar` requires authentication, returns only the caller's tasks, excludes archived spaces by default, accepts `include_archived=true`, and returns structured `422` responses for invalid or excessive ranges.

**Step 2: Run tests to verify RED**

Run: `python -m pytest tests/integration/test_calendar.py -q`

Expected: FAIL with `404` for `/calendar`.

**Step 3: Add the router and application wiring**

Instantiate `CalendarService` in `create_app`, add a `/calendar` router with aware datetime query parameters, translate calendar validation errors into the existing API error shape, and declare `CalendarResponse` as the response model.

**Step 4: Run tests to verify GREEN**

Run: `python -m pytest tests/integration/test_calendar.py -q`

Expected: PASS.

**Step 5: Commit**

Commit message: `feat: expose bounded global calendar API`

### Task 3: Frontend calendar contract and view model

**Files:**
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/api.ts`
- Create: `apps/web/lib/global-calendar.ts`
- Create: `apps/web/tests/global-calendar.test.ts`
- Modify: `apps/web/tests/contracts.test.ts`

**Step 1: Write the failing tests**

Assert range query serialization, response field names, local date grouping, stable workspace colors, month grid range calculation, per-workspace filtering, and aggregate task/minute/workspace counts.

**Step 2: Run tests to verify RED**

Run: `npm test -- tests/global-calendar.test.ts tests/contracts.test.ts`

Expected: FAIL because calendar types/helpers/API methods are absent.

**Step 3: Implement types, API method, and pure helpers**

Add `CalendarTask`/`CalendarResponse`, `api.getCalendar`, and pure functions for month bounds, date keys, task grouping, workspace colors, filtering, and summary counts. Do not put UI state or network calls in the helper module.

**Step 4: Run tests to verify GREEN**

Run: `npm test -- tests/global-calendar.test.ts tests/contracts.test.ts`

Expected: PASS.

**Step 5: Commit**

Commit message: `feat: add global calendar client contract`

### Task 4: Shared authenticated sidebar

**Files:**
- Create: `apps/web/components/app-sidebar.tsx`
- Modify: `apps/web/components/learning-home.tsx`
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/components/account-center.tsx`
- Modify: `apps/web/components/admin-route.tsx`
- Modify: `apps/web/components/admin-console.tsx`
- Modify: `apps/web/lib/i18n.ts`
- Modify: `apps/web/tests/components.test.tsx`

**Step 1: Write the failing component tests**

Assert global home/calendar links, recent workspace links, role-gated admin entry, contextual workspace navigation, account anchors, active-route semantics, and consistent utility actions. Render real components with deterministic props rather than mocking the sidebar.

**Step 2: Run tests to verify RED**

Run: `npm test -- tests/components.test.tsx`

Expected: FAIL because `AppSidebar` and the unified structure do not exist.

**Step 3: Extract and adopt `AppSidebar`**

Make the component presentation-only. Reuse it from home, workspace, account, and admin routes. Account/admin routes load the workspace list with their existing authenticated session; failures preserve the page and show a retryable localized error. Add IDs to account sections for in-page navigation.

**Step 4: Run tests to verify GREEN**

Run: `npm test -- tests/components.test.tsx`

Expected: PASS.

**Step 5: Commit**

Commit message: `feat: unify authenticated navigation shell`

### Task 5: Global calendar page and task deep links

**Files:**
- Create: `apps/web/app/calendar/page.tsx`
- Create: `apps/web/components/global-calendar.tsx`
- Modify: `apps/web/components/schedule-calendar.tsx`
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/tests/components.test.tsx`
- Modify: `apps/web/tests/contracts.test.ts`

**Step 1: Write the failing UI tests**

Assert loading/error/empty states, monthly navigation, workspace filters, read-only task agenda, task links containing workspace/session IDs, and focused workspace-calendar tasks.

**Step 2: Run tests to verify RED**

Run: `npm test -- tests/components.test.tsx tests/contracts.test.ts`

Expected: FAIL because the route and components are absent.

**Step 3: Implement the page**

Restore session state, request only the visible calendar grid range, render statistics/month grid/day agenda, and reload when month/archive filter changes. Parse the `session` query on the workspace calendar and pass it as a focus hint to `ScheduleCalendar`; focus changes the visible month/date and applies an accessible highlight.

**Step 4: Run tests to verify GREEN**

Run: `npm test -- tests/components.test.tsx tests/contracts.test.ts`

Expected: PASS.

**Step 5: Commit**

Commit message: `feat: add cross-workspace calendar experience`

### Task 6: Cohesive responsive styling and final verification

**Files:**
- Modify: `apps/web/app/styles.css`
- Modify: `docs/plans/2026-08-08-global-calendar-shell-design.md` only if implementation decisions materially differ

**Step 1: Add structural style assertions where practical**

Extend component tests to assert semantic labels, active states, focus targets, and responsive navigation hooks. Avoid brittle pixel-value tests.

**Step 2: Implement the visual system**

Unify sidebar width, grouping, workspace color markers, right-content page headers, account anchors, admin context navigation, sticky behavior, keyboard focus, mobile drawer/stacking, calendar colors, and empty/error states using existing design tokens and typography.

**Step 3: Run focused and full verification**

Run:

- `python -m pytest -q`
- `npm test`
- `npm run lint`
- `npm run build`

Expected: all commands exit `0` with no test failures or lint/build errors.

**Step 4: Browser verification**

Create representative workspaces/tasks in isolated local data. Verify `/`, `/calendar`, one workspace calendar deep link, `/account`, and `/admin` at desktop and mobile widths. Confirm CSS resources load, no console errors occur, and tasks never cross users.

**Step 5: Commit**

Commit message: `style: align authenticated pages around shared shell`

