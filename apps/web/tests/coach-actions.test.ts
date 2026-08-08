import { describe, expect, it, vi } from "vitest";

import {
  executeCoachAction,
  pendingCoachTurn,
} from "../lib/coach-actions";
import type {
  AdjustPracticeProposal,
  SaveQuestionProposal,
  UpdatePlanSessionProposal,
} from "../lib/types";


const adjustProposal: AdjustPracticeProposal = {
  type: "adjust_practice",
  action_id: "action-adjust",
  topic_id: "cache",
  topic_name: "Cache consistency",
  difficulty: 2,
  learning_mode: "concept",
  destructive: true,
};

describe("coach action execution", () => {
  it("requires confirmation before replacing a question with a non-empty draft", async () => {
    const applyAdjust = vi.fn(async () => true);

    const outcome = await executeCoachAction(adjustProposal, {
      appliedActionIds: new Set(),
      hasDraft: true,
      applyAdjust,
      applyPlanUpdate: vi.fn(async () => true),
      applySaveQuestion: vi.fn(async () => true),
    });

    expect(outcome.status).toBe("confirmation_required");
    expect(applyAdjust).not.toHaveBeenCalled();
  });

  it("uses the proposal action id for a confirmed replacement and does not apply it twice", async () => {
    const appliedActionIds = new Set<string>();
    const applyAdjust = vi.fn(async (proposal: AdjustPracticeProposal) => {
      expect(proposal.action_id).toBe("action-adjust");
      return true;
    });
    const options = {
      appliedActionIds,
      hasDraft: true,
      confirmed: true,
      applyAdjust,
      applyPlanUpdate: vi.fn(async () => true),
      applySaveQuestion: vi.fn(async () => true),
    };

    expect((await executeCoachAction(adjustProposal, options)).status).toBe("applied");
    expect((await executeCoachAction(adjustProposal, options)).status).toBe("applied");
    expect(applyAdjust).toHaveBeenCalledTimes(1);
    expect(appliedActionIds.has("action-adjust")).toBe(true);
  });

  it("routes plan and saved-question proposals to their existing write handlers", async () => {
    const planProposal: UpdatePlanSessionProposal = {
      type: "update_plan_session",
      action_id: "action-plan",
      session_id: "session-1",
      session_label: "Aug 12, 20:00 · Cache consistency",
      planned_at: "2026-08-12T12:00:00Z",
      status: null,
    };
    const saveProposal: SaveQuestionProposal = {
      type: "save_question",
      action_id: "action-save",
      question_id: "question-1",
      saved: true,
    };
    const applyPlanUpdate = vi.fn(async () => true);
    const applySaveQuestion = vi.fn(async () => false);
    const base = {
      appliedActionIds: new Set<string>(),
      hasDraft: false,
      applyAdjust: vi.fn(async () => true),
      applyPlanUpdate,
      applySaveQuestion,
    };

    expect((await executeCoachAction(planProposal, base)).status).toBe("applied");
    expect((await executeCoachAction(saveProposal, base)).status).toBe("failed");
    expect(applyPlanUpdate).toHaveBeenCalledWith(planProposal);
    expect(applySaveQuestion).toHaveBeenCalledWith(saveProposal);
  });

});

describe("coach turn identity", () => {
  it("reuses a failed turn id for the same message and replaces it for a new message", () => {
    const ids = ["turn-1", "turn-2"];
    const createId = () => ids.shift() ?? "unexpected";

    const first = pendingCoachTurn(null, "Make it easier", createId);
    const retry = pendingCoachTurn(first, "Make it easier", createId);
    const changed = pendingCoachTurn(retry, "Save this question", createId);

    expect(retry).toBe(first);
    expect(changed).toEqual({ id: "turn-2", message: "Save this question" });
  });
});
