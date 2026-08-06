# RefineQ architecture

RefineQ uses one Python backend and one TypeScript frontend.

```text
Browser
  -> Next.js web application
  -> FastAPI HTTP API
       -> identity and access checks
       -> learning-domain services
       -> grounded agent service
       -> atomic JSON repositories and SQLite knowledge index
  -> REFINEQ_DATA_ROOT
```

## Backend boundaries

- `identity` owns accounts, password verification, sessions, and request identity.
- `learning` owns projects, diagnostics, planning, mastery, attempts, evidence, and review state.
- `knowledge` validates and extracts uploads, then indexes chunks per owner and project.
- `agent` assembles trusted state and untrusted retrieved material into grounded model requests.
- `storage` provides atomic persistence and version-conflict detection.
- `api` maps authenticated HTTP requests to those services without moving domain rules into routes.

Every repository operation receives an owner identifier. Cross-owner lookups return no resource,
which prevents project identifiers from becoming authorization tokens.

## Frontend boundary

`apps/web` is a focused learning workspace. It calls the backend through the same-origin `/api`
rewrite, so browser code never needs direct access to backend credentials or storage paths.

## Runtime state

All mutable state is rooted at `REFINEQ_DATA_ROOT`. Source directories are read-only at runtime.
This single boundary also defines the backup and restore unit.

