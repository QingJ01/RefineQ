import type { LearningMode, WorkspaceSnapshot } from "./types";


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
const SNAPSHOT_VERSION = 1;
export const WORKSPACE_SNAPSHOT_TTL_MS = 5 * 60 * 1_000;

export interface WorkspaceSnapshotHandoff extends WorkspaceSnapshot {
  client_state?: {
    learningMode: LearningMode;
    masteryBefore: number | null;
  };
}

interface SnapshotEnvelope {
  version: typeof SNAPSHOT_VERSION;
  saved_at: number;
  snapshot: WorkspaceSnapshotHandoff;
}

function snapshotKey(workspaceId: string) {
  return `${SNAPSHOT_PREFIX}${workspaceId}`;
}

export function saveWorkspaceSnapshot(
  storage: SnapshotStorage,
  snapshot: WorkspaceSnapshotHandoff,
  now = Date.now(),
): boolean {
  const envelope: SnapshotEnvelope = {
    version: SNAPSHOT_VERSION,
    saved_at: now,
    snapshot,
  };
  try {
    storage.setItem(snapshotKey(snapshot.workspace.id), JSON.stringify(envelope));
    return true;
  } catch {
    return false;
  }
}

export function consumeWorkspaceSnapshot(
  storage: SnapshotStorage,
  workspaceId: string,
  now = Date.now(),
): WorkspaceSnapshotHandoff | null {
  const key = snapshotKey(workspaceId);
  const raw = storage.getItem(key);
  if (!raw) return null;
  storage.removeItem(key);
  try {
    const envelope = JSON.parse(raw) as Partial<SnapshotEnvelope>;
    if (
      envelope.version !== SNAPSHOT_VERSION
      || typeof envelope.saved_at !== "number"
      || now - envelope.saved_at > WORKSPACE_SNAPSHOT_TTL_MS
      || now < envelope.saved_at
    ) return null;
    const snapshot = envelope.snapshot;
    return snapshot?.workspace?.id === workspaceId ? snapshot : null;
  } catch {
    return null;
  }
}

export function removeWorkspaceSnapshot(storage: SnapshotStorage, workspaceId: string): void {
  storage.removeItem(snapshotKey(workspaceId));
}

export function clearWorkspaceSnapshots(storage: EnumerableSnapshotStorage): void {
  const keys: string[] = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (key?.startsWith(SNAPSHOT_PREFIX)) keys.push(key);
  }
  keys.forEach((key) => storage.removeItem(key));
}
