# RefineQ architecture

RefineQ uses one Python backend and one TypeScript frontend.

```text
Browser
  -> Next.js web application
  -> FastAPI HTTP API
       -> identity and access checks
       -> administrator integration control plane
       -> home supervisor policy, one-shot answers, and signed action previews
       -> implicit workspace routing (AI + deterministic fallback)
       -> learning-domain services
       -> grounded question generation and structured grading
       -> grounded agent service
       -> SQL repositories and hybrid knowledge retrieval
  -> PostgreSQL + pgvector (accounts, learning state, chunks, vectors, settings)
  -> REFINEQ_DATA_ROOT or S3-compatible storage (original uploads)
```

## Backend boundaries

- `identity` owns accounts, password verification, sessions, and request identity.
- `home` owns deterministic homepage scope/routing policy, isolated one-shot generation, bounded cross-space projections, signed previews, and content-free dispatch events. It delegates every durable learning mutation to existing domain services.
- `workspaces` resolves each intent to an existing or new private learning space and restores it.
- `learning` owns the bounded initial self-assessment, planning, mastery, attempts, grading evidence, and review state.
- `knowledge` validates and extracts uploads, then indexes chunks per owner and learning space.
- `integrations` encrypts platform credentials and owns chat, embedding, OCR, and object-storage adapters.
- `agent` assembles trusted state and untrusted retrieved material into grounded model requests.
- `database` owns PostgreSQL/SQLite engine setup, schema creation, and transaction boundaries.
- `storage` provides SQL persistence and version-conflict detection through the existing repository contract.
- `api` maps authenticated HTTP requests to those services without moving domain rules into routes.

Every repository operation receives an owner identifier. Cross-owner lookups return no resource,
which prevents learning-space identifiers from becoming authorization tokens. Model-generated
workspace IDs and citations are accepted only when they occur in the server-supplied candidate set.

The initial diagnostic is deliberately a one-time, fixed self-assessment over the workspace topics.
It is not presented as an adaptive or model-derived diagnosis. A material upload does not silently
change that topic set: candidate topics come only from bounded titles and explicit tags, are shown as
suggestions, and require an owner-authorized confirmation. Acceptance updates workspace metadata and
learning state as one compensated operation; if either write fails, both observable records are
restored.

Model and embedding calls follow a snapshot/network/conditional-commit boundary. Services take the
minimum owner-scoped snapshot in a short transaction, release the database connection before calling
an external service, then open a second short transaction and recheck the idempotency key, quota, and
relevant state before committing. Per-request process locks avoid duplicate provider work on one
instance; database constraints, version checks, and PostgreSQL advisory locks remain the cross-process
authority. Nested owner scopes acquire their own advisory transaction locks rather than inheriting an
unrelated outer scope.

## Frontend boundary

`apps/web` exposes one Agent-first supervisor entry instead of asking learners to create containers manually. The homepage keeps one transient typed result, never a chat history; server `auto_navigate` is the only navigation authority, while writes require a visible diff or editable preview and a signed confirmation.
It calls the backend through the same-origin `/api` rewrite, so browser code never needs direct
access to backend credentials or storage paths.

The learning workspace keeps authentication, workspace navigation, practice, and Agent conversation
state in separate hooks. Each asynchronous practice or Agent request carries the generation of the
workspace that created it; switching workspaces invalidates that generation and remounts the session
canvas, so late responses cannot leak questions, answers, progress, or conversations across spaces.

Learner routes cover today, path, materials, progress, and account settings. The workspace switcher
preserves keyboard focus and browser history, while every practice question exposes its source
provenance. Plans are editable, attempts retain notes and appeal state, and retries reopen the exact
prompt. Material metadata, tags, filters, sorting, selection, and bulk deletion all remain scoped to
the authenticated owner and active workspace.

Administrator routes are a separate role-gated control plane. Integration settings and operations
share the same shell, while user quotas, background-job status, audit activity, and managed backups
come from dedicated administrator APIs. User-facing errors are localized from stable server error
codes; backend exception text and filesystem paths are not rendered in the browser.

## Runtime state and fallback

Production uses PostgreSQL with the pgvector extension. SQLite remains an explicit local-development
and test fallback when `REFINEQ_DATABASE_URL` is unset; it is not the production topology. Original
uploads use a local object store rooted at `REFINEQ_DATA_ROOT` by default and can be switched to an
S3-compatible service in the administrator console.

Platform model settings have one production persistence path in the administrator integration
repository. Learning and Agent consumers depend on the narrow `ModelSettingsRepository` protocol
(`load`) instead of carrying a second file-backed credential implementation. This keeps encryption,
authorization, and audit behavior in one control plane.

Local text extraction for PDF, DOCX, TXT, and Markdown does not need a third-party API. OCR is only
invoked when a PDF has no usable text and the administrator enabled the OCR integration. Embedding
failures degrade to lexical retrieval, and model failures retain deterministic learning flows.

Material chunks prefer paragraph and sentence boundaries and retain a bounded overlap so facts at a
cut remain retrievable. Hybrid search filters low-similarity semantic candidates before combining
lexical and semantic ranks with weighted reciprocal-rank fusion. Rank fusion, rather than raw-score
addition, prevents one provider's score scale from dominating the result.

Workspace deletion uses a recoverable two-phase material journal. Learning, session, and workspace
records are snapshotted and deleted in one owner transaction; material index/object deletion runs
only after that transaction commits. Any failure restores missing records at their original schema
and data versions without overwriting a concurrent survivor. Uploads revalidate the workspace after
parsing and while holding the shared project lease, preventing orphaned material writes.
