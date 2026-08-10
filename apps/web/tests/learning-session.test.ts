import { describe, expect, it } from "vitest";

import {
  buildLessonHighlights,
  buildSessionSteps,
  remainingSessionMinutes,
  summaryReserveMinutes,
  inferLearningMode,
  learningModeForActivity,
  selectTodayPlanSession,
  selectYesterdayEvidence,
  sessionStage,
} from "../lib/learning-session";


describe("universal capability learning session", () => {
  it("keeps one clear four-step flow for every learning activity", () => {
    expect(buildSessionSteps("case", "zh").map((step) => step.label)).toEqual([
      "快速回顾",
      "今天学习",
      "练一练",
      "总结复盘",
    ]);
  });

  it("turns a dense material excerpt into a short readable list", () => {
    expect(buildLessonHighlights(
      "极限描述函数在点附近的趋势。函数在该点可以没有定义。\n\n函数值与极限需要区分。",
    )).toEqual([
      "极限描述函数在点附近的趋势。",
      "函数在该点可以没有定义。",
      "函数值与极限需要区分。",
    ]);
  });

  it("moves one session from learning to practice to feedback", () => {
    expect(sessionStage(null, null)).toBe("review");
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

it("scales the fixed session flow to the available time", () => {
  expect(buildSessionSteps("concept", "zh", 20).map((step) => step.minutes)).toEqual([2, 4, 10, 4]);
  expect(buildSessionSteps("concept", "zh", 120).map((step) => step.minutes)).toEqual([5, 20, 85, 10]);
  expect(summaryReserveMinutes(45)).toBe(6);
  expect(remainingSessionMinutes(0, 45, 10 * 60_000)).toBe(35);
  expect(buildSessionSteps("concept", "zh", 20, false).map((step) => step.minutes)).toEqual([0, 6, 10, 4]);
});

it("uses only yesterday's learning evidence for quick review", () => {
  const now = new Date(2026, 7, 10, 14, 0, 0);
  const evidence = [
    { id: "old", kind: "attempt" as const, source_id: "a", summary: "old", observed_at: "2026-08-08T09:00:00+08:00", details: { topic_id: "old" } },
    { id: "yesterday", kind: "attempt" as const, source_id: "b", summary: "limits", observed_at: "2026-08-09T09:00:00+08:00", details: { topic_id: "limits" } },
    { id: "material", kind: "material" as const, source_id: "c", summary: "upload", observed_at: "2026-08-09T10:00:00+08:00", details: {} },
    { id: "today", kind: "attempt" as const, source_id: "d", summary: "today", observed_at: "2026-08-10T09:00:00+08:00", details: { topic_id: "today" } },
  ];
  expect(selectYesterdayEvidence(evidence, now).map((item) => item.id)).toEqual(["yesterday"]);
});
