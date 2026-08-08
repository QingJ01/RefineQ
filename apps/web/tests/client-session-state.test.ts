import { describe, expect, it } from "vitest";

import {
  clearUserScopedSessionState,
  isCurrentUserSession,
  readWorkspaceRouteNotice,
  ROUTE_NOTICE_TTL_MS,
  writeWorkspaceRouteNotice,
} from "../lib/client-session-state";
import type { WorkspaceRoute } from "../lib/types";

class MemoryStorage {
  private values = new Map<string, string>();

  getItem(key: string) { return this.values.get(key) ?? null; }
  setItem(key: string, value: string) { this.values.set(key, value); }
  removeItem(key: string) { this.values.delete(key); }
  key(index: number) { return Array.from(this.values.keys())[index] ?? null; }
  get length() { return this.values.size; }
}

const route: WorkspaceRoute = {
  action: "switched",
  confidence: 0.9,
  reason: "The material belongs here",
  workspace: {
    id: "workspace-1",
    title: "Calculus",
    subject: "mathematics",
    goal: "Master limits",
    topics: ["Limits"],
    keywords: ["calculus"],
    routing_summary: "Calculus learning",
    archived: false,
    created_at: "2026-08-08T00:00:00Z",
    last_active_at: "2026-08-08T00:00:00Z",
  },
};

describe("user-scoped browser session state", () => {
  it("clears credentials, drafts, route notices, and snapshot handoffs only", () => {
    const storage = new MemoryStorage();
    storage.setItem("refineq.learning-session", "secret");
    storage.setItem("refineq.practice-draft:workspace-1:question-1", "private answer");
    storage.setItem("refineq.workspace-route-notice", "route");
    storage.setItem("refineq.workspace-snapshot:workspace-1", "snapshot");
    storage.setItem("refineq.ui-preference", "keep");

    clearUserScopedSessionState(storage);

    expect(storage.getItem("refineq.learning-session")).toBeNull();
    expect(storage.getItem("refineq.practice-draft:workspace-1:question-1")).toBeNull();
    expect(storage.getItem("refineq.workspace-route-notice")).toBeNull();
    expect(storage.getItem("refineq.workspace-snapshot:workspace-1")).toBeNull();
    expect(storage.getItem("refineq.ui-preference")).toBe("keep");
  });

  it("expires route notices instead of reviving them for the whole tab session", () => {
    const storage = new MemoryStorage();
    writeWorkspaceRouteNotice(storage, { route, previousWorkspaceId: "workspace-0" }, 1_000);

    expect(readWorkspaceRouteNotice(storage, 1_001)).toMatchObject({ route });
    expect(readWorkspaceRouteNotice(storage, 1_000 + ROUTE_NOTICE_TTL_MS + 1)).toBeNull();
    expect(storage.getItem("refineq.workspace-route-notice")).toBeNull();
  });

  it("accepts only the token that still owns the current browser session", () => {
    const storage = new MemoryStorage();
    storage.setItem("refineq.learning-session", JSON.stringify({ token: "new-token" }));

    expect(isCurrentUserSession(storage, "new-token")).toBe(true);
    expect(isCurrentUserSession(storage, "old-token")).toBe(false);
    expect(isCurrentUserSession(storage, "")).toBe(false);
  });
});
