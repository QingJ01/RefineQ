# Complete Review Remediation Design

## Objective

Close every confirmed P1/P2 defect from the project review and harden the public-deployment boundary without changing RefineQ's core product model: one learner, automatically selected learning spaces, uploaded evidence, AI practice, and explainable grading.

## Chosen approach

Use layered, fail-closed boundaries instead of route-specific patches. Input validation belongs in domain models and reusable policies; storage operations expose atomic batch or rollback behavior; model calls use one validated endpoint policy and finite timeouts; UI state is controlled by the workspace shell. This keeps the same Python/FastAPI and Next.js/TypeScript stack and minimizes new infrastructure.

Alternatives considered:

- Relying on a reverse proxy for SSRF, limits, and quotas was rejected because local and hackathon deployments may bypass the proxy.
- Replacing file storage with a hosted database/object store was rejected because it raises deployment cost and does not fit the existing offline-friendly architecture.
- Letting the LLM parse every natural-language constraint was rejected because dates and durations need deterministic behavior even when no model is configured.

## Security and reliability boundaries

- Model endpoints must use HTTPS and must not resolve to loopback, private, link-local, multicast, reserved, or unspecified IP ranges. An explicit server-side hostname allowlist can enable approved internal gateways. Model settings are encrypted at rest with a deployment key and legacy plaintext records are migrated after a successful read.
- OpenAI-compatible calls use finite connect/read timeouts and bounded retries. Agent context uses a rolling message/character budget, model output is capped, and invalid citation markers are removed from the user-visible answer.
- Study plans require a future exam and a bounded horizon. Workspace provisioning validates and builds all derived state before persistence, then compensates on unexpected write failure.
- Uploads are preflighted completely before commit. DOCX archives and PDFs have page, expanded-byte, compression-ratio, extracted-character, and processing-time budgets. Batch index writes and material-file writes roll back together on failure.
- Authentication and expensive mutation endpoints receive per-client/per-user sliding-window limits. Per-user workspace count, stored-material bytes, and material count are capped through settings.

## Learning behavior

- Natural-language intent parsing extracts common Chinese and English relative exam dates and daily-minute constraints, while explicit structured values always win. Ambiguous intent keeps safe defaults.
- Deterministic workspace reuse requires meaningful topic/title/goal overlap; a broad subject match alone never merges spaces.
- Fallback grading cannot pass an answer that only repeats the topic. A passing fallback answer must show sufficient substance, concept coverage, and an example/application signal. Low-confidence grading does not raise mastery.
- The practice UI has an explicit next-question transition. Uploaded materials are controlled by the workspace parent, so navigation cannot restore stale state. Agent errors become visible, recoverable UI state with a direct settings path.

## Verification

Each behavior is introduced with a regression test that first fails for the confirmed defect. Final verification covers Python unit/integration/contract tests, Ruff, frontend Vitest/ESLint/build, Playwright browser flow, container build/health checks, dependency audits, and secret scanning. Dependency installs use committed lock files or hashes so CI and local builds resolve the same versions.

