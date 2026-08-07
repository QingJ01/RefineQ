import { describe, expect, it } from "vitest";

import {
  buildSessionSteps,
  inferLearningMode,
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

  it("defaults open-ended capabilities to case or project learning", () => {
    expect(inferLearningMode("product", "验证真实用户需求")).toBe("case");
    expect(inferLearningMode("programming", "用 TypeScript 做一个可运行的产品")).toBe("project");
    expect(inferLearningMode("mathematics", "准备高等数学期末考试")).toBe("exam");
  });
});
