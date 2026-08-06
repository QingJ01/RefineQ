# Complete Review Remediation Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix every confirmed code-review defect and make RefineQ safe, bounded, recoverable, and usable through repeated personal-learning sessions.

**Architecture:** Enforce reusable policies at domain boundaries, make multi-resource writes transactional or compensating, and keep frontend state controlled by the workspace shell. Preserve the FastAPI/Next.js stack and existing API compatibility while adding safe configuration knobs.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLite/atomic JSON, PyMuPDF, python-docx, cryptography/Fernet, Next.js 16, React 19, TypeScript, Vitest, Playwright, Docker Compose.

---

### Task 1: Secure model configuration and transport

**Files:**
- Modify: `src/refineq/config.py`
- Modify: `src/refineq/agent/settings.py`
- Modify: `src/refineq/agent/service.py`
- Modify: `src/refineq/agent/structured.py`
- Modify: `src/refineq/api/app.py`
- Modify: `src/refineq/api/routers/settings.py`
- Test: `tests/unit/agent/test_settings.py`
- Test: `tests/unit/agent/test_structured.py`
- Test: `tests/integration/test_agent_chat.py`

**Steps:**

1. Add failing tests for private/link-local/HTTP endpoints, allowlisted internal gateways, encrypted persistence, legacy migration, finite transport timeouts, bounded history, bounded replies, and invalid citation removal.
2. Run the focused tests and confirm each fails for the reviewed behavior.
3. Implement `ModelEndpointPolicy`, encrypted schema v2 persistence, legacy schema v1 migration, finite OpenAI client limits, rolling context/history retention, and citation sanitization.
4. Run focused and agent integration tests until green; run Ruff on touched files.
5. Commit as `fix: secure model configuration and agent context`.

### Task 2: Bound planning and honor learner intent

**Files:**
- Modify: `src/refineq/learning/planning.py`
- Modify: `src/refineq/workspaces/models.py`
- Modify: `src/refineq/workspaces/routing.py`
- Modify: `src/refineq/workspaces/intelligence.py`
- Modify: `src/refineq/workspaces/service.py`
- Modify: `src/refineq/api/routers/workspaces.py`
- Modify: `src/refineq/storage/workspaces.py`
- Modify: `src/refineq/storage/learning.py`
- Test: `tests/unit/learning/test_planning_and_evidence.py`
- Test: `tests/unit/workspaces/test_routing.py`
- Test: `tests/unit/workspaces/test_intelligent_routing.py`
- Test: `tests/integration/test_workspace_journey.py`

**Steps:**

1. Add failing tests for maximum plan horizon, past exam validation, Chinese/English relative dates and daily minutes, explicit-value precedence, subject-only non-reuse, and zero persisted state after provisioning failure.
2. Verify the tests reproduce the year-9999 allocation, ignored intent, Python/Rust merge, and orphaned workspace bugs.
3. Implement bounded planning, deterministic constraint extraction, stricter reuse scoring, narrow model-fallback exceptions, and a prebuild/compensating provisioning transaction.
4. Return stable 4xx domain errors for invalid goals rather than 500 responses.
5. Run focused and integration tests, then commit as `fix: make workspace planning bounded and atomic`.

### Task 3: Make uploads resource-bounded and atomic

**Files:**
- Modify: `src/refineq/config.py`
- Modify: `src/refineq/knowledge/extract.py`
- Modify: `src/refineq/knowledge/index.py`
- Modify: `src/refineq/knowledge/policy.py`
- Modify: `src/refineq/api/routers/materials.py`
- Test: `tests/unit/knowledge/test_extract.py`
- Test: `tests/unit/knowledge/test_index.py`
- Test: `tests/integration/test_material_upload.py`

**Steps:**

1. Add failing tests for oversized DOCX expansion, excessive compression ratio, PDF page count, extracted-character budget, per-user material quota, valid-plus-invalid batch rollback, and index-write rollback.
2. Confirm the focused tests fail before production edits.
3. Add archive/PDF extraction budgets and deadline checks, execute extraction off the event loop, preflight every file, stage material files, and commit metadata/chunks in one SQLite transaction with compensating file cleanup.
4. Add total material count/byte quota checks before extraction and stable 413/422 errors.
5. Run focused and integration tests, then commit as `fix: bound and atomically persist learning materials`.

### Task 4: Protect public API capacity and identity validation

**Files:**
- Create: `src/refineq/api/limits.py`
- Modify: `src/refineq/config.py`
- Modify: `src/refineq/api/app.py`
- Modify: `src/refineq/api/dependencies.py`
- Modify: `src/refineq/api/routers/auth.py`
- Modify: mutation routers under `src/refineq/api/routers/`
- Modify: `src/refineq/identity/models.py`
- Test: `tests/unit/test_config.py`
- Test: `tests/integration/test_auth.py`
- Test: `tests/integration/test_workspace_journey.py`

**Steps:**

1. Add failing tests for login/register burst limiting, authenticated mutation limiting, workspace-count quota, invalid identifiers, and UTF-8 passwords over bcrypt's byte limit.
2. Confirm failures match the reviewed capacity and validation gaps.
3. Implement a thread-safe monotonic sliding-window limiter keyed by trusted client address or user id, configurable limits, workspace quota enforcement, path-id validation, and byte-aware password validation.
4. Return `429` with `Retry-After` and stable structured codes; never turn validation failures into 500s.
5. Run focused and integration tests, then commit as `fix: add API abuse and quota boundaries`.

### Task 5: Make fallback grading evidence-worthy

**Files:**
- Modify: `src/refineq/learning/intelligence.py`
- Modify: `src/refineq/learning/service.py`
- Test: `tests/unit/learning/test_intelligence.py`
- Test: `tests/integration/test_ai_practice.py`

**Steps:**

1. Add failing tests proving a topic echo and generic filler fail, while a substantive explanation plus example can pass.
2. Add a failing integration test proving uncertain fallback grading cannot increase mastery.
3. Implement deterministic token/character, expected-concept, and example/application signals plus a `mastery_evidence` confidence field.
4. Gate BKT updates on trustworthy evidence and return actionable feedback.
5. Run learning tests and commit as `fix: require substantive evidence for fallback grading`.

### Task 6: Repair repeated-session frontend flows

**Files:**
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/components/practice-card.tsx`
- Modify: `apps/web/components/material-dropzone.tsx`
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/components/agent-panel.tsx`
- Modify: `apps/web/lib/i18n.ts`
- Test: `apps/web/tests/components.test.tsx`
- Test: `apps/web/tests/contracts.test.ts`
- Test: `apps/web/tests/e2e/learning-journey.spec.ts`

**Steps:**

1. Add failing component tests for next-question state, controlled material refresh after remount, agent error/retry/settings guidance, and request timeout errors.
2. Confirm failures before editing components.
3. Add explicit practice phases and next-question action, lift materials to the workspace parent, handle agent exceptions with recoverable UI, preload public model settings, and use abortable API requests.
4. Extend Playwright to answer two consecutive questions, upload then navigate away/back, and recover from an unconfigured model.
5. Run Vitest/ESLint/build and commit as `fix: make learning sessions repeatable and recoverable`.

### Task 7: Reproducible dependencies, docs, and complete verification

**Files:**
- Modify: `pyproject.toml`
- Create: `requirements.lock`
- Modify: `apps/web/package-lock.json` only through the package manager when necessary
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/operations.md` or the existing deployment documentation
- Modify: `.github/workflows/ci.yml`
- Modify: `infra/backend.Dockerfile`
- Test: `tests/contract/test_deployment.py`
- Test: `tests/contract/test_secret_scan.py`

**Steps:**

1. Add contract tests requiring encrypted-key configuration guidance, pinned Python installs, and CI use of the lock file.
2. Pin a tested Python dependency graph and update Docker/CI to install it reproducibly.
3. Resolve the Starlette test-client deprecation through the supported dependency/API path and keep test output warning-free.
4. Document endpoint allowlisting, encryption-key rotation/backup behavior, quotas, limits, and extraction budgets.
5. Run `pytest`, Ruff check/format, Vitest, ESLint, Next build, Playwright, `pip check`, Python vulnerability audit, npm audit, Docker image/Compose health checks, secret scan, and `git diff --check`.
6. Review the complete diff, commit final documentation/lock updates, merge to `main`, push, and monitor GitHub Actions to completion.

