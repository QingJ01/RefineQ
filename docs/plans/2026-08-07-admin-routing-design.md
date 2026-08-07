# Admin information architecture and routing design

## Problem

The web application exposes only the `/` route. Administrator mode is represented by the
`section === "admin"` state inside `StudyWorkspace`, so the address bar never changes, `/admin`
cannot be opened directly, refresh loses the administrator view, and browser history cannot return
between learning and administration. The administrator screen also renders four complete service
forms at once beneath a large hero and summary grid, which makes configuration difficult to scan.

## Chosen design

Use real App Router pages. `/admin` is a concise platform overview, while
`/admin/integrations/[kind]` edits one of `chat`, `embedding`, `ocr`, or `object_storage`. A shared
client-side `AdminRoute` restores the existing local learning session, verifies the current user
through `/auth/me`, and redirects unauthenticated or non-admin users to `/`. Valid administrators
remain on the requested URL after refresh. Learning surfaces navigate with Next.js routing instead
of mutating an internal section value.

`AdminConsole` becomes a stable shell with compact navigation and a focused content stage. The
sidebar is the only capability index and communicates configuration state with small status dots.
The overview therefore avoids repeating all four integrations: it shows a compact system-health
strip, one prioritized next action, setup progress, and the platform guardrails. A detail page
renders only one configuration form, grouped into service status, basic settings, credentials, and
network security while preserving save, connection test, secret masking, and private-network
controls. Desktop uses a restrained sidebar plus content column; mobile turns navigation into a
horizontal strip, hides redundant status dots, and keeps form fields single-column.

## Error and access behavior

- Missing or malformed local sessions redirect to `/`.
- Expired tokens are cleared before redirecting.
- Learners cannot render administrator data and are redirected to `/`.
- Unknown integration kinds use the branded Next.js not-found flow.
- API loading and error states remain inline inside the administrator shell.

## Verification

Contract tests prove that real route files exist and the learning shell no longer models Admin as a
section. Component tests prove that the overview contains status, next-action, and guardrail regions
without repeated service forms, and that detail mode renders one selected form with three clear
configuration groups. Playwright verifies direct navigation, refresh persistence, detail URLs, and
browser back behavior with an administrator account.
