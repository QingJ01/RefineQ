import type {
  AccountExport,
  AgentReply,
  AgentSessionContext,
  AgentSessionDetail,
  AgentSessionSummary,
  AdminOverview,
  AdminAuditPage,
  AdminJobsResponse,
  AdminUsersPage,
  AnswerResult,
  AttemptFeedbackInput,
  AttemptFeedbackResponse,
  AuthCapabilities,
  AuthResponse,
  CalendarResponse,
  HomeActionReceipt,
  HomeDispatchResult,
  HomeWorkspaceProposal,
  LearningWorkspace,
  LearningInsights,
  IntegrationKind,
  IntegrationTestResult,
  IntegrationUpdateInput,
  MaterialAnalysis,
  JourneyEvent,
  LearningMetricsResponse,
  MaterialRecord,
  NextAction,
  MaterialUpdateInput,
  ManagedBackup,
  ManagedBackupsResponse,
  PasswordResetAccepted,
  PlanUpdateInput,
  PracticeRequest,
  PracticeQuestion,
  Progress,
  PublicIntegrationSettings,
  PublicModelSettings,
  SearchSource,
  SavedPracticeQuestion,
  RestoreValidationResponse,
  StudyPlan,
  StudySession,
  TargetedPlanInput,
  TopicSuggestion,
  User,
  WorkspaceRoute,
  WorkspaceSnapshot,
} from "./types";


type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type UnauthorizedListener = (token: string) => void;

const unauthorizedListeners = new Set<UnauthorizedListener>();

export function subscribeUnauthorized(listener: UnauthorizedListener): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

function broadcastUnauthorized(token: string): void {
  unauthorizedListeners.forEach((listener) => {
    try {
      listener(token);
    } catch {
      // Session reset listeners must not mask the original API error.
    }
  });
}

interface LongRequestTimeouts {
  model: number;
  upload: number;
}

const DEFAULT_LONG_REQUEST_TIMEOUTS: LongRequestTimeouts = {
  model: 120_000,
  upload: 240_000,
};

const MATERIAL_ANALYSIS_RECOVERY_ATTEMPTS = 30;
const MATERIAL_ANALYSIS_RECOVERY_INTERVAL_MS = 1_500;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly detail?: Record<string, unknown>,
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
  private readonly profileCache = new Map<string, { expiresAt: number; value: Promise<User> }>();
  private readonly workspaceCache = new Map<string, {
    expiresAt: number;
    value: Promise<LearningWorkspace[]>;
  }>();
  private readonly readCacheTtlMs = 5_000;

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
      clearTimeout(timeout);
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        if (response.status === 401 && token) {
          this.clearReadCache(token);
          broadcastUnauthorized(token);
        }
        throw new ApiError(
          response.status,
          body?.error?.code ?? "request_error",
          body?.error?.message ?? `Request failed (${response.status})`,
          body?.error?.detail,
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

  private cached<T>(
    cache: Map<string, { expiresAt: number; value: Promise<T> }>,
    key: string,
    load: () => Promise<T>,
  ): Promise<T> {
    const current = cache.get(key);
    const now = Date.now();
    if (current && current.expiresAt > now) return current.value;
    const value = load().catch((caught) => {
      if (cache.get(key)?.value === value) cache.delete(key);
      throw caught;
    });
    cache.set(key, { expiresAt: now + this.readCacheTtlMs, value });
    return value;
  }

  clearReadCache(token?: string): void {
    if (!token) {
      this.profileCache.clear();
      this.workspaceCache.clear();
      return;
    }
    this.profileCache.delete(token);
    this.clearWorkspaceReadCache(token);
  }

  private clearWorkspaceReadCache(token: string): void {
    for (const key of this.workspaceCache.keys()) {
      if (key.startsWith(`${token}:`)) this.workspaceCache.delete(key);
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

  getAuthCapabilities(): Promise<AuthCapabilities> {
    return this.request("/auth/capabilities");
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
    return this.cached(this.profileCache, token, () => this.request("/auth/me", {}, token));
  }

  updateProfile(token: string, displayName: string): Promise<User> {
    return this.request<User>(
      "/auth/profile",
      { method: "PATCH", body: JSON.stringify({ display_name: displayName }) },
      token,
    ).then((user) => {
      this.profileCache.delete(token);
      return user;
    });
  }

  changePassword(token: string, currentPassword: string, newPassword: string): Promise<void> {
    return this.request(
      "/auth/password",
      {
        method: "PUT",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      },
      token,
    );
  }

  exportAccount(token: string): Promise<AccountExport> {
    return this.request("/auth/export", {}, token);
  }

  revokeSessions(token: string): Promise<void> {
    return this.request("/auth/sessions", { method: "DELETE" }, token);
  }

  deleteAccount(
    token: string,
    currentPassword: string,
    confirmation: string,
  ): Promise<void> {
    return this.request(
      "/auth/account",
      {
        method: "DELETE",
        body: JSON.stringify({
          current_password: currentPassword,
          confirmation,
        }),
      },
      token,
    );
  }

  listWorkspaces(token: string, includeArchived = false): Promise<LearningWorkspace[]> {
    const query = includeArchived ? "?include_archived=true" : "";
    const key = `${token}:${includeArchived ? "archived" : "active"}`;
    return this.cached(
      this.workspaceCache,
      key,
      () => this.request(`/workspaces${query}`, {}, token),
    );
  }

  getCalendar(
    token: string,
    startsAt: string,
    endsAt: string,
    includeArchived = false,
  ): Promise<CalendarResponse> {
    const query = new URLSearchParams({ starts_at: startsAt, ends_at: endsAt });
    if (includeArchived) query.set("include_archived", "true");
    return this.request(`/calendar?${query.toString()}`, {}, token);
  }

  updateWorkspace(
    token: string,
    workspaceId: string,
    input: { title?: string; goal?: string; archived?: boolean },
  ): Promise<LearningWorkspace> {
    return this.request<LearningWorkspace>(
      `/workspaces/${workspaceId}`,
      { method: "PATCH", body: JSON.stringify(input) },
      token,
    ).then((workspace) => {
      this.clearWorkspaceReadCache(token);
      return workspace;
    });
  }

  deleteWorkspace(token: string, workspaceId: string): Promise<void> {
    return this.request<void>(`/workspaces/${workspaceId}`, { method: "DELETE" }, token)
      .then(() => {
        this.clearWorkspaceReadCache(token);
      });
  }

  resolveWorkspace(token: string, intent: string, signal?: AbortSignal): Promise<WorkspaceRoute> {
    return this.request<WorkspaceRoute>(
      "/workspaces/resolve",
      {
        method: "POST",
        body: JSON.stringify({
          intent,
          timezone_offset_minutes: -new Date().getTimezoneOffset(),
        }),
        signal,
      },
      token,
      this.longRequestTimeouts.model,
    ).then((route) => {
      this.clearWorkspaceReadCache(token);
      return route;
    });
  }

  dispatchHome(
    token: string,
    input: {
      request_id: string;
      text: string;
      timezone_offset_minutes: number;
      clarification?: { continuation_token: string; option_id: string } | null;
    },
    signal?: AbortSignal,
  ): Promise<HomeDispatchResult> {
    return this.request<HomeDispatchResult>(
      "/home/dispatch",
      { method: "POST", body: JSON.stringify(input), signal },
      token,
      20_000,
    ).then((result) => {
      if (
        result.kind === "open_workspace"
        && result.workspace_target.route_action === "created"
      ) this.clearWorkspaceReadCache(token);
      return result;
    });
  }

  confirmHomeAction(
    token: string,
    input: {
      request_id: string;
      confirmation_token: string;
      proposal: Record<string, unknown>;
      idempotency_key: string;
    },
  ): Promise<HomeActionReceipt> {
    return this.request<HomeActionReceipt>(
      "/home/actions/confirm",
      { method: "POST", body: JSON.stringify(input) },
      token,
      30_000,
    ).then((receipt) => {
      if (receipt.operation === "create_workspace" && receipt.status === "succeeded") {
        this.clearWorkspaceReadCache(token);
      }
      return receipt;
    });
  }

  cancelHomeAction(token: string, requestId: string): Promise<void> {
    return this.request(
      "/home/actions/cancel",
      { method: "POST", body: JSON.stringify({ request_id: requestId }) },
      token,
    );
  }

  undoHomeCreation(
    token: string,
    input: { request_id: string; workspace_id: string; undo_token: string },
  ): Promise<HomeActionReceipt> {
    return this.request<HomeActionReceipt>(
      "/home/actions/undo",
      { method: "POST", body: JSON.stringify(input) },
      token,
      30_000,
    ).then((receipt) => {
      if (receipt.status === "succeeded") this.clearWorkspaceReadCache(token);
      return receipt;
    });
  }

  reviseHomeWorkspaceProposal(
    token: string,
    input: {
      request_id: string;
      confirmation_token: string;
      original_proposal: HomeWorkspaceProposal;
      changes: {
        title?: string;
        goal?: string;
        exam_at?: string;
        daily_minutes?: number;
      };
    },
  ): Promise<HomeWorkspaceProposal> {
    return this.request(
      "/home/actions/revise",
      { method: "POST", body: JSON.stringify(input) },
      token,
      30_000,
    );
  }

  getWorkspaceSnapshot(
    token: string,
    workspaceId: string,
    timezoneOffsetMinutes = -new Date().getTimezoneOffset(),
  ): Promise<WorkspaceSnapshot> {
    return this.request(
      `/workspaces/${workspaceId}/snapshot?timezone_offset_minutes=${timezoneOffsetMinutes}`,
      {},
      token,
    );
  }

  getWorkspaceNextAction(
    token: string,
    workspaceId: string,
    timezoneOffsetMinutes = -new Date().getTimezoneOffset(),
  ): Promise<NextAction> {
    return this.request(
      `/workspaces/${workspaceId}/next-action?timezone_offset_minutes=${timezoneOffsetMinutes}`,
      {},
      token,
    );
  }

  listWorkspaceTopicSuggestions(
    token: string,
    workspaceId: string,
  ): Promise<TopicSuggestion[]> {
    return this.request(`/workspaces/${workspaceId}/topic-suggestions`, {}, token);
  }

  acceptWorkspaceTopicSuggestion(
    token: string,
    workspaceId: string,
    suggestionId: string,
  ): Promise<WorkspaceSnapshot> {
    return this.request(
      `/workspaces/${workspaceId}/topic-suggestions/${suggestionId}/accept`,
      { method: "POST" },
      token,
    );
  }

  submitWorkspaceDiagnostic(
    token: string,
    workspaceId: string,
    results: Array<{ topic_id: string; is_correct: boolean }>,
  ): Promise<Progress> {
    return this.request(
      `/workspaces/${workspaceId}/learning/diagnostic`,
      {
        method: "POST",
        body: JSON.stringify({ diagnostic_id: "initial", results }),
      },
      token,
    );
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
          plan_session_id: options.planSessionId,
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
    options?: { promptHash?: string; signal?: AbortSignal },
  ): Promise<AnswerResult> {
    return this.request(
      `/workspaces/${workspaceId}/learning/answer`,
      {
        method: "POST",
        signal: options?.signal,
        body: JSON.stringify({
          attempt_id: attemptId ?? crypto.randomUUID().replaceAll("-", ""),
          question_id: questionId,
          answer,
          ...(options?.promptHash ? { prompt_hash: options.promptHash } : {}),
        }),
      },
      token,
      this.longRequestTimeouts.model,
    );
  }

  markWorkspaceGradeShown(
    token: string,
    workspaceId: string,
    attemptId: string,
  ): Promise<JourneyEvent> {
    return this.request(
      `/workspaces/${workspaceId}/learning/attempts/${attemptId}/shown`,
      { method: "POST" },
      token,
    );
  }

  updateWorkspacePlanSession(
    token: string,
    workspaceId: string,
    sessionId: string,
    input: { status?: "planned" | "completed"; planned_at?: string; minutes?: number },
  ): Promise<StudySession> {
    return this.request<StudySession>(
      `/workspaces/${workspaceId}/learning/plan/sessions/${sessionId}`,
      {
        method: "PATCH",
        body: JSON.stringify({
          ...input,
          timezone_offset_minutes: -new Date().getTimezoneOffset(),
        }),
      },
      token,
    );
  }

  addWorkspacePlanSession(
    token: string,
    workspaceId: string,
    input: { topic_name: string; planned_at: string; minutes: number; activity: string },
  ): Promise<StudySession> {
    return this.request<StudySession>(
      `/workspaces/${workspaceId}/learning/plan/sessions`,
      {
        method: "POST",
        body: JSON.stringify({
          ...input,
          timezone_offset_minutes: -new Date().getTimezoneOffset(),
        }),
      },
      token,
    );
  }

  clearWorkspacePlan(token: string, workspaceId: string): Promise<void> {
    return this.request<void>(
      `/workspaces/${workspaceId}/learning/plan`,
      { method: "DELETE" },
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
      {
        method: "PUT",
        body: JSON.stringify({
          ...input,
          timezone_offset_minutes: -new Date().getTimezoneOffset(),
        }),
      },
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

  uploadLibraryMaterials(token: string, files: File[], signal?: AbortSignal): Promise<MaterialRecord[]> {
    const body = new FormData();
    files.forEach((file) => body.append("files", file));
    return this.request(
      "/materials/library",
      { method: "POST", body, signal },
      token,
      this.longRequestTimeouts.upload,
    );
  }

  listLibraryMaterials(token: string): Promise<MaterialRecord[]> {
    return this.request("/materials/library", {}, token);
  }

  deleteLibraryMaterial(token: string, materialId: string): Promise<void> {
    return this.request(
      `/materials/library/${encodeURIComponent(materialId)}`,
      { method: "DELETE" },
      token,
    );
  }

  bulkDeleteLibraryMaterials(token: string, materialIds: string[]): Promise<void> {
    return this.request(
      "/materials/library",
      {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ material_ids: materialIds }),
      },
      token,
    );
  }

  attachLibraryMaterial(
    token: string,
    sourceScope: string,
    materialId: string,
    workspaceId: string,
  ): Promise<MaterialRecord> {
    return this.request(
      `/materials/library/${encodeURIComponent(sourceScope)}/${encodeURIComponent(materialId)}/attach/${encodeURIComponent(workspaceId)}`,
      { method: "POST" },
      token,
      this.longRequestTimeouts.upload,
    );
  }

  analyzeWorkspaceMaterial(
    token: string,
    workspaceId: string,
    materialId: string,
  ): Promise<MaterialAnalysis> {
    return this.request<MaterialAnalysis>(
      `/workspaces/${workspaceId}/materials/${materialId}/analysis`,
      { method: "POST" },
      token,
      this.longRequestTimeouts.model,
    );
  }

  getWorkspaceMaterialAnalysis(
    token: string,
    workspaceId: string,
    materialId: string,
  ): Promise<MaterialAnalysis> {
    return this.request<MaterialAnalysis>(
      `/workspaces/${workspaceId}/materials/${materialId}/analysis`,
      {},
      token,
    );
  }

  createTargetedPlan(
    token: string,
    workspaceId: string,
    input: TargetedPlanInput,
  ): Promise<StudyPlan> {
    // The endpoint is synchronous and commits even if this request times out, so
    // every call must carry an idempotency key that a retry can reuse to replay
    // the committed plan instead of forging a new one. Callers that manage their
    // own stable key (e.g. across an abort/retry) keep it; others get a fresh one.
    const body: TargetedPlanInput = {
      ...input,
      idempotency_key: input.idempotency_key ?? crypto.randomUUID().replaceAll("-", ""),
    };
    return this.request<StudyPlan>(
      `/workspaces/${workspaceId}/learning/plan/targeted`,
      { method: "POST", body: JSON.stringify(body) },
      token,
      this.longRequestTimeouts.model,
    );
  }

  async waitForWorkspaceMaterialAnalysis(
    token: string,
    workspaceId: string,
    materialId: string,
    notBefore?: string,
  ): Promise<MaterialAnalysis> {
    let lastError: unknown;
    for (let attempt = 0; attempt < MATERIAL_ANALYSIS_RECOVERY_ATTEMPTS; attempt += 1) {
      try {
        const analysis = await this.getWorkspaceMaterialAnalysis(token, workspaceId, materialId);
        if (!notBefore || Date.parse(analysis.analyzed_at) >= Date.parse(notBefore)) return analysis;
      } catch (caught) {
        lastError = caught;
        const recoverable = caught instanceof ApiError
          && (caught.status === 404 || caught.status >= 500);
        if (!recoverable || attempt === MATERIAL_ANALYSIS_RECOVERY_ATTEMPTS - 1) throw caught;
      }
      if (attempt === MATERIAL_ANALYSIS_RECOVERY_ATTEMPTS - 1) {
        throw lastError ?? new ApiError(
          408,
          "material_analysis_timeout",
          "Material analysis did not finish in time",
        );
      }
      await new Promise((resolve) => setTimeout(resolve, MATERIAL_ANALYSIS_RECOVERY_INTERVAL_MS));
    }
    throw lastError;
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

  updateWorkspaceMaterial(
    token: string,
    workspaceId: string,
    materialId: string,
    input: MaterialUpdateInput,
  ): Promise<MaterialRecord> {
    return this.request(
      `/workspaces/${workspaceId}/materials/${materialId}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      },
      token,
    );
  }

  bulkDeleteWorkspaceMaterials(
    token: string,
    workspaceId: string,
    materialIds: string[],
  ): Promise<void> {
    return this.request(
      `/workspaces/${workspaceId}/materials`,
      {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ material_ids: materialIds }),
      },
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

  listAdminUsers(token: string, page = 1, pageSize = 20): Promise<AdminUsersPage> {
    return this.request(`/admin/users?page=${page}&page_size=${pageSize}`, {}, token);
  }

  getAdminJobs(token: string): Promise<AdminJobsResponse> {
    return this.request("/admin/jobs", {}, token);
  }

  getAdminLearningMetrics(
    token: string,
    startsAt: string,
    endsAt: string,
  ): Promise<LearningMetricsResponse> {
    const query = new URLSearchParams({ starts_at: startsAt, ends_at: endsAt });
    return this.request(`/admin/metrics/learning?${query.toString()}`, {}, token);
  }

  listAdminAudit(token: string, page = 1, pageSize = 20): Promise<AdminAuditPage> {
    return this.request(`/admin/audit?page=${page}&page_size=${pageSize}`, {}, token);
  }

  listAdminBackups(token: string): Promise<ManagedBackupsResponse> {
    return this.request("/admin/backups", {}, token);
  }

  createAdminBackup(token: string): Promise<ManagedBackup> {
    return this.request("/admin/backups", { method: "POST" }, token);
  }

  validateAdminRestore(
    token: string,
    backupId: string,
  ): Promise<RestoreValidationResponse> {
    return this.request(
      `/admin/backups/${backupId}/restore-validation`,
      {
        method: "POST",
        body: JSON.stringify({ confirmation: `RESTORE ${backupId}` }),
      },
      token,
    );
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
