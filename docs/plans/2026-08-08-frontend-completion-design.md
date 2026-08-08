# RefineQ Frontend Completion Design

## Objective

Close every product gap identified in the 2026-08-08 frontend audit without replacing the current visual system or weakening RefineQ's owner/workspace isolation. The result must be a real end-to-end product: visible agent continuity, verifiable learning sources, editable learning plans, actionable review and progress, account management, scalable material organization, operational administration, and a usable mobile experience.

## Delivery approach

Work in four vertical slices so every slice can be tested and reverted independently.

### Slice 1: Agent continuity and grounded evidence

Mount the existing full `AgentPanel` experience inside the workspace and preserve the contextual coach as a compact entry point. Both surfaces share the same workspace session APIs. Learners can create, reopen, delete, retry, stop, and inspect sourced responses. A missing model becomes an explicit capability state: administrators receive a direct configuration action, while learners receive a clear explanation and retain deterministic learning flows.

Questions and grading responses distinguish grounded content from generic fallback content. A question may only claim that it is based on uploaded material when it contains owner- and workspace-validated sources. The UI exposes those sources beside the prompt and feedback.

### Slice 2: Planning, review, and progress

Add one atomic learning-plan update operation supporting goal, deadline, daily minutes, topic order, and regeneration. Session completion and deferral remain narrow operations. Feedback exposes rubric details, retry, and an appeal/note path. Review state is projected as an actionable due queue. Progress adds history, error-category summaries, and topic drill-down using existing attempts and evidence rather than a second analytics store.

### Slice 3: Learner product completion

Replace the deceptive workspace link with a true switcher. Add account/security controls for profile updates, password changes, session invalidation, export, and account deletion. Extend materials with editable labels/tags, status filters, sort, selection, and bulk deletion. Centralize localized API error mapping. Improve mobile navigation with visible section context, shortcuts, sticky task actions, and readable secondary type.

### Slice 4: Operations and maintainability

Expose administrator user/quota summaries, indexing/job state, audit logs, backup creation and restore through guarded APIs and working UI. Destructive operations require confirmation and are written to the existing audit log. Split `StudyWorkspace` into domain hooks and focused surfaces after behavior is protected by tests.

## Data flow and security

FastAPI remains the authorization boundary. Every new workspace operation receives the authenticated owner ID and validates the target workspace before reading or writing state. Administrative endpoints require the existing admin dependency. Uploaded content remains untrusted and can never supply instructions to the agent.

Learning extensions are stored in the existing owner-scoped versioned learning record when they belong to one workspace. Account, audit, and material metadata use SQL tables where cross-record queries or administrative pagination are required. Updates run inside the existing SQL/session or owner transaction mechanisms. Backups continue to use the fail-safe operations service; the API exposes only validated backup identifiers under `REFINEQ_DATA_ROOT`.

## Error handling

The API returns stable error codes. The frontend maps codes to locale-specific copy and never exposes raw backend English in a Chinese screen. Recoverable failures show retry. Configuration failures show capability status and the correct setup route. External AI, embedding, OCR, and object-storage failures degrade to documented local behavior without pretending the unavailable capability succeeded.

## Testing and acceptance

Each behavior follows red-green-refactor. Backend tests cover validation, ownership, admin authorization, atomic writes, and destructive-operation safety. Frontend tests cover visible behavior and API contracts. Chrome verification runs against an isolated `REFINEQ_DATA_ROOT` at desktop and mobile viewports.

Acceptance requires:

- all Python tests, frontend tests, Ruff, ESLint, secret scan, and production build pass;
- the core learner and administrator journeys complete without unexpected 4xx/5xx responses;
- every material-grounded claim has inspectable evidence;
- all audited gaps have either a working feature or an explicitly tested unavailable state;
- no runtime data or temporary audit tooling is committed.
