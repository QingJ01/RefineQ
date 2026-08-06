export type Locale = "zh" | "en";

export interface User {
  id: string;
  email: string;
  display_name: string;
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
}

export interface StudySession {
  id: string;
  topic_id: string;
  planned_at: string;
  minutes: number;
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
  mode?: "ai" | "fallback";
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
  grading_mode: "ai" | "fallback";
  replayed: boolean;
}

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
  filename: string;
  content_type: string;
  size: number;
  status: string;
  chunk_count: number;
  content_sha256: string;
  indexed_at: string;
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
}

export interface PublicModelSettings {
  base_url: string;
  model: string;
  temperature: number;
  configured: boolean;
  api_key_hint: string;
}
