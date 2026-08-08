import { describe, expect, it } from "vitest";

import {
  clearWorkspaceSnapshots,
  consumeWorkspaceSnapshot,
  removeWorkspaceSnapshot,
  saveWorkspaceSnapshot,
  WORKSPACE_SNAPSHOT_TTL_MS,
} from "../lib/workspace-snapshot-handoff";
import type { WorkspaceSnapshot } from "../lib/types";


class MemoryStorage {
  private values = new Map<string, string>();

  getItem(key: string) { return this.values.get(key) ?? null; }
  setItem(key: string, value: string) { this.values.set(key, value); }
  removeItem(key: string) { this.values.delete(key); }
  key(index: number) { return Array.from(this.values.keys())[index] ?? null; }
  get length() { return this.values.size; }
}

const snapshot = {
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
  progress: {
    goal: "Master limits",
    mastery: { limits: 0.2 },
    topics: { limits: "Limits" },
    topic_order: ["limits"],
    diagnostic_count: 0,
    attempt_count: 0,
    plan_id: null,
  },
  plan: null,
  evidence: [],
  materials: [],
} satisfies WorkspaceSnapshot;

describe("workspace snapshot handoff", () => {
  it("hands a prefetched snapshot to the next route exactly once", () => {
    const storage = new MemoryStorage();

    saveWorkspaceSnapshot(storage, snapshot, 1_000);

    expect(consumeWorkspaceSnapshot(storage, "workspace-1", 1_001)).toEqual(snapshot);
    expect(consumeWorkspaceSnapshot(storage, "workspace-1", 1_001)).toBeNull();
  });

  it("preserves local learning mode, mastery baseline, and topic suggestions", () => {
    const storage = new MemoryStorage();
    const enriched = {
      ...snapshot,
      topic_suggestions: [{
        id: "suggestion-1",
        name: "Continuity",
        source_material_ids: ["material-1"],
      }],
      client_state: { learningMode: "project" as const, masteryBefore: 0.35 },
    };

    saveWorkspaceSnapshot(storage, enriched, 1_000);

    expect(consumeWorkspaceSnapshot(storage, "workspace-1", 1_001)).toEqual(enriched);
  });

  it("rejects an expired snapshot and removes it", () => {
    const storage = new MemoryStorage();
    saveWorkspaceSnapshot(storage, snapshot, 1_000);

    expect(consumeWorkspaceSnapshot(
      storage,
      "workspace-1",
      1_000 + WORKSPACE_SNAPSHOT_TTL_MS + 1,
    )).toBeNull();
    expect(consumeWorkspaceSnapshot(storage, "workspace-1", 1_001)).toBeNull();
  });

  it("degrades safely when browser storage is full", () => {
    const storage = new MemoryStorage();
    storage.setItem = () => { throw new DOMException("full", "QuotaExceededError"); };

    expect(saveWorkspaceSnapshot(storage, snapshot, 1_000)).toBe(false);
  });

  it("does not return a snapshot for a different workspace", () => {
    const storage = new MemoryStorage();
    saveWorkspaceSnapshot(storage, snapshot);

    expect(consumeWorkspaceSnapshot(storage, "workspace-2")).toBeNull();
  });

  it("can discard a stale snapshot without consuming another workspace", () => {
    const storage = new MemoryStorage();
    saveWorkspaceSnapshot(storage, snapshot);
    saveWorkspaceSnapshot(storage, {
      ...snapshot,
      workspace: { ...snapshot.workspace, id: "workspace-2" },
    });

    removeWorkspaceSnapshot(storage, "workspace-1");

    expect(consumeWorkspaceSnapshot(storage, "workspace-1")).toBeNull();
    expect(consumeWorkspaceSnapshot(storage, "workspace-2")?.workspace.id).toBe("workspace-2");
  });

  it("clears every cached workspace snapshot without touching unrelated session state", () => {
    const storage = new MemoryStorage();
    saveWorkspaceSnapshot(storage, snapshot);
    saveWorkspaceSnapshot(storage, {
      ...snapshot,
      workspace: { ...snapshot.workspace, id: "workspace-2" },
    });
    storage.setItem("refineq.learning-session", "keep");

    clearWorkspaceSnapshots(storage);

    expect(consumeWorkspaceSnapshot(storage, "workspace-1")).toBeNull();
    expect(consumeWorkspaceSnapshot(storage, "workspace-2")).toBeNull();
    expect(storage.getItem("refineq.learning-session")).toBe("keep");
  });
});
