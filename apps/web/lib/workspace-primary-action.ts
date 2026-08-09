import type { NextAction } from "./types";

export type WorkspacePrimaryAction = "next_action" | "diagnostic" | "none";

export function chooseWorkspacePrimaryAction(input: {
  diagnosticCount: number;
  attemptCount: number;
  nextActionType: NextAction["action_type"] | null;
}): WorkspacePrimaryAction {
  if (input.diagnosticCount === 0 && input.attemptCount === 0) {
    return input.nextActionType === "upload_material" ? "next_action" : "diagnostic";
  }
  return input.nextActionType ? "next_action" : "none";
}
