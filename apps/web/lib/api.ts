import type {
  AgentReply,
  AgentSessionContext,
  AgentSessionDetail,
  AgentSessionSummary,
  AdminOverview,
  AnswerResult,
  AttemptFeedbackInput,
  AttemptFeedbackResponse,
  AuthResponse,
  LearningWorkspace,
  LearningInsights,
  IntegrationKind,
  IntegrationTestResult,
  IntegrationUpdateInput,
  MaterialRecord,
  PasswordResetAccepted,
  PlanUpdateInput,
  PracticeRequest,
  PracticeQuestion,
  PublicIntegrationSettings,
  PublicModelSettings,
  SearchSource,
  SavedPracticeQuestion,
  StudyPlan,
  StudySession,
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
  upload: 240_000,
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
      if (response.status === 204) return undefined as T;
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

  requestPasswordReset(email: string): Promise<PasswordResetAccepted> {
    return this.request("/auth/password-reset/request", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
  }

  completePasswordReset(token: string, password: string): Promise<void> {
    return this.request("/auth/password-reset/complete", {
      method: "POST",
      body: JSON.stringify({ token, password }),
    });
  }

  getProfile(token: string): Promise<User> {
    return this.request("/auth/me", {}, token);
  }

  listWorkspaces(token: string, includeArchived = false): Promise<LearningWorkspace[]> {
    const query = includeArchived ? "?include_archived=true" : "";
    return this.request(`/workspaces${query}`, {}, token);
  }

  updateWorkspace(
    token: string,
    workspaceId: string,
    input: { title?: string; goal?: string; archived?: boolean },
  ): Promise<LearningWorkspace> {
    return this.request(
      `/workspaces/${workspaceId}`,
      { method: "PATCH", body: JSON.stringify(input) },
      token,
    );
  }

  deleteWorkspace(token: string, workspaceId: string): Promise<void> {
    return this.request(`/workspaces/${workspaceId}`, { method: "DELETE" }, token);
  }

  resolveWorkspace(token: string, intent: string, signal?: AbortSignal): Promise<WorkspaceRoute> {
    return this.request(
      "/workspaces/resolve",
      { method: "POST", body: JSON.stringify({ intent }), signal },
      token,
      this.longRequestTimeouts.model,
    );
  }

  getWorkspaceSnapshot(token: string, workspaceId: string): Promise<WorkspaceSnapshot> {
    return this.request(`/workspaces/${workspaceId}/snapshot`, {}, token);
  }

  getWorkspaceQuestion(
    token: string,
    workspaceId: string,
    signal?: AbortSignal,
  ): Promise<PracticeQuestion> {
    return this.request(
      `/workspaces/${workspaceId}/learning/question`,
      { signal },
      token,
    );
  }

  createWorkspaceQuestion(
    token: string,
    workspaceId: string,
    options: PracticeRequest = {},
    signal?: AbortSignal,
  ): Promise<PracticeQuestion> {
    return this.request(
      `/workspaces/${workspaceId}/learning/question`,
      {
        method: "POST",
        signal,
        body: JSON.stringify({
          request_id: options.requestId ?? crypto.randomUUID().replaceAll("-", ""),
          topic_id: options.topicId,
          difficulty: options.difficulty,
          mode: options.learningMode ?? "concept",
          replace: options.replace ?? false,
          review_session_id: options.reviewSessionId,
        }),
      },
      token,
      this.longRequestTimeouts.model,
    );
  }

  setWorkspaceQuestionSaved(
    token: string,
    workspaceId: string,
    questionId: string,
    saved: boolean,
  ): Promise<SavedPracticeQuestion> {
    return this.request(
      `/workspaces/${workspaceId}/learning/questions/${questionId}/saved`,
      { method: "PUT", body: JSON.stringify({ saved }) },
      token,
    );
  }

  listWorkspaceSavedQuestions(
    token: string,
    workspaceId: string,
  ): Promise<SavedPracticeQuestion[]> {
    return this.request(
      `/workspaces/${workspaceId}/learning/questions/saved`,
      {},
      token,
    );
  }

  submitWorkspaceAnswer(
    token: string,
    workspaceId: string,
    questionId: string,
    answer: string,
    attemptId?: string,
    signal?: AbortSignal,
  ): Promise<AnswerResult> {
    return this.request(
      `/workspaces/${workspaceId}/learning/answer`,
      {
        method: "POST",
        signal,
        body: JSON.stringify({
          attempt_id: attemptId ?? crypto.randomUUID().replaceAll("-", ""),
          question_id: questionId,
          answer,
        }),
      },
      token,
      this.longRequestTimeouts.model,
    );
  }

  updateWorkspacePlanSession(
    token: string,
    workspaceId: string,
    sessionId: string,
    input: { status?: "planned" | "completed"; planned_at?: string },
  ): Promise<StudySession> {
    return this.request<StudySession>(
      `/workspaces/${workspaceId}/learning/plan/sessions/${sessionId}`,
      { method: "PATCH", body: JSON.stringify(input) },
      token,
    );
  }

  updateWorkspacePlan(
    token: string,
    workspaceId: string,
    input: PlanUpdateInput,
  ): Promise<StudyPlan> {
    return this.request<StudyPlan>(
      `/workspaces/${workspaceId}/learning/plan`,
      { method: "PUT", body: JSON.stringify(input) },
      token,
    );
  }

  getWorkspaceInsights(token: string, workspaceId: string): Promise<LearningInsights> {
    return this.request(`/workspaces/${workspaceId}/learning/insights`, {}, token);
  }

  retryWorkspaceQuestion(
    token: string,
    workspaceId: string,
    questionId: string,
  ): Promise<PracticeQuestion> {
    return this.request(
      `/workspaces/${workspaceId}/learning/questions/${questionId}/retry`,
      { method: "POST" },
      token,
    );
  }

  updateWorkspaceAttemptFeedback(
    token: string,
    workspaceId: string,
    attemptId: string,
    input: AttemptFeedbackInput,
  ): Promise<AttemptFeedbackResponse> {
    return this.request(
      `/workspaces/${workspaceId}/learning/attempts/${attemptId}/feedback`,
      { method: "PATCH", body: JSON.stringify(input) },
      token,
    );
  }

  uploadWorkspaceMaterials(
    token: string,
    workspaceId: string,
    files: File[],
    signal?: AbortSignal,
  ): Promise<MaterialRecord[]> {
    const body = new FormData();
    files.forEach((file) => body.append("files", file));
    return this.request(
      `/workspaces/${workspaceId}/materials`,
      { method: "POST", body, signal },
      token,
      this.longRequestTimeouts.upload,
    );
  }

  listWorkspaceMaterials(token: string, workspaceId: string): Promise<MaterialRecord[]> {
    return this.request(`/workspaces/${workspaceId}/materials`, {}, token);
  }

  searchWorkspaceMaterials(token: string, workspaceId: string, query: string): Promise<SearchSource[]> {
    return this.request<SearchSource[]>(
      `/workspaces/${workspaceId}/materials/search?q=${encodeURIComponent(query)}`,
      {},
      token,
    );
  }

  deleteWorkspaceMaterial(
    token: string,
    workspaceId: string,
    materialId: string,
  ): Promise<void> {
    return this.request(
      `/workspaces/${workspaceId}/materials/${materialId}`,
      { method: "DELETE" },
      token,
    );
  }

  async downloadWorkspaceMaterial(
    token: string,
    workspaceId: string,
    materialId: string,
  ): Promise<Blob> {
    const response = await this.fetcher(
      `${this.baseUrl}/workspaces/${workspaceId}/materials/${materialId}/download`,
      { headers: authHeaders(token) },
    );
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new ApiError(
        response.status,
        body?.error?.code ?? "request_error",
        body?.error?.message ?? `Request failed (${response.status})`,
      );
    }
    return response.blob();
  }

  chatWorkspace(
    token: string,
    workspaceId: string,
    message: string,
    sessionId?: string,
    turnId?: string,
    signal?: AbortSignal,
    sessionContext?: AgentSessionContext,
  ): Promise<AgentReply> {
    return this.request(
      `/workspaces/${workspaceId}/agent/chat`,
      {
        method: "POST",
        body: JSON.stringify({
          message,
          session_id: sessionId,
          turn_id: turnId,
          session_context: sessionContext,
        }),
        signal,
      },
      token,
      this.longRequestTimeouts.model,
    );
  }

  listWorkspaceAgentSessions(
    token: string,
    workspaceId: string,
  ): Promise<AgentSessionSummary[]> {
    return this.request(`/workspaces/${workspaceId}/agent/sessions`, {}, token);
  }

  getWorkspaceAgentSession(
    token: string,
    workspaceId: string,
    sessionId: string,
  ): Promise<AgentSessionDetail> {
    return this.request(
      `/workspaces/${workspaceId}/agent/sessions/${sessionId}`,
      {},
      token,
    );
  }

  deleteWorkspaceAgentSession(
    token: string,
    workspaceId: string,
    sessionId: string,
  ): Promise<void> {
    return this.request(
      `/workspaces/${workspaceId}/agent/sessions/${sessionId}`,
      { method: "DELETE" },
      token,
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

  getAdminOverview(token: string): Promise<AdminOverview> {
    return this.request("/admin/overview", {}, token);
  }

  listIntegrations(token: string): Promise<PublicIntegrationSettings[]> {
    return this.request("/admin/integrations", {}, token);
  }

  updateIntegration(
    token: string,
    kind: IntegrationKind,
    input: IntegrationUpdateInput,
  ): Promise<PublicIntegrationSettings> {
    return this.request(
      `/admin/integrations/${kind}`,
      { method: "PUT", body: JSON.stringify(input) },
      token,
    );
  }

  testIntegration(
    token: string,
    kind: IntegrationKind,
  ): Promise<IntegrationTestResult> {
    return this.request(
      `/admin/integrations/${kind}/test`,
      { method: "POST" },
      token,
      this.longRequestTimeouts.model,
    );
  }
}

export const api = new ApiClient();
