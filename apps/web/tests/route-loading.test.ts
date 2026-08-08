import { describe, expect, it } from "vitest";

import { routeLoadingText } from "../lib/route-loading";


describe("route-aware loading copy", () => {
  it("distinguishes learner restoration from protected route verification", () => {
    expect(routeLoadingText("/learn/math/today", "zh").title).toBe("正在恢复学习空间");
    expect(routeLoadingText("/account", "en").title).toBe("Verifying account access");
    expect(routeLoadingText("/admin/operations", "en").title).toBe("Verifying administrator access");
  });
});
