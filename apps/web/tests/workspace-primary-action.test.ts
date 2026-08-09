import { describe, expect, it } from "vitest";

import { chooseWorkspacePrimaryAction } from "../lib/workspace-primary-action";

describe("workspace primary action arbitration", () => {
  it("shows upload before diagnostic when the workspace has no material", () => {
    expect(chooseWorkspacePrimaryAction({
      diagnosticCount: 0,
      attemptCount: 0,
      nextActionType: "upload_material",
    })).toBe("next_action");
  });

  it("shows exactly one diagnostic after material becomes available", () => {
    expect(chooseWorkspacePrimaryAction({
      diagnosticCount: 0,
      attemptCount: 0,
      nextActionType: "start_practice",
    })).toBe("diagnostic");
  });

  it("returns to the computed next action after onboarding", () => {
    expect(chooseWorkspacePrimaryAction({
      diagnosticCount: 1,
      attemptCount: 0,
      nextActionType: "start_session",
    })).toBe("next_action");
  });
});
