import type {
  AgentReply,
  AnswerResult,
  AuthResponse,
  LearningEvidence,
  LearningWorkspace,
  MaterialRecord,
  PracticeQuestion,
  Progress,
  Project,
  PublicModelSettings,
  StudyPlan,
  TopicSeed,
  User,
  WorkspaceRoute,
  WorkspaceSnapshot,
} from "./types";


type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

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

  constructor(
    private readonly baseUrl = "/api",
    fetcher: Fetcher = globalThis.fetch.bind(globalThis),
  ) {
    this.fetcher = fetcher;
  }

  private async request<T>(
    path: string,
    options: RequestInit = {},
    token: string | null = null,
  ): Promise<T> {
    const isForm = options.body instanceof FormData;
    const response = await this.fetcher(`${this.baseUrl}${path}`, {
      ...options,
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
    return response.json() as Promise<T>;
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

  createProject(token: string, name: string): Promise<Project> {
    return this.request(
      "/projects",
      { method: "POST", body: JSON.stringify({ name }) },
      token,
    );
  }

  listWorkspaces(token: string): Promise<LearningWorkspace[]> {
    return this.request("/workspaces", {}, token);
  }

  resolveWorkspace(token: string, intent: string): Promise<WorkspaceRoute> {
    return this.request(
      "/workspaces/resolve",
      { method: "POST", body: JSON.stringify({ intent }) },
      token,
    );
  }

  getWorkspaceSnapshot(token: string, workspaceId: string): Promise<WorkspaceSnapshot> {
    return this.request(`/workspaces/${workspaceId}/snapshot`, {}, token);
  }

  seedProject(
    token: string,
    projectId: string,
    input: {
      goal: string;
      exam_at: string;
      daily_minutes: number;
      topics: TopicSeed[];
    },
  ): Promise<Progress> {
    return this.request(
      `/projects/${projectId}/learning/seed`,
      { method: "POST", body: JSON.stringify(input) },
      token,
    );
  }

  createPlan(token: string, projectId: string): Promise<StudyPlan> {
    return this.request(
      `/projects/${projectId}/learning/plan`,
      { method: "POST" },
      token,
    );
  }

  getProgress(token: string, projectId: string): Promise<Progress> {
    return this.request(`/projects/${projectId}/learning/progress`, {}, token);
  }

  getQuestion(token: string, projectId: string): Promise<PracticeQuestion> {
    return this.request(`/projects/${projectId}/learning/question`, {}, token);
  }

  submitAnswer(
    token: string,
    projectId: string,
    questionId: string,
    answer: string,
  ): Promise<AnswerResult> {
    return this.request(
      `/projects/${projectId}/learning/answer`,
      {
        method: "POST",
        body: JSON.stringify({
          attempt_id: crypto.randomUUID().replaceAll("-", ""),
          question_id: questionId,
          answer,
        }),
      },
      token,
    );
  }

  getWorkspaceQuestion(token: string, workspaceId: string): Promise<PracticeQuestion> {
    return this.request(`/workspaces/${workspaceId}/learning/question`, {}, token);
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
    );
  }

  getEvidence(token: string, projectId: string): Promise<LearningEvidence[]> {
    return this.request(`/projects/${projectId}/learning/evidence`, {}, token);
  }

  uploadMaterials(
    token: string,
    projectId: string,
    files: File[],
  ): Promise<MaterialRecord[]> {
    const body = new FormData();
    files.forEach((file) => body.append("files", file));
    return this.request(
      `/projects/${projectId}/materials`,
      { method: "POST", body },
      token,
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
    );
  }

  chat(
    token: string,
    projectId: string,
    message: string,
    sessionId?: string,
  ): Promise<AgentReply> {
    return this.request(
      `/projects/${projectId}/agent/chat`,
      {
        method: "POST",
        body: JSON.stringify({ message, session_id: sessionId }),
      },
      token,
    );
  }

  chatWorkspace(
    token: string,
    workspaceId: string,
    message: string,
    sessionId?: string,
  ): Promise<AgentReply> {
    return this.request(
      `/workspaces/${workspaceId}/agent/chat`,
      {
        method: "POST",
        body: JSON.stringify({ message, session_id: sessionId }),
      },
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
}

export const api = new ApiClient();
