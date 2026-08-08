import { describe, expect, it } from "vitest";

import { ApiError } from "../lib/api";
import { localizeApiError } from "../lib/error-messages";


describe("localized API errors", () => {
  it("maps stable API codes without leaking backend English", () => {
    expect(localizeApiError(
      new ApiError(401, "invalid_credentials", "Invalid email or password"),
      "zh",
    )).toBe("邮箱或密码错误");
    expect(localizeApiError(
      new ApiError(409, "model_not_configured", "Model not configured"),
      "zh",
    )).toBe("学习 Agent 尚未配置模型，你仍可继续使用本地学习功能。");
    expect(localizeApiError(
      new ApiError(413, "material_quota", "Quota exceeded"),
      "en",
    )).toBe("The material limit for this learning space has been reached.");
    expect(localizeApiError(
      new ApiError(409, "workspace_quota", "Learning workspace quota reached"),
      "zh",
    )).toBe("学习空间数量已达到上限。");
    expect(localizeApiError(
      new ApiError(409, "material_mutation_busy", "Material mutation is busy"),
      "zh",
    )).toBe("资料正在被整理，请稍后重试上传。");
  });

  it("uses a safe localized fallback for unknown failures", () => {
    expect(localizeApiError(new Error("internal storage path"), "zh"))
      .toBe("操作没有完成，请稍后重试。");
  });
});
