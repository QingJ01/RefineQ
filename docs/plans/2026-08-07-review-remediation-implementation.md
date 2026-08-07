# Complete Review Remediation Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for each behavior and superpowers:verification-before-completion before reporting success.

**Goal:** Fix every actionable issue from the 2026-08-07 complete code review.

**Architecture:** Preserve the current application boundaries while moving consistency into database
transactions, binding storage rollback to the concrete backend, bounding OCR/embedding work, and
using PostgreSQL indexes for production retrieval. Keep SQLite as a tested local fallback.

**Tech Stack:** Python 3.11+, FastAPI, AnyIO, SQLAlchemy, PostgreSQL 17, pgvector, PyMuPDF, boto3,
Next.js 16, React 19, TypeScript, pytest, Vitest, Playwright, GitHub Actions.

---

### Task 1: Fail-closed object storage rollback

**Files:**
- Modify: `src/refineq/integrations/object_storage.py`
- Modify: `src/refineq/integrations/repository.py`
- Test: `tests/unit/integrations/test_object_storage.py`
- Test: `tests/unit/integrations/test_repository.py`

1. Add failing tests for conditional S3 creation, backend-bound rollback, canonical keys, and corrupt-secret failure.
2. Run the focused tests and confirm the old implementation fails for the intended assertions.
3. Implement conditional creation, hash verification, rollback handles, and a distinct configuration-corruption exception.
4. Run the focused tests to green.

### Task 2: Transactional quota and non-blocking uploads

**Files:**
- Modify: `src/refineq/knowledge/index.py`
- Modify: `src/refineq/api/routers/materials.py`
- Test: `tests/unit/knowledge/test_index.py`
- Test: `tests/integration/test_material_upload.py`

1. Add failing tests for replacement-aware quota, quota failure rollback, and worker-thread execution.
2. Confirm failures against the process-local lock implementation.
3. Add a quota-aware index transaction with a PostgreSQL advisory lock and SQLite process lock.
4. Move blocking storage/index work to AnyIO's worker pool and translate quota errors to HTTP 413.
5. Run the focused tests to green.

### Task 3: Indexed PostgreSQL hybrid retrieval and embedding backfill

**Files:**
- Modify: `src/refineq/database/engine.py`
- Modify: `src/refineq/knowledge/index.py`
- Modify: `src/refineq/api/routers/admin.py`
- Test: `tests/unit/knowledge/test_hybrid_search.py`
- Test: `tests/integration/test_postgres_database.py`

1. Add failing tests for bounded PostgreSQL candidates, embedding batches, partial failure, and backfill.
2. Add `pg_trgm` and the trigram index alongside existing FTS and HNSW indexes.
3. Implement bounded SQL lexical and semantic candidate queries and candidate fusion.
4. Add sanitized embedding diagnostics, batches, and missing-vector backfill scheduled after embedding updates.
5. Run local focused tests; leave the real PostgreSQL test environment-gated locally.

### Task 4: Bounded mixed-PDF OCR and real vision health test

**Files:**
- Modify: `src/refineq/integrations/ocr.py`
- Modify: `src/refineq/integrations/service.py`
- Modify: `src/refineq/api/routers/materials.py`
- Modify: `src/refineq/config.py`
- Test: `tests/unit/integrations/test_ocr.py`
- Test: `tests/integration/test_admin_integrations.py`

1. Add failing tests for page batching, pixel/encoded-byte rejection, mixed text/scanned PDFs, and a vision request health check.
2. Implement pre-render budgets, incremental rendering, ordered page reconstruction, and actual vision testing.
3. Connect mixed-PDF augmentation to successful local PDF extraction.
4. Run focused tests to green.

### Task 5: Endpoint allowlists and runtime address validation

**Files:**
- Create: `src/refineq/integrations/endpoints.py`
- Modify: `src/refineq/integrations/models.py`
- Modify: `src/refineq/integrations/repository.py`
- Modify: `src/refineq/agent/settings.py`
- Modify: outbound model, embedding, OCR, and object-storage transports
- Modify: `src/refineq/config.py`, `.env.example`, `infra/compose.yml`, deployment docs
- Test: `tests/unit/integrations/test_endpoints.py`
- Test: integration configuration tests

1. Add failing tests for localhost aliases, DNS-to-private addresses, explicit private opt-in, and storage allowlists.
2. Implement normalized allowlists and runtime DNS/IP checks.
3. Invoke validation immediately before every outbound provider client is used.
4. Update deployment configuration and run focused tests.

### Task 6: Admin status and global session controls

**Files:**
- Modify: `apps/web/components/learning-home.tsx`
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/components/admin-console.tsx`
- Modify: `apps/web/app/styles.css`
- Test: `apps/web/tests/components.test.tsx`
- Test: `apps/web/tests/contracts.test.ts`

1. Add failing component/contract tests for logout controls and immediate test-status projection.
2. Add home/admin logout actions and responsive styling.
3. Update the integration card state after a connection-test response.
4. Run Vitest, ESLint, and the Next.js build.

### Task 7: Real PostgreSQL CI and documentation

**Files:**
- Modify: `.github/workflows/tests.yml`
- Modify: `tests/integration/test_postgres_database.py`
- Modify: `docs/deployment.md`, `docs/operations.md`, `README.md`

1. Expand the environment-gated PostgreSQL tests for vector/lexical search, JSONB, and concurrent quota enforcement.
2. Add a healthy pgvector service and database URL to the Python CI job.
3. Document endpoint allowlists, private-network opt-in, OCR budgets, and embedding backfill behavior.
4. Run the complete project verification matrix and inspect the final diff and repository status.
