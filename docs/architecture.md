# RefineQ architecture

RefineQ uses one Python backend and one TypeScript frontend.

```text
Browser
  -> Next.js web application
  -> FastAPI HTTP API
       -> identity and access checks
       -> administrator integration control plane
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
- `workspaces` resolves each intent to an existing or new private learning space and restores it.
- `learning` owns diagnostics, planning, mastery, attempts, grading evidence, and review state.
- `knowledge` validates and extracts uploads, then indexes chunks per owner and learning space.
- `integrations` encrypts platform credentials and owns chat, embedding, OCR, and object-storage adapters.
- `agent` assembles trusted state and untrusted retrieved material into grounded model requests.
- `database` owns PostgreSQL/SQLite engine setup, schema creation, and transaction boundaries.
- `storage` provides SQL persistence and version-conflict detection through the existing repository contract.
- `api` maps authenticated HTTP requests to those services without moving domain rules into routes.

Every repository operation receives an owner identifier. Cross-owner lookups return no resource,
which prevents learning-space identifiers from becoming authorization tokens. Model-generated
workspace IDs and citations are accepted only when they occur in the server-supplied candidate set.

## Frontend boundary

`apps/web` exposes one Agent-first entry instead of asking learners to create containers manually.
It calls the backend through the same-origin `/api` rewrite, so browser code never needs direct
access to backend credentials or storage paths.

## Runtime state and fallback

Production uses PostgreSQL with the pgvector extension. SQLite remains an explicit local-development
and test fallback when `REFINEQ_DATABASE_URL` is unset; it is not the production topology. Original
uploads use a local object store rooted at `REFINEQ_DATA_ROOT` by default and can be switched to an
S3-compatible service in the administrator console.

Local text extraction for PDF, DOCX, TXT, and Markdown does not need a third-party API. OCR is only
invoked when a PDF has no usable text and the administrator enabled the OCR integration. Embedding
failures degrade to lexical retrieval, and model failures retain deterministic learning flows.
