# Hackathon Code Hardening Design

## Scope

This change closes the code-level gaps found in the hackathon adversarial audit. It deliberately does not deploy RefineQ, create interview evidence, fill submission forms, or manufacture user feedback. The implementation covers four boundaries: production-correct demo seeding, optional SMTP password reset delivery, one coherent exam-oriented default story, and a real mobile core-loop browser test.

## Demo seeding

The demo operation must use the same database URL as the running application. `scripts/seed_demo.py` will construct `Settings`, open `Database(settings.resolved_database_url)`, initialize it, and pass that database into the demo operation. The operation will no longer construct a private SQLite database from `data_root`.

The demo email remains a configurable non-secret identifier. The password becomes a required `REFINEQ_DEMO_PASSWORD` secret for the command instead of a source constant or command-line argument. The command will never print the password. Re-running with the same credentials remains idempotent; an existing account with a different password fails explicitly rather than silently modifying a shared account.

The seed content will use one clearly fictional, presentation-only computer-architecture exam workspace. It will not claim to represent the later real interview subject.

## Password reset delivery

Password reset is available when either SMTP delivery is fully configured or the existing isolated-test token exposure flag is enabled. A public `GET /auth/capabilities` endpoint exposes only the boolean capability, never SMTP details.

SMTP uses the Python standard library. Configuration is all-or-none: host and sender are required; username and password must appear together; STARTTLS and implicit TLS cannot both be enabled. The delivery service creates a plain-text reset message with a URL fragment such as `https://example.com/#reset-token=...`, keeping the token out of reverse-proxy request logs and referrer URLs.

The reset-request endpoint preserves account-enumeration resistance. Missing accounts and known accounts return the same response. Delivery runs after the response and catches/logs failures without credentials or tokens. When neither delivery nor isolated token exposure is available, no reset token is created. The frontend probes capabilities, hides “Forgot password?” by default, and opens reset mode when a valid fragment is present.

## Product story and mobile proof

Homepage guidance, demo data, and the primary learner browser fixture will use the same exam-oriented language: a dated computer-architecture exam, daily study time, personal lecture notes, source-grounded practice, grading, and progress evidence. Universal learning modes remain supported; only the default and submission-facing examples change.

A dedicated 390×844 Playwright journey will register a learner, create an exam workspace, upload a material, start a grounded exam task, submit an answer, and open progress without switching to desktop. This proves the mobile core loop rather than only navigation and touch-target dimensions.

## Error handling and security

- SMTP secrets remain `SecretStr` settings and never enter API responses or logs.
- The demo password is required at execution time and never committed or printed.
- Reset delivery failure does not reveal whether an account exists.
- The token fragment is removed from browser history immediately after the frontend consumes it.
- Existing rate limits, one-time token semantics, token expiry, and session revocation remain unchanged.

## Verification

Every behavior change follows red-green TDD. Focused Python and frontend tests run after each change. Final verification runs Pytest, Ruff check/format, the secret scan, Vitest, ESLint, the production build, and Playwright E2E.
