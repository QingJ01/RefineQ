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

export interface LearningWorkspace {
  id: string;
  title: string;
  subject: string;
  goal: string;
  topics: string[];
  keywords: string[];
  routing_summary: string;
  archived: boolean;
  created_at: string;
  last_active_at: string;
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

export interface Progress {
  goal: string;
  mastery: Record<string, number>;
  topics: Record<string, string>;
  diagnostic_count: number;
  attempt_count: number;
  plan_id: string | null;
}

export interface PracticeQuestion {
  id: string;
  topic_id: string;
  prompt: string;
  difficulty_level?: number;
  citations?: string[];
  sources?: SearchSource[];
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
  grading_mode: "ai" | "fallback";
  mastery_updated: boolean;
  next_review_at?: string | null;
  replayed: boolean;
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
  content_type: string;
  size: number;
  status: string;
  chunk_count: number;
  content_sha256: string;
  indexed_at: string;
}

export type MaterialType =
  | "textbook"
  | "lecture_notes"
  | "exam"
  | "problem_set"
  | "mixed"
  | "unknown";

export interface MaterialSectionAnalysis {
  title: string;
  topics: string[];
  citation_ids: string[];
}

export interface MaterialAnalysis {
  material_id: string;
  filename: string;
  material_type: MaterialType;
  title: string;
  summary: string;
  sections: MaterialSectionAnalysis[];
  topics: string[];
  confidence: number;
  mode: "ai" | "fallback";
  analyzed_at: string;
}

export interface TargetedPlanInput {
  material_id: string;
  focus_topics: string[];
  exam_at: string;
  daily_minutes: number;
  study_weekdays: number[];
  preferred_hour: number;
  timezone_offset_minutes: number;
  routine_notes: string;
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
