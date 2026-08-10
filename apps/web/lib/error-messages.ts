import { ApiError } from "./api";
import type { Locale } from "./types";


const messages: Record<Locale, Record<string, string>> = {
  zh: {
    material_filename_exists: "同名文件已存在，请直接从总资料库选择，或修改文件名后再上传。",
    material_bulk_delete_failed: "所选资料未能安全删除，原文件与索引已尽力恢复。",
    material_mutation_busy: "资料正在被整理，请稍后重试上传。",
    unsupported_material: "不支持这种资料格式，请选择 PDF、DOCX、TXT 或 MD 文件。",
    material_limit: "文件超过 20 MB 上传上限。",
    material_extraction_failed: "无法读取这份资料的内容，请检查文件后重试。",
    material_extraction_limit: "资料内容过大或过于复杂，无法安全解析。",
    material_not_found: "这份资料不存在或已被删除。",
    material_required: "请先上传一份可检索的学习资料。",
    material_insufficient: "现有资料与这个主题不匹配，请上传相关资料后重试。",
    workspace_not_found: "这个学习空间不存在或已不可用。",
    request_body_too_large: "上传内容超过服务器允许的大小。",
    upload_body_timeout: "上传耗时过长，请检查网络后重试。",
    backup_creation_failed: "系统备份未能安全创建，请稍后重试。",
    backup_listing_failed: "系统备份列表暂时无法读取，请稍后重试。",
    backup_not_found: "这个备份不存在或已被移除。",
    backup_invalid: "备份完整性校验失败，请勿用于恢复。",
    restore_confirmation_required: "恢复校验口令不匹配，请重新确认备份 ID。",
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
    learning_conflict: "学习状态已变化，请重新同步后再试。",
    daily_capacity_exceeded: "这一天的学习时长已排满，请改到其他日期或缩短这次时长。",
    learning_error: "学习服务暂时无法完成操作，请稍后重试。",
    learning_not_seeded: "这个学习空间尚未准备完成。",
    invalid_learning_constraints: "学习目标、日期或时长设置不完整。",
    question_not_found: "找不到这道题，可能已被历史记录清理。",
    attempt_not_found: "找不到这次作答记录。",
    agent_session_not_found: "找不到这段教练对话。",
    agent_session_conflict: "教练对话状态已变化，请重新同步。",
    agent_session_limit: "教练对话数量已达到上限，请先清理旧对话。",
    agent_error: "学习 Agent 暂时无法完成请求。",
    integration_not_configured: "这项外部能力尚未配置。",
    invalid_integration: "外部能力配置无效，请检查后重试。",
    model_endpoint_not_allowed: "模型服务地址不在允许范围内。",
    workspace_error: "学习空间暂时无法完成这个操作，请稍后重试。",
    project_not_found: "找不到对应的学习空间。",
    invalid_identifier: "请求标识无效。",
  },
  en: {
    material_filename_exists: "A file with this name already exists. Select it from the material library or rename the file.",
    material_bulk_delete_failed: "The selected materials could not be deleted safely. Files and indexes were restored where possible.",
    material_mutation_busy: "Materials are being organized. Try the upload again shortly.",
    unsupported_material: "This material type is not supported. Choose a PDF, DOCX, TXT, or MD file.",
    material_limit: "The file exceeds the 20 MB upload limit.",
    material_extraction_failed: "The material content could not be read. Check the file and try again.",
    material_extraction_limit: "The material is too large or complex to parse safely.",
    material_not_found: "That material does not exist or has been removed.",
    material_required: "Upload a searchable study source before starting practice.",
    material_insufficient: "No uploaded source matches this topic. Upload a relevant source and try again.",
    workspace_not_found: "That learning space does not exist or is unavailable.",
    request_body_too_large: "The upload exceeds the server request limit.",
    upload_body_timeout: "The upload took too long. Check your connection and try again.",
    backup_creation_failed: "The system backup could not be created safely. Try again shortly.",
    backup_listing_failed: "The backup list is temporarily unavailable. Try again shortly.",
    backup_not_found: "That backup does not exist or has been removed.",
    backup_invalid: "Backup integrity validation failed. Do not use it for restore.",
    restore_confirmation_required: "The restore confirmation does not match this backup ID.",
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
    learning_conflict: "Learning state changed. Resync and try again.",
    daily_capacity_exceeded: "That day is already full for its daily study minutes. Pick another day or shorten the session.",
    learning_error: "The learning service could not finish this action. Try again shortly.",
    learning_not_seeded: "This learning space is not ready yet.",
    invalid_learning_constraints: "The learning goal, date, or time constraints are incomplete.",
    question_not_found: "That question is no longer available.",
    attempt_not_found: "That attempt could not be found.",
    agent_session_not_found: "That coach conversation could not be found.",
    agent_session_conflict: "The coach conversation changed. Resync and try again.",
    agent_session_limit: "The coach conversation limit has been reached. Remove an older conversation first.",
    agent_error: "The learning Agent could not finish this request.",
    integration_not_configured: "This integration has not been configured.",
    invalid_integration: "The integration settings are invalid. Check them and try again.",
    model_endpoint_not_allowed: "That model endpoint is not allowed.",
    workspace_error: "The learning space could not finish this action. Try again shortly.",
    project_not_found: "That learning space could not be found.",
    invalid_identifier: "The request identifier is invalid.",
  },
};

const fallbacks: Record<Locale, string> = {
  zh: "操作没有完成，请稍后重试。",
  en: "The action did not finish. Try again shortly.",
};

export function localizeApiError(caught: unknown, locale: Locale): string {
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    return locale === "zh"
      ? "当前网络已断开，请恢复连接后重试。"
      : "You are offline. Reconnect and try again.";
  }
  if (caught instanceof ApiError) {
    return messages[locale][caught.code] ?? fallbacks[locale];
  }
  return fallbacks[locale];
}

/**
 * Describe a plan mutation failure, enriching a daily-budget conflict with the
 * server-suggested next open day so the learner knows where the session fits.
 */
export function describePlanCapacityError(caught: unknown, locale: Locale): string {
  const base = localizeApiError(caught, locale);
  if (caught instanceof ApiError && caught.code === "daily_capacity_exceeded") {
    const nextFree = caught.detail?.next_free_date;
    if (typeof nextFree === "string") {
      return locale === "zh"
        ? `${base}最早可安排到 ${nextFree}。`
        : `${base} The next open day is ${nextFree}.`;
    }
  }
  return base;
}
