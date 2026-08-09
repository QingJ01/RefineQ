export type Locale = "zh" | "en";
export type LearningMode = "concept" | "case" | "project" | "exam";

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: "learner" | "admin";
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: "bearer";
  user: User;
}

export interface AccountExport {
  exported_at: string;
  user: User;
  records: Array<Record<string, unknown>>;
  materials: Array<Record<string, unknown>>;
}

export interface LearningWorkspace {
  id: string;
  title: string;
  subject: string;
  goal: string;
  original_goal?: string;
  topics: string[];
  keywords: string[];
  routing_summary: string;
  archived: boolean;
  created_at: string;
  last_active_at: string;
}

export interface CalendarTask {
  id: string;
  workspace_id: string;
  workspace_title: string;
  workspace_archived: boolean;
  topic_id: string;
  topic_label: string;
  planned_at: string;
  minutes: number;
  activity: "learn" | "practice" | "apply" | "review";
  status: "planned" | "completed";
}

export interface CalendarResponse {
  starts_at: string;
  ends_at: string;
  tasks: CalendarTask[];
}

export interface WorkspaceRoute {
  action: "created" | "switched" | "reused";
  confidence: number;
  reason: string;
  workspace: LearningWorkspace;
}

export interface WorkspaceSnapshot {
  workspace: LearningWorkspace;
  progress: Progress;
  plan: StudyPlan | null;
  evidence: LearningEvidence[];
  materials: MaterialRecord[];
  saved_questions?: SavedPracticeQuestion[];
  active_question?: PracticeQuestion | null;
  last_answer?: AnswerResult | null;
  topic_suggestions?: TopicSuggestion[];
  next_action: NextAction;
}

export interface NextActionAlternative {
  action_type: "open_materials" | "view_plan" | "start_practice";
  target_id: string | null;
}

export interface NextAction {
  id: string;
  workspace_id: string;
  version: number;
  expires_at: string;
  action_type: "upload_material" | "start_review" | "start_session" | "repair_pace" | "start_practice";
  trigger: "material_missing" | "due_review" | "scheduled_session" | "pace_risk" | "weak_topic";
  reason_code: string;
  reason: string;
  preconditions: Record<string, boolean>;
  evidence_refs: string[];
  expected_outcome: string;
  target_id: string | null;
  topic_id: string | null;
  minutes: number | null;
  alternatives: NextActionAlternative[];
  risk_level: "low" | "medium" | "high";
  approval_mode: "advise" | "confirm" | "auto_safe";
}

export interface JourneyEvent {
  id: string;
  workspace_id: string;
  name: "intent_submitted" | "workspace_ready" | "workspace_opened" | "material_searchable" | "question_started" | "grounded_grade_created" | "grounded_grade_shown";
  occurred_at: string;
  ref_id: string | null;
}

export interface TopicSuggestion {
  id: string;
  name: string;
  source_material_ids: string[];
}

export interface StudySession {
  id: string;
  topic_id: string;
  planned_at: string;
  minutes: number;
  activity?: "learn" | "practice" | "apply" | "review";
  status?: "planned" | "completed";
}

export interface StudyPlan {
  id: string;
  goal: string;
  exam_at: string;
  daily_minutes: number;
  sessions: StudySession[];
}

export interface PlanUpdateInput {
  goal: string;
  exam_at: string;
  daily_minutes: number;
  topic_order: string[];
  regenerate: boolean;
}

export interface Progress {
  goal: string;
  mastery: Record<string, number>;
  stable?: Record<string, boolean>;
  topics: Record<string, string>;
  topic_order: string[];
  diagnostic_count: number;
  attempt_count: number;
  plan_id: string | null;
}

export interface DiagnosticResultInput {
  topic_id: string;
  is_correct: boolean;
}

export interface PracticeQuestion {
  id: string;
  topic_id: string;
  prompt: string;
  explanation?: string | null;
  difficulty_level?: number;
  citations?: string[];
  sources?: SearchSource[];
  grounding?: "material" | "general";
  learning_mode?: LearningMode;
  mode?: "ai" | "fallback";
  saved?: boolean;
}

export interface SavedPracticeQuestion extends PracticeQuestion {
  saved: boolean;
  saved_at: string | null;
}

export interface PracticeRequest {
  requestId?: string;
  topicId?: string;
  learningMode?: LearningMode;
  difficulty?: number;
  replace?: boolean;
  reviewSessionId?: string;
  planSessionId?: string;
}

export interface AnswerResult {
  attempt_id: string;
  question_id: string;
  topic_id: string;
  is_correct: boolean;
  mastery: number;
  difficulty_level: number;
  evidence_id: string;
  score: number;
  feedback: string;
  strengths: string[];
  gaps: string[];
  misconceptions: string[];
  citations: string[];
  sources?: SearchSource[];
  grounding?: "material" | "general";
  grading_mode: "ai" | "fallback";
  mastery_updated: boolean;
  next_review_at?: string | null;
  completed_review_session_id?: string | null;
  completed_plan_session_id?: string | null;
  answer?: string;
  observed_at?: string | null;
  learner_note?: string | null;
  appealed?: boolean;
  replayed: boolean;
}

export interface MasteryHistoryPoint {
  attempt_id: string;
  topic_id: string;
  mastery: number;
  observed_at: string;
}

export interface TopicInsight {
  topic_id: string;
  topic_name: string;
  mastery: number;
  attempt_count: number;
  error_count: number;
  last_practiced_at: string | null;
}

export interface DueReviewInsight {
  session_id: string;
  topic_id: string;
  topic_name: string;
  due_at: string;
  minutes: number;
  overdue: boolean;
}

export interface AttemptInsight {
  attempt_id: string;
  question_id: string;
  topic_id: string;
  topic_name: string;
  question_prompt: string;
  answer: string;
  is_correct: boolean;
  mastery: number;
  score: number;
  feedback: string;
  strengths: string[];
  gaps: string[];
  misconceptions: string[];
  citations: string[];
  sources: SearchSource[];
  grounding: "material" | "general";
  grading_mode: string;
  mastery_updated: boolean;
  observed_at: string;
  learner_note: string | null;
  appealed: boolean;
}

export interface LearningInsights {
  workspace_id: string;
  mastery_history: MasteryHistoryPoint[];
  topics: TopicInsight[];
  due_reviews: DueReviewInsight[];
  attempts: AttemptInsight[];
}

export interface AttemptFeedbackInput {
  learner_note?: string | null;
  appealed?: boolean;
}

export interface AttemptFeedbackResponse {
  attempt_id: string;
  learner_note: string | null;
  appealed: boolean;
}

export interface AgentSessionContext {
  learning_mode: LearningMode;
  stage: "learn" | "practice" | "reflect";
  question?: string;
  draft?: string;
  feedback?: string;
  timezone?: string;
}

export interface AdjustPracticeProposal {
  type: "adjust_practice";
  action_id: string;
  topic_id: string;
  topic_name: string;
  difficulty: number;
  learning_mode: LearningMode;
  destructive: boolean;
}

export interface UpdatePlanSessionProposal {
  type: "update_plan_session";
  action_id: string;
  session_id: string;
  session_label: string;
  status: "planned" | "completed" | null;
  planned_at: string | null;
}

export interface SaveQuestionProposal {
  type: "save_question";
  action_id: string;
  question_id: string;
  saved: boolean;
}

export interface RejectedActionProposal {
  type: "rejected";
  reason_code: string;
  summary: string;
  candidates: string[];
}

export type ExecutableActionProposal =
  | AdjustPracticeProposal
  | UpdatePlanSessionProposal
  | SaveQuestionProposal;

export type CoachActionProposal = ExecutableActionProposal | RejectedActionProposal;

export type EvidenceKind =
  | "attempt"
  | "diagnostic"
  | "review"
  | "self_explanation"
  | "material";

export interface LearningEvidence {
  id: string;
  kind: EvidenceKind;
  source_id: string;
  summary: string;
  observed_at: string;
  details: Record<string, unknown>;
}

export interface MaterialRecord {
  id: string;
  project_id?: string;
  filename: string;
  title?: string;
  tags?: string[];
  content_type: string;
  size: number;
  status: string;
  chunk_count: number;
  content_sha256: string;
  indexed_at: string;
}

export interface MaterialUpdateInput {
  title?: string;
  tags?: string[];
}

export interface SearchSource {
  citation_id: string;
  material_id: string;
  filename: string;
  chunk_index: number;
  text: string;
  score: number;
}

export interface AgentReply {
  session_id: string;
  message: string;
  citations: string[];
  sources: SearchSource[];
  action_proposal?: CoachActionProposal | null;
}

export interface AgentMessage {
  role: "user" | "assistant";
  content: string;
  citations: string[];
  sources?: SearchSource[];
}

export interface AgentSessionSummary {
  id: string;
  workspace_id: string;
  preview: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface AgentSessionDetail extends AgentSessionSummary {
  messages: AgentMessage[];
}

export interface PasswordResetAccepted {
  accepted: boolean;
  reset_token?: string | null;
}

export interface AuthCapabilities {
  password_reset_available: boolean;
}

export interface PublicModelSettings {
  base_url: string;
  model: string;
  temperature: number;
  configured: boolean;
  api_key_hint: string;
}

export type IntegrationKind = "chat" | "embedding" | "ocr" | "object_storage";

export interface PublicIntegrationSettings {
  kind: IntegrationKind;
  enabled: boolean;
  configured: boolean;
  config: Record<string, string | number | boolean>;
  secret_hints: Record<string, string>;
  last_test_status: "ok" | "failed" | null;
  last_test_message: string | null;
  last_tested_at: string | null;
}

export interface IntegrationUpdateInput {
  enabled: boolean;
  config: Record<string, string | number | boolean>;
  secrets: Record<string, string>;
}

export interface IntegrationTestResult {
  kind: IntegrationKind;
  status: "ok" | "failed";
  message: string;
}

export interface AdminOverview {
  database: "postgresql" | "sqlite";
  pgvector: boolean;
  users: number;
  integrations_configured: number;
}

export interface AdminQuotaValues {
  materials: number;
  material_bytes: number;
  workspaces: number;
}

export interface AdminUserSummary extends User {
  usage: AdminQuotaValues;
  quotas: AdminQuotaValues;
}

export interface AdminUsersPage {
  items: AdminUserSummary[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface AdminJobSummary {
  id: "material_index" | "embedding_backfill";
  status: "idle" | "pending";
  pending: number;
  completed: number;
  failed: number;
  total: number;
  last_activity_at: string | null;
}

export interface AdminJobsResponse {
  items: AdminJobSummary[];
  observed_at: string;
}

export interface DurationPercentiles {
  sample_size: number;
  p50: number | null;
  p90: number | null;
}

export interface LearningMetricsResponse {
  starts_at: string;
  ends_at: string;
  weekly_active_learners: number;
  grounded_loop_completers: number;
  grounded_loop_completion_rate: number;
  intent_to_grounded_grade_seconds: DurationPercentiles;
  revisit_open_to_question_seconds: DurationPercentiles;
}

export interface AdminAuditEntry {
  id: number;
  actor_id: string;
  actor_email: string;
  action: string;
  target: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface AdminAuditPage {
  items: AdminAuditEntry[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface ManagedBackup {
  id: string;
  created_at: string;
  size: number;
  file_count: number;
  total_bytes: number;
}

export interface ManagedBackupsResponse {
  items: ManagedBackup[];
  total: number;
}

export interface RestoreValidationResponse extends ManagedBackup {
  status: "validated";
}
