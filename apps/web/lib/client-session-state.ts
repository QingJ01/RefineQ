import type { WorkspaceRoute } from "./types";
import { loadLearningSession } from "./session";


interface EnumerableSessionStorage {
  readonly length: number;
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
  key(index: number): string | null;
}

export const ROUTE_NOTICE_KEY = "refineq.workspace-route-notice";
export const ROUTE_NOTICE_TTL_MS = 5 * 60 * 1_000;

const USER_SCOPED_EXACT_KEYS = new Set([
  "refineq.learning-session",
  ROUTE_NOTICE_KEY,
]);
const USER_SCOPED_PREFIXES = [
  "refineq.practice-draft:",
  "refineq.workspace-snapshot:",
];

export interface WorkspaceRouteNotice {
  route: WorkspaceRoute;
  previousWorkspaceId: string | null;
}

interface WorkspaceRouteNoticeEnvelope extends WorkspaceRouteNotice {
  created_at: number;
}

export function clearUserScopedSessionState(storage: EnumerableSessionStorage): void {
  const keys: string[] = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (
      key
      && (
        USER_SCOPED_EXACT_KEYS.has(key)
        || USER_SCOPED_PREFIXES.some((prefix) => key.startsWith(prefix))
      )
    ) keys.push(key);
  }
  keys.forEach((key) => storage.removeItem(key));
}

export function isCurrentUserSession(
  storage: Pick<EnumerableSessionStorage, "getItem">,
  token: string,
): boolean {
  return token.length > 0 && loadLearningSession(storage)?.token === token;
}

export function writeWorkspaceRouteNotice(
  storage: Pick<EnumerableSessionStorage, "setItem">,
  notice: WorkspaceRouteNotice,
  now = Date.now(),
): boolean {
  try {
    storage.setItem(ROUTE_NOTICE_KEY, JSON.stringify({ ...notice, created_at: now }));
    return true;
  } catch {
    return false;
  }
}

export function readWorkspaceRouteNotice(
  storage: Pick<EnumerableSessionStorage, "getItem" | "removeItem">,
  now = Date.now(),
): WorkspaceRouteNotice | null {
  const raw = storage.getItem(ROUTE_NOTICE_KEY);
  if (!raw) return null;
  try {
    const notice = JSON.parse(raw) as Partial<WorkspaceRouteNoticeEnvelope>;
    if (
      !notice.route?.workspace?.id
      || typeof notice.created_at !== "number"
      || now < notice.created_at
      || now - notice.created_at > ROUTE_NOTICE_TTL_MS
    ) {
      storage.removeItem(ROUTE_NOTICE_KEY);
      return null;
    }
    return {
      route: notice.route,
      previousWorkspaceId: typeof notice.previousWorkspaceId === "string"
        ? notice.previousWorkspaceId
        : null,
    };
  } catch {
    storage.removeItem(ROUTE_NOTICE_KEY);
    return null;
  }
}

export function clearWorkspaceRouteNotice(
  storage: Pick<EnumerableSessionStorage, "removeItem">,
): void {
  storage.removeItem(ROUTE_NOTICE_KEY);
}
