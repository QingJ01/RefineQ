"use client";

import {
  Activity,
  ArchiveRestore,
  ArrowLeft,
  ArrowRight,
  BrainCircuit,
  Check,
  Database,
  FileScan,
  Gauge,
  HardDrive,
  LayoutDashboard,
  ListChecks,
  LoaderCircle,
  PlugZap,
  Save,
  ShieldCheck,
  TriangleAlert,
  Users,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { AppSidebar } from "@/components/app-sidebar";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { api } from "@/lib/api";
import { localizeApiError } from "@/lib/error-messages";
import type {
  AdminAuditPage,
  AdminJobsResponse,
  AdminOverview,
  AdminUsersPage,
  IntegrationKind,
  LearningWorkspace,
  Locale,
  ManagedBackup,
  ManagedBackupsResponse,
  PublicIntegrationSettings,
} from "@/lib/types";
import { projectIntegrationTestResult } from "@/lib/view-models";


type FieldDefinition = {
  key: string;
  label: string;
  placeholder?: string;
  type?: "text" | "number" | "password" | "select" | "boolean";
  options?: Array<{ value: string; label: string }>;
};

type IntegrationDefinition = {
  kind: IntegrationKind;
  icon: typeof BrainCircuit;
  title: string;
  eyebrow: string;
  description: string;
  configFields: FieldDefinition[];
  secretFields: FieldDefinition[];
};

const copy = {
  zh: {
    title: "系统设置",
    subtitle: "查看平台运行状态，并按需配置学习 Agent 使用的外部能力。",
    back: "返回学习空间",
    users: "注册用户",
    database: "业务数据库",
    vector: "向量检索",
    configured: "已配置能力",
    active: "已启用",
    inactive: "未启用",
    ready: "凭据已保存",
    missing: "等待配置",
    save: "保存配置",
    test: "测试连接",
    saving: "正在保存",
    testing: "正在测试",
    saved: "配置已安全保存",
    secretHint: "留空会继续使用当前密钥",
    loading: "正在读取平台状态…",
    logout: "退出登录",
    overview: "系统概览",
    integrations: "能力配置",
    configure: "打开配置",
    backOverview: "返回概览",
    language: "English",
    encrypted: "密钥由服务端加密保存",
    systemStatus: "运行状态",
    nextAction: "下一步",
    allReady: "核心能力已经就绪",
    allReadyDescription: "当前没有需要处理的配置问题。你仍可从左侧随时检查或调整服务。",
    completeSetup: "完成配置",
    retrySetup: "检查连接",
    setupProgress: "配置进度",
    principles: "运行原则",
    localParsing: "本地解析优先",
    localParsingDescription: "PDF、DOCX、TXT 与 Markdown 优先在本地提取内容。",
    encryptedDescription: "浏览器不会读取已经保存的完整密钥。",
    onDemand: "按需调用",
    onDemandDescription: "未启用的外部服务不会产生请求或调用成本。",
    serviceStatus: "服务状态",
    serviceStatusDescription: "只有启用后，学习 Agent 才会调用这项能力。",
    basicSettings: "基础配置",
    basicSettingsDescription: "设置服务地址、模型以及运行参数。",
    credentials: "访问凭据",
    credentialsDescription: "凭据提交后只在服务端加密保存。",
    networkSecurity: "网络安全",
    networkSecurityDescription: "默认阻止访问私网地址，降低服务端请求伪造风险。",
    networkWarning: "仅在明确使用可信内网服务时开启私网访问。",
    saveTest: "保存并测试",
    unsavedWarning: "当前配置尚未保存，确定离开并丢弃更改吗？",
    unsaved: "有未保存的更改",
    stay: "继续编辑",
    discard: "丢弃并离开",
    loadFailed: "配置读取失败，为避免覆盖已有设置，编辑已锁定。",
    reload: "重新读取",
    connectionSucceeded: "连接测试通过",
    connectionFailed: "连接测试失败，请检查地址、凭据与网络设置。",
  },
  en: {
    title: "System settings",
    subtitle: "Review platform health and configure the external services used by the learning Agent.",
    back: "Back to learning",
    users: "Registered users",
    database: "Application database",
    vector: "Vector retrieval",
    configured: "Configured services",
    active: "Enabled",
    inactive: "Disabled",
    ready: "Credentials saved",
    missing: "Needs setup",
    save: "Save configuration",
    test: "Test connection",
    saving: "Saving",
    testing: "Testing",
    saved: "Configuration saved securely",
    secretHint: "Leave blank to keep the current secret",
    loading: "Loading platform status…",
    logout: "Sign out",
    overview: "Overview",
    integrations: "Integrations",
    configure: "Open settings",
    backOverview: "Back to overview",
    language: "中文",
    encrypted: "Secrets are encrypted on the server",
    systemStatus: "System status",
    nextAction: "Next action",
    allReady: "Core capabilities are ready",
    allReadyDescription: "There are no configuration issues to resolve. You can still review any service from the sidebar.",
    completeSetup: "Complete setup",
    retrySetup: "Check connection",
    setupProgress: "Setup progress",
    principles: "Operating principles",
    localParsing: "Local parsing first",
    localParsingDescription: "PDF, DOCX, TXT, and Markdown content is extracted locally first.",
    encryptedDescription: "The browser never receives a complete saved secret.",
    onDemand: "On-demand calls",
    onDemandDescription: "Disabled external services make no requests and incur no usage cost.",
    serviceStatus: "Service status",
    serviceStatusDescription: "The learning Agent can only call this capability when it is enabled.",
    basicSettings: "Basic settings",
    basicSettingsDescription: "Set the service endpoint, model, and runtime parameters.",
    credentials: "Credentials",
    credentialsDescription: "Credentials are encrypted and stored only on the server.",
    networkSecurity: "Network security",
    networkSecurityDescription: "Private-network access is blocked by default to reduce SSRF risk.",
    networkWarning: "Only enable private-network access for a service you explicitly trust.",
    saveTest: "Save and test",
    unsavedWarning: "This configuration has unsaved changes. Leave and discard them?",
    unsaved: "Unsaved changes",
    stay: "Keep editing",
    discard: "Discard and leave",
    loadFailed: "Settings failed to load. Editing is locked to avoid overwriting saved configuration.",
    reload: "Reload settings",
    connectionSucceeded: "Connection test passed",
    connectionFailed: "Connection test failed. Check the endpoint, credentials, and network settings.",
  },
} as const;

const definitions: Record<Locale, IntegrationDefinition[]> = {
  zh: [
    {
      kind: "chat",
      icon: BrainCircuit,
      title: "模型推理",
      eyebrow: "CHAT / REASONING",
      description: "负责 Agent 对话、自动空间识别、出题和智能判分。支持 OpenAI 兼容接口。",
      configFields: [
        { key: "base_url", label: "API 地址", placeholder: "https://api.openai.com/v1" },
        { key: "model", label: "模型名称", placeholder: "gpt-4.1-mini" },
        { key: "temperature", label: "温度", type: "number", placeholder: "0.2" },
        {
          key: "allow_private_network",
          label: "允许私网地址",
          type: "boolean",
          options: [{ value: "false", label: "否" }, { value: "true", label: "是" }],
        },
      ],
      secretFields: [{ key: "api_key", label: "API Key", type: "password" }],
    },
    {
      kind: "embedding",
      icon: Database,
      title: "语义检索",
      eyebrow: "EMBEDDING / PGVECTOR",
      description: "把资料分块转换为向量，与 PostgreSQL 全文检索共同寻找更相关的学习证据。",
      configFields: [
        { key: "base_url", label: "API 地址", placeholder: "https://api.openai.com/v1" },
        { key: "model", label: "Embedding 模型", placeholder: "text-embedding-3-small" },
        { key: "dimensions", label: "向量维度", type: "number", placeholder: "1536" },
        {
          key: "allow_private_network",
          label: "允许私网地址",
          type: "boolean",
          options: [{ value: "false", label: "否" }, { value: "true", label: "是" }],
        },
      ],
      secretFields: [{ key: "api_key", label: "API Key", type: "password" }],
    },
    {
      kind: "ocr",
      icon: FileScan,
      title: "扫描识别",
      eyebrow: "OCR / VISION",
      description: "仅在扫描 PDF 无法本地提取文字时调用视觉模型，普通文档不会产生 OCR 成本。",
      configFields: [
        { key: "base_url", label: "API 地址", placeholder: "https://api.openai.com/v1" },
        { key: "model", label: "视觉模型", placeholder: "gpt-4.1-mini" },
        {
          key: "allow_private_network",
          label: "允许私网地址",
          type: "boolean",
          options: [{ value: "false", label: "否" }, { value: "true", label: "是" }],
        },
      ],
      secretFields: [{ key: "api_key", label: "API Key", type: "password" }],
    },
    {
      kind: "object_storage",
      icon: HardDrive,
      title: "文件存储",
      eyebrow: "OBJECTS / S3",
      description: "保存 PDF、DOCX 和笔记原文件。兼容 R2、OSS、COS、S3 与 MinIO。",
      configFields: [
        { key: "endpoint_url", label: "Endpoint", placeholder: "https://..." },
        { key: "bucket", label: "Bucket", placeholder: "refineq-private" },
        { key: "region", label: "Region", placeholder: "auto" },
        {
          key: "addressing_style",
          label: "寻址方式",
          type: "select",
          options: [
            { value: "auto", label: "自动" },
            { value: "path", label: "Path style" },
            { value: "virtual", label: "Virtual host" },
          ],
        },
        {
          key: "allow_private_network",
          label: "允许私网地址",
          type: "boolean",
          options: [{ value: "false", label: "否" }, { value: "true", label: "是" }],
        },
      ],
      secretFields: [
        { key: "access_key_id", label: "Access Key ID", type: "password" },
        { key: "secret_access_key", label: "Secret Access Key", type: "password" },
      ],
    },
  ],
  en: [
    {
      kind: "chat",
      icon: BrainCircuit,
      title: "Model inference",
      eyebrow: "CHAT / REASONING",
      description: "Powers Agent chat, workspace routing, question generation, and grading.",
      configFields: [
        { key: "base_url", label: "API endpoint", placeholder: "https://api.openai.com/v1" },
        { key: "model", label: "Model", placeholder: "gpt-4.1-mini" },
        { key: "temperature", label: "Temperature", type: "number", placeholder: "0.2" },
        {
          key: "allow_private_network",
          label: "Allow private network",
          type: "boolean",
          options: [{ value: "false", label: "No" }, { value: "true", label: "Yes" }],
        },
      ],
      secretFields: [{ key: "api_key", label: "API Key", type: "password" }],
    },
    {
      kind: "embedding",
      icon: Database,
      title: "Semantic retrieval",
      eyebrow: "EMBEDDING / PGVECTOR",
      description: "Combines semantic vectors with PostgreSQL full-text evidence retrieval.",
      configFields: [
        { key: "base_url", label: "API endpoint", placeholder: "https://api.openai.com/v1" },
        { key: "model", label: "Embedding model", placeholder: "text-embedding-3-small" },
        { key: "dimensions", label: "Vector dimensions", type: "number", placeholder: "1536" },
        {
          key: "allow_private_network",
          label: "Allow private network",
          type: "boolean",
          options: [{ value: "false", label: "No" }, { value: "true", label: "Yes" }],
        },
      ],
      secretFields: [{ key: "api_key", label: "API Key", type: "password" }],
    },
    {
      kind: "ocr",
      icon: FileScan,
      title: "Scanned document OCR",
      eyebrow: "OCR / VISION",
      description: "Uses vision only when scanned PDFs contain no locally extractable text.",
      configFields: [
        { key: "base_url", label: "API endpoint", placeholder: "https://api.openai.com/v1" },
        { key: "model", label: "Vision model", placeholder: "gpt-4.1-mini" },
        {
          key: "allow_private_network",
          label: "Allow private network",
          type: "boolean",
          options: [{ value: "false", label: "No" }, { value: "true", label: "Yes" }],
        },
      ],
      secretFields: [{ key: "api_key", label: "API Key", type: "password" }],
    },
    {
      kind: "object_storage",
      icon: HardDrive,
      title: "File storage",
      eyebrow: "OBJECTS / S3",
      description: "Stores original learning files through any S3-compatible service.",
      configFields: [
        { key: "endpoint_url", label: "Endpoint", placeholder: "https://..." },
        { key: "bucket", label: "Bucket", placeholder: "refineq-private" },
        { key: "region", label: "Region", placeholder: "auto" },
        {
          key: "addressing_style",
          label: "Addressing style",
          type: "select",
          options: [
            { value: "auto", label: "Auto" },
            { value: "path", label: "Path style" },
            { value: "virtual", label: "Virtual host" },
          ],
        },
        {
          key: "allow_private_network",
          label: "Allow private network",
          type: "boolean",
          options: [{ value: "false", label: "No" }, { value: "true", label: "Yes" }],
        },
      ],
      secretFields: [
        { key: "access_key_id", label: "Access Key ID", type: "password" },
        { key: "secret_access_key", label: "Secret Access Key", type: "password" },
      ],
    },
  ],
};

const defaults: PublicIntegrationSettings[] = [
  {
    kind: "chat",
    enabled: false,
    configured: false,
    config: {
      base_url: "https://api.openai.com/v1",
      model: "",
      temperature: 0.2,
      allow_private_network: false,
    },
    secret_hints: {}, last_test_status: null, last_test_message: null, last_tested_at: null,
  },
  {
    kind: "embedding",
    enabled: false,
    configured: false,
    config: {
      base_url: "https://api.openai.com/v1",
      model: "text-embedding-3-small",
      dimensions: 1536,
      allow_private_network: false,
    },
    secret_hints: {}, last_test_status: null, last_test_message: null, last_tested_at: null,
  },
  {
    kind: "ocr",
    enabled: false,
    configured: false,
    config: {
      base_url: "https://api.openai.com/v1",
      model: "gpt-4.1-mini",
      allow_private_network: false,
    },
    secret_hints: {}, last_test_status: null, last_test_message: null, last_tested_at: null,
  },
  {
    kind: "object_storage",
    enabled: false,
    configured: false,
    config: {
      endpoint_url: "",
      bucket: "",
      region: "auto",
      addressing_style: "auto",
      allow_private_network: false,
    },
    secret_hints: {}, last_test_status: null, last_test_message: null, last_tested_at: null,
  },
];

function errorMessage(caught: unknown, locale: Locale): string {
  return localizeApiError(caught, locale);
}


const operationsCopy = {
  zh: {
    title: "运维控制台",
    subtitle: "查看用户配额、后台任务与审计记录，并管理经过完整性校验的系统备份。",
    nav: "平台运维",
    users: "用户与配额",
    activity: "审计活动",
    jobs: "素材任务",
    backups: "备份与恢复校验",
    loading: "正在读取运维数据…",
    emptyUsers: "暂无用户。",
    emptyAudit: "暂无审计记录。",
    emptyBackups: "尚未创建托管备份。",
    createBackup: "创建备份",
    creating: "正在创建…",
    validate: "校验恢复候选",
    confirmTitle: "校验这个恢复候选？",
    confirmDescription: "服务端会完整解压并校验备份，但不会覆盖当前运行数据。确认口令会精确绑定此备份 ID。",
    confirm: "确认并校验",
    cancel: "取消",
    validated: "备份完整性校验通过；实际恢复仍需离线执行。",
    created: "新备份已创建并写入审计记录。",
    retry: "重试",
    previous: "上一页",
    next: "下一页",
    materials: "资料",
    workspaces: "空间",
    storage: "存储",
    pending: "待处理",
    complete: "已完成",
    failed: "失败",
    idle: "空闲",
    email: "账户",
    adminRole: "管理员",
    learnerRole: "学习者",
    unknownRole: "成员",
    materialIndex: "资料索引",
    embeddingBackfill: "向量补录",
    files: "个文件",
    otherActivity: "平台操作",
    auditActions: {
      "backup.created": "已创建系统备份",
      "backup.restore_validated": "已校验恢复候选",
      "integration.updated": "已更新外部能力配置",
      "integration.tested": "已测试外部能力连接",
    },
  },
  en: {
    title: "Operations control plane",
    subtitle: "Inspect user quotas, background work, and audit events, then manage integrity-checked backups.",
    nav: "Platform operations",
    users: "Users and quotas",
    activity: "Audit activity",
    jobs: "Material jobs",
    backups: "Backup and restore validation",
    loading: "Loading operations data…",
    emptyUsers: "No users yet.",
    emptyAudit: "No audit events yet.",
    emptyBackups: "No managed backups have been created.",
    createBackup: "Create backup",
    creating: "Creating…",
    validate: "Validate restore candidate",
    confirmTitle: "Validate this restore candidate?",
    confirmDescription: "The server will fully extract and verify this backup without overwriting live data. The confirmation token is bound to this backup ID.",
    confirm: "Confirm and validate",
    cancel: "Cancel",
    validated: "Backup integrity passed; an actual restore still requires an offline operation.",
    created: "A new backup was created and recorded in the audit log.",
    retry: "Retry",
    previous: "Previous",
    next: "Next",
    materials: "Materials",
    workspaces: "Workspaces",
    storage: "Storage",
    pending: "Pending",
    complete: "Completed",
    failed: "Failed",
    idle: "Idle",
    email: "Account",
    adminRole: "Administrator",
    learnerRole: "Learner",
    unknownRole: "Member",
    materialIndex: "Material index",
    embeddingBackfill: "Embedding backfill",
    files: "files",
    otherActivity: "Platform operation",
    auditActions: {
      "backup.created": "System backup created",
      "backup.restore_validated": "Restore candidate validated",
      "integration.updated": "Integration settings updated",
      "integration.tested": "Integration connection tested",
    },
  },
};


function roleLabel(role: string, locale: Locale): string {
  const c = operationsCopy[locale];
  if (role === "admin") return c.adminRole;
  if (role === "learner") return c.learnerRole;
  return c.unknownRole;
}


function auditActionLabel(action: string, locale: Locale): string {
  const c = operationsCopy[locale];
  const actions: Record<string, string> = c.auditActions;
  return actions[action] ?? c.otherActivity;
}


export async function refreshAdminAudit<T>(
  load: () => Promise<T>,
  apply: (value: T) => void,
): Promise<boolean> {
  try {
    apply(await load());
    return true;
  } catch {
    return false;
  }
}


function formatBytes(value: number, locale: Locale): string {
  if (value < 1024) return `${value} B`;
  return new Intl.NumberFormat(locale === "zh" ? "zh-CN" : "en-US", {
    maximumFractionDigits: 1,
  }).format(value / 1024) + " KB";
}


function AdminOperationsPanel({ token, locale }: { token: string; locale: Locale }) {
  const c = operationsCopy[locale];
  const [users, setUsers] = useState<AdminUsersPage | null>(null);
  const [jobs, setJobs] = useState<AdminJobsResponse | null>(null);
  const [audit, setAudit] = useState<AdminAuditPage | null>(null);
  const [backups, setBackups] = useState<ManagedBackupsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState<"create" | "validate" | null>(null);
  const [selectedBackup, setSelectedBackup] = useState<ManagedBackup | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let active = true;
    Promise.all([
      api.listAdminUsers(token, 1, 20),
      api.getAdminJobs(token),
      api.listAdminAudit(token, 1, 20),
      api.listAdminBackups(token),
    ]).then(([nextUsers, nextJobs, nextAudit, nextBackups]) => {
      if (!active) return;
      setUsers(nextUsers);
      setJobs(nextJobs);
      setAudit(nextAudit);
      setBackups(nextBackups);
    }).catch((caught: unknown) => {
      if (active) setError(errorMessage(caught, locale));
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [locale, nonce, token]);

  async function loadUsers(page: number) {
    try {
      setUsers(await api.listAdminUsers(token, page, 20));
    } catch (caught) {
      setError(errorMessage(caught, locale));
    }
  }

  async function loadAudit(page: number) {
    try {
      setAudit(await api.listAdminAudit(token, page, 20));
    } catch (caught) {
      setError(errorMessage(caught, locale));
    }
  }

  async function createBackup() {
    setBusy("create");
    setError("");
    setNotice("");
    try {
      const created = await api.createAdminBackup(token);
      setBackups((current) => ({
        items: [created, ...(current?.items ?? [])],
        total: (current?.total ?? 0) + 1,
      }));
      setNotice(c.created);
      await refreshAdminAudit(
        () => api.listAdminAudit(token, audit?.page ?? 1, 20),
        setAudit,
      );
    } catch (caught) {
      setError(errorMessage(caught, locale));
    } finally {
      setBusy(null);
    }
  }

  async function validateRestore() {
    if (!selectedBackup) return;
    setBusy("validate");
    setError("");
    setNotice("");
    try {
      await api.validateAdminRestore(token, selectedBackup.id);
      setSelectedBackup(null);
      setNotice(c.validated);
      await refreshAdminAudit(
        () => api.listAdminAudit(token, audit?.page ?? 1, 20),
        setAudit,
      );
    } catch (caught) {
      setError(errorMessage(caught, locale));
    } finally {
      setBusy(null);
    }
  }

  const dateFormat = new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  });

  return (
    <div className="admin-operations" data-testid="admin-operations" aria-busy={loading}>
      {(error || notice) && (
        <div className={error ? "admin-operations-notice error" : "admin-operations-notice"} role={error ? "alert" : "status"}>
          <span>{error || notice}</span>
          {error && <button type="button" onClick={() => {
            setLoading(true);
            setError("");
            setNonce((value) => value + 1);
          }}>{c.retry}</button>}
        </div>
      )}
      {loading && <p className="admin-operations-loading"><LoaderCircle className="spin" size={18} /> {c.loading}</p>}

      <section className="admin-operation-card admin-users-card" data-testid="admin-users">
        <header><Users size={18} /><div><span>01</span><h2>{c.users}</h2></div></header>
        {users?.items.length ? (
          <div className="admin-operation-table-wrap"><table><thead><tr><th>{c.email}</th><th>{c.materials}</th><th>{c.storage}</th><th>{c.workspaces}</th></tr></thead><tbody>
            {users.items.map((user) => <tr key={user.id}><td><strong>{user.display_name}</strong><small>{user.email} · {roleLabel(user.role, locale)}</small></td><td>{user.usage.materials}/{user.quotas.materials}</td><td>{formatBytes(user.usage.material_bytes, locale)} / {formatBytes(user.quotas.material_bytes, locale)}</td><td>{user.usage.workspaces}/{user.quotas.workspaces}</td></tr>)}
          </tbody></table></div>
        ) : !loading && <p className="admin-operation-empty">{c.emptyUsers}</p>}
        {users && users.pages > 1 && <footer className="admin-operation-pagination"><span>{users.page}/{users.pages}</span><button disabled={users.page <= 1} onClick={() => void loadUsers(users.page - 1)}>{c.previous}</button><button disabled={users.page >= users.pages} onClick={() => void loadUsers(users.page + 1)}>{c.next}</button></footer>}
      </section>

      <section className="admin-operation-card" data-testid="admin-jobs">
        <header><ListChecks size={18} /><div><span>02</span><h2>{c.jobs}</h2></div></header>
        <div className="admin-job-grid">
          {jobs?.items.map((job) => <article key={job.id}><span className={`admin-job-status ${job.status}`}>{job.status === "idle" ? c.idle : c.pending}</span><strong>{job.id === "material_index" ? c.materialIndex : c.embeddingBackfill}</strong><dl><div><dt>{c.pending}</dt><dd>{job.pending}</dd></div><div><dt>{c.complete}</dt><dd>{job.completed}</dd></div><div><dt>{c.failed}</dt><dd>{job.failed}</dd></div></dl></article>)}
        </div>
      </section>

      <section className="admin-operation-card" data-testid="admin-activity">
        <header><Activity size={18} /><div><span>03</span><h2>{c.activity}</h2></div></header>
        {audit?.items.length ? <ol className="admin-audit-list">{audit.items.map((entry) => <li key={entry.id}><i /><div><strong>{auditActionLabel(entry.action, locale)}</strong><span>{entry.actor_email} · {entry.target}</span></div><time dateTime={entry.created_at}>{dateFormat.format(new Date(entry.created_at))}</time></li>)}</ol> : !loading && <p className="admin-operation-empty">{c.emptyAudit}</p>}
        {audit && audit.pages > 1 && <footer className="admin-operation-pagination"><span>{audit.page}/{audit.pages}</span><button disabled={audit.page <= 1} onClick={() => void loadAudit(audit.page - 1)}>{c.previous}</button><button disabled={audit.page >= audit.pages} onClick={() => void loadAudit(audit.page + 1)}>{c.next}</button></footer>}
      </section>

      <section className="admin-operation-card admin-backup-card" data-testid="admin-backups">
        <header><ArchiveRestore size={18} /><div><span>04</span><h2>{c.backups}</h2></div><button type="button" className="primary-action" data-testid="admin-create-backup" disabled={busy !== null} onClick={() => void createBackup()}>{busy === "create" ? c.creating : c.createBackup}</button></header>
        {backups?.items.length ? <ul className="admin-backup-list">{backups.items.map((backup) => <li key={backup.id}><div><strong>{backup.id}</strong><span>{dateFormat.format(new Date(backup.created_at))} · {backup.file_count} {c.files} · {formatBytes(backup.total_bytes, locale)}</span></div><button type="button" className="secondary-action" onClick={() => setSelectedBackup(backup)}>{c.validate}</button></li>)}</ul> : !loading && <p className="admin-operation-empty">{c.emptyBackups}</p>}
      </section>

      <ConfirmDialog
        open={selectedBackup !== null}
        title={c.confirmTitle}
        description={`${c.confirmDescription} RESTORE ${selectedBackup?.id ?? ""}`}
        confirmLabel={c.confirm}
        cancelLabel={c.cancel}
        busy={busy === "validate"}
        onConfirm={validateRestore}
        onCancel={() => setSelectedBackup(null)}
      />
    </div>
  );
}

function IntegrationCard({
  token,
  definition,
  setting,
  locale,
  onChange,
  locked = false,
}: {
  token: string;
  definition: IntegrationDefinition;
  setting: PublicIntegrationSettings;
  locale: Locale;
  onChange: (setting: PublicIntegrationSettings) => void;
  locked?: boolean;
}) {
  const c = copy[locale];
  const [enabled, setEnabled] = useState(setting.enabled);
  const [config, setConfig] = useState(setting.config);
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<"save" | "test" | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [pendingHref, setPendingHref] = useState<string | null>(null);
  const isDirty = enabled !== setting.enabled
    || JSON.stringify(config) !== JSON.stringify(setting.config)
    || Object.values(secrets).some((value) => value.length > 0);

  useEffect(() => {
    if (!isDirty) return;
    const beforeunload = (event: BeforeUnloadEvent) => event.preventDefault();
    const guardNavigation = (event: MouseEvent) => {
      const target = event.target as Element | null;
      const link = target?.closest("a[href]") as HTMLAnchorElement | null;
      if (!link || link.target === "_blank" || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const destination = new URL(link.href, window.location.href);
      if (destination.origin !== window.location.origin || destination.hash && destination.pathname === window.location.pathname) return;
      event.preventDefault();
      setPendingHref(destination.href);
    };
    window.addEventListener("beforeunload", beforeunload);
    document.addEventListener("click", guardNavigation, true);
    return () => {
      window.removeEventListener("beforeunload", beforeunload);
      document.removeEventListener("click", guardNavigation, true);
    };
  }, [c.unsavedWarning, isDirty]);

  async function persistConfiguration(): Promise<PublicIntegrationSettings> {
    return api.updateIntegration(token, definition.kind, { enabled, config, secrets });
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy("save");
    setError("");
    setNotice("");
    try {
      const updated = await persistConfiguration();
      setSecrets({});
      setConfig(updated.config);
      setEnabled(updated.enabled);
      setNotice(c.saved);
      onChange(updated);
    } catch (caught) {
      setError(errorMessage(caught, locale));
    } finally {
      setBusy(null);
    }
  }

  async function testConnection() {
    setBusy("test");
    setError("");
    setNotice("");
    try {
      const result = await api.testIntegration(token, definition.kind);
      onChange(projectIntegrationTestResult(setting, result, new Date().toISOString()));
      if (result.status === "failed") setError(c.connectionFailed);
      else setNotice(c.connectionSucceeded);
    } catch (caught) {
      setError(errorMessage(caught, locale));
    } finally {
      setBusy(null);
    }
  }

  async function saveAndTest() {
    setBusy("save");
    setError("");
    setNotice("");
    try {
      const updated = await persistConfiguration();
      setSecrets({});
      setConfig(updated.config);
      setEnabled(updated.enabled);
      onChange(updated);
      setBusy("test");
      const result = await api.testIntegration(token, definition.kind);
      const projected = projectIntegrationTestResult(updated, result, new Date().toISOString());
      onChange(projected);
      if (result.status === "failed") setError(c.connectionFailed);
      else setNotice(c.connectionSucceeded);
    } catch (caught) {
      setError(errorMessage(caught, locale));
    } finally {
      setBusy(null);
    }
  }

  function updateConfig(field: FieldDefinition, value: string) {
    setConfig((current) => ({
      ...current,
      [field.key]: field.type === "number"
        ? Number(value)
        : field.type === "boolean"
          ? value === "true"
          : value,
    }));
  }

  function renderConfigField(field: FieldDefinition) {
    return (
      <label key={field.key}>
        <span>{field.label}</span>
        {field.type === "select" || field.type === "boolean" ? (
          <select
            value={String(config[field.key] ?? "")}
            onChange={(event) => updateConfig(field, event.target.value)}
          >
            {field.options?.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        ) : (
          <input
            type={field.type === "number" ? "number" : "text"}
            step={field.key === "temperature" ? "0.1" : undefined}
            value={String(config[field.key] ?? "")}
            placeholder={field.placeholder}
            onChange={(event) => updateConfig(field, event.target.value)}
            required
          />
        )}
      </label>
    );
  }

  const basicFields = definition.configFields.filter(
    (field) => field.key !== "allow_private_network",
  );
  const networkFields = definition.configFields.filter(
    (field) => field.key === "allow_private_network",
  );

  return (
    <article
      className={`integration-card integration-${definition.kind}`}
      data-testid={`integration-card-${definition.kind}`}
    >
      <form onSubmit={save}>
        <fieldset className="integration-fieldset" disabled={locked}>
        <section className="admin-service-control">
          <div>
            <span className="kicker">SERVICE CONTROL</span>
            <h2>{c.serviceStatus}</h2>
            <p>{c.serviceStatusDescription}</p>
          </div>
          <label className="integration-switch">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(event) => setEnabled(event.target.checked)}
            />
            <span>{enabled ? c.active : c.inactive}</span>
          </label>
          <div className="integration-health-row">
            <span className={setting.configured ? "healthy" : "waiting"}>
              {setting.configured ? <Check size={13} /> : <TriangleAlert size={13} />}
              {setting.configured ? c.ready : c.missing}
            </span>
            {setting.last_test_status && (
              <span className={setting.last_test_status === "ok" ? "healthy" : "failed"}>
                <PlugZap size={13} /> {setting.last_test_status === "ok" ? c.connectionSucceeded : c.connectionFailed}
              </span>
            )}
          </div>
        </section>

        <section className="admin-form-section" data-testid="admin-form-section-basic">
          <header className="admin-form-section-header">
            <span>01</span>
            <div>
              <h3>{c.basicSettings}</h3>
              <p>{c.basicSettingsDescription}</p>
            </div>
          </header>
          <div className="integration-fields">
            {basicFields.map(renderConfigField)}
          </div>
        </section>

        <section className="admin-form-section" data-testid="admin-form-section-credentials">
          <header className="admin-form-section-header">
            <span>02</span>
            <div>
              <h3>{c.credentials}</h3>
              <p>{c.credentialsDescription}</p>
            </div>
          </header>
          <div className="integration-fields integration-secret-fields">
            {definition.secretFields.map((field) => (
              <label key={field.key}>
                <span>
                  {field.label}
                  {setting.secret_hints[field.key] && <em>{setting.secret_hints[field.key]}</em>}
                </span>
                <input
                  type="password"
                  value={secrets[field.key] ?? ""}
                  placeholder={c.secretHint}
                  onChange={(event) => setSecrets((current) => ({
                    ...current,
                    [field.key]: event.target.value,
                  }))}
                />
              </label>
            ))}
          </div>
        </section>

        <section className="admin-form-section" data-testid="admin-form-section-network">
          <header className="admin-form-section-header">
            <span>03</span>
            <div>
              <h3>{c.networkSecurity}</h3>
              <p>{c.networkSecurityDescription}</p>
            </div>
          </header>
          <div className="integration-fields integration-network-fields">
            {networkFields.map(renderConfigField)}
          </div>
          <p className="admin-network-note">
            <TriangleAlert size={14} /> {c.networkWarning}
          </p>
        </section>
        {(notice || error) && (
          <p className={error ? "integration-notice error" : "integration-notice"} role="status">
            {error || notice}
          </p>
        )}
        <footer className="integration-actions">
          {isDirty && <span className="integration-dirty">{c.unsaved}</span>}
          <button
            type="button"
            className="quiet-button"
            onClick={() => void testConnection()}
            disabled={busy !== null || !setting.configured || isDirty}
          >
            {busy === "test" ? <LoaderCircle className="spin" size={15} /> : <PlugZap size={15} />}
            {busy === "test" ? c.testing : c.test}
          </button>
          <button
            type="button"
            data-testid="admin-save-test"
            className="secondary-action"
            onClick={() => void saveAndTest()}
            disabled={busy !== null}
          >
            {busy === "test" ? <LoaderCircle className="spin" size={15} /> : <PlugZap size={15} />}
            {c.saveTest}
          </button>
          <button className="primary-action" disabled={busy !== null}>
            {busy === "save" ? <LoaderCircle className="spin" size={15} /> : <Save size={15} />}
            {busy === "save" ? c.saving : c.save}
          </button>
        </footer>
        </fieldset>
      </form>
      <ConfirmDialog
        open={pendingHref !== null}
        title={c.unsaved}
        description={c.unsavedWarning}
        confirmLabel={c.discard}
        cancelLabel={c.stay}
        tone="danger"
        onConfirm={() => {
          if (pendingHref) window.location.assign(pendingHref);
        }}
        onCancel={() => setPendingHref(null)}
      />
    </article>
  );
}

export function AdminConsole({
  token,
  locale,
  activeKind,
  activeSection,
  workspaces = [],
  onLogout,
  onToggleLocale,
}: {
  token: string;
  locale: Locale;
  activeKind?: IntegrationKind;
  activeSection?: "overview" | "operations";
  workspaces?: LearningWorkspace[];
  onLogout: () => void;
  onToggleLocale: () => void;
}) {
  const c = copy[locale];
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [integrations, setIntegrations] = useState(defaults);
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadNonce, setLoadNonce] = useState(0);
  const byKind = useMemo(
    () => new Map(integrations.map((integration) => [integration.kind, integration])),
    [integrations],
  );

  useEffect(() => {
    if (activeSection === "operations") return;
    let active = true;
    Promise.all([api.getAdminOverview(token), api.listIntegrations(token)])
      .then(([nextOverview, nextIntegrations]) => {
        if (!active) return;
        setOverview(nextOverview);
        setIntegrations(nextIntegrations);
      })
      .catch((caught: unknown) => {
        if (active) setLoadError(errorMessage(caught, locale));
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [activeSection, locale, token, loadNonce]);

  function updateIntegration(updated: PublicIntegrationSettings) {
    setIntegrations((current) => current.map((item) => (
      item.kind === updated.kind ? updated : item
    )));
  }

  const localizedDefinitions = definitions[locale];
  const activeDefinition = activeKind
    ? localizedDefinitions.find((definition) => definition.kind === activeKind)
    : undefined;
  const configuredCount = integrations.filter((integration) => integration.configured).length;
  const effectiveConfiguredCount = overview?.integrations_configured ?? configuredCount;
  const nextSetting = integrations.find((integration) => integration.last_test_status === "failed")
    ?? integrations.find((integration) => !integration.configured);
  const nextDefinition = nextSetting
    ? localizedDefinitions.find((definition) => definition.kind === nextSetting.kind)
    : undefined;

  return (
    <main id="main-content" className="admin-console">
      <div className="admin-shell">
        <AppSidebar
          locale={locale}
          active="admin"
          workspaces={workspaces}
          isAdmin
          contextOwnsActive
          contextLabel={c.title}
          contextNavigation={(
          <div className="admin-nav">
            <Link className={!activeKind && activeSection !== "operations" ? "active" : ""} href="/admin">
              <LayoutDashboard size={18} />
              <span>{c.overview}</span>
            </Link>
            <Link className={activeSection === "operations" ? "active" : ""} href="/admin/operations">
              <Activity size={18} />
              <span>{operationsCopy[locale].nav}</span>
            </Link>
            <span className="admin-nav-label">{c.integrations}</span>
            {localizedDefinitions.map(({ kind, icon: Icon, title }) => {
              const setting = byKind.get(kind);
              return (
              <Link
                key={kind}
                className={activeKind === kind ? "active" : ""}
                href={`/admin/integrations/${kind}`}
              >
                <Icon size={18} />
                <span>{title}</span>
                <i
                  className={`admin-nav-status ${setting?.configured ? "ready" : ""}`}
                  aria-label={setting?.configured ? c.ready : c.missing}
                />
              </Link>
              );
            })}
          </div>
          )}
          onToggleLocale={onToggleLocale}
          onLogout={onLogout}
        />

        <section className="admin-main">
          <header className="admin-page-header">
            <div>
              <span className="kicker">
                {activeSection === "operations"
                  ? "REFINEQ / OPERATIONS"
                  : activeDefinition ? activeDefinition.eyebrow : "REFINEQ / SETTINGS"}
              </span>
              <h1>{activeSection === "operations" ? operationsCopy[locale].title : activeDefinition?.title ?? c.title}</h1>
              <p>{activeSection === "operations" ? operationsCopy[locale].subtitle : activeDefinition?.description ?? c.subtitle}</p>
            </div>
          </header>

          {loadError && (
            <div className="admin-load-error" role="alert">
              <TriangleAlert size={20} />
              <div><strong>{c.loadFailed}</strong><span>{loadError}</span></div>
              <button type="button" className="secondary-action" onClick={() => {
                setLoading(true);
                setLoadError("");
                setLoadNonce((current) => current + 1);
              }}>{c.reload}</button>
            </div>
          )}

          {activeSection === "operations" ? (
            <AdminOperationsPanel token={token} locale={locale} />
          ) : loadError ? null : activeDefinition && activeKind ? (
            <div className="admin-integration-detail" data-testid="admin-integration-detail">
              <Link className="admin-detail-back" href="/admin">
                <ArrowLeft size={15} /> {c.backOverview}
              </Link>
              <IntegrationCard
                key={`${activeKind}-${byKind.get(activeKind)?.enabled}-${JSON.stringify(
                  byKind.get(activeKind)?.config,
                )}`}
                token={token}
                definition={activeDefinition}
                setting={byKind.get(activeKind) ?? defaults[0]}
                locale={locale}
                onChange={updateIntegration}
                locked={loading}
              />
            </div>
          ) : (
            <div className="admin-overview" data-testid="admin-overview">
              <section
                className="admin-system-status"
                data-testid="admin-system-status"
                aria-label={c.loading}
              >
                <header>
                  <span className="kicker">SYSTEM HEALTH</span>
                  <h2>{c.systemStatus}</h2>
                </header>
                <article>
                  <Database size={17} />
                  <div>
                  <span>{c.users}</span>
                  <strong>{overview?.users ?? "—"}</strong>
                  </div>
                </article>
                <article>
                  <HardDrive size={17} />
                  <div>
                  <span>{c.database}</span>
                  <strong>{overview?.database ?? "—"}</strong>
                  </div>
                </article>
                <article>
                  <Gauge size={17} />
                  <div>
                  <span>{c.vector}</span>
                  <strong>{overview ? (overview.pgvector ? "pgvector" : "fallback") : "—"}</strong>
                  </div>
                </article>
                <article>
                  <PlugZap size={17} />
                  <div>
                  <span>{c.configured}</span>
                  <strong>{effectiveConfiguredCount}/4</strong>
                  </div>
                </article>
              </section>

              <div className="admin-overview-grid">
                <section className="admin-next-action" data-testid="admin-next-action">
                  <div>
                    <span className="kicker">NEXT ACTION</span>
                    <h2>{c.nextAction}</h2>
                  </div>
                  {nextDefinition && nextSetting ? (
                    <div className="admin-next-action-body">
                      <span className="admin-next-action-icon">
                        <nextDefinition.icon size={22} />
                      </span>
                      <div>
                        <h3>
                          {nextSetting.last_test_status === "failed"
                            ? `${c.retrySetup}：${nextDefinition.title}`
                            : `${c.completeSetup}：${nextDefinition.title}`}
                        </h3>
                        <p>
                          {nextSetting.last_test_status === "failed"
                            ? c.connectionFailed
                            : nextDefinition.description}
                        </p>
                      </div>
                      <Link
                        className="primary-action"
                        href={`/admin/integrations/${nextDefinition.kind}`}
                      >
                        {c.configure} <ArrowRight size={15} />
                      </Link>
                    </div>
                  ) : (
                    <div className="admin-next-action-body is-ready">
                      <span className="admin-next-action-icon"><Check size={22} /></span>
                      <div>
                        <h3>{c.allReady}</h3>
                        <p>{c.allReadyDescription}</p>
                      </div>
                    </div>
                  )}
                  <div className="admin-setup-progress">
                    <span>{c.setupProgress}</span>
                    <strong>{effectiveConfiguredCount}/4</strong>
                    <div><i style={{ width: `${effectiveConfiguredCount * 25}%` }} /></div>
                  </div>
                </section>

                <aside className="admin-principles" data-testid="admin-principles">
                  <div>
                    <span className="kicker">GUARDRAILS</span>
                    <h2>{c.principles}</h2>
                  </div>
                  <ul>
                    <li>
                      <FileScan size={17} />
                      <span><strong>{c.localParsing}</strong><small>{c.localParsingDescription}</small></span>
                    </li>
                    <li>
                      <ShieldCheck size={17} />
                      <span><strong>{c.encrypted}</strong><small>{c.encryptedDescription}</small></span>
                    </li>
                    <li>
                      <PlugZap size={17} />
                      <span><strong>{c.onDemand}</strong><small>{c.onDemandDescription}</small></span>
                    </li>
                  </ul>
                </aside>
              </div>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
