import type { LearningMode, Locale, StudySession } from "./types";


export type LearningSessionStage = "learn" | "practice" | "reflect";

export interface LearningSessionStep {
  id: "align" | "learn" | "practice" | "reflect";
  label: string;
  minutes: number;
}

export function learningModeForActivity(
  activity: NonNullable<StudySession["activity"]>,
): LearningMode {
  return {
    learn: "concept",
    practice: "case",
    apply: "project",
    review: "exam",
  }[activity];
}

const steps: Record<LearningMode, Record<Locale, LearningSessionStep[]>> = {
  concept: {
    zh: [
      { id: "align", label: "快速回顾", minutes: 5 },
      { id: "learn", label: "理解概念", minutes: 10 },
      { id: "practice", label: "主动练习", minutes: 20 },
      { id: "reflect", label: "总结复盘", minutes: 10 },
    ],
    en: [
      { id: "align", label: "Quick review", minutes: 5 },
      { id: "learn", label: "Understand", minutes: 10 },
      { id: "practice", label: "Active practice", minutes: 20 },
      { id: "reflect", label: "Wrap up", minutes: 10 },
    ],
  },
  case: {
    zh: [
      { id: "align", label: "目标校准", minutes: 5 },
      { id: "learn", label: "案例拆解", minutes: 10 },
      { id: "practice", label: "实战任务", minutes: 20 },
      { id: "reflect", label: "反馈复盘", minutes: 10 },
    ],
    en: [
      { id: "align", label: "Align goal", minutes: 5 },
      { id: "learn", label: "Analyze case", minutes: 10 },
      { id: "practice", label: "Apply", minutes: 20 },
      { id: "reflect", label: "Reflect", minutes: 10 },
    ],
  },
  project: {
    zh: [
      { id: "align", label: "定义产出", minutes: 5 },
      { id: "learn", label: "方法拆解", minutes: 10 },
      { id: "practice", label: "项目实战", minutes: 20 },
      { id: "reflect", label: "作品复盘", minutes: 10 },
    ],
    en: [
      { id: "align", label: "Define output", minutes: 5 },
      { id: "learn", label: "Break down", minutes: 10 },
      { id: "practice", label: "Build", minutes: 20 },
      { id: "reflect", label: "Review work", minutes: 10 },
    ],
  },
  exam: {
    zh: [
      { id: "align", label: "快速回顾", minutes: 5 },
      { id: "learn", label: "考点梳理", minutes: 10 },
      { id: "practice", label: "模拟作答", minutes: 20 },
      { id: "reflect", label: "错题复习", minutes: 10 },
    ],
    en: [
      { id: "align", label: "Quick review", minutes: 5 },
      { id: "learn", label: "Key points", minutes: 10 },
      { id: "practice", label: "Mock answer", minutes: 20 },
      { id: "reflect", label: "Review errors", minutes: 10 },
    ],
  },
};

export function buildSessionSteps(mode: LearningMode, locale: Locale): LearningSessionStep[] {
  return steps[mode][locale];
}

export function sessionStage(
  question: { id: string } | null,
  result: { score: number } | null,
): LearningSessionStage {
  if (result) return "reflect";
  if (question) return "practice";
  return "learn";
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
