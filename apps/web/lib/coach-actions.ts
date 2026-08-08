import type {
  AdjustPracticeProposal,
  CoachActionProposal,
  SaveQuestionProposal,
  UpdatePlanSessionProposal,
} from "./types";


export interface PendingCoachTurn {
  id: string;
  message: string;
}

export type CoachActionOutcome =
  | { status: "applied"; replayed: boolean }
  | { status: "confirmation_required" }
  | { status: "failed" }
  | { status: "rejected" }
  | { status: "synced" };

interface CoachActionHandlers {
  appliedActionIds: Set<string>;
  hasDraft: boolean;
  confirmed?: boolean;
  historical?: boolean;
  applyAdjust: (proposal: AdjustPracticeProposal) => Promise<boolean>;
  applyPlanUpdate: (proposal: UpdatePlanSessionProposal) => Promise<boolean>;
  applySaveQuestion: (proposal: SaveQuestionProposal) => Promise<boolean>;
  refreshSnapshot: () => Promise<void>;
}

export function pendingCoachTurn(
  current: PendingCoachTurn | null,
  message: string,
  createId: () => string,
): PendingCoachTurn {
  if (current?.message === message) return current;
  return { id: createId(), message };
}

export async function executeCoachAction(
  proposal: CoachActionProposal,
  handlers: CoachActionHandlers,
): Promise<CoachActionOutcome> {
  if (proposal.type === "rejected") return { status: "rejected" };

  if (handlers.appliedActionIds.has(proposal.action_id)) {
    return { status: "applied", replayed: true };
  }

  if (handlers.historical) {
    try {
      await handlers.refreshSnapshot();
      return { status: "synced" };
    } catch {
      return { status: "failed" };
    }
  }

  if (
    proposal.type === "adjust_practice"
    && proposal.destructive
    && handlers.hasDraft
    && !handlers.confirmed
  ) {
    return { status: "confirmation_required" };
  }

  try {
    const applied = proposal.type === "adjust_practice"
      ? await handlers.applyAdjust(proposal)
      : proposal.type === "update_plan_session"
        ? await handlers.applyPlanUpdate(proposal)
        : await handlers.applySaveQuestion(proposal);
    if (!applied) return { status: "failed" };
    handlers.appliedActionIds.add(proposal.action_id);
    return { status: "applied", replayed: false };
  } catch {
    return { status: "failed" };
  }
}
