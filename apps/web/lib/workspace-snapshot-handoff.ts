import type { WorkspaceSnapshot } from "./types";


interface SnapshotStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

interface EnumerableSnapshotStorage extends SnapshotStorage {
  readonly length: number;
  key(index: number): string | null;
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

export function clearWorkspaceSnapshots(storage: EnumerableSnapshotStorage): void {
  const keys: string[] = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (key?.startsWith(SNAPSHOT_PREFIX)) keys.push(key);
  }
  keys.forEach((key) => storage.removeItem(key));
}
