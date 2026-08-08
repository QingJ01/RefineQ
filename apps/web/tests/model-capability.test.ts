import { describe, expect, it } from "vitest";

import { loadModelCapability } from "../lib/model-capability";


describe("model capability loading", () => {
  it("keeps local learning available when capability status cannot be loaded", async () => {
    const configured = await loadModelCapability(async () => {
      throw new Error("settings endpoint unavailable");
    });

    expect(configured).toBeNull();
  });

  it("returns the configured state when the capability endpoint responds", async () => {
    await expect(loadModelCapability(async () => ({ configured: true })))
      .resolves.toBe(true);
  });
});
