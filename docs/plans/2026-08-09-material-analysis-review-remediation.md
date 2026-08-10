# Material Analysis Review Remediation Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Merge the updated adversarial audit with the material-analysis release review, eliminate the confirmed data-integrity and trust-boundary defects, and restore one coherent upload-to-analysis-to-plan product flow.

**Architecture:** Keep canonical material bytes and chunks in the owner-scoped `library`, model workspace use through `workspace_materials`, and enforce every destructive or planning transition at the service boundary. Treat retrieval text as untrusted evidence, never as a grading key. Make structured-model capability observable through one schema-enforced transport and an administrator canary. The web experience exposes one primary next action at a time and only mutates the records visible to the user.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Pydantic v2, pytest, Next.js/React/TypeScript, Vitest, Playwright.

---

## Task 1: Make the v2-to-v3 material migration duplicate-safe

**Files:**

- Modify: `src/refineq/database/engine.py`
- Test: `tests/operations/test_workspace_migration.py`

1. Add a migration fixture containing identical `material_id` and chunk indexes in two workspaces for one owner.
2. Run the focused migration test and confirm the current bulk `project_id = 'library'` update violates the unique constraints.
3. Before canonicalization, insert every workspace link, choose one deterministic source row for each owner/material pair, and remove duplicate material/chunk rows.
4. Run the focused migration tests and assert one canonical material, one chunk set, and both workspace links remain.

## Task 2: Repair canonical-library projections and physical deletion

**Files:**

- Modify: `src/refineq/knowledge/index.py`
- Modify: `src/refineq/knowledge/deletion.py`
- Modify: `src/refineq/materials/repository.py`
- Modify: `src/refineq/api/routers/materials.py`
- Test: `tests/integration/test_material_upload.py`
- Test: `tests/unit/knowledge/test_material_deletion.py`

1. Add failing tests proving workspace status counts are zero after linking a canonical material, library deletion leaves workspace links behind, same-content re-upload reattaches stale workspaces, and a second-row deletion fault leaves the first SQL row deleted.
2. Compute counts by joining `workspace_materials` to canonical `materials` under the same owner.
3. Delete canonical link rows and material/chunk rows in the same database transaction.
4. Delete a prepared batch in one SQL transaction rather than one transaction per entry; retain the object journal for compensation.
5. Remove successful library analysis projections so a same-content upload cannot inherit stale analysis.
6. Run focused integration and deletion tests.

## Task 3: Enforce evidence and planning invariants

**Files:**

- Modify: `src/refineq/materials/service.py`
- Modify: `src/refineq/learning/personalized.py`
- Modify: `src/refineq/api/app.py`
- Modify: `src/refineq/api/routers/learning.py`
- Test: `tests/unit/materials/test_material_analysis_service.py`
- Test: `tests/unit/learning/test_personalized_plan.py`

1. Add failing tests for hallucinated citations/topics, planning from an unlinked material, unknown focus topics, out-of-budget sessions, wrong weekdays, and sessions beyond the exam.
2. Discard analysis sections without a valid retrieved citation and derive public topics from supported sections only; use the deterministic fallback when none survive.
3. Inject the knowledge index into targeted planning and require an owner-scoped workspace link before reading analysis.
4. Validate focus topics against the evidence-backed analysis and normalize generated sessions to preferred weekdays/hour, the exam boundary, non-overlap, and the daily budget.
5. Map invalid or missing planning inputs to recoverable API errors.
6. Run focused service and API tests.

## Task 4: Close the grading evidence-poisoning path

**Files:**

- Modify: `src/refineq/learning/intelligence.py`
- Test: `tests/unit/learning/test_learning_intelligence.py`
- Test: `tests/integration/test_learning_journey.py`

1. Add a failing regression proving the first retrieved chunk becomes the fallback `expected_answer` and can award mastery.
2. Make deterministic fallback questions carry no grading key and make fallback grading without a trusted key explicitly non-mastery evidence.
3. Decouple the passing threshold from the separate `example_present` feature so a trustworthy 70-point answer is not displayed as failed.
4. Assert a poisoned fallback answer can produce coaching feedback but cannot alter BKT, difficulty, plan completion, or review scheduling.
5. Run focused intelligence and learning-journey tests.

## Task 5: Strengthen home routing and goal preservation

**Files:**

- Modify: `src/refineq/home/policy.py`
- Modify: `src/refineq/workspaces/routing.py`
- Test: `tests/unit/home/test_home_policy.py`
- Test: `tests/unit/workspaces/test_routing.py`

1. Add failing cases for pasted/粘贴/下面这段 transformations containing malicious planning language, bare “exam/final” language without a real constraint, and a dated/minutes constraint that should create a workspace.
2. Replace the broad regular-expression time gate with `infer_intent_constraints` and only treat an actual parsed date or quantity as a strong long-term signal.
3. Expand the explicit one-shot text boundary so the payload remains untrusted data even when it contains commands.
4. Add deterministic linear-algebra concept preservation for eigenvalues, orthogonal projection, and least squares instead of collapsing the goal to generic mathematics.
5. Run focused routing tests.

## Task 6: Make structured-model health reflect the actual contract

**Files:**

- Modify: `src/refineq/agent/structured.py`
- Modify: `src/refineq/integrations/service.py`
- Modify: `src/refineq/api/app.py`
- Test: `tests/unit/agent/test_structured.py`
- Test: `tests/integration/test_admin_integrations.py`

1. Add failing transport tests proving the provider receives no response schema and an admin test can pass despite returning structurally unusable JSON.
2. Append the exact Pydantic JSON schema to a provider-neutral system instruction while retaining OpenAI-compatible JSON-object mode.
3. Replace the chat “Reply OK” probe with a nested structured capability canary executed through the production transport.
4. Set bounded, no-retry classifier/generator transports so model failure returns a deterministic fallback before the web proxy reports a false timeout.
5. Run transport and administrator integration tests.

## Task 7: Restore the intended frontend journey

**Files:**

- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/components/material-dropzone.tsx`
- Modify: `apps/web/app/library/page.tsx`
- Modify: `apps/web/tests/components.test.tsx`
- Modify: `apps/web/tests/contracts.test.ts`
- Modify: `apps/web/tests/learning-home-direction.test.tsx`
- Modify: `apps/web/tests/e2e/primary-learning-journey.spec.ts`
- Modify: `apps/web/tests/e2e/first-use-journey.spec.ts`

1. Add failing component/contract tests showing a new workspace hides the upload action, targeted planning has no caller, filtered selection includes hidden materials, and library load failure is trapped behind a spinner.
2. Make `upload_material` the sole initial primary action and defer diagnostic until searchable evidence exists.
3. Restore an evidence-backed targeted-plan form with exam date, daily budget, preferred hour/weekdays, supported topics, pending/error states, and calendar handoff.
4. Restrict bulk operations to visible selections and clear stale selection on filter/search changes.
5. Render library errors independently of authentication loading and remove the meaningless canonical `project_id` location count.
6. Run Vitest and the two first-use Playwright journeys.

## Task 8: Reconcile documentation and verify the release

**Files:**

- Modify: `docs/audits/2026-08-09-full-product-adversarial-audit.md`
- Modify: `docs/plans/2026-08-09-material-analysis-review-remediation.md`

1. Add an implementation disposition table mapping every confirmed finding to its regression test and code boundary; distinguish fixed release blockers from longer-horizon persistent Agent Operation work.
2. Run `python -m pytest -q`.
3. Run `python -m ruff check src tests scripts`.
4. Run `npm test`, `npm run lint`, and `npm run build` in `apps/web`.
5. Run the relevant Playwright suite with production services and verify screenshots/error states manually.
6. Request an independent read-only code review, address every P0/P1 finding with a failing regression first, then repeat the full verification matrix.

---

## Execution record

Implementation completed on `codex/material-analysis-review-fixes` in an isolated worktree. The plan's conceptual boundaries were kept, with the following concrete adjustments discovered during red/green verification:

- Migration coverage lives in `tests/unit/database/test_engine.py`, matching the repository's existing migration-test boundary.
- Material analysis is a canonical owner-scoped projection. Workspace authorization still happens through `KnowledgeIndex.get_material`; the stored analysis itself is no longer duplicated per workspace.
- Explicit targeted-plan generation replaces the conflicting future calendar instead of opportunistically appending sessions. Appending made the feature fail for the normal case where the onboarding plan had already consumed the daily budget.
- The target-plan form inherits the workspace's existing exam date. A browser regression caught the original 14-day default silently overwriting the learner's stated deadline.
- Global-library physical deletion is distinct from workspace unlinking in both API and copy. Re-uploading the same content does not silently restore old links or a stale analysis projection.
- A full-suite failure exposed an empty material-deletion batch in workspace undo; it is now a valid no-op while preserving the recovery lease lifecycle.
- A full browser-suite timing failure exposed answer entry during learning-mode question replacement; the answer surface is now disabled until the replacement settles.
- Independent review found ten additional P1 defects. Recovery now preserves the original migrated storage key and includes analysis records in the durable deletion journal; targeted plans preserve completed/pending sessions and replay identical requests; the question model's answer key is always ignored and only an isolated topic-only compiler can create a trusted key; quoted explanation inputs and cross-workspace frontend responses cannot trigger side effects.
- Follow-up hardening adds a database canonical-material unique index, serializes legacy analysis migration, rejects sparse model plans, caps the targeted topic selection at 30, and exposes global-library workspace associations.
- Final adversarial review found that an incompatible pending session could survive replanning and that long analysis/plan generation could commit after a concurrent unlink or physical delete. Pending references are now detached when new constraints reject them; model work stays outside the global material lease, while the short final commit acquires that lease and revalidates all material/link/analysis preconditions.
- The final grading attack copied the generated prompt, changed one article, and appended generic filler while forcing model-error fallback. Ordered prompt-overlap detection now keeps both exact and near-copy answers below the pass line and prevents mastery evidence.
- The merge-gate review found two final cross-boundary defects: late workspace links could outlive either a canonical material or their workspace, and a broad control-word denylist rejected legitimate academic topics such as operating systems and rule of law. Linking, workspace deletion, and physical deletion now share the recovery lease plus an owner-locked database recheck; busy deletes return a retryable 409. Topic hardening now detects instruction-shaped phrases without rejecting ordinary subject names.

### Verification gates

The final evidence is maintained in §9 of `docs/audits/2026-08-09-full-product-adversarial-audit.md`. No supplied API key, generated data directory, browser trace, screenshot artifact, or model response is committed by this plan.
