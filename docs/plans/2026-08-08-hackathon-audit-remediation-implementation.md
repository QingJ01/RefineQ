# Hackathon Audit Remediation Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close every still-valid code finding from the hackathon adversarial audit without weakening evidence integrity, trust boundaries, or transactional safety.

**Architecture:** Treat learning evidence, proxy identity, persistent operations, and database transactions as explicit boundaries. Use deterministic local gates around model output, optimistic short transactions around network work, and user confirmation around material-derived topic suggestions.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy, PostgreSQL/SQLite, Next.js 16, React 19, TypeScript, Vitest, Playwright, Docker Compose, Caddy.

---

### Task 1: Intent parsing, positioning, and deterministic topic ordering

**Files:**
- Modify: README.md
- Modify: src/refineq/workspaces/constraints.py
- Modify: apps/web/components/progress-insights.tsx
- Test: tests/unit/workspaces/test_constraints.py
- Test: apps/web/tests/components.test.tsx

1. Add failing tests for M/D parsing, relative-over-absolute precedence, and mastery tie ordering.
2. Run the two focused suites and confirm the new assertions fail for the intended reason.
3. Add slash-date parsing without weakening explicit-year validation; choose relative constraints first when both occur.
4. Add topic ID as the secondary frontend sort key and rewrite the README opening around the concrete exam-and-material situation.
5. Re-run focused tests, lint the frontend, and commit.

### Task 2: Independent mastery evidence, stable mastery, and AI evidence gate

**Files:**
- Modify: src/refineq/learning/models.py
- Modify: src/refineq/learning/intelligence.py
- Modify: src/refineq/learning/service.py
- Modify: apps/web/lib/types.ts
- Modify: apps/web/components/progress-insights.tsx
- Test: tests/unit/learning/test_bkt.py
- Test: tests/unit/learning/test_intelligence.py
- Test: tests/unit/learning/test_diagnostic_and_difficulty.py
- Test: tests/integration/test_ai_practice.py
- Test: tests/integration/test_learning_journey.py
- Test: apps/web/tests/components.test.tsx

1. Add failing tests proving one question can update BKT/difficulty at most once after its first sufficient attempt.
2. Add failing tests proving model sufficient_evidence cannot bypass the deterministic substantive-answer gate.
3. Add failing API/UI tests for stable mastery and regression tests that preserve consecutive difficulty semantics.
4. Add a bounded credited_question_ids field, derive mastery_updated from evidence sufficiency and independence, and expose stable by topic.
5. Require local gate AND model gate for AI mastery evidence; keep score feedback available even when mastery is unchanged.
6. Render “mastered” only for stable topics, run all focused suites, and commit.

### Task 3: Authentication and trusted-proxy boundary

**Files:**
- Modify: src/refineq/api/limits.py
- Modify: infra/compose.yml
- Modify: .env.example
- Modify: docs/deployment.md
- Test: tests/unit/api/test_limits.py
- Test: tests/contract/test_deployment.py

1. Add failing tests that password-reset endpoints consume the auth bucket and deployment config never trusts all forwarded clients.
2. Add a deterministic Compose network address for Caddy and trust only that address by default.
3. Document the override contract and add a real proxy-header integration check where the environment permits it.
4. Run focused auth, limit, entrypoint, and deployment contract tests; commit.

### Task 4: Health routing, startup checks, and persistent backups

**Files:**
- Modify: src/refineq/config.py
- Modify: src/refineq/operations/admin.py
- Modify: infra/Caddyfile
- Modify: infra/Dockerfile.api
- Modify: infra/Dockerfile.web
- Modify: infra/compose.yml
- Modify: .env.example
- Modify: docs/operations.md
- Test: tests/operations/test_backup.py
- Test: tests/unit/test_config.py
- Test: tests/contract/test_deployment.py

1. Add failing tests for REFINEQ_BACKUP_ROOT, an independent backup volume, public /health routing, and fast health intervals.
2. Resolve backup_root only through Settings and mount /backups as its own named volume.
3. Route /health directly to the API and reduce initial health-check latency without changing readiness semantics.
4. Run focused tests and, if Docker is available, validate the rendered Compose model; commit.

### Task 5: Honest feedback, readable coach context, and privacy-safe observability

**Files:**
- Modify: src/refineq/agent/actions.py
- Modify: src/refineq/agent/context.py
- Modify: src/refineq/agent/service.py
- Modify: src/refineq/learning/intelligence.py
- Modify: apps/web/components/learning-session-canvas.tsx
- Modify: apps/web/app/styles.css
- Test: tests/unit/agent/test_actions.py
- Test: tests/unit/agent/test_context.py
- Test: tests/unit/learning/test_intelligence.py
- Test: apps/web/tests/components.test.tsx

1. Add failing tests for readable weak-topic names, truthful misconception rendering, AI/fallback badges, and sanitized fallback/capacity logs.
2. Pass topic labels into coach context, render misconceptions only when supplied, and render generation/grading modes.
3. Emit structured event/reason/duration fields without user identifiers, answers, source text, tokens, or endpoints.
4. Run focused backend/frontend tests and commit.

### Task 6: Plan and evidence feedback loops

**Files:**
- Modify: src/refineq/learning/intelligence.py
- Modify: src/refineq/learning/service.py
- Modify: src/refineq/api/routers/learning.py
- Modify: apps/web/lib/types.ts
- Modify: apps/web/lib/api.ts
- Modify: apps/web/components/study-workspace.tsx
- Test: tests/unit/learning/test_intelligence.py
- Test: tests/integration/test_ai_practice.py
- Test: tests/integration/test_learning_journey.py
- Test: apps/web/tests/contracts.test.ts

1. Add failing tests for plan_session_id topic/mode selection, automatic completion after sufficient submission, and bounded same-topic learning needs.
2. Map learn/practice/apply/review to concept/case/project/exam on the server and store the originating plan session on the question.
3. Complete the originating session only when the attempt supplies mastery evidence.
4. Pass the latest three same-topic gaps/misconceptions in an explicitly untrusted prompt block.
5. Update frontend request wiring, run focused tests, and commit.

### Task 7: Reachable initial diagnostic

**Files:**
- Modify: src/refineq/api/routers/learning.py
- Modify: apps/web/lib/types.ts
- Modify: apps/web/lib/api.ts
- Create: apps/web/components/initial-diagnostic.tsx
- Modify: apps/web/components/study-workspace.tsx
- Modify: apps/web/app/styles.css
- Test: tests/integration/test_learning_journey.py
- Test: apps/web/tests/components.test.tsx
- Test: apps/web/tests/contracts.test.ts

1. Add failing API client and component tests for one bounded initial self-assessment per workspace.
2. Expose the existing workspace diagnostic route, submit one true/false result per topic, and refresh snapshot/progress afterward.
3. Label it as an initial self-assessment rather than an adaptive AI diagnosis.
4. Run focused tests, accessibility-oriented component assertions, lint, and commit.

### Task 8: User-confirmed material topic suggestions

**Files:**
- Modify: src/refineq/workspaces/service.py
- Modify: src/refineq/storage/workspaces.py
- Modify: src/refineq/api/routers/workspaces.py
- Modify: apps/web/lib/types.ts
- Modify: apps/web/lib/api.ts
- Modify: apps/web/components/material-dropzone.tsx
- Modify: apps/web/components/study-workspace.tsx
- Test: tests/integration/test_workspace_journey.py
- Test: apps/web/tests/components.test.tsx

1. Add failing tests that suggestions derive only from bounded titles/tags, never auto-write, and require explicit acceptance.
2. Add an owner-scoped suggestion endpoint and an atomic accept operation that appends workspace and learning topics together.
3. Show suggestions after upload with explicit accept controls; refresh snapshot after acceptance.
4. Run focused isolation, rollback, component, and lint tests; commit.

### Task 9: Short transaction boundaries and nested advisory locks

**Files:**
- Modify: src/refineq/storage/sql_store.py
- Modify: src/refineq/learning/service.py
- Modify: src/refineq/workspaces/service.py
- Modify: src/refineq/agent/service.py
- Test: tests/unit/storage/test_sql_store.py
- Test: tests/integration/test_workspace_journey.py
- Test: tests/integration/test_agent_chat.py
- Test: tests/integration/test_ai_practice.py

1. Add failing concurrency tests with blocking transports that prove reads remain possible while model work is pending.
2. Add a PostgreSQL-oriented test proving nested scopes acquire their own advisory transaction locks.
3. Split question generation, workspace routing, and agent reply generation into snapshot/network/conditional-commit phases.
4. Recheck request_id, turn_id, pending state, quota, and record version during the final short transaction; replay or conflict instead of double-writing.
5. Run focused concurrency suites repeatedly and commit.

### Task 10: Boundary-preserving chunks and rank-based hybrid retrieval

**Files:**
- Modify: src/refineq/knowledge/index.py
- Test: tests/unit/knowledge/test_index.py
- Test: tests/unit/knowledge/test_hybrid_search.py

1. Add failing tests for a fact spanning a chunk boundary, rank-scale invariance, and low-similarity exclusion.
2. Split near sentence/paragraph boundaries, keep approximately 12 percent bounded overlap, and guarantee forward progress.
3. Fuse positive lexical and above-threshold semantic ranks with weighted reciprocal-rank fusion.
4. Run index, hybrid, material upload, and AI-practice tests; commit.

### Task 11: Remove unshipped dead implementations

**Files:**
- Modify: src/refineq/agent/settings.py
- Delete: src/refineq/learning/diagnostic.py
- Delete: src/refineq/learning/errors.py
- Modify: src/refineq/learning/evidence.py
- Modify: src/refineq/learning/models.py
- Delete: tests/unit/agent/test_settings.py
- Delete: tests/unit/learning/test_errors.py
- Modify: tests/unit/learning/test_diagnostic_and_difficulty.py
- Modify: tests/unit/learning/test_planning_and_evidence.py
- Test: tests/contract/test_repository_shape.py

1. Add or update repository-shape assertions so removed internal engines cannot be advertised accidentally.
2. Convert ModelSettingsRepository to the structural interface actually consumed by production.
3. Remove unused adaptive-diagnostic, error-analysis, and recommendation implementations and their isolated tests.
4. Keep the shipped initial diagnostic API, evidence creation, and platform model configuration intact.
5. Run unit, integration, import, and repository-shape tests; commit.

### Task 12: Documentation, full verification, review, and integration

**Files:**
- Modify: docs/plans/2026-08-08-hackathon-audit-remediation.md
- Modify: docs/architecture.md
- Modify: docs/operations.md
- Modify: README.md

1. Reconcile every finding with implemented, rejected-with-reason, or already-fixed status.
2. Run ruff check, ruff format --check, the full Python suite, frontend tests, frontend lint, frontend build, Playwright, secret scan, and Compose config.
3. Request an independent code review over origin/main..HEAD and fix every Critical or Important finding with a new RED/GREEN cycle.
4. Re-run the complete verification gate after review fixes.
5. Push codex/hackathon-remediation, create a ready PR, inspect checks and diff, merge only when green, then verify origin/main contains the merge.
