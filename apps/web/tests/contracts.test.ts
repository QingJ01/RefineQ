import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it, vi } from "vitest";

import { ApiClient, ApiError, authHeaders } from "../lib/api";
import { messages } from "../lib/i18n";
import { loadNextQuestion } from "../lib/practice-flow";
import { clearLearningSession, loadLearningSession, saveLearningSession } from "../lib/session";
import { clearSelectedFiles } from "../lib/upload-flow";
import {
  buildPlanRows,
  evidenceTone,
  practiceStatus,
} from "../lib/view-models";
import type { StudyPlan } from "../lib/types";


describe("authentication and API errors", () => {
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
    expect(styles).toContain(".workspace-nav button:active:not(:disabled)");
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
    saveLearningSession(storage, { token: "token-1", workspaceId: "math-space" });

    expect(loadLearningSession(storage)).toEqual({
      token: "token-1",
      workspaceId: "math-space",
    });

    clearLearningSession(storage);
    expect(loadLearningSession(storage)).toBeNull();
  });

  it("rejects malformed persisted session data", () => {
    const storage = memoryStorage();
    storage.setItem("refineq.learning-session", "not-json");

    expect(loadLearningSession(storage)).toBeNull();
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
    const rows = buildPlanRows(plan, "en-US");

    expect(rows.map((row) => row.sequence)).toEqual([1, 2]);
    expect(rows[0].topic).toBe("limits");
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
