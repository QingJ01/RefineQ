import { ApiError } from "./api";
import type { Locale } from "./types";


const messages: Record<Locale, Record<string, string>> = {
  zh: {
    material_bulk_delete_failed: "所选资料未能安全删除，原文件与索引已尽力恢复。",
    material_mutation_busy: "资料正在被整理，请稍后重试上传。",
    invalid_credentials: "邮箱或密码错误",
    unauthorized: "登录状态已失效，请重新登录。",
    model_not_configured: "学习 Agent 尚未配置模型，你仍可继续使用本地学习功能。",
    material_quota: "当前学习空间的资料额度已用完。",
    project_quota: "学习空间数量已达到上限。",
    workspace_quota: "学习空间数量已达到上限。",
    rate_limit_exceeded: "操作过于频繁，请稍后再试。",
    request_timeout: "请求超时，请重试。",
    validation_error: "提交的信息不完整或格式不正确。",
    invalid_reset_token: "重置链接无效或已过期。",
    account_confirmation_mismatch: "请输入当前账户邮箱以确认删除。",
    account_deletion_blocked: "账户仍关联平台配置，请先移交配置后再删除。",
    account_deletion_failed: "账户删除未安全完成，你的数据和登录仍然保留。",
    not_found: "没有找到请求的内容。",
    service_unavailable: "服务暂时不可用，请稍后重试。",
    conflict: "当前状态已发生变化，请刷新后重试。",
  },
  en: {
    material_bulk_delete_failed: "The selected materials could not be deleted safely. Files and indexes were restored where possible.",
    material_mutation_busy: "Materials are being organized. Try the upload again shortly.",
    invalid_credentials: "Invalid email or password.",
    unauthorized: "Your session has expired. Sign in again.",
    model_not_configured: "The learning Agent has not been configured. Local learning tools remain available.",
    material_quota: "The material limit for this learning space has been reached.",
    project_quota: "You have reached the learning-space limit.",
    workspace_quota: "You have reached the learning-space limit.",
    rate_limit_exceeded: "Too many requests. Try again shortly.",
    request_timeout: "The request timed out. Try again.",
    validation_error: "Some submitted information is missing or invalid.",
    invalid_reset_token: "The reset link is invalid or has expired.",
    account_confirmation_mismatch: "Type the current account email to confirm deletion.",
    account_deletion_blocked: "This account still owns platform configuration that must be transferred first.",
    account_deletion_failed: "Deletion did not complete safely. Your data and sign-in remain available.",
    not_found: "The requested item could not be found.",
    service_unavailable: "The service is temporarily unavailable. Try again later.",
    conflict: "The item changed. Refresh and try again.",
  },
};

const fallbacks: Record<Locale, string> = {
  zh: "操作没有完成，请稍后重试。",
  en: "The action did not finish. Try again shortly.",
};

export function localizeApiError(caught: unknown, locale: Locale): string {
  if (caught instanceof ApiError) {
    return messages[locale][caught.code] ?? fallbacks[locale];
  }
  return fallbacks[locale];
}
