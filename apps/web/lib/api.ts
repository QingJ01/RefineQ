import type {
  AgentReply,
  AnswerResult,
  AuthResponse,
  LearningWorkspace,
  MaterialRecord,
  PracticeQuestion,
  PublicModelSettings,
  User,
  WorkspaceRoute,
  WorkspaceSnapshot,
} from "./types";


type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

interface LongRequestTimeouts {
  model: number;
  upload: number;
}

const DEFAULT_LONG_REQUEST_TIMEOUTS: LongRequestTimeouts = {
  model: 120_000,
  upload: 180_000,
};

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function authHeaders(token: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export class ApiClient {
  private readonly fetcher: Fetcher;
  private readonly longRequestTimeouts: LongRequestTimeouts;

  constructor(
    private readonly baseUrl = "/api",
    fetcher: Fetcher = globalThis.fetch.bind(globalThis),
    private readonly timeoutMs = 30_000,
    longRequestTimeouts: Partial<LongRequestTimeouts> = {},
  ) {
    this.fetcher = fetcher;
    this.longRequestTimeouts = {
      ...DEFAULT_LONG_REQUEST_TIMEOUTS,
      ...longRequestTimeouts,
    };
  }

  private async request<T>(
    path: string,
    options: RequestInit = {},
    token: string | null = null,
    timeoutMs = this.timeoutMs,
  ): Promise<T> {
    const controller = new AbortController();
    const externalSignal = options.signal;
    let timedOut = false;
    const abortFromCaller = () => controller.abort(externalSignal?.reason);
    if (externalSignal?.aborted) abortFromCaller();
    else externalSignal?.addEventListener("abort", abortFromCaller, { once: true });
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
    try {
      const isForm = options.body instanceof FormData;
      const response = await this.fetcher(`${this.baseUrl}${path}`, {
        ...options,
        signal: controller.signal,
        headers: {
          ...(isForm ? {} : { "Content-Type": "application/json" }),
          ...authHeaders(token),
          ...options.headers,
        },
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new ApiError(
          response.status,
          body?.error?.code ?? "request_error",
          body?.error?.message ?? `Request failed (${response.status})`,
        );
      }
      return await response.json() as T;
    } catch (caught) {
      if (timedOut) {
        throw new ApiError(408, "request_timeout", "Request timed out");
      }
      throw caught;
    } finally {
      clearTimeout(timeout);
      externalSignal?.removeEventListener("abort", abortFromCaller);
    }
  }

  register(email: string, password: string, displayName: string): Promise<AuthResponse> {
    return this.request("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, display_name: displayName }),
    });
  }

  login(email: string, password: string): Promise<AuthResponse> {
    return this.request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  }

  getProfile(token: string): Promise<User> {
    return this.request("/auth/me", {}, token);
  }

  listWorkspaces(token: string): Promise<LearningWorkspace[]> {
    return this.request("/workspaces", {}, token);
  }

  resolveWorkspace(token: string, intent: string): Promise<WorkspaceRoute> {
    return this.request(
      "/workspaces/resolve",
      { method: "POST", body: JSON.stringify({ intent }) },
      token,
      this.longRequestTimeouts.model,
    );
  }

  getWorkspaceSnapshot(token: string, workspaceId: string): Promise<WorkspaceSnapshot> {
    return this.request(`/workspaces/${workspaceId}/snapshot`, {}, token);
  }

  getWorkspaceQuestion(token: string, workspaceId: string): Promise<PracticeQuestion> {
    return this.request(
      `/workspaces/${workspaceId}/learning/question`,
      {},
      token,
      this.longRequestTimeouts.model,
    );
  }

  submitWorkspaceAnswer(
    token: string,
    workspaceId: string,
    questionId: string,
    answer: string,
  ): Promise<AnswerResult> {
    return this.request(
      `/workspaces/${workspaceId}/learning/answer`,
      {
        method: "POST",
        body: JSON.stringify({
          attempt_id: crypto.randomUUID().replaceAll("-", ""),
          question_id: questionId,
          answer,
        }),
      },
      token,
      this.longRequestTimeouts.model,
    );
  }

  uploadWorkspaceMaterials(
    token: string,
    workspaceId: string,
    files: File[],
  ): Promise<MaterialRecord[]> {
    const body = new FormData();
    files.forEach((file) => body.append("files", file));
    return this.request(
      `/workspaces/${workspaceId}/materials`,
      { method: "POST", body },
      token,
      this.longRequestTimeouts.upload,
    );
  }

  chatWorkspace(
    token: string,
    workspaceId: string,
    message: string,
    sessionId?: string,
    turnId?: string,
  ): Promise<AgentReply> {
    return this.request(
      `/workspaces/${workspaceId}/agent/chat`,
      {
        method: "POST",
        body: JSON.stringify({ message, session_id: sessionId, turn_id: turnId }),
      },
      token,
      this.longRequestTimeouts.model,
    );
  }

  getModelSettings(token: string): Promise<PublicModelSettings> {
    return this.request("/settings/model", {}, token);
  }

  updateModelSettings(
    token: string,
    input: { base_url: string; model: string; api_key: string; temperature: number },
  ): Promise<PublicModelSettings> {
    return this.request(
      "/settings/model",
      { method: "PUT", body: JSON.stringify(input) },
      token,
    );
  }
}

export const api = new ApiClient();
