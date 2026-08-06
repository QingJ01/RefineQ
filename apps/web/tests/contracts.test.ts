import { describe, expect, it, vi } from "vitest";

import { ApiClient, ApiError, authHeaders } from "../lib/api";
import { messages } from "../lib/i18n";
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
    const error = new ApiError(404, "project_not_found", "Project not found");

    expect(error.status).toBe(404);
    expect(error.code).toBe("project_not_found");
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
