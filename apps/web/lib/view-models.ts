import type {
  AnswerResult,
  EvidenceKind,
  IntegrationTestResult,
  PublicIntegrationSettings,
  StudyPlan,
} from "./types";


export interface PlanRow {
  id: string;
  sequence: number;
  topic: string;
  dateLabel: string;
  minutesLabel: string;
}

export function buildPlanRows(
  plan: StudyPlan,
  locale: string,
  topicLabels: Record<string, string> = {},
): PlanRow[] {
  return plan.sessions.map((session, index) => ({
    id: session.id,
    sequence: index + 1,
    topic: topicLabels[session.topic_id]
      ?? (locale.toLowerCase().startsWith("zh") ? "未命名主题" : "Untitled topic"),
    dateLabel: new Intl.DateTimeFormat(locale, {
      month: "short",
      day: "numeric",
    }).format(new Date(session.planned_at)),
    minutesLabel: `${session.minutes} min`,
  }));
}

export type PracticeStatus = "mastered" | "revise" | "replayed";

export function practiceStatus(
  result: Pick<AnswerResult, "is_correct" | "replayed">,
): PracticeStatus {
  if (result.replayed) return "replayed";
  return result.is_correct ? "mastered" : "revise";
}

export type EvidenceTone = "jade" | "amber" | "ink";

export function evidenceTone(kind: EvidenceKind): EvidenceTone {
  if (kind === "attempt" || kind === "review") return "jade";
  if (kind === "diagnostic" || kind === "self_explanation") return "amber";
  return "ink";
}

export function projectIntegrationTestResult(
  setting: PublicIntegrationSettings,
  result: IntegrationTestResult,
  testedAt: string,
): PublicIntegrationSettings {
  return {
    ...setting,
    last_test_status: result.status,
    last_test_message: result.message,
    last_tested_at: testedAt,
  };
}
