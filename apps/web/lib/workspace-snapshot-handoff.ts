import type { WorkspaceSnapshot } from "./types";


interface SnapshotStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

const SNAPSHOT_PREFIX = "refineq.workspace-snapshot:";

function snapshotKey(workspaceId: string) {
  return `${SNAPSHOT_PREFIX}${workspaceId}`;
}

export function saveWorkspaceSnapshot(
  storage: SnapshotStorage,
  snapshot: WorkspaceSnapshot,
) {
  storage.setItem(snapshotKey(snapshot.workspace.id), JSON.stringify(snapshot));
}

export function consumeWorkspaceSnapshot(
  storage: SnapshotStorage,
  workspaceId: string,
): WorkspaceSnapshot | null {
  const key = snapshotKey(workspaceId);
  const raw = storage.getItem(key);
  if (!raw) return null;
  storage.removeItem(key);
  try {
    const snapshot = JSON.parse(raw) as WorkspaceSnapshot;
    return snapshot.workspace?.id === workspaceId ? snapshot : null;
  } catch {
    return null;
  }
}
