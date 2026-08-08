# Learning Workspace Navigation And Layout Design

## Product decision

RefineQ uses a workspace-first information architecture. The personal learning home and a learning workspace are different locations, and the URL is the only authority for which location is visible.

- `/` is always the personal learning home after authentication.
- `/learn/:workspaceId/:section` is always one isolated learning workspace.
- The supported workspace sections remain `today`, `path`, `materials`, and `progress`.
- Session storage remembers authentication, locale, and the last workspace identifier for convenience, but it never decides whether the home route renders a workspace.

This removes the current conflict where browser history reaches `/` while session state immediately reopens the last workspace.

## Navigation hierarchy

The workspace sidebar will expose three levels in a stable order:

1. RefineQ brand and an explicit “学习首页” link to `/`.
2. A current-space switcher showing the workspace title, current topic, and progress. Activating it returns to the home workspace list.
3. Workspace-local links for 今日、学习路径、资料、进步.

The current workspace name moves from the bottom of the sidebar to the top of the workspace navigation so scope is visible before the learner acts. Logout always replaces the current route with `/`. A missing or archived workspace URL also returns to `/` instead of rendering the home screen under an invalid learning URL.

## Layout direction

The existing calm blue, warm-white, and editorial typography are retained. The redesign changes density and composition rather than the brand language.

- Workspace header and content share a wider responsive frame.
- Today uses a flexible learning column with a compact contextual rail; it no longer forces the canvas to fill the viewport height.
- Feedback typography is bounded for readable line lengths, and empty strengths or gaps get explicit compact empty text instead of blank cards.
- Progress uses a wide two-column composition: mastery on the left and the evidence ledger on the right. It collapses to one column at medium widths.
- Path and materials receive wider but readable content frames.
- Mobile keeps the existing horizontal section navigation and converts the space switcher to a compact control.

## State and error behavior

- Opening a workspace fetches only that workspace snapshot before navigating to its canonical URL.
- Changing sections keeps the same workspace identifier in every link.
- Returning home clears transient routing notices and workspace UI state, but does not destroy the last workspace reference.
- Direct visits to unavailable workspace URLs redirect to the home route.
- Authentication errors clear the session and return to `/`; non-authentication errors remain visible in the current valid surface.

## Verification

Contract tests will cover route ownership, explicit home and workspace-switcher links, logout routing, and responsive layout rules. Existing component, lint, build, Python, and CI browser tests remain the regression suite. Browser-driven visual QA requires the user’s selected browser; until then, visual verification is limited to the supplied screenshots, rendered component structure, and production build.
