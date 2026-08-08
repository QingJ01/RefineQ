import { describe, expect, it } from "vitest";

import {
  buildSessionSteps,
  inferLearningMode,
  learningModeForActivity,
  selectTodayPlanSession,
  sessionStage,
} from "../lib/learning-session";


describe("universal capability learning session", () => {
  it("uses activity language for case learning instead of exam-only steps", () => {
    expect(buildSessionSteps("case", "zh").map((step) => step.label)).toEqual([
      "目标校准",
      "案例拆解",
      "实战任务",
      "反馈复盘",
    ]);
  });

  it("moves one session from learning to practice to feedback", () => {
    expect(sessionStage(null, null)).toBe("learn");
    expect(sessionStage({ id: "task-1" }, null)).toBe("practice");
    expect(sessionStage({ id: "task-1" }, { score: 86 })).toBe("reflect");
  });

  it("maps every plan activity to the learning behavior it promises", () => {
    expect(learningModeForActivity("learn")).toBe("concept");
    expect(learningModeForActivity("practice")).toBe("case");
    expect(learningModeForActivity("apply")).toBe("project");
    expect(learningModeForActivity("review")).toBe("exam");
  });

  it("defaults open-ended capabilities to case or project learning", () => {
    expect(inferLearningMode("product", "验证真实用户需求")).toBe("case");
    expect(inferLearningMode("programming", "用 TypeScript 做一个可运行的产品")).toBe("project");
    expect(inferLearningMode("mathematics", "准备高等数学期末考试")).toBe("exam");
  });

  it("selects an unfinished session scheduled for the learner's local today only", () => {
    const now = new Date(2026, 7, 8, 12, 0, 0);
    const session = (id: string, date: Date, status: "planned" | "completed" = "planned") => ({
      id,
      topic_id: "limits",
      planned_at: date.toISOString(),
      minutes: 45,
      status,
    });
    const sessions = [
      session("yesterday", new Date(2026, 7, 7, 9, 0, 0)),
      session("today-completed", new Date(2026, 7, 8, 8, 0, 0), "completed"),
      session("today", new Date(2026, 7, 8, 9, 0, 0)),
      session("tomorrow", new Date(2026, 7, 9, 9, 0, 0)),
    ];

    expect(selectTodayPlanSession(sessions, now)?.id).toBe("today");
    expect(selectTodayPlanSession([sessions[0], sessions[3]], now)).toBeUndefined();
  });
});
