# Admin Routing and Information Architecture Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace state-only administrator mode with refresh-safe Next.js routes and a focused overview-to-detail console.

**Architecture:** Add App Router pages for the administrator overview and integration details. A client route guard restores and verifies the saved session, while `AdminConsole` renders either an overview or one service form inside a shared shell.

**Tech Stack:** Next.js 16 App Router, React 19, TypeScript, vanilla CSS, Vitest, Playwright

---

### Task 1: Lock the route contract

**Files:**
- Modify: `apps/web/tests/contracts.test.ts`
- Modify: `apps/web/tests/components.test.tsx`

1. Add tests for `/admin` and `/admin/integrations/[kind]` page files.
2. Assert `StudyWorkspace` no longer contains an Admin section state.
3. Assert overview mode renders system status, one next action, and guardrails without configuration forms.
4. Assert detail mode renders exactly the selected integration form and its three setting groups.
5. Run `npm test` and confirm the new assertions fail for the missing route architecture.

### Task 2: Add route parsing and the administrator guard

**Files:**
- Create: `apps/web/lib/admin-routes.ts`
- Create: `apps/web/components/admin-route.tsx`
- Create: `apps/web/app/admin/page.tsx`
- Create: `apps/web/app/admin/integrations/[kind]/page.tsx`

1. Add a typed allowlist parser for integration route segments.
2. Restore the session, fetch the profile, and redirect invalid roles to `/`.
3. Render loading and inline route errors without exposing Admin data first.
4. Pass a valid optional integration kind into `AdminConsole`.
5. Run focused tests until the route contract passes.

### Task 3: Replace internal Admin state navigation

**Files:**
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/components/learning-home.tsx`

1. Remove `admin` from the learning `Section` union and render path.
2. Navigate administrator actions to `/admin` with `useRouter`.
3. Keep all learner sections as local workspace state.
4. Run component and contract tests.

### Task 4: Recompose the administrator interface

**Files:**
- Modify: `apps/web/components/admin-console.tsx`
- Modify: `apps/web/app/styles.css`

1. Build a compact Admin shell and route-aware navigation.
2. Render a compact health strip, prioritized next action, setup progress, and guardrails on `/admin`.
3. Keep the capability index in the sidebar instead of repeating four service rows in the content.
4. Render one `IntegrationCard` on a detail route, grouped into basic settings, credentials, and network security.
5. Preserve save, test, logout, language, loading, and error behavior.
6. Add focused responsive styles and remove obsolete grid/hero styling.
7. Run component tests and update only intentional snapshots/assertions.

### Task 5: Verify browser navigation

**Files:**
- Modify: `apps/web/tests/e2e/learning-journey.spec.ts`

1. Add an administrator journey that opens `/admin`, enters a service route, refreshes, and goes back.
2. Confirm a learner cannot remain on `/admin`.
3. Run `npm run test:e2e` and fix only reproduced failures.
4. Run `npm test`, `npm run lint`, and `npm run build`.
5. Review `git diff --check` and the complete working-tree diff.
