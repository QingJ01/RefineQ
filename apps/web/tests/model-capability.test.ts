import { describe, expect, it } from "vitest";

import {
  loadModelCapability,
  refreshModelCapability,
  resolveModelCapability,
} from "../lib/model-capability";


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

  it("uses a successful local recheck when the parent probe is unknown", () => {
    expect(resolveModelCapability(null, true)).toBe(true);
    expect(resolveModelCapability(undefined, true)).toBe(true);
    expect(resolveModelCapability(null, null)).toBeNull();
  });

  it("keeps a known unconfigured result authoritative", () => {
    expect(resolveModelCapability(false, true)).toBe(false);
    expect(resolveModelCapability(null, false)).toBe(false);
  });

  it("returns and publishes the result of an explicit recheck", async () => {
    const published: Array<boolean | null> = [];

    const result = await refreshModelCapability(
      async () => ({ configured: true }),
      (configured) => published.push(configured),
    );

    expect(result).toBe(true);
    expect(published).toEqual([true]);
  });
});
