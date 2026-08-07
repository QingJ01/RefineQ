# Complete Review Remediation Design

## Scope and constraints

This remediation closes the issues found in the 2026-08-07 project review without replacing the
existing FastAPI, SQLAlchemy, PostgreSQL/pgvector, and Next.js architecture. The current repository
is the implementation workspace; no Git worktree is used. Uploaded material remains untrusted,
SQLite remains the local-development fallback, and PostgreSQL is the production consistency and
retrieval authority.

## Storage and upload consistency

Every stored object returns a rollback handle bound to the exact backend that accepted the write.
S3 writes use conditional creation and content hashes so an indexing failure can remove only an
object created by that request. Object keys are independent of filename extensions, preventing a
metadata-only filename change from orphaning an old object. Integration-secret corruption is a
configuration failure, not an absent integration, so configured storage fails closed instead of
silently switching to the local volume.

The upload route keeps cheap validation and extraction outside the database transaction. Blocking
storage, embedding, and SQL work runs in AnyIO's worker pool. Final quota validation and material
replacement happen in one database transaction. PostgreSQL uses a transaction-scoped advisory lock
per owner; SQLite uses the existing process lock for development. Replacement uploads contribute
only their count and byte deltas to quota calculations.

## Retrieval and embedding lifecycle

PostgreSQL lexical retrieval selects a bounded candidate set with full-text rank plus indexed
trigram substring matching for Chinese and exact phrases. Semantic retrieval independently selects
a bounded pgvector candidate set. Python only fuses these candidates; it never loads the complete
workspace corpus on PostgreSQL. SQLite retains its bounded-development fallback behavior.

Embedding requests are split into bounded batches. Failures are logged without provider secrets,
and successful batches remain usable when a later batch fails. A backfill operation fills missing
vectors and is scheduled after an administrator enables or updates the embedding integration, so
legacy migrated chunks can acquire vectors without re-uploading their source documents.

## OCR and outbound integration security

OCR identifies textless pages in mixed PDFs, renders only those pages, validates estimated pixel
budgets before rendering, limits encoded bytes, and sends small page batches to the vision model.
Text pages and OCR pages are reconstructed in original order. The administrator OCR connection test
sends an actual tiny image through the configured vision model.

All enabled integrations require an operator-owned hostname allowlist. Object storage has its own
allowlist setting. Before outbound calls, hostnames are resolved and any loopback, link-local,
private, reserved, or otherwise non-global destination is rejected. A private endpoint requires
both an allowlisted hostname and an explicit per-integration private-network switch. Redirect
following remains disabled at the HTTP client boundary.

## Product and verification behavior

The no-workspace home and the administrator console both expose logout controls. Integration test
results update their persisted-status badge immediately. GitHub Actions starts a real pgvector
PostgreSQL service and exercises schema creation, SQL lexical/vector retrieval, JSONB persistence,
and cross-instance quota serialization. Unit and integration regression tests cover every local
behavioral fix; full Python, frontend, lint, build, secret-scan, and E2E verification remains the
completion gate.
