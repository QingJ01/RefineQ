import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it, vi } from "vitest";

import {
  ApiClient,
  ApiError,
  authHeaders,
  subscribeUnauthorized,
} from "../lib/api";
import { shouldClearAccountSession } from "../components/account-center";
import { messages } from "../lib/i18n";
import { loadNextQuestion } from "../lib/practice-flow";
import { validatePlanSettings } from "../lib/plan-settings";
import {
  learningSections,
  parseLearningSection,
  resolveLearningShellPath,
} from "../lib/learning-routes";
import {
  clearLearningSession,
  installSessionHandoff,
  loadLearningSession,
  requestSessionHandoff,
  saveLearningLocale,
  saveLearningSession,
} from "../lib/session";
import {
  clearSelectedFiles,
  createSerialTaskQueue,
  isAbortError,
  runSerially,
  validateUploadFile,
} from "../lib/upload-flow";
import { resolveRequestedWorkspace } from "../lib/workspace-route-state";
import {
    buildPlanRows,
    evidenceTone,
    practiceStatus,
    projectIntegrationTestResult,
} from "../lib/view-models";
import type { StudyPlan } from "../lib/types";


describe("workspace state boundaries", () => {
  it("separates authentication, workspace, practice, and agent state into domain hooks", () => {
    const hookFiles = {
      auth: fileURLToPath(new URL("../hooks/use-learning-auth.ts", import.meta.url)),
      workspace: fileURLToPath(new URL("../hooks/use-workspace-state.ts", import.meta.url)),
      practice: fileURLToPath(new URL("../hooks/use-practice-state.ts", import.meta.url)),
      agent: fileURLToPath(new URL("../hooks/use-agent-state.ts", import.meta.url)),
    };

    expect(Object.values(hookFiles).every(existsSync)).toBe(true);
    if (!Object.values(hookFiles).every(existsSync)) return;

    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );
    const authSource = readFileSync(hookFiles.auth, "utf8");
    const stateSource = readFileSync(hookFiles.workspace, "utf8");
    const practiceSource = readFileSync(hookFiles.practice, "utf8");
    const agentSource = readFileSync(hookFiles.agent, "utf8");

    expect(workspaceSource).toContain("useLearningAuth()");
    expect(workspaceSource).toContain("useWorkspaceState()");
    expect(workspaceSource).toContain("usePracticeState()");
    expect(workspaceSource).toContain("useAgentState()");
    expect(authSource).toContain("clearLearningSession");
    expect(authSource).toContain("saveLearningLocale");
    expect(stateSource).toContain("applySnapshot");
    expect(practiceSource).toContain("questionRequestIdRef");
    expect(practiceSource).toContain("attemptIdRef");
    expect(practiceSource).toContain("practiceGenerationRef.current += 1");
    expect(practiceSource).toContain("refineq.practice-draft:");
    expect(workspaceSource).toContain("isPracticeGenerationCurrent(generation)");
    expect(workspaceSource).toContain("key={workspace.id}");
    expect(agentSource).toContain("api.chatWorkspace");
    expect(agentSource).toContain("agentGenerationRef.current === generation");
  });
});


describe("administrator integration status", () => {
  it("projects a connection test result into the visible integration status", () => {
    const setting = {
      kind: "ocr" as const,
      enabled: true,
      configured: true,
      config: { base_url: "https://api.openai.com/v1", model: "vision" },
      secret_hints: { api_key: "••••test" },
      last_test_status: null,
      last_test_message: null,
      last_tested_at: null,
    };

    const updated = projectIntegrationTestResult(
      setting,
      { kind: "ocr", status: "ok", message: "Connection succeeded" },
      "2026-08-07T12:00:00.000Z",
    );

    expect(updated.last_test_status).toBe("ok");
    expect(updated.last_test_message).toBe("Connection succeeded");
    expect(updated.last_tested_at).toBe("2026-08-07T12:00:00.000Z");
  });
});


describe("administrator routing", () => {
  it("uses real overview and integration detail routes instead of workspace section state", () => {
    const adminPage = fileURLToPath(new URL("../app/admin/page.tsx", import.meta.url));
    const integrationPage = fileURLToPath(
      new URL("../app/admin/integrations/[kind]/page.tsx", import.meta.url),
    );
    const operationsPage = fileURLToPath(
      new URL("../app/admin/operations/page.tsx", import.meta.url),
    );
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );
    const sidebarSource = readFileSync(
      fileURLToPath(new URL("../components/app-sidebar.tsx", import.meta.url)),
      "utf8",
    );

    expect(existsSync(adminPage)).toBe(true);
    expect(existsSync(integrationPage)).toBe(true);
    expect(existsSync(operationsPage)).toBe(true);
    expect(workspaceSource).toContain("<AppSidebar");
    expect(sidebarSource).toContain('href="/admin"');
    expect(workspaceSource).not.toContain('section === "admin"');
    expect(workspaceSource).not.toContain('"coach" | "admin"');
  });

  it("uses typed administrator operation endpoints and exact restore confirmations", async () => {
    const requests: Array<{ path: string; method: string; body?: unknown }> = [];
    const client = new ApiClient("/api", async (input, init) => {
      const path = String(input);
      requests.push({
        path,
        method: init?.method ?? "GET",
        body: init?.body ? JSON.parse(String(init.body)) : undefined,
      });
      if (path.includes("/users")) {
        return new Response(JSON.stringify({ items: [], page: 1, page_size: 20, total: 0, pages: 0 }));
      }
      if (path.includes("/jobs")) {
        return new Response(JSON.stringify({ items: [], observed_at: "2026-08-08T00:00:00Z" }));
      }
      if (path.includes("/audit")) {
        return new Response(JSON.stringify({ items: [], page: 1, page_size: 20, total: 0, pages: 0 }));
      }
      if (path.endsWith("/backups") && init?.method === "POST") {
        return new Response(JSON.stringify({
          id: "backup_20260808T000000000000Z_12345678",
          created_at: "2026-08-08T00:00:00Z",
          size: 10,
          file_count: 1,
          total_bytes: 5,
        }), { status: 201 });
      }
      if (path.includes("restore-validation")) {
        return new Response(JSON.stringify({
          status: "validated",
          id: "backup_20260808T000000000000Z_12345678",
          created_at: "2026-08-08T00:00:00Z",
          size: 10,
          file_count: 1,
          total_bytes: 5,
        }));
      }
      return new Response(JSON.stringify({ items: [], total: 0 }));
    });

    const backupId = "backup_20260808T000000000000Z_12345678";
    await client.listAdminUsers("token", 1, 20);
    await client.getAdminJobs("token");
    await client.listAdminAudit("token", 1, 20);
    await client.listAdminBackups("token");
    await client.createAdminBackup("token");
    await client.validateAdminRestore("token", backupId);

    expect(requests.map((item) => item.path)).toEqual([
      "/api/admin/users?page=1&page_size=20",
      "/api/admin/jobs",
      "/api/admin/audit?page=1&page_size=20",
      "/api/admin/backups",
      "/api/admin/backups",
      `/api/admin/backups/${backupId}/restore-validation`,
    ]);
    expect(requests.at(-1)?.body).toEqual({ confirmation: `RESTORE ${backupId}` });
  });

  it("localizes administrator operation labels and hides raw API failures", () => {
    const source = readFileSync(
      fileURLToPath(new URL("../components/admin-console.tsx", import.meta.url)),
      "utf8",
    );

    expect(source).toContain("localizeApiError(caught, locale)");
    expect(source).not.toContain("`${caught.code}: ${caught.message}`");
    expect(source).toContain("c.email");
    expect(source).toContain("c.materialIndex");
    expect(source).toContain("c.embeddingBackfill");
    expect(source).toContain("c.files");
    expect(source).toContain("auditActionLabel(entry.action, locale)");
    expect(source).toContain("roleLabel(user.role, locale)");
    expect(source).not.toContain("setError(result.message)");
    expect(source).not.toContain("setNotice(result.message)");
  });
});


describe("durable learner routing", () => {
  it("uses capability-oriented learner routes and keeps legacy links recoverable", () => {
    expect(learningSections).toEqual(["today", "plan", "materials", "progress"]);
    expect(parseLearningSection("path")).toBe("plan");
    expect(parseLearningSection("calendar")).toBe("plan");
    expect(parseLearningSection("evidence")).toBe("progress");
    expect(parseLearningSection("coach")).toBe("today");
  });

  it("resolves home, valid workspaces, and unavailable workspace URLs explicitly", () => {
    const workspaces = [{ id: "math-space" }, { id: "product-space" }];

    expect(resolveRequestedWorkspace(undefined, workspaces)).toEqual({ kind: "home" });
    expect(resolveRequestedWorkspace("math-space", workspaces)).toEqual({
      kind: "workspace",
      workspace: workspaces[0],
    });
    expect(resolveRequestedWorkspace("missing-space", workspaces)).toEqual({
      kind: "unavailable",
    });
  });

  it("treats the URL as the only authority for opening a learning workspace", () => {
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );

    expect(workspaceSource).toContain("const selectedId = initialWorkspaceId;");
    expect(workspaceSource).not.toContain("saved.home");
    expect(workspaceSource).toContain("redirectUnavailableWorkspace");
  });

  it("returns authentication exits to the canonical personal home", () => {
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );

    const logoutStart = workspaceSource.indexOf("function logout()");
    const returnHomeStart = workspaceSource.indexOf("function returnHome()");
    expect(logoutStart).toBeGreaterThanOrEqual(0);
    expect(returnHomeStart).toBeGreaterThan(logoutStart);
    expect(workspaceSource.slice(logoutStart, returnHomeStart)).toContain(
      'router.replace("/")',
    );
  });

  it("shows direct-route restoration as loading until authentication opens the workspace", () => {
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );
    const authenticatedStart = workspaceSource.indexOf("async function authenticated");
    const openWorkspaceStart = workspaceSource.indexOf("async function openWorkspace");
    const authenticatedSource = workspaceSource.slice(authenticatedStart, openWorkspaceStart);

    expect(authenticatedSource).toContain("if (initialWorkspaceId) setHomeBusy(true);");
    expect(authenticatedSource).toContain("if (initialWorkspaceId) setHomeBusy(false);");
  });

  it("ships a real learning route and uses it for section navigation", () => {
    const learningPage = fileURLToPath(
      new URL("../app/learn/[workspaceId]/[section]/page.tsx", import.meta.url),
    );
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );
    const layoutSource = readFileSync(
      fileURLToPath(new URL("../app/layout.tsx", import.meta.url)),
      "utf8",
    );
    const shellSource = readFileSync(
      fileURLToPath(new URL("../components/learning-app-shell.tsx", import.meta.url)),
      "utf8",
    );

    expect(existsSync(learningPage)).toBe(true);
    expect(layoutSource).toContain("<LearningAppShell>{children}</LearningAppShell>");
    expect(shellSource).toContain("resolveLearningShellPath(usePathname())");
    expect(workspaceSource).toContain('import Link from "next/link"');
    expect(workspaceSource).toContain("href={learningPath(workspace.id, id)}");
    expect(workspaceSource).toContain('aria-current={section === id ? "page" : undefined}');
  });

  it("separates personal home, current space, and local workspace sections", () => {
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );
    const switcherSource = readFileSync(
      fileURLToPath(new URL("../components/workspace-switcher.tsx", import.meta.url)),
      "utf8",
    );
    const sidebarSource = readFileSync(
      fileURLToPath(new URL("../components/app-sidebar.tsx", import.meta.url)),
      "utf8",
    );

    expect(workspaceSource).toContain("<AppSidebar");
    expect(sidebarSource).toContain('data-testid="app-nav-home"');
    expect(workspaceSource).toContain("<WorkspaceSwitcher");
    expect(switcherSource).toContain('data-testid="workspace-switcher"');
    expect(workspaceSource).toContain('contextLabel={t("workspaceSections")}');
    expect(workspaceSource).not.toContain('className="sidebar-learning"');
    expect(workspaceSource).toContain('onHomeNavigate={prepareHomeNavigation}');
    expect(workspaceSource).toContain('data-testid="workspace-route-state"');
    expect(switcherSource).toContain('aria-label={`${text.switchSpace}: ${current.title}`}');
  });

  it("reuses one learner shell while home and learning URLs change", () => {
    const shellSource = readFileSync(
      fileURLToPath(new URL("../components/learning-app-shell.tsx", import.meta.url)),
      "utf8",
    );

    expect(shellSource.match(/<StudyWorkspace/g)).toHaveLength(2);
    expect(shellSource).not.toContain("key={route.workspaceId}");
    expect(resolveLearningShellPath("/")).toEqual({ kind: "home" });
    expect(resolveLearningShellPath("/learn/space%201/materials")).toEqual({
      kind: "workspace",
      workspaceId: "space 1",
      section: "materials",
    });
    expect(resolveLearningShellPath("/learn/space-1/unknown")).toEqual({ kind: "other" });
    expect(resolveLearningShellPath("/admin")).toEqual({ kind: "other" });
  });

  it("never hands stale workspace state across a shared-shell route change", () => {
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );
    const restoreStart = workspaceSource.indexOf("async function restore()");
    const authenticatedStart = workspaceSource.indexOf("async function authenticated");
    const restoreSource = workspaceSource.slice(restoreStart, authenticatedStart);
    const openStart = workspaceSource.indexOf("async function openWorkspace");
    const resolveStart = workspaceSource.indexOf("async function resolveIntent");
    const uploadStart = workspaceSource.indexOf("async function uploadMaterials");
    const openSource = workspaceSource.slice(openStart, resolveStart);
    const resolveSource = workspaceSource.slice(resolveStart, uploadStart);

    expect(restoreSource.indexOf("clearWorkspaceState()"))
      .toBeLessThan(restoreSource.indexOf("api.getWorkspaceSnapshot"));
    expect(openSource).toContain("removeWorkspaceSnapshot(window.sessionStorage, target.id)");
    expect(openSource).not.toContain("saveWorkspaceSnapshot");
    expect(resolveSource).toContain("removeWorkspaceSnapshot(window.sessionStorage, route.workspace.id)");
    expect(resolveSource).not.toContain("saveWorkspaceSnapshot");
  });

  it("hands off every volatile learning field and resets user-scoped state on exit", () => {
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );
    const shellSource = readFileSync(
      fileURLToPath(new URL("../components/learning-app-shell.tsx", import.meta.url)),
      "utf8",
    );

    expect(workspaceSource).toContain("topic_suggestions: topicSuggestions");
    expect(workspaceSource).toContain("client_state:");
    expect(workspaceSource).toContain("setMasteryBefore(snapshot.client_state.masteryBefore)");
    expect(workspaceSource).toContain("setLearningMode(snapshot.client_state.learningMode)");
    expect(workspaceSource).toContain("persistWorkspaceHandoffRef.current = persistWorkspaceHandoff");
    expect(workspaceSource).toContain("persistWorkspaceHandoffRef.current()");
    expect(workspaceSource).toContain("savedSession?.token !== activeToken");
    expect(workspaceSource).toContain("installHistoryNavigationGuard");
    expect(workspaceSource).toContain("clearUserScopedSessionState(window.sessionStorage)");
    expect(shellSource).toContain("subscribeUnauthorized");
    expect(shellSource).toContain("if (!isCurrentUserSession(window.sessionStorage, token)) return;");
    expect(shellSource).toContain("clearUserScopedSessionState(window.sessionStorage)");
  });

  it("marks home navigation busy before dropping the active workspace", () => {
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );
    const prepareStart = workspaceSource.indexOf("function commitHomeNavigation");
    const logoutStart = workspaceSource.indexOf("function prepareRouteNavigation", prepareStart);
    const prepareSource = workspaceSource.slice(prepareStart, logoutStart);

    expect(prepareSource.indexOf("setHomeBusy(true)")).toBeGreaterThanOrEqual(0);
    expect(prepareSource.indexOf("setHomeBusy(true)"))
      .toBeLessThan(prepareSource.indexOf("setWorkspace(null)"));
  });

  it("renders the automatic routing decision with correction controls", () => {
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );

    expect(workspaceSource).toContain('data-testid="workspace-route-notice"');
    expect(workspaceSource).toContain('data-testid="workspace-routing-summary"');
    expect(workspaceSource).toContain("workspace.routing_summary");
    expect(workspaceSource).not.toContain("}, 7000);");
    expect(workspaceSource).toContain("route.confidence");
    expect(workspaceSource).toContain("route.reason");
    expect(workspaceSource).toContain("undoWorkspaceRoute");
  });

  it("keeps reviews on Today and gives learning records their own anchor", () => {
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );

    expect(workspaceSource.match(/<ReviewQueue/g)).toHaveLength(1);
    expect(workspaceSource).toContain('{section === "today" && (');
    expect(workspaceSource).toContain('id="learning-record"');
    expect(workspaceSource).toContain('href="#learning-record"');
    expect(workspaceSource).toContain("onStartPlanSession={startPlanSession}");
  });
});


describe("responsive learning workspace layout", () => {
  it("uses wide desktop space without forcing an empty viewport-height canvas", () => {
    const styles = readFileSync(
      fileURLToPath(new URL("../app/styles.css", import.meta.url)),
      "utf8",
    );

    expect(styles).toContain("grid-template-columns: minmax(0, 1fr) minmax(300px, 360px);");
    expect(styles).toContain("max-width: 1600px;");
    expect(styles).not.toContain("min-height: max(760px, calc(100vh - 108px));");
    expect(styles).toMatch(
      /@media \(max-width: 760px\)[\s\S]*\.plan-session-editor\s*\{[^}]*grid-column: 3;[^}]*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/,
    );
  });

  it("places capability progress and the evidence ledger side by side on wide screens", () => {
    const styles = readFileSync(
      fileURLToPath(new URL("../app/styles.css", import.meta.url)),
      "utf8",
    );

    expect(styles).toMatch(
      /\.learning-progress-view\s*\{[^}]*grid-template-columns: minmax\(0, 1\.35fr\) minmax\(320px, 0\.65fr\)/s,
    );
  });

  it("keeps mobile section context, shortcuts, focus, and task actions explicit", () => {
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );
    const canvasSource = readFileSync(
      fileURLToPath(new URL("../components/learning-session-canvas.tsx", import.meta.url)),
      "utf8",
    );
    const styles = readFileSync(
      fileURLToPath(new URL("../app/styles.css", import.meta.url)),
      "utf8",
    );

    expect(workspaceSource).toContain('data-testid="mobile-section-context"');
    expect(workspaceSource).toContain('data-testid={`mobile-shortcut-${id}`}');
    expect(workspaceSource).toContain("sectionHeadingRef.current?.focus");
    expect(canvasSource).toContain('data-testid="mobile-sticky-task-action"');
    expect(styles).toMatch(/\.mobile-context-shortcuts a\s*\{[^}]*min-height: 44px/s);
    expect(styles).toMatch(/\.mobile-sticky-task-action[^}]*position: sticky/s);
    expect(styles).toMatch(/\.session-task > label[^}]*font-size: 12px/s);
    expect(styles).toMatch(/\.workspace-switcher\s*\{[^}]*min-height: 44px/s);
    expect(styles).toMatch(/\.workspace-switcher > strong\s*\{[^}]*font-size: 12px/s);
    expect(styles).toMatch(/\.session-source-link[^}]*min-height: 44px/s);
    expect(styles).toMatch(/\.recent-card-actions button,[\s\S]*?min-width: 44px/s);
    expect(styles).toMatch(/\.material-actions button[\s\S]*?min-height: 44px/s);
    expect(styles).toContain("@media (hover: none)");
    expect(styles).toMatch(/\.calendar-grid\s*\{[^}]*grid-template-columns: 1fr/s);
    expect(styles).toMatch(/\.calendar-day\.empty\s*\{[^}]*display: none/s);
  });
});


describe("authentication and API errors", () => {
  it("uses the authenticated account management contracts", async () => {
    const requests: Array<{ path: string; method: string; body?: unknown }> = [];
    const client = new ApiClient("/api", async (input, init) => {
      const path = String(input);
      requests.push({
        path,
        method: init?.method ?? "GET",
        body: init?.body ? JSON.parse(String(init.body)) : undefined,
      });
      if (path.endsWith("/profile")) {
        return new Response(JSON.stringify({
          id: "user-1",
          email: "learner@example.com",
          display_name: "Focused Learner",
          role: "learner",
          created_at: "2026-08-08T00:00:00Z",
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (path.endsWith("/export")) {
        return new Response(JSON.stringify({
          exported_at: "2026-08-08T00:00:00Z",
          user: { id: "user-1", email: "learner@example.com", display_name: "Learner", role: "learner", created_at: "2026-08-08T00:00:00Z" },
          records: [],
          materials: [],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return new Response(null, { status: 204 });
    });

    await client.updateProfile("token", "Focused Learner");
    await client.changePassword("token", "current-password", "new-secure-password");
    await client.exportAccount("token");
    await client.revokeSessions("token");
    await client.deleteAccount("token", "current-password", "learner@example.com");

    expect(requests).toEqual([
      { path: "/api/auth/profile", method: "PATCH", body: { display_name: "Focused Learner" } },
      { path: "/api/auth/password", method: "PUT", body: { current_password: "current-password", new_password: "new-secure-password" } },
      { path: "/api/auth/export", method: "GET", body: undefined },
      { path: "/api/auth/sessions", method: "DELETE", body: undefined },
      { path: "/api/auth/account", method: "DELETE", body: { current_password: "current-password", confirmation: "learner@example.com" } },
    ]);
  });

  it("keeps the account route reachable from home and a learning workspace", () => {
    const accountPage = fileURLToPath(new URL("../app/account/page.tsx", import.meta.url));
    const homeSource = readFileSync(
      fileURLToPath(new URL("../components/learning-home.tsx", import.meta.url)),
      "utf8",
    );
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );
    const sidebarSource = readFileSync(
      fileURLToPath(new URL("../components/app-sidebar.tsx", import.meta.url)),
      "utf8",
    );

    expect(existsSync(accountPage)).toBe(true);
    expect(homeSource).toContain("<AppSidebar");
    expect(workspaceSource).toContain("<AppSidebar");
    expect(sidebarSource).toContain('data-testid="app-nav-account"');
    expect(sidebarSource).toContain('href="/account"');
  });

  it("delays releasing the account export until the browser can start the download", () => {
    const accountSource = readFileSync(
      fileURLToPath(new URL("../components/account-center.tsx", import.meta.url)),
      "utf8",
    );

    expect(accountSource).toContain("setTimeout(() => URL.revokeObjectURL(url)");
  });

  it("sends platform integration changes only to administrator endpoints", async () => {
    let requestedPath = "";
    let requestedInit: RequestInit | undefined;
    const client = new ApiClient("/api", async (input, init) => {
      requestedPath = String(input);
      requestedInit = init;
      return new Response(JSON.stringify({
        kind: "chat",
        enabled: true,
        configured: true,
        config: {
          base_url: "https://api.openai.com/v1",
          model: "gpt-4.1-mini",
          temperature: 0.2,
        },
        secret_hints: { api_key: "••••1234" },
        last_test_status: null,
        last_test_message: null,
        last_tested_at: null,
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    });

    await client.updateIntegration("admin-token", "chat", {
      enabled: true,
      config: {
        base_url: "https://api.openai.com/v1",
        model: "gpt-4.1-mini",
        temperature: 0.2,
      },
      secrets: { api_key: "sk-secret" },
    });

    expect(requestedPath).toBe("/api/admin/integrations/chat");
    expect(requestedInit?.method).toBe("PUT");
    expect(requestedInit?.headers).toMatchObject({ Authorization: "Bearer admin-token" });
    expect(JSON.parse(String(requestedInit?.body))).toMatchObject({
      secrets: { api_key: "sk-secret" },
    });
  });

  it("adds a bearer token only when authenticated", () => {
    expect(authHeaders("token-1")).toEqual({ Authorization: "Bearer token-1" });
    expect(authHeaders(null)).toEqual({});
  });

  it("preserves stable API error codes", () => {
    const error = new ApiError(404, "workspace_not_found", "Learning space not found");

    expect(error.status).toBe(404);
    expect(error.code).toBe("workspace_not_found");
  });

  it("turns an API error envelope into ApiError", async () => {
    const client = new ApiClient("/api", async () =>
      new Response(
        JSON.stringify({
          error: { code: "unauthorized", message: "Authentication required" },
        }),
        { status: 401, headers: { "Content-Type": "application/json" } },
      ),
    );

    await expect(client.getProfile("bad-token")).rejects.toMatchObject({
      status: 401,
      code: "unauthorized",
    });
  });

  it("broadcasts an authenticated 401 so every product area can reset consistently", async () => {
    const unauthorized = vi.fn();
    const unsubscribe = subscribeUnauthorized(unauthorized);
    const client = new ApiClient("/api", async () => new Response(
      JSON.stringify({ error: { code: "unauthorized", message: "Expired" } }),
      { status: 401, headers: { "Content-Type": "application/json" } },
    ));

    try {
      await expect(client.getProfile("expired-token")).rejects.toBeInstanceOf(ApiError);
      expect(unauthorized).toHaveBeenCalledWith("expired-token");
    } finally {
      unsubscribe();
    }
  });

  it("deduplicates short-lived profile and workspace reads without crossing tokens", async () => {
    const calls: string[] = [];
    const client = new ApiClient("/api", async (input) => {
      calls.push(String(input));
      const isProfile = String(input).endsWith("/auth/me");
      return new Response(JSON.stringify(isProfile ? {
        id: "user-1",
        email: "learner@example.com",
        display_name: "Learner",
        role: "learner",
        created_at: "2026-08-08T00:00:00Z",
      } : []), { status: 200, headers: { "Content-Type": "application/json" } });
    });

    await Promise.all([
      client.getProfile("token-1"),
      client.getProfile("token-1"),
      client.listWorkspaces("token-1"),
      client.listWorkspaces("token-1"),
    ]);
    await client.getProfile("token-2");

    expect(calls.filter((path) => path.endsWith("/auth/me"))).toHaveLength(2);
    expect(calls.filter((path) => path.endsWith("/workspaces"))).toHaveLength(1);
  });

  it("supports no-content mutation responses", async () => {
    const client = new ApiClient("/api", async () => new Response(null, { status: 204 }));

    await expect(client.deleteWorkspace("token-1", "workspace-1")).resolves.toBeUndefined();
  });

  it("keeps the browser receiver when using the default fetch", async () => {
    const receivers: unknown[] = [];
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(function (
      this: unknown,
    ) {
      receivers.push(this);
      return Promise.resolve(
        new Response(
          JSON.stringify({
            id: "user-1",
            email: "learner@example.com",
            display_name: "Learner",
            created_at: "2026-08-06T00:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    });

    try {
      await new ApiClient().getProfile("token-1");
      expect(receivers).toEqual([globalThis]);
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("aborts a request that exceeds the client timeout", async () => {
    vi.useFakeTimers();
    const client = new ApiClient(
      "/api",
      async (_input, init) => new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("aborted", "AbortError"));
        });
      }),
      25,
    );

    const pending = client.getProfile("token-1");
    const rejection = expect(pending).rejects.toMatchObject({
      status: 408,
      code: "request_timeout",
    });
    await vi.advanceTimersByTimeAsync(25);

    await rejection;
    vi.useRealTimers();
  });

  it("does not turn a caller cancellation into a timeout or product error", async () => {
    const controller = new AbortController();
    const client = new ApiClient("/api", async (_input, init) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("cancelled", "AbortError")));
    }));

    const pending = client.uploadWorkspaceMaterials(
      "token-1",
      "workspace-1",
      [new File(["notes"], "notes.md")],
      controller.signal,
    );
    controller.abort();

    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    await expect(pending.catch((error) => isAbortError(error))).resolves.toBe(true);
  });

  it("does not abort response parsing after response headers arrive", async () => {
    vi.useFakeTimers();
    let signal: AbortSignal | null | undefined;
    const client = new ApiClient("/api", async (_input, init) => {
      signal = init?.signal;
      return {
        ok: true,
        status: 200,
        json: () => new Promise((resolve, reject) => {
          signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
          setTimeout(() => resolve({
            id: "user-1",
            email: "learner@example.com",
            display_name: "Learner",
            role: "learner",
            created_at: "2026-08-08T00:00:00Z",
          }), 50);
        }),
      } as Response;
    }, 25);

    const pending = client.getProfile("token-1");
    await vi.advanceTimersByTimeAsync(50);
    await expect(pending).resolves.toMatchObject({ id: "user-1" });
    expect(signal?.aborted).toBe(false);
    vi.useRealTimers();
  });

  it("only clears the account session for authentication failures", () => {
    expect(shouldClearAccountSession(new ApiError(401, "invalid_token", "expired"))).toBe(true);
    expect(shouldClearAccountSession(new ApiError(403, "forbidden", "forbidden"))).toBe(true);
    expect(shouldClearAccountSession(new ApiError(502, "upstream", "offline"))).toBe(false);
    expect(shouldClearAccountSession(new Error("network"))).toBe(false);
  });

  it("runs a multi-file upload queue serially", async () => {
    const events: string[] = [];
    await runSerially(["one", "two", "three"], async (item) => {
      events.push(`start:${item}`);
      await Promise.resolve();
      events.push(`finish:${item}`);
    });

    expect(events).toEqual([
      "start:one", "finish:one",
      "start:two", "finish:two",
      "start:three", "finish:three",
    ]);
  });

  it("keeps separately selected upload batches in one serial queue", async () => {
    const events: string[] = [];
    const releases: Array<() => void> = [];
    const uploads = createSerialTaskQueue<string>(async (item) => {
      events.push(`start:${item}`);
      await new Promise<void>((resolve) => releases.push(resolve));
      events.push(`finish:${item}`);
    });

    uploads.enqueue(["one", "two"]);
    uploads.enqueue(["three"]);
    await vi.waitFor(() => expect(events).toEqual(["start:one"]));
    releases.shift()?.();
    await vi.waitFor(() => expect(events).toEqual(["start:one", "finish:one", "start:two"]));
    releases.shift()?.();
    await vi.waitFor(() => expect(events).toContain("start:three"));
    releases.shift()?.();
    await vi.waitFor(() => expect(events.at(-1)).toBe("finish:three"));
  });

  it("does not start queued uploads after the queue is closed", async () => {
    const events: string[] = [];
    let release: (() => void) | undefined;
    const uploads = createSerialTaskQueue<string>(async (item) => {
      events.push(item);
      await new Promise<void>((resolve) => { release = resolve; });
    });

    uploads.enqueue(["one", "two"]);
    await vi.waitFor(() => expect(events).toEqual(["one"]));
    uploads.close();
    release?.();
    await Promise.resolve();
    expect(events).toEqual(["one"]);
    expect(uploads.pendingCount()).toBe(0);
  });

  it("keeps upload cleanup and route redirects explicit in the workspace UI", () => {
    const materialSource = readFileSync(
      fileURLToPath(new URL("../components/material-dropzone.tsx", import.meta.url)),
      "utf8",
    );
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );

    expect(materialSource).toContain('addEventListener("beforeunload"');
    expect(materialSource).toContain("controller.abort()");
    expect(materialSource).toContain("consumeHistoryUploadContinuation()");
    expect(materialSource).toContain("onUploadActivityChange");
    expect(workspaceSource).toContain("onUploadActivityChange={setUploadInProgress}");
    expect(workspaceSource).toContain("navigationBlockReason");
    expect(workspaceSource).toContain("event.preventDefault()");
    expect(workspaceSource).toContain("pendingRouteActionRef.current");
    expect(workspaceSource).toContain("workspaceRef.current?.id === targetWorkspaceId");
    expect(workspaceSource).toContain("setHomeBusy(true)");
    expect(workspaceSource).toContain("if (isAbortError(caught)) return []");
    expect(workspaceSource).toContain("learningModeForActivity(session.activity");
    expect(workspaceSource).toContain("planSessionId: session.id");
    expect(workspaceSource).toContain("onStartSession={startPlanSession}");
    expect(workspaceSource).toContain('data-testid="resync-workspace"');
  });

  it("uses the model timeout and stable turn identifiers for Agent chat", async () => {
    vi.useFakeTimers();
    let signal: AbortSignal | null | undefined;
    let body = "";
    const client = new ApiClient(
      "/api",
      async (_input, init) => {
        signal = init?.signal;
        body = String(init?.body);
        return new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("aborted", "AbortError"));
          });
        });
      },
      25,
      { model: 75, upload: 100 },
    );

    const pending = client.chatWorkspace(
      "token-1",
      "workspace-1",
      "Explain limits",
      "session-1",
      "turn-1",
    );
    const rejection = expect(pending).rejects.toMatchObject({
      status: 408,
      code: "request_timeout",
    });
    await vi.advanceTimersByTimeAsync(25);
    expect(signal?.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(50);

    await rejection;
    expect(JSON.parse(body)).toMatchObject({
      session_id: "session-1",
      turn_id: "turn-1",
    });
    vi.useRealTimers();
  });

  it("sends current learning state to the session coach", async () => {
    let body = "";
    const client = new ApiClient("/api", async (_input, init) => {
      body = String(init?.body);
      return new Response(JSON.stringify({
        session_id: "coach-1",
        message: "Try a smaller step",
        citations: [],
        sources: [],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    });

    await client.chatWorkspace(
      "token",
      "workspace-1",
      "Help me",
      "coach-1",
      "turn-1",
      undefined,
      {
        learning_mode: "project",
        stage: "practice",
        question: "Build a prototype",
        draft: "My first step",
        timezone: "Asia/Shanghai",
      },
    );

    expect(JSON.parse(body).session_context).toEqual({
      learning_mode: "project",
      stage: "practice",
      question: "Build a prototype",
      draft: "My first step",
      timezone: "Asia/Shanghai",
    });
  });

  it("returns discriminated coach action proposals from Agent chat", async () => {
    const proposal = {
      type: "adjust_practice" as const,
      action_id: "action-1",
      topic_id: "limits",
      topic_name: "Limits",
      difficulty: 2,
      learning_mode: "concept" as const,
      destructive: true,
    };
    const client = new ApiClient("/api", async () => new Response(JSON.stringify({
      session_id: "coach-1",
      message: "We can try an easier question.",
      citations: [],
      sources: [],
      action_proposal: proposal,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));

    const response = await client.chatWorkspace(
      "token",
      "workspace-1",
      "Give me an easier question",
      "coach-1",
      "turn-1",
    );

    expect(response.action_proposal).toEqual(proposal);
  });
});


describe("recoverable client workflows", () => {
  it("keeps the graded question intact when loading the next question fails", async () => {
    const previous = { id: "question-1", answer: "A limit is...", score: 80 };
    let state = previous;

    await expect(loadNextQuestion(
      async () => { throw new Error("model unavailable"); },
      (question) => { state = { id: question.id, answer: "", score: 0 }; },
    )).rejects.toThrow("model unavailable");

    expect(state).toBe(previous);
  });

  it("clears a file input so the same material can be selected again", () => {
    const input = { value: "C:\\fakepath\\notes.pdf" };

    clearSelectedFiles(input);

    expect(input.value).toBe("");
  });
});


describe("targeted and saved practice API", () => {
  it("sends topic, plan session, learning mode, difficulty, and replacement intent without leaking them into paths", async () => {
    let requestedPath = "";
    let requestedInit: RequestInit | undefined;
    const client = new ApiClient("/api", async (input, init) => {
      requestedPath = String(input);
      requestedInit = init;
      return new Response(JSON.stringify({
        id: "question-2",
        topic_id: "limits",
        prompt: "Explain a limit",
        difficulty_level: 4,
        citations: [],
        sources: [],
        mode: "ai",
        saved: false,
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    });

    await client.createWorkspaceQuestion("token", "workspace-1", {
      requestId: "question-request-1",
      topicId: "limits",
      learningMode: "case",
      difficulty: 4,
      replace: true,
      planSessionId: "plan-session-1",
    });

    expect(requestedPath).toBe("/api/workspaces/workspace-1/learning/question");
    expect(requestedInit?.method).toBe("POST");
    expect(JSON.parse(String(requestedInit?.body))).toEqual({
      request_id: "question-request-1",
      topic_id: "limits",
      difficulty: 4,
      mode: "case",
      replace: true,
      plan_session_id: "plan-session-1",
    });
  });

  it("persists and lists saved questions", async () => {
    const requests: Array<{ path: string; method: string; body: string }> = [];
    const client = new ApiClient("/api", async (input, init) => {
      requests.push({
        path: String(input),
        method: init?.method ?? "GET",
        body: String(init?.body ?? ""),
      });
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    await client.setWorkspaceQuestionSaved("token", "workspace-1", "question-1", true);
    await client.listWorkspaceSavedQuestions("token", "workspace-1");

    expect(requests).toEqual([
      {
        path: "/api/workspaces/workspace-1/learning/questions/question-1/saved",
        method: "PUT",
        body: JSON.stringify({ saved: true }),
      },
      {
        path: "/api/workspaces/workspace-1/learning/questions/saved",
        method: "GET",
        body: "",
      },
    ]);
  });
});


describe("projectless product surface", () => {
  it("does not ship the retired project wizard or call project routes", () => {
    const wizard = fileURLToPath(new URL("../components/goal-wizard.tsx", import.meta.url));
    const apiSource = readFileSync(
      fileURLToPath(new URL("../lib/api.ts", import.meta.url)),
      "utf8",
    );

    expect(existsSync(wizard)).toBe(false);
    expect(apiSource).not.toContain("/projects/");
    expect(apiSource).not.toContain("createProject");
  });

  it("gives every clickable surface pressed-state feedback", () => {
    const styles = readFileSync(
      fileURLToPath(new URL("../app/styles.css", import.meta.url)),
      "utf8",
    );

    expect(styles).toContain(".quiet-button:active:not(:disabled)");
    expect(styles).toContain(".auth-tabs button:active:not(:disabled)");
    expect(styles).toContain(".recent-grid button:active:not(:disabled)");
    expect(styles).toContain(".workspace-nav a:active");
    expect(styles).toContain(".wordmark-button:active:not(:disabled)");
    expect(styles).toContain(".upload-surface:active:not(:disabled)");
  });

  it("keeps authentication supporting copy readable", () => {
    const styles = readFileSync(
      fileURLToPath(new URL("../app/styles.css", import.meta.url)),
      "utf8",
    );

    expect(styles).toContain("--auth-supporting-size: 19px");
    expect(styles).toContain("--auth-card-supporting-size: 14px");
    expect(styles).toMatch(/\.auth-copy > p\s*\{[^}]*font-size: var\(--auth-supporting-size\)/s);
    expect(styles).toMatch(/\.auth-form-heading p\s*\{[^}]*font-size: var\(--auth-card-supporting-size\)/s);
  });

  it("gives the desktop authentication form enough visual weight", () => {
    const styles = readFileSync(
      fileURLToPath(new URL("../app/styles.css", import.meta.url)),
      "utf8",
    );

    expect(styles).toMatch(/\.auth-form-card\s*\{[^}]*width: min\(500px,[^}]*padding: 44px/s);
    expect(styles).toMatch(/\.auth-tabs button\s*\{[^}]*min-height: 42px/s);
    expect(styles).toMatch(/\.auth-form-card input\s*\{[^}]*min-height: 46px/s);
    expect(styles).toMatch(/\.auth-form-card \.primary-action\s*\{[^}]*min-height: 46px/s);
  });

  it("fills the authentication stage with composed visual surfaces", () => {
    const styles = readFileSync(
      fileURLToPath(new URL("../app/styles.css", import.meta.url)),
      "utf8",
    );

    expect(styles).toMatch(/\.auth-form-side\s*\{[^}]*min-height: calc\(100dvh - 32px\)[^}]*margin: 16px[^}]*border-radius: 26px/s);
    expect(styles).toMatch(/\.auth-illustration\s*\{[^}]*width: clamp\(390px, 34vw, 500px\)/s);
    expect(styles).toMatch(/@media \(max-width: 900px\)[\s\S]*?\.auth-form-side\s*\{[^}]*min-height: auto[^}]*margin: 0/s);
  });

  it("keeps the welcome illustration decorative and desktop-only", () => {
    const styles = readFileSync(
      fileURLToPath(new URL("../app/styles.css", import.meta.url)),
      "utf8",
    );

    expect(styles).toMatch(/\.auth-illustration\s*\{[^}]*pointer-events: none/s);
    expect(styles).toMatch(/@media \(max-width: 900px\)[\s\S]*?\.auth-illustration\s*\{[^}]*display: none/s);
    expect(styles).not.toContain(".auth-memory-track");
    expect(styles).not.toContain(".auth-memory-step");
  });
});


describe("persistent personal learning session", () => {
  function memoryStorage(): Storage {
    const values = new Map<string, string>();
    return {
      get length() { return values.size; },
      clear: () => values.clear(),
      getItem: (key) => values.get(key) ?? null,
      key: (index) => Array.from(values.keys())[index] ?? null,
      removeItem: (key) => { values.delete(key); },
      setItem: (key, value) => { values.set(key, value); },
    };
  }

  it("restores and clears the token plus last learning workspace", () => {
    const storage = memoryStorage();
    saveLearningSession(storage, {
      token: "token-1",
      workspaceId: "math-space",
      locale: "en",
    });

    expect(loadLearningSession(storage)).toEqual({
      token: "token-1",
      workspaceId: "math-space",
      locale: "en",
    });

    expect(storage.getItem("refineq.learning-session")).not.toContain('"home"');

    clearLearningSession(storage);
    expect(loadLearningSession(storage)).toBeNull();
  });

  it("rejects malformed persisted session data", () => {
    const storage = memoryStorage();
    storage.setItem("refineq.learning-session", "not-json");

    expect(loadLearningSession(storage)).toBeNull();
  });

  it("drops legacy view state because the URL owns home versus workspace", () => {
    const storage = memoryStorage();
    storage.setItem("refineq.learning-session", JSON.stringify({
      token: "token-1",
      workspaceId: "math-space",
      locale: "zh",
      home: false,
    }));

    expect(loadLearningSession(storage)).toEqual({
      token: "token-1",
      workspaceId: "math-space",
      locale: "zh",
    });
    expect(loadLearningSession(storage)).not.toHaveProperty("home");
  });

  it("keeps the last workspace when language changes from personal home", () => {
    const storage = memoryStorage();
    saveLearningSession(storage, {
      token: "token-1",
      workspaceId: "math-space",
      locale: "zh",
    });

    saveLearningLocale(storage, "token-1", "en");

    expect(loadLearningSession(storage)).toEqual({
      token: "token-1",
      workspaceId: "math-space",
      locale: "en",
    });
  });

  it("keeps bearer tokens out of persistent local storage", () => {
    const sources = ["../components/study-workspace.tsx", "../components/admin-route.tsx"]
      .map((path) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8"));

    expect(sources.every((source) => source.includes("window.sessionStorage"))).toBe(true);
    expect(sources.every((source) => !source.includes("window.localStorage"))).toBe(true);
  });

  it("clears every user-scoped browser value from every account exit surface", () => {
    const sources = [
      "../components/study-workspace.tsx",
      "../components/account-center.tsx",
      "../components/admin-route.tsx",
      "../components/global-calendar-route.tsx",
    ].map((path) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8"));

    expect(sources.every((source) => source.includes("clearUserScopedSessionState(window.sessionStorage)")))
      .toBe(true);
  });

  it("hands a short-lived session to a new same-origin tab", async () => {
    type Listener = (event: MessageEvent) => void;
    const peers = new Set<FakeChannel>();
    class FakeChannel {
      listeners = new Set<Listener>();
      constructor() { peers.add(this); }
      postMessage(message: unknown) {
        for (const peer of peers) {
          queueMicrotask(() => peer.listeners.forEach((listener) => listener({ data: message } as MessageEvent)));
        }
      }
      addEventListener(_type: "message", listener: Listener) { this.listeners.add(listener); }
      removeEventListener(_type: "message", listener: Listener) { this.listeners.delete(listener); }
      close() { peers.delete(this); }
    }
    const storage = () => {
      const values = new Map<string, string>();
      return {
        get length() { return values.size; },
        clear: () => values.clear(),
        getItem: (key: string) => values.get(key) ?? null,
        key: (index: number) => Array.from(values.keys())[index] ?? null,
        setItem: (key: string, value: string) => { values.set(key, value); },
        removeItem: (key: string) => { values.delete(key); },
      } satisfies Storage;
    };
    const existingTab = storage();
    const newTab = storage();
    saveLearningSession(existingTab, { token: "short-lived-token", workspaceId: "workspace-1", locale: "en" });
    const createChannel = () => new FakeChannel();
    const stop = installSessionHandoff(existingTab, createChannel);

    const restored = await requestSessionHandoff(newTab, createChannel, 50);

    expect(restored).toEqual({ token: "short-lived-token", workspaceId: "workspace-1", locale: "en" });
    expect(loadLearningSession(newTab)).toEqual(restored);
    stop();
  });
});


describe("implicit workspace API", () => {
  it("lists and explicitly accepts owner-scoped material topic suggestions", async () => {
    const requests: Array<{ path: string; method: string }> = [];
    const client = new ApiClient("/api", async (input, init) => {
      requests.push({ path: String(input), method: String(init?.method ?? "GET") });
      const body = String(input).endsWith("/accept") ? {} : [];
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    await client.listWorkspaceTopicSuggestions("token", "math-space");
    await client.acceptWorkspaceTopicSuggestion("token", "math-space", "topic_epsilon");

    expect(requests).toEqual([
      { path: "/api/workspaces/math-space/topic-suggestions", method: "GET" },
      {
        path: "/api/workspaces/math-space/topic-suggestions/topic_epsilon/accept",
        method: "POST",
      },
    ]);
  });

  it("submits the initial diagnostic through the owner-scoped workspace route", async () => {
    let requestedPath = "";
    let requestedBody: unknown;
    const client = new ApiClient("/api", async (input, init) => {
      requestedPath = String(input);
      requestedBody = JSON.parse(String(init?.body));
      return new Response(JSON.stringify({
        goal: "Pass calculus",
        mastery: { limits: 0.4 },
        topics: { limits: "Limits" },
        topic_order: ["limits"],
        diagnostic_count: 1,
        attempt_count: 0,
        plan_id: "plan-1",
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    });

    await client.submitWorkspaceDiagnostic("token", "math-space", [
      { topic_id: "limits", is_correct: true },
    ]);

    expect(requestedPath).toBe("/api/workspaces/math-space/learning/diagnostic");
    expect(requestedBody).toEqual({
      diagnostic_id: "initial",
      results: [{ topic_id: "limits", is_correct: true }],
    });
  });

  it("resolves an intent and restores a workspace snapshot", async () => {
    const requests: Array<{ path: string; method: string }> = [];
    const client = new ApiClient("/api", async (input, init) => {
      const path = String(input);
      requests.push({ path, method: init?.method ?? "GET" });
      if (path.endsWith("/workspaces/resolve")) {
        return new Response(JSON.stringify({
          action: "created",
          confidence: 0.92,
          reason: "新学习方向",
          workspace: {
            id: "math-space",
            title: "高等数学",
            subject: "mathematics",
            goal: "复习高数",
            topics: ["极限"],
            keywords: ["高数", "极限"],
            routing_summary: "数学学习",
            created_at: "2026-08-06T00:00:00Z",
            last_active_at: "2026-08-06T00:00:00Z",
          },
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return new Response(JSON.stringify({
        workspace: { id: "math-space" },
        progress: null,
        plan: null,
        evidence: [],
        materials: [],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    });

    const route = await client.resolveWorkspace("token-1", "复习高数");
      await client.getWorkspaceSnapshot("token-1", route.workspace.id, 480);
      await client.getWorkspaceNextAction("token-1", route.workspace.id, 480);

      expect(requests).toEqual([
        { path: "/api/workspaces/resolve", method: "POST" },
        {
          path: "/api/workspaces/math-space/snapshot?timezone_offset_minutes=480",
          method: "GET",
        },
        {
          path: "/api/workspaces/math-space/next-action?timezone_offset_minutes=480",
          method: "GET",
        },
      ]);
  });

  it("updates plan settings through the workspace plan contract", async () => {
    let body: Record<string, unknown> | undefined;
    const client = new ApiClient("/api", async (input, init) => {
      expect(String(input)).toBe("/api/workspaces/math-space/learning/plan");
      expect(init?.method).toBe("PUT");
      const parsed = JSON.parse(String(init?.body)) as Record<string, unknown>;
      body = parsed;
      return new Response(JSON.stringify({
        id: "plan-2",
        goal: parsed.goal,
        exam_at: parsed.exam_at,
        daily_minutes: parsed.daily_minutes,
        sessions: [{
          id: "session-2",
          topic_id: "limits",
          planned_at: "2026-08-09T08:00:00Z",
          minutes: parsed.daily_minutes,
        }],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    });

    const plan = await client.updateWorkspacePlan("token-1", "math-space", {
      goal: "Pass calculus",
      exam_at: "2026-08-20T23:59:59Z",
      daily_minutes: 35,
      topic_order: ["limits"],
      regenerate: true,
    });

    expect(body).toEqual({
      goal: "Pass calculus",
      exam_at: "2026-08-20T23:59:59Z",
      daily_minutes: 35,
      topic_order: ["limits"],
      regenerate: true,
    });
    expect(plan.id).toBe("plan-2");
  });

  it("loads insights, retries the same question, and updates learner feedback", async () => {
    const requests: Array<{ path: string; method: string; body?: unknown }> = [];
    const client = new ApiClient("/api", async (input, init) => {
      const path = String(input);
      requests.push({
        path,
        method: init?.method ?? "GET",
        body: init?.body ? JSON.parse(String(init.body)) : undefined,
      });
      if (path.endsWith("/insights")) {
        return new Response(JSON.stringify({
          workspace_id: "math-space",
          mastery_history: [],
          topics: [],
          due_reviews: [],
          attempts: [],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (path.endsWith("/retry")) {
        return new Response(JSON.stringify({
          id: "question-1",
          topic_id: "limits",
          prompt: "Explain limits",
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return new Response(JSON.stringify({
        attempt_id: "attempt-1",
        learner_note: "Review this rubric",
        appealed: true,
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    });

    await client.getWorkspaceInsights("token-1", "math-space");
    await client.retryWorkspaceQuestion("token-1", "math-space", "question-1");
    await client.updateWorkspaceAttemptFeedback("token-1", "math-space", "attempt-1", {
      learner_note: "Review this rubric",
      appealed: true,
    });

    expect(requests).toEqual([
      { path: "/api/workspaces/math-space/learning/insights", method: "GET" },
      { path: "/api/workspaces/math-space/learning/questions/question-1/retry", method: "POST" },
      {
        path: "/api/workspaces/math-space/learning/attempts/attempt-1/feedback",
        method: "PATCH",
        body: { learner_note: "Review this rubric", appealed: true },
      },
    ]);
  });
});


describe("global calendar API", () => {
  it("serializes a bounded range and archived-space preference", async () => {
    let requestedPath = "";
    let requestedInit: RequestInit | undefined;
    const client = new ApiClient("/api", async (input, init) => {
      requestedPath = String(input);
      requestedInit = init;
      return new Response(JSON.stringify({
        starts_at: "2026-07-26T00:00:00.000Z",
        ends_at: "2026-09-06T00:00:00.000Z",
        tasks: [],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    });

    await client.getCalendar(
      "calendar-token",
      "2026-07-26T00:00:00.000Z",
      "2026-09-06T00:00:00.000Z",
      true,
    );

    expect(requestedPath).toBe(
      "/api/calendar?starts_at=2026-07-26T00%3A00%3A00.000Z"
      + "&ends_at=2026-09-06T00%3A00%3A00.000Z&include_archived=true",
    );
    expect(requestedInit?.method ?? "GET").toBe("GET");
    expect((requestedInit?.headers as Record<string, string>).Authorization).toBe(
      "Bearer calendar-token",
    );
  });
});


describe("internally computable learning metrics", () => {
  it("marks a material-grounded grade as shown and reads the admin metric window", async () => {
    const requests: Array<{ path: string; method: string }> = [];
    const client = new ApiClient("/api", async (input, init) => {
      requests.push({ path: String(input), method: init?.method ?? "GET" });
      return new Response(JSON.stringify({}), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    await client.markWorkspaceGradeShown("token", "workspace-1", "attempt-1");
    await client.getAdminLearningMetrics(
      "token",
      "2026-08-03T00:00:00.000Z",
      "2026-08-10T00:00:00.000Z",
    );

    expect(requests).toEqual([
      {
        path: "/api/workspaces/workspace-1/learning/attempts/attempt-1/shown",
        method: "POST",
      },
      {
        path: "/api/admin/metrics/learning?starts_at=2026-08-03T00%3A00%3A00.000Z&ends_at=2026-08-10T00%3A00%3A00.000Z",
        method: "GET",
      },
    ]);
  });
});


describe("global calendar route", () => {
  it("loads a bounded owner calendar and hands task deep links to an executable Today session", () => {
    const page = fileURLToPath(new URL("../app/calendar/page.tsx", import.meta.url));
    const route = fileURLToPath(new URL("../components/global-calendar-route.tsx", import.meta.url));
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );

    expect(existsSync(page)).toBe(true);
    expect(existsSync(route)).toBe(true);
    if (!existsSync(page) || !existsSync(route)) return;
    const pageSource = readFileSync(page, "utf8");
    const routeSource = readFileSync(route, "utf8");
    expect(pageSource).toContain("<GlobalCalendarRoute");
    expect(routeSource).toContain("api.getCalendar");
    expect(routeSource).toContain("calendarGridRange");
    expect(routeSource).toContain("includeArchived");
    expect(workspaceSource).toContain("new URLSearchParams(window.location.search)");
    expect(workspaceSource).toContain("preferredSessionId={focusedPlanSessionId}");
  });
});


describe("unified authenticated shell styling", () => {
  it("gives shared navigation and the global calendar explicit desktop and mobile layouts", () => {
    const styles = readFileSync(
      fileURLToPath(new URL("../app/styles.css", import.meta.url)),
      "utf8",
    );

    expect(styles).toContain("/* Unified authenticated application shell */");
    expect(styles).toContain(".app-sidebar {");
    expect(styles).toContain(".global-calendar-shell {");
      expect(styles).toContain(".global-calendar-layout {");
      expect(styles).toContain('.global-calendar [data-color="0"]');
      expect(styles).toContain("@media (max-width: 900px)");
      expect(styles).not.toContain("min-width: 720px");
      expect(styles).toContain(".calendar-weekdays,\n  .global-month-calendar .calendar-weekdays");
      expect(styles).toContain(".calendar-grid,\n  .global-calendar-grid");
      expect(styles).toContain(".global-calendar-day.outside,\n  .global-calendar-day.empty");
      expect(styles).toContain("min-height: 64px;");
    });
});

describe("plan setting validation", () => {
  it("requires a goal, a future date, valid minutes, and every topic exactly once", () => {
    const invalid = validatePlanSettings({
      goal: " ",
      examDate: "2026-08-08",
      dailyMinutes: 4,
      topicOrder: ["limits", "limits"],
      availableTopics: ["limits", "derivatives"],
    }, new Date("2026-08-08T08:00:00Z"));

    expect(invalid).toEqual(expect.objectContaining({
      goal: expect.any(String),
      examDate: expect.any(String),
      dailyMinutes: expect.any(String),
      topicOrder: expect.any(String),
    }));
    expect(validatePlanSettings({
      goal: "Pass calculus",
      examDate: "2026-08-20",
      dailyMinutes: 35,
      topicOrder: ["derivatives", "limits"],
      availableTopics: ["limits", "derivatives"],
    }, new Date("2026-08-08T08:00:00Z"))).toEqual({});
  });
});

describe("recoverable material and Agent interactions", () => {
  it("validates supported learning files before upload", () => {
    expect(validateUploadFile({ name: "notes.md", size: 100 })).toBeNull();
    expect(validateUploadFile({ name: "notes.markdown", size: 100 })).toBe("unsupported_type");
    expect(validateUploadFile({ name: "large.pdf", size: 21 * 1024 * 1024 })).toBe("file_too_large");
    expect(validateUploadFile({ name: "image.exe", size: 100 })).toBe("unsupported_type");
    expect(validateUploadFile({ name: "large.pdf", size: 30 * 1024 * 1024 })).toBe("file_too_large");
  });

  it("uses metadata and bulk organization API contracts", async () => {
    const requests: Array<{ path: string; method: string; body?: unknown }> = [];
    const client = new ApiClient("/api", async (input, init) => {
      requests.push({
        path: String(input),
        method: init?.method ?? "GET",
        body: init?.body ? JSON.parse(String(init.body)) : undefined,
      });
      if (init?.method === "PATCH") {
        return new Response(JSON.stringify({
          id: "material-1",
          project_id: "workspace-1",
          filename: "limits.txt",
          title: "Limits handbook",
          tags: ["exam"],
          content_type: "text/plain",
          size: 12,
          status: "indexed",
          chunk_count: 1,
          content_sha256: "abc",
          indexed_at: "2026-08-08T00:00:00Z",
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return new Response(null, { status: 204 });
    });

    await client.updateWorkspaceMaterial(
      "token",
      "workspace-1",
      "material-1",
      { title: "Limits handbook", tags: ["exam"] },
    );
    await client.bulkDeleteWorkspaceMaterials(
      "token",
      "workspace-1",
      ["material-1", "material-2"],
    );

    expect(requests).toEqual([
      {
        path: "/api/workspaces/workspace-1/materials/material-1",
        method: "PATCH",
        body: { title: "Limits handbook", tags: ["exam"] },
      },
      {
        path: "/api/workspaces/workspace-1/materials",
        method: "DELETE",
        body: { material_ids: ["material-1", "material-2"] },
      },
    ]);
  });

  it("ships cancellation, retry, history, and source controls", () => {
    const materialSource = readFileSync(
      fileURLToPath(new URL("../components/material-dropzone.tsx", import.meta.url)),
      "utf8",
    );
    const agentSource = readFileSync(
      fileURLToPath(new URL("../components/agent-panel.tsx", import.meta.url)),
      "utf8",
    );

    expect(materialSource).toContain("AbortController");
    expect(materialSource).toContain("retryUpload");
    expect(materialSource).toContain("onDrop");
    expect(agentSource).toContain("AbortController");
    expect(agentSource).toContain('data-testid="agent-stop"');
    expect(agentSource).toContain("navigator.clipboard.writeText");
    expect(agentSource).toContain("listWorkspaceAgentSessions");
    expect(agentSource).toContain("SourceDrawer");
  });

  it("mounts the complete Agent experience from the production learning session", () => {
    const canvasSource = readFileSync(
      fileURLToPath(new URL("../components/learning-session-canvas.tsx", import.meta.url)),
      "utf8",
    );
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );

    expect(canvasSource).toContain("<AgentPanel");
    expect(canvasSource).toContain("onApplyAction={onApplyCoachAction}");
    expect(canvasSource).toContain('data-testid="workspace-agent"');
    expect(workspaceSource).toContain("agentToken={auth.access_token}");
  });

  it("ships complete material search states and Agent guidance", () => {
    const materialSource = readFileSync(
      fileURLToPath(new URL("../components/material-dropzone.tsx", import.meta.url)),
      "utf8",
    );
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );
    const agentSource = readFileSync(
      fileURLToPath(new URL("../components/agent-panel.tsx", import.meta.url)),
      "utf8",
    );
    const drawerSource = readFileSync(
      fileURLToPath(new URL("../components/source-drawer.tsx", import.meta.url)),
      "utf8",
    );

    expect(materialSource).toContain('data-testid="material-search-empty"');
    expect(materialSource).toContain('data-testid="clear-material-search"');
    expect(materialSource).toContain('data-testid="clear-upload-queue"');
    expect(materialSource).toContain("SourceDrawer");
    expect(materialSource).toContain('data-testid="material-filter-status"');
    expect(materialSource).toContain('data-testid="material-bulk-delete"');
    expect(workspaceSource).toContain("updateWorkspaceMaterial");
    expect(workspaceSource).toContain("bulkDeleteWorkspaceMaterials");
    expect(agentSource).toContain('data-testid="agent-suggestion"');
    expect(agentSource).toContain("scrollIntoView");
    expect(agentSource).toContain("onOpenSettings");
    expect(drawerSource).toContain("focusable");
    expect(drawerSource).not.toContain("source.citation_id");
  });
});

describe("safe authentication and administration", () => {
  it("ships password recovery and dirty-form protections", () => {
    const authSource = readFileSync(
      fileURLToPath(new URL("../components/auth-panel.tsx", import.meta.url)),
      "utf8",
    );
    const adminSource = readFileSync(
      fileURLToPath(new URL("../components/admin-console.tsx", import.meta.url)),
      "utf8",
    );

    expect(authSource).toContain("requestPasswordReset");
    expect(authSource).toContain("completePasswordReset");
    expect(authSource).toContain("passwordRules");
    expect(adminSource).toContain("beforeunload");
    expect(adminSource).toContain("isDirty");
    expect(adminSource).toContain("saveAndTest");
    expect(adminSource).toContain("loadError");
    expect(authSource).not.toContain("localStorage");
    expect(adminSource).not.toContain("localStorage");
  });

  it("uses application dialogs and inline editing instead of browser prompts", () => {
    const paths = [
      "../components/learning-home.tsx",
      "../components/material-dropzone.tsx",
      "../components/agent-panel.tsx",
      "../components/admin-console.tsx",
    ];
    const sources = paths.map((path) => readFileSync(
      fileURLToPath(new URL(path, import.meta.url)),
      "utf8",
    ));

    for (const source of sources) {
      expect(source).not.toContain("window.prompt");
      expect(source).not.toContain("window.confirm");
    }
    expect(sources[0]).toContain("workspace-rename-form");
    expect(sources.every((source) => source.includes("ConfirmDialog"))).toBe(true);
  });
});

describe("accessible application shell", () => {
  it("provides a keyboard skip target and localized document state", () => {
    const layoutSource = readFileSync(
      fileURLToPath(new URL("../app/layout.tsx", import.meta.url)),
      "utf8",
    );
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );

    expect(layoutSource).toContain('href="#main-content"');
    expect(layoutSource).toContain("skip-link");
    expect(workspaceSource).toContain('id="main-content"');
    expect(workspaceSource).toContain("document.documentElement.lang");
    expect(workspaceSource).toContain('aria-live="polite"');
    expect(workspaceSource).toContain("caught.status === 401");
  });

  it("ships branded route loading, error, and not-found recovery states", () => {
    const loadingPath = fileURLToPath(new URL("../app/loading.tsx", import.meta.url));
    const errorPath = fileURLToPath(new URL("../app/error.tsx", import.meta.url));
    const notFoundPath = fileURLToPath(new URL("../app/not-found.tsx", import.meta.url));
    const globalErrorPath = fileURLToPath(new URL("../app/global-error.tsx", import.meta.url));

    expect(existsSync(loadingPath)).toBe(true);
    expect(existsSync(errorPath)).toBe(true);
    expect(existsSync(notFoundPath)).toBe(true);
    expect(existsSync(globalErrorPath)).toBe(true);
    expect(readFileSync(loadingPath, "utf8")).toContain('data-testid="route-loading"');
    expect(readFileSync(errorPath, "utf8")).toContain("reset()");
    expect(readFileSync(notFoundPath, "utf8")).toContain('href="/"');
    expect(readFileSync(loadingPath, "utf8")).toContain("useSessionLocale");
    expect(readFileSync(errorPath, "utf8")).toContain("useSessionLocale");
    expect(readFileSync(notFoundPath, "utf8")).toContain("useSessionLocale");
  });

  it("provides application and social metadata", () => {
    const layoutSource = readFileSync(
      fileURLToPath(new URL("../app/layout.tsx", import.meta.url)),
      "utf8",
    );

    expect(layoutSource).toContain("applicationName");
    expect(layoutSource).toContain("openGraph");
    expect(layoutSource).toContain("twitter");
    expect(layoutSource).toContain("icons");
  });

  it("sets browser security headers for every web route", () => {
    const configSource = readFileSync(
      fileURLToPath(new URL("../next.config.ts", import.meta.url)),
      "utf8",
    );

    expect(configSource).toContain("Content-Security-Policy");
    expect(configSource).toContain("frame-ancestors 'none'");
    expect(configSource).toContain("X-Content-Type-Options");
    expect(configSource).toContain("Referrer-Policy");
    expect(configSource).toContain('process.env.NODE_ENV === "development"');
    expect(configSource).toContain("'unsafe-eval'");
  });

  it("exposes reset tokens only to the isolated browser-test API process", () => {
    const configSource = readFileSync(
      fileURLToPath(new URL("../playwright.config.ts", import.meta.url)),
      "utf8",
    );
    const backendStart = configSource.indexOf('command: `"${python}" -m uvicorn');
    const frontendStart = configSource.indexOf('command: "npm run dev');

    expect(backendStart).toBeGreaterThanOrEqual(0);
    expect(frontendStart).toBeGreaterThan(backendStart);
    expect(configSource.slice(backendStart, frontendStart)).toContain(
      'REFINEQ_PASSWORD_RESET_EXPOSE_TOKEN: "true"',
    );
    expect(configSource.slice(frontendStart)).not.toContain(
      "REFINEQ_PASSWORD_RESET_EXPOSE_TOKEN",
    );
  });

  it("shows password recovery only after public capability detection", () => {
    const authSource = readFileSync(
      fileURLToPath(new URL("../components/auth-panel.tsx", import.meta.url)),
      "utf8",
    );
    const apiSource = readFileSync(
      fileURLToPath(new URL("../lib/api.ts", import.meta.url)),
      "utf8",
    );
    const typesSource = readFileSync(
      fileURLToPath(new URL("../lib/types.ts", import.meta.url)),
      "utf8",
    );

    expect(typesSource).toContain("AuthCapabilities");
    expect(typesSource).toContain("password_reset_available: boolean");
    expect(apiSource).toContain('this.request("/auth/capabilities")');
    expect(authSource).toContain("api.getAuthCapabilities()");
    expect(authSource).toContain("passwordResetAvailable &&");
    expect(authSource).toContain('window.location.hash.startsWith("#reset-token=")');
    expect(authSource).toContain("window.history.replaceState");
  });
});


describe("learning view models", () => {
  const plan: StudyPlan = {
    id: "plan-1",
    goal: "Pass calculus",
    exam_at: "2026-08-10T08:00:00Z",
    daily_minutes: 45,
    sessions: [
      {
        id: "session-1",
        topic_id: "limits",
        planned_at: "2026-08-06T08:00:00Z",
        minutes: 45,
      },
      {
        id: "session-2",
        topic_id: "derivatives",
        planned_at: "2026-08-07T08:00:00Z",
        minutes: 45,
      },
    ],
  };

  it("turns plan sessions into numbered timeline rows", () => {
    const rows = buildPlanRows(plan, "en-US", { limits: "Function limits" });

    expect(rows.map((row) => row.sequence)).toEqual([1, 2]);
    expect(rows[0].topic).toBe("Function limits");
    expect(rows[1].topic).toBe("Untitled topic");
    expect(rows[0].minutesLabel).toBe("45 min");
  });

  it("distinguishes fresh and replayed practice results", () => {
    expect(practiceStatus({ is_correct: true, replayed: false })).toBe("mastered");
    expect(practiceStatus({ is_correct: false, replayed: false })).toBe("revise");
    expect(practiceStatus({ is_correct: true, replayed: true })).toBe("replayed");
  });

  it("maps evidence kinds to restrained visual tones", () => {
    expect(evidenceTone("attempt")).toBe("jade");
    expect(evidenceTone("diagnostic")).toBe("amber");
    expect(evidenceTone("material")).toBe("ink");
  });
});


it("keeps Chinese and English locale keys in parity", () => {
  expect(Object.keys(messages.zh).sort()).toEqual(Object.keys(messages.en).sort());
});


it("routes workspace restoration failures through the safe localized mapper", () => {
  const workspaceSource = readFileSync(
    fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
    "utf8",
  );
  const restoreStart = workspaceSource.indexOf("async function restore()");
  const routeNoticeStart = workspaceSource.indexOf("if (!route) return;");
  const restoreSource = workspaceSource.slice(restoreStart, routeNoticeStart);

  expect(restoreSource).toContain("localizeApiError(caught, saved.locale ?? \"zh\")");
  expect(restoreSource).not.toContain("caught.message");
  expect(workspaceSource).toContain('data-testid="auth-restore-error"');
});


it("treats model capability checks as optional and propagates runtime unavailability", () => {
  const workspaceSource = readFileSync(
    fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
    "utf8",
  );
  const canvasSource = readFileSync(
    fileURLToPath(new URL("../components/learning-session-canvas.tsx", import.meta.url)),
    "utf8",
  );
  const agentSource = readFileSync(
    fileURLToPath(new URL("../components/agent-panel.tsx", import.meta.url)),
    "utf8",
  );

  expect(workspaceSource).toContain("loadModelCapability(() => api.getModelSettings");
  expect(workspaceSource).toContain("onModelUnavailable={() => setModelConfigured(false)}");
  expect(canvasSource).toContain("onModelUnavailable={onModelUnavailable}");
  expect(agentSource).toContain("onModelUnavailable?.()");
});


describe("navigation efficiency remediation", () => {
  it("invalidates cached identity and workspace collections after successful mutations", async () => {
    const calls: string[] = [];
    const client = new ApiClient("/api", async (input) => {
      const path = String(input);
      calls.push(path);
      if (path.endsWith("/auth/me") || path.endsWith("/auth/profile")) {
        return new Response(JSON.stringify({
          id: "user-1",
          email: "learner@example.com",
          display_name: "Learner",
          role: "learner",
          created_at: "2026-08-08T00:00:00Z",
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (path.endsWith("/workspaces/space-1") || path.endsWith("/workspaces/resolve")) {
        return new Response(JSON.stringify({ id: "space-1" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    await client.getProfile("token");
    await client.updateProfile("token", "Updated");
    await client.getProfile("token");
    await client.listWorkspaces("token");
    await client.updateWorkspace("token", "space-1", { title: "Updated" });
    await client.listWorkspaces("token");
    await client.resolveWorkspace("token", "new goal");
    await client.listWorkspaces("token");

    expect(calls.filter((path) => path.endsWith("/auth/me"))).toHaveLength(2);
    expect(calls.filter((path) => path.endsWith("/workspaces"))).toHaveLength(3);
  });

  it("keeps locale out of data-fetch dependencies and restores independent reads in parallel", () => {
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );
    const adminSource = readFileSync(
      fileURLToPath(new URL("../components/admin-console.tsx", import.meta.url)),
      "utf8",
    );

    expect(workspaceSource).not.toContain("auth?.access_token, locale, section");
    expect(adminSource).not.toContain("[locale, nonce, token]");
    expect(adminSource).not.toContain("[activeSection, locale, token, loadNonce]");
    expect(workspaceSource).toContain("api.listWorkspaces(saved.token),");
    expect(workspaceSource).toContain("api.getWorkspaceInsights(saved.token, selected.id)");
    expect(workspaceSource.match(/applySnapshot\(snapshot\);\s+if \(restoredInsights\)/g))
      .toHaveLength(2);
    expect(workspaceSource).toContain("api.getWorkspaceInsights(saved.token, selected.id).catch(() => null)");
    expect(workspaceSource).toContain("persistWorkspaceHandoffRef.current();\n          setWorkspace(null)");
  });

  it("uses client-side routing after dirty-form confirmation and removes retired navigation CSS", () => {
    const adminSource = readFileSync(
      fileURLToPath(new URL("../components/admin-console.tsx", import.meta.url)),
      "utf8",
    );
    const adminRouteSource = readFileSync(
      fileURLToPath(new URL("../components/admin-route.tsx", import.meta.url)),
      "utf8",
    );
    const cssSource = readFileSync(
      fileURLToPath(new URL("../app/styles.css", import.meta.url)),
      "utf8",
    );

    expect(adminRouteSource).toContain("router.push(");
    expect(adminSource).not.toContain("window.location.assign(pendingHref)");
    expect(cssSource).not.toContain(".app-spaces-all");
    expect(cssSource).not.toContain(".app-recent-spaces > small");
  });
});
