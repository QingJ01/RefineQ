# Learning Home Command Center Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the signed-in home page into a usable personal learning command center that shares the workspace shell and exposes real entry points into each learning space.

**Architecture:** Keep the existing Next.js client shell and API contracts. Derive the current space from the first active workspace, render navigation with Next.js `Link`, and route every shortcut through the existing `/learn/[workspaceId]/[section]` URLs. No new aggregate backend, payment, quota, or model behavior is introduced.

**Tech Stack:** Next.js 16, React 19, TypeScript, lucide-react, CSS, Vitest server rendering tests.

---

### Task 1: Lock the command-center contract

**Files:**
- Modify: `apps/web/tests/components.test.tsx`
- Test: `apps/web/tests/components.test.tsx`

**Step 1: Write the failing test**

Add assertions that the home renders a learning-home active navigation item, a current-space continue action, and direct `today`, `path`, `materials`, and `progress` URLs for an active workspace.

**Step 2: Run test to verify it fails**

Run: `npm test -- --run tests/components.test.tsx`

Expected: FAIL because the current home only opens a workspace through a button and has no section links.

**Step 3: Implement the minimal component structure**

Update `LearningHome` to use `Link`, derive the first non-archived workspace as the current space, and expose accessible section shortcuts without changing the existing management callbacks.

**Step 4: Run test to verify it passes**

Run: `npm test -- --run tests/components.test.tsx`

Expected: PASS.

### Task 2: Unify the signed-in product shell

**Files:**
- Modify: `apps/web/components/learning-home.tsx`
- Modify: `apps/web/app/styles.css`
- Modify: `apps/web/lib/i18n.ts`

**Step 1: Write the failing presentation assertions**

Assert the home has the same sidebar hierarchy as the workspace, a page header, a primary continue card, the Agent composer, and recent-space cards.

**Step 2: Run test to verify it fails**

Run: `npm test -- --run tests/components.test.tsx`

Expected: FAIL on the missing command-center regions.

**Step 3: Implement the layout and states**

Use the existing design tokens and 264px shell, add real navigation affordances, preserve empty/archived states, and keep responsive behavior aligned with the workspace navigation.

**Step 4: Run test to verify it passes**

Run: `npm test -- --run tests/components.test.tsx`

Expected: PASS.

### Task 3: Verify the complete web application

**Files:**
- Verify: `apps/web`

**Step 1: Run the complete unit test suite**

Run: `npm test`

Expected: all tests pass.

**Step 2: Run lint**

Run: `npm run lint`

Expected: exit 0 with no lint errors.

**Step 3: Build the production bundle**

Run: `npm run build`

Expected: exit 0 and all routes compile.

**Step 4: Review the final diff**

Confirm no secrets, generated output, payment behavior, quota behavior, or unrelated changes are included.
