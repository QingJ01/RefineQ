import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../lib/api";
import { localizeApiError } from "../lib/error-messages";


describe("localized API errors", () => {
  afterEach(() => vi.unstubAllGlobals());
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
    expect(localizeApiError(
      new ApiError(503, "backup_creation_failed", "Backup could not be created safely"),
      "zh",
    )).toBe("系统备份未能安全创建，请稍后重试。");
    expect(localizeApiError(
      new ApiError(415, "unsupported_material", "Unsupported material"),
      "zh",
    )).toBe("不支持这种资料格式，请选择 PDF、DOCX、TXT 或 MD 文件。");
    expect(localizeApiError(
      new ApiError(413, "material_limit", "Material too large"),
      "en",
    )).toBe("The file exceeds the 20 MB upload limit.");
    expect(localizeApiError(
      new ApiError(422, "material_extraction_failed", "Could not extract"),
      "zh",
    )).toBe("无法读取这份资料的内容，请检查文件后重试。");
  });

  it("uses a safe localized fallback for unknown failures", () => {
    expect(localizeApiError(new Error("internal storage path"), "zh"))
      .toBe("操作没有完成，请稍后重试。");
  });

  it("distinguishes an offline browser from a server failure", () => {
    vi.stubGlobal("navigator", { onLine: false });
    expect(localizeApiError(new TypeError("Failed to fetch"), "zh"))
      .toBe("当前网络已断开，请恢复连接后重试。");
  });

  it("covers learning, Agent, and integration error codes", () => {
    expect(localizeApiError(new ApiError(409, "learning_conflict", "raw"), "en"))
      .toBe("Learning state changed. Resync and try again.");
    expect(localizeApiError(new ApiError(404, "attempt_not_found", "raw"), "zh"))
      .toBe("找不到这次作答记录。");
    expect(localizeApiError(new ApiError(409, "integration_not_configured", "raw"), "en"))
      .toBe("This integration has not been configured.");
  });
});
