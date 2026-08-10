import type { LearningEvidence, LearningMode, Locale, StudySession } from "./types";


export type LearningSessionStage = "review" | "learn" | "practice" | "reflect";

export interface LearningSessionStep {
  id: "align" | "learn" | "practice" | "reflect";
  label: string;
  minutes: number;
}

const activityModes: Record<
  NonNullable<StudySession["activity"]>,
  LearningMode
> = {
  learn: "concept",
  practice: "case",
  apply: "project",
  review: "exam",
};

export function learningModeForActivity(
  activity: NonNullable<StudySession["activity"]>,
): LearningMode {
  return activityModes[activity];
}

const steps: Record<LearningMode, Record<Locale, LearningSessionStep[]>> = {
  concept: {
    zh: [
      { id: "align", label: "快速回顾", minutes: 5 },
      { id: "learn", label: "今天学习", minutes: 10 },
      { id: "practice", label: "练一练", minutes: 20 },
      { id: "reflect", label: "总结复盘", minutes: 10 },
    ],
    en: [
      { id: "align", label: "Quick review", minutes: 5 },
      { id: "learn", label: "Learn today", minutes: 10 },
      { id: "practice", label: "Practice", minutes: 20 },
      { id: "reflect", label: "Wrap up", minutes: 10 },
    ],
  },
  case: {
    zh: [
      { id: "align", label: "快速回顾", minutes: 5 },
      { id: "learn", label: "今天学习", minutes: 10 },
      { id: "practice", label: "练一练", minutes: 20 },
      { id: "reflect", label: "总结复盘", minutes: 10 },
    ],
    en: [
      { id: "align", label: "Quick review", minutes: 5 },
      { id: "learn", label: "Learn today", minutes: 10 },
      { id: "practice", label: "Practice", minutes: 20 },
      { id: "reflect", label: "Wrap up", minutes: 10 },
    ],
  },
  project: {
    zh: [
      { id: "align", label: "快速回顾", minutes: 5 },
      { id: "learn", label: "今天学习", minutes: 10 },
      { id: "practice", label: "练一练", minutes: 20 },
      { id: "reflect", label: "总结复盘", minutes: 10 },
    ],
    en: [
      { id: "align", label: "Quick review", minutes: 5 },
      { id: "learn", label: "Learn today", minutes: 10 },
      { id: "practice", label: "Practice", minutes: 20 },
      { id: "reflect", label: "Wrap up", minutes: 10 },
    ],
  },
  exam: {
    zh: [
      { id: "align", label: "快速回顾", minutes: 5 },
      { id: "learn", label: "今天学习", minutes: 10 },
      { id: "practice", label: "练一练", minutes: 20 },
      { id: "reflect", label: "总结复盘", minutes: 10 },
    ],
    en: [
      { id: "align", label: "Quick review", minutes: 5 },
      { id: "learn", label: "Learn today", minutes: 10 },
      { id: "practice", label: "Practice", minutes: 20 },
      { id: "reflect", label: "Review errors", minutes: 10 },
    ],
  },
};

export function summaryReserveMinutes(totalMinutes: number): number {
  const desired = totalMinutes <= 25 ? 4 : totalMinutes <= 60 ? 6 : totalMinutes <= 90 ? 8 : 10;
  return Math.min(desired, Math.max(1, Math.floor(totalMinutes) - 3));
}

export function buildSessionSteps(
  mode: LearningMode,
  locale: Locale,
  totalMinutes = 45,
  includeReview = true,
): LearningSessionStep[] {
  const labels = steps[mode][locale];
  const summary = summaryReserveMinutes(totalMinutes);
  const reviewAllocation = Math.max(1, Math.min(5, Math.round(totalMinutes * 0.1)));
  const review = includeReview ? reviewAllocation : 0;
  const requestedLearn = Math.max(1, Math.min(20, Math.round(totalMinutes * 0.2)))
    + (includeReview ? 0 : reviewAllocation);
  const learn = Math.min(requestedLearn, Math.max(1, totalMinutes - review - summary - 1));
  const practice = totalMinutes - review - learn - summary;
  const minutes = [review, learn, practice, summary];
  return labels.map((step, index) => ({ ...step, minutes: minutes[index] }));
}

export function selectYesterdayEvidence(
  evidence: readonly LearningEvidence[],
  now = new Date(),
): LearningEvidence[] {
  const yesterdayStart = new Date(now);
  yesterdayStart.setHours(0, 0, 0, 0);
  yesterdayStart.setDate(yesterdayStart.getDate() - 1);
  const todayStart = new Date(yesterdayStart);
  todayStart.setDate(todayStart.getDate() + 1);
  return evidence.filter((item) => {
    if (!item.observed_at || !["attempt", "review", "self_explanation"].includes(item.kind)) {
      return false;
    }
    const observedAt = new Date(item.observed_at);
    return !Number.isNaN(observedAt.getTime())
      && observedAt >= yesterdayStart
      && observedAt < todayStart;
  });
}

export function remainingSessionMinutes(
  startedAt: number,
  totalMinutes: number,
  now = Date.now(),
): number {
  const elapsedMinutes = Math.max(0, Math.floor((now - startedAt) / 60_000));
  return Math.max(0, totalMinutes - elapsedMinutes);
}

export function buildLessonHighlights(text: string, limit = 5): string[] {
  const candidates = text
    .replace(/\r/g, "")
    .split(/\n+|(?<=[。！？；])\s*/)
    .map((item) => item.replace(/\s+/g, " ").trim())
    .filter((item) => item.length >= 8 && item.length <= 260);
  const seen = new Set<string>();
  const highlights: string[] = [];
  for (const candidate of candidates) {
    const key = candidate.toLocaleLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    highlights.push(candidate);
    if (highlights.length === limit) break;
  }
  return highlights;
}

export function sessionStage(
  question: { id: string } | null,
  result: { score: number } | null,
): LearningSessionStage {
  if (result) return "reflect";
  if (question) return "practice";
  return "review";
}

export function selectTodayPlanSession(
  sessions: readonly StudySession[],
  now = new Date(),
): StudySession | undefined {
  return sessions.find((session) => {
    if (session.status === "completed") return false;
    const plannedAt = new Date(session.planned_at);
    return plannedAt.getFullYear() === now.getFullYear()
      && plannedAt.getMonth() === now.getMonth()
      && plannedAt.getDate() === now.getDate();
  });
}

export function inferLearningMode(subject: string, goal: string): LearningMode {
  const text = `${subject} ${goal}`.toLocaleLowerCase();
  if (/考试|考研|高考|期末|exam|test|quiz|mathematics|math|language/.test(text)) {
    return "exam";
  }
  if (/编程|代码|开发|搭建|实现|build|coding|programming|typescript|javascript|python/.test(text)) {
    return "project";
  }
  if (/产品|运营|案例|策略|用户|需求|product|operation|marketing|case/.test(text)) {
    return "case";
  }
  return "concept";
}
