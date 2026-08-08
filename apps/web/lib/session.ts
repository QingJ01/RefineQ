export interface LearningSession {
  token: string;
  workspaceId?: string;
  locale?: "zh" | "en";
}

const SESSION_KEY = "refineq.learning-session";

export function loadLearningSession(storage: Storage): LearningSession | null {
  const raw = storage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<LearningSession>;
    if (typeof parsed.token !== "string" || parsed.token.length === 0) return null;
    if (parsed.workspaceId !== undefined && typeof parsed.workspaceId !== "string") {
      return null;
    }
    const locale = parsed.locale === "en" || parsed.locale === "zh" ? parsed.locale : undefined;
    return { token: parsed.token, workspaceId: parsed.workspaceId, locale };
  } catch {
    return null;
  }
}

export function saveLearningSession(storage: Storage, session: LearningSession): void {
  storage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function saveLearningLocale(
  storage: Storage,
  token: string,
  locale: "zh" | "en",
  activeWorkspaceId?: string,
): void {
  const saved = loadLearningSession(storage);
  saveLearningSession(storage, {
    token,
    workspaceId: activeWorkspaceId ?? saved?.workspaceId,
    locale,
  });
}

export function clearLearningSession(storage: Storage): void {
  storage.removeItem(SESSION_KEY);
}
