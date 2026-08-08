import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it, vi } from "vitest";

import { ApiClient, ApiError, authHeaders } from "../lib/api";
import { messages } from "../lib/i18n";
import { loadNextQuestion } from "../lib/practice-flow";
import { learningSections, parseLearningSection } from "../lib/learning-routes";
import {
  clearLearningSession,
  loadLearningSession,
  saveLearningLocale,
  saveLearningSession,
} from "../lib/session";
import { clearSelectedFiles, validateUploadFile } from "../lib/upload-flow";
import { resolveRequestedWorkspace } from "../lib/workspace-route-state";
import {
    buildPlanRows,
    evidenceTone,
    practiceStatus,
    projectIntegrationTestResult,
} from "../lib/view-models";
import type { StudyPlan } from "../lib/types";


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
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );

    expect(existsSync(adminPage)).toBe(true);
    expect(existsSync(integrationPage)).toBe(true);
    expect(workspaceSource).toContain('router.push("/admin")');
    expect(workspaceSource).not.toContain('section === "admin"');
    expect(workspaceSource).not.toContain('"coach" | "admin"');
  });
});


describe("durable learner routing", () => {
  it("uses capability-oriented learner routes and keeps legacy links recoverable", () => {
    expect(learningSections).toEqual(["today", "path", "materials", "progress"]);
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

    expect(existsSync(learningPage)).toBe(true);
    expect(workspaceSource).toContain('import Link from "next/link"');
    expect(workspaceSource).toContain("href={learningPath(workspace.id, id)}");
    expect(workspaceSource).toContain('aria-current={section === id ? "page" : undefined}');
  });

  it("separates personal home, current space, and local workspace sections", () => {
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );

    expect(workspaceSource).toContain('data-testid="workspace-home-link"');
    expect(workspaceSource).toContain('data-testid="workspace-switcher"');
    expect(workspaceSource).toContain('className="workspace-nav-label"');
    expect(workspaceSource).not.toContain('className="sidebar-learning"');
    expect(workspaceSource).not.toContain('onClick={prepareHomeNavigation}');
    expect(workspaceSource).toContain('data-testid="workspace-route-state"');
    expect(workspaceSource).toContain('aria-label={`${t("switchSpace")}: ${workspace.title}`}');
  });

  it("remounts learner state when the URL switches to a different workspace", () => {
    const routeSource = readFileSync(
      fileURLToPath(new URL("../components/learning-route.tsx", import.meta.url)),
      "utf8",
    );

    expect(routeSource).toContain("key={workspaceId}");
  });

  it("renders the automatic routing decision with correction controls", () => {
    const workspaceSource = readFileSync(
      fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
      "utf8",
    );

    expect(workspaceSource).toContain('data-testid="workspace-route-notice"');
    expect(workspaceSource).toContain("route.confidence");
    expect(workspaceSource).toContain("route.reason");
    expect(workspaceSource).toContain("undoWorkspaceRoute");
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
});


describe("authentication and API errors", () => {
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
      },
    );

    expect(JSON.parse(body).session_context).toEqual({
      learning_mode: "project",
      stage: "practice",
      question: "Build a prototype",
      draft: "My first step",
    });
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
  it("sends topic, learning mode, difficulty, and replacement intent without leaking them into paths", async () => {
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
    });

    expect(requestedPath).toBe("/api/workspaces/workspace-1/learning/question");
    expect(requestedInit?.method).toBe("POST");
    expect(JSON.parse(String(requestedInit?.body))).toEqual({
      request_id: "question-request-1",
      topic_id: "limits",
      difficulty: 4,
      mode: "case",
      replace: true,
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
});


describe("implicit workspace API", () => {
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
    await client.getWorkspaceSnapshot("token-1", route.workspace.id);

    expect(requests).toEqual([
      { path: "/api/workspaces/resolve", method: "POST" },
      { path: "/api/workspaces/math-space/snapshot", method: "GET" },
    ]);
  });
});

describe("recoverable material and Agent interactions", () => {
  it("validates supported learning files before upload", () => {
    expect(validateUploadFile({ name: "notes.md", size: 100 })).toBeNull();
    expect(validateUploadFile({ name: "image.exe", size: 100 })).toBe("unsupported_type");
    expect(validateUploadFile({ name: "large.pdf", size: 30 * 1024 * 1024 })).toBe("file_too_large");
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
    expect(canvasSource).toContain('data-testid="workspace-agent"');
    expect(workspaceSource).toContain("agentToken={auth.access_token}");
  });

  it("ships complete material search states and Agent guidance", () => {
    const materialSource = readFileSync(
      fileURLToPath(new URL("../components/material-dropzone.tsx", import.meta.url)),
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

    expect(existsSync(loadingPath)).toBe(true);
    expect(existsSync(errorPath)).toBe(true);
    expect(existsSync(notFoundPath)).toBe(true);
    expect(readFileSync(loadingPath, "utf8")).toContain('data-testid="route-loading"');
    expect(readFileSync(errorPath, "utf8")).toContain("reset()");
    expect(readFileSync(notFoundPath, "utf8")).toContain('href="/"');
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
});
