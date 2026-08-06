import type { AnswerResult, EvidenceKind, StudyPlan } from "./types";


export interface PlanRow {
  id: string;
  sequence: number;
  topic: string;
  dateLabel: string;
  minutesLabel: string;
}

export function buildPlanRows(plan: StudyPlan, locale: string): PlanRow[] {
  return plan.sessions.map((session, index) => ({
    id: session.id,
    sequence: index + 1,
    topic: session.topic_id,
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
