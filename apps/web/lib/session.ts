export interface LearningSession {
  token: string;
  workspaceId?: string;
  locale?: "zh" | "en";
}

const SESSION_KEY = "refineq.learning-session";
const SESSION_CHANNEL = "refineq.session-handoff";

interface SessionChannel {
  postMessage(message: unknown): void;
  addEventListener(type: "message", listener: (event: MessageEvent) => void): void;
  removeEventListener(type: "message", listener: (event: MessageEvent) => void): void;
  close(): void;
}

type SessionChannelFactory = (name: string) => SessionChannel;

function createSessionChannel(name: string): SessionChannel {
  return new BroadcastChannel(name);
}

function sessionOrigin(): string {
  return typeof location === "undefined" ? "refineq://local" : location.origin;
}

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

export function installSessionHandoff(
  storage: Storage,
  createChannel: SessionChannelFactory = createSessionChannel,
): () => void {
  if (typeof BroadcastChannel === "undefined" && createChannel === createSessionChannel) return () => undefined;
  const channel = createChannel(SESSION_CHANNEL);
  const origin = sessionOrigin();
  const onMessage = (event: MessageEvent) => {
    const message = event.data as { type?: string; requestId?: string; origin?: string };
    if (message.type !== "request" || !message.requestId || message.origin !== origin) return;
    const session = loadLearningSession(storage);
    if (!session) return;
    channel.postMessage({ type: "response", requestId: message.requestId, origin, session });
  };
  channel.addEventListener("message", onMessage);
  return () => {
    channel.removeEventListener("message", onMessage);
    channel.close();
  };
}

export function requestSessionHandoff(
  storage: Storage,
  createChannel: SessionChannelFactory = createSessionChannel,
  timeoutMs = 600,
): Promise<LearningSession | null> {
  if (typeof BroadcastChannel === "undefined" && createChannel === createSessionChannel) return Promise.resolve(null);
  const channel = createChannel(SESSION_CHANNEL);
  const requestId = crypto.randomUUID();
  const origin = sessionOrigin();
  return new Promise((resolve) => {
    const finish = (session: LearningSession | null) => {
      globalThis.clearTimeout(timeout);
      channel.removeEventListener("message", onMessage);
      channel.close();
      if (session) saveLearningSession(storage, session);
      resolve(session);
    };
    const onMessage = (event: MessageEvent) => {
      const message = event.data as {
        type?: string;
        requestId?: string;
        origin?: string;
        session?: LearningSession;
      };
      if (message.type !== "response" || message.requestId !== requestId || message.origin !== origin) return;
      const session = message.session;
      if (!session || typeof session.token !== "string" || session.token.length === 0) return;
      finish(session);
    };
    const timeout = globalThis.setTimeout(() => finish(null), timeoutMs);
    channel.addEventListener("message", onMessage);
    channel.postMessage({ type: "request", requestId, origin });
  });
}
