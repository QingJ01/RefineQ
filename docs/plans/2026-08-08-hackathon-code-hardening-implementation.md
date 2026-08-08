# Hackathon Code Hardening Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the demo, password reset, default product story, and mobile core loop production-honest before deployment and user-research work begins.

**Architecture:** Reuse the configured `Database` for demo data, add a small standard-library SMTP delivery boundary behind auth capability detection, and keep the frontend truthful by hiding unavailable recovery. Align submission-facing fixtures around one exam journey and prove it at a mobile viewport.

**Tech Stack:** Python 3.11–3.13, FastAPI, Pydantic Settings, SQLAlchemy, standard-library SMTP, Next.js 16, React 19, TypeScript, Vitest, Playwright.

---

### Task 1: Seed demo data into the configured database

**Files:**
- Modify: `src/refineq/config.py`
- Modify: `src/refineq/operations/demo.py`
- Modify: `scripts/seed_demo.py`
- Modify: `tests/operations/test_demo.py`

**Step 1: Write the failing tests**

Add tests that pass a non-default `Database` into `seed_demo`, assert no private SQLite database is created, require an explicit password, keep a same-password rerun idempotent, and verify the command does not print a password.

**Step 2: Run tests to verify RED**

Run: `python -m pytest tests/operations/test_demo.py -q`

Expected: FAIL because `seed_demo` still creates its own SQLite database and exposes a constant password.

**Step 3: Implement the minimal database and credential boundary**

Change the operation API to accept `Database`, `data_root`, `email`, and `password`. Add `demo_email` and optional secret `demo_password` settings. Make the CLI open `Settings.resolved_database_url`, require the secret, close the database in `finally`, and print only the email and workspace.

**Step 4: Run tests to verify GREEN**

Run: `python -m pytest tests/operations/test_demo.py -q`

Expected: PASS.

**Step 5: Commit**

Commit: `fix: seed demo data in the configured database`

### Task 2: Add optional SMTP reset delivery and capability detection

**Files:**
- Create: `src/refineq/identity/password_reset.py`
- Modify: `src/refineq/config.py`
- Modify: `src/refineq/identity/models.py`
- Modify: `src/refineq/api/app.py`
- Modify: `src/refineq/api/routers/auth.py`
- Create: `tests/unit/identity/test_password_reset_delivery.py`
- Modify: `tests/integration/test_auth.py`

**Step 1: Write failing configuration and delivery tests**

Cover default-disabled delivery, complete SMTP configuration, invalid partial credentials, mutually exclusive TLS modes, message recipients, safe fragment URL construction, and sanitized delivery failures.

**Step 2: Run tests to verify RED**

Run: `python -m pytest tests/unit/identity/test_password_reset_delivery.py tests/integration/test_auth.py -q`

Expected: FAIL because the delivery service and capability model do not exist.

**Step 3: Implement SMTP delivery**

Add immutable SMTP configuration, a delivery protocol, standard-library SMTP transport with an injectable factory, and a no-op/disabled implementation. Build a reset URL with a fragment and send a plain-text message.

**Step 4: Write and verify failing API tests**

Add tests for `/auth/capabilities`, uniform responses, no token creation while disabled, scheduled delivery for known users, no delivery for unknown users, and isolated exposed-token compatibility.

**Step 5: Implement API integration**

Initialize the delivery service in `create_app`, expose the boolean capability, and schedule safe delivery after reset requests. Preserve the existing one-time token contract.

**Step 6: Run tests to verify GREEN**

Run: `python -m pytest tests/unit/identity/test_password_reset_delivery.py tests/integration/test_auth.py -q`

Expected: PASS.

**Step 7: Commit**

Commit: `feat: deliver password resets through optional smtp`

### Task 3: Hide unavailable recovery and consume reset fragments

**Files:**
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/components/auth-panel.tsx`
- Modify: `apps/web/tests/components.test.tsx`
- Modify: `apps/web/tests/contracts.test.ts`

**Step 1: Write failing frontend tests**

Assert that recovery is hidden before/when capabilities are disabled, shown when enabled, and that `#reset-token=...` opens reset mode then clears the fragment.

**Step 2: Run tests to verify RED**

Run: `npm test -- --run apps/web/tests/components.test.tsx apps/web/tests/contracts.test.ts`

Expected: FAIL because the frontend does not request auth capabilities or consume reset fragments.

**Step 3: Implement minimal frontend behavior**

Add the capability type and API call. Fetch capabilities in `AuthPanel`, default to unavailable, conditionally render the control, and consume/clear the reset fragment in an effect.

**Step 4: Run tests to verify GREEN**

Run: `npm test -- --run apps/web/tests/components.test.tsx apps/web/tests/contracts.test.ts`

Expected: PASS.

**Step 5: Commit**

Commit: `fix: show password recovery only when available`

### Task 4: Align the default exam story

**Files:**
- Modify: `src/refineq/operations/demo.py`
- Modify: `tests/operations/test_demo.py`
- Modify: `apps/web/lib/i18n.ts`
- Modify: `apps/web/tests/learning-home-direction.test.tsx`
- Modify: `apps/web/tests/e2e/learning-journey.spec.ts`

**Step 1: Write failing copy and demo assertions**

Require homepage guidance to include exam, date, and daily-time cues. Require demo data to use computer-architecture notes and explicitly presentation-only metadata.

**Step 2: Run tests to verify RED**

Run: `python -m pytest tests/operations/test_demo.py -q` and `npm test -- --run apps/web/tests/learning-home-direction.test.tsx`

Expected: FAIL against the current general/product-thinking and calculus fixtures.

**Step 3: Update defaults and fixtures**

Replace submission-facing copy and demo seed content with one computer-architecture exam journey while retaining universal capability support elsewhere.

**Step 4: Run tests to verify GREEN**

Run the same focused commands; expected PASS.

**Step 5: Commit**

Commit: `fix: align submission-facing exam story`

### Task 5: Prove the complete mobile core loop

**Files:**
- Modify: `apps/web/tests/e2e/learning-journey.spec.ts`

**Step 1: Write the mobile journey before changing application code**

At 390×844, register, create the dated exam workspace, upload source material, start an exam task, submit an answer, and inspect progress. Keep all interactions on mobile.

**Step 2: Run Playwright to verify RED or discover existing support**

Run: `npm run test:e2e -- --grep "mobile exam"`

Expected: either a focused failure that identifies the missing mobile behavior or PASS if existing product behavior already satisfies the new proof. If it passes immediately, retain it as new coverage without claiming a product fix.

**Step 3: Implement only confirmed application fixes**

If the test reveals a real mobile blocker, add the smallest UI change and a focused component/contract test first. Do not redesign the interface.

**Step 4: Re-run Playwright**

Expected: PASS at 390×844 without switching viewports.

**Step 5: Commit**

Commit: `test: prove the mobile exam learning loop`

### Task 6: Wire runtime configuration and perform final verification

**Files:**
- Modify: `.env.example`
- Modify: `infra/compose.yml`
- Modify: `README.md`

**Step 1: Add configuration contract tests or static assertions first**

Extend existing contract tests to require SMTP, public-site URL, and demo credential variables in Compose/example configuration without literal secrets.

**Step 2: Run the focused tests to verify RED**

Expected: FAIL until the configuration is wired.

**Step 3: Add non-secret configuration documentation and Compose passthrough**

Document variable names and behavior only. Do not add deployment values or real credentials.

**Step 4: Run the full verification matrix**

Run:

- `python -m pytest -q`
- `python -m ruff check src tests scripts`
- `python -m ruff format --check src tests scripts`
- `python scripts/scan_secrets.py`
- `npm test -- --run`
- `npm run lint`
- `npm run build`
- `npm run test:e2e`

Expected: all pass with no unexpected browser errors.

**Step 5: Commit**

Commit: `docs: document optional smtp and demo settings`
