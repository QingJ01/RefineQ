# Final Demo Remediation Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development and superpowers:verification-before-completion task-by-task.

**Goal:** Fix the confirmed MCP disconnect and Agent action race, add browser coverage and accessibility, then deploy the verified commit.

**Architecture:** Preserve consumed ASGI messages in the MCP gateway. Fence Agent practice actions with the learning-state version inside the existing generation lock, while retaining request-id replay semantics.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, React 19, Next.js 16, Vitest, Playwright, Docker Compose, Caddy.

---

### Task 1: Preserve MCP disconnect messages

**Files:**
- Modify: `tests/integration/test_mcp_auth.py`
- Modify: `src/refineq/mcp/auth.py`

1. Add tests for a complete body followed by disconnect and a partial body interrupted by disconnect.
2. Run the focused tests and confirm they fail because the gateway emits an invented empty request.
3. Cache consumed ASGI messages and delegate to the original receiver after the cache drains.
4. Run the focused MCP tests and confirm they pass.

### Task 2: Fence Agent practice actions against stale learning state

**Files:**
- Modify: `tests/integration/test_agent_chat.py`
- Modify: `src/refineq/agent/actions.py`
- Modify: `src/refineq/agent/service.py`
- Modify: `src/refineq/learning/service.py`
- Modify: `src/refineq/api/routers/learning.py`
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/components/study-workspace.tsx`

1. Add an integration test that creates a proposal, mutates learning state in another request, and expects action application to return 409 without replacing the concurrent question.
2. Run the test and confirm it fails with the current HTTP 200 no-op behavior.
3. Add `expected_state_version` to adjust-practice proposals and question requests.
4. Validate the version inside the question-generation lock after request-id replay and before the pending-question shortcut.
5. Pass the version from the Agent UI and run focused backend/frontend tests.

### Task 3: Cover the executable Agent browser flow and label material search

**Files:**
- Modify: `apps/web/tests/e2e/learning-journey.spec.ts`
- Modify: `apps/web/components/material-dropzone.tsx`

1. Add a Playwright scenario with a non-null adjust-practice proposal and assert the apply request and visible replacement.
2. Run it and confirm it fails before the mock/action flow is implemented.
3. Add the minimal route mock and assertions needed for the real UI flow.
4. Add `aria-label`, `name`, and `autoComplete="off"` to material search.
5. Run the focused browser test.

### Task 4: Verify, commit, deploy, and smoke test

1. Run Python tests, Ruff check/format, secret scan, frontend tests, ESLint, production build, and Playwright.
2. Confirm the Git identity is `QingJ01 <qingj1314@163.com>` and commit only intended files.
3. Deploy the committed revision with the existing server Compose project without replacing `.env` or volumes.
4. Confirm container health, public HTTPS/readiness, security headers, learner navigation, and MCP endpoint behavior.
