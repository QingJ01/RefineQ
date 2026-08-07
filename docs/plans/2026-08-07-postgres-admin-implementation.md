# PostgreSQL Admin Platform Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace file/SQLite business persistence with PostgreSQL + pgvector, add encrypted platform integrations and an admin-only configuration console, and bootstrap an administrator account.

**Architecture:** Preserve existing repository contracts through a SQL JSONB record store, while using normalized identity, integration, audit, material, and chunk tables. PostgreSQL is the production runtime; SQLite remains a test-only compatibility dialect. External capabilities degrade independently so uploads and lexical search remain usable without optional APIs.

**Tech Stack:** Python 3.11–3.13, FastAPI, SQLAlchemy 2, Psycopg 3, pgvector, PostgreSQL, OpenAI-compatible APIs, boto3 S3 client, Next.js 16, React 19, TypeScript, Pytest, Vitest.

---

### Task 1: Database foundation and schema lifecycle

**Files:**
- Modify: `pyproject.toml`
- Modify: `requirements.lock`
- Modify: `requirements-dev.lock`
- Modify: `src/refineq/config.py`
- Create: `src/refineq/database/engine.py`
- Create: `src/refineq/database/schema.py`
- Test: `tests/unit/database/test_engine.py`
- Test: `tests/unit/test_config.py`

**Steps:** Add failing configuration and schema tests; verify RED; implement URL validation, engine creation, pgvector-aware schema initialization and transaction helpers; verify GREEN; run focused Ruff checks.

### Task 2: PostgreSQL record store compatibility

**Files:**
- Create: `src/refineq/storage/sql_store.py`
- Modify: `src/refineq/api/app.py`
- Test: `tests/unit/storage/test_sql_store.py`
- Modify: `tests/integration/*`

**Steps:** Write contract tests for create/read/list/save/mutate/delete, owner isolation, optimistic versions and transactional quota locks; verify RED; implement the store against SQLAlchemy; inject it through the app factory; verify repository and journey suites.

### Task 3: Database identity, roles, and administrator bootstrap

**Files:**
- Modify: `src/refineq/identity/models.py`
- Rewrite: `src/refineq/identity/service.py`
- Modify: `src/refineq/api/dependencies.py`
- Create: `src/refineq/operations/admin.py`
- Create: `scripts/create_admin.py`
- Test: `tests/integration/test_admin_auth.py`
- Test: `tests/operations/test_admin.py`

**Steps:** Add failing role and authorization tests; verify RED; implement database-backed users, server JWT secret, live role lookup and admin dependency; implement idempotent administrator creation; verify GREEN and ensure plaintext passwords never persist.

### Task 4: Encrypted platform integrations and admin API

**Files:**
- Create: `src/refineq/integrations/models.py`
- Create: `src/refineq/integrations/repository.py`
- Create: `src/refineq/integrations/service.py`
- Create: `src/refineq/api/routers/admin.py`
- Modify: `src/refineq/agent/settings.py`
- Modify: `src/refineq/api/app.py`
- Test: `tests/unit/integrations/test_repository.py`
- Test: `tests/integration/test_admin_integrations.py`

**Steps:** Test secret encryption/redaction, role denial, typed provider validation, enable/disable and connection-test error envelopes; verify RED; implement repository/service/router; make Agent settings resolve platform defaults with optional per-user compatibility; verify GREEN.

### Task 5: PostgreSQL knowledge index and pgvector retrieval

**Files:**
- Rewrite: `src/refineq/knowledge/index.py`
- Create: `src/refineq/knowledge/embeddings.py`
- Test: `tests/unit/knowledge/test_hybrid_search.py`
- Modify: `tests/unit/knowledge/test_index.py`

**Steps:** Add failing tests for material transactions, lexical isolation, vector storage, hybrid ranking and embedding failure fallback; verify RED; implement database material/chunk storage, OpenAI-compatible embeddings and reciprocal score fusion; verify GREEN.

### Task 6: Unified object storage and OCR hooks

**Files:**
- Create: `src/refineq/integrations/object_storage.py`
- Create: `src/refineq/integrations/ocr.py`
- Modify: `src/refineq/api/routers/materials.py`
- Test: `tests/unit/integrations/test_object_storage.py`
- Test: `tests/unit/integrations/test_ocr.py`
- Modify: `tests/integration/test_material_upload.py`

**Steps:** Test local/S3 key isolation, rollback, scan detection and OCR fallback; verify RED; implement storage abstraction and optional OCR; update upload transaction flow; verify GREEN.

### Task 7: Administrator console

**Files:**
- Create: `apps/web/components/admin-console.tsx`
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/i18n.ts`
- Modify: `apps/web/app/styles.css`
- Modify: `apps/web/tests/components.test.tsx`
- Modify: `apps/web/tests/contracts.test.ts`

**Steps:** Add failing rendering and API contract tests; verify RED; implement role-aware navigation, provider cards, secret-safe forms, health badges and connection tests in the existing warm editorial visual language; verify GREEN, responsive behavior and accessibility.

### Task 8: Migration, deployment, bootstrap, and operations

**Files:**
- Create: `scripts/migrate_to_postgres.py`
- Create: `tests/operations/test_postgres_migration.py`
- Modify: `infra/compose.yml`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/deployment.md`
- Modify: `docs/operations.md`

**Steps:** Test dry-run, idempotency and source preservation; verify RED; implement migration reporting; add pgvector service/readiness and environment variables; initialize the requested administrator locally; run all verification commands and document the unavailable real-container check if Docker remains absent.
