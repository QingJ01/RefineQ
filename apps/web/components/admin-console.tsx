"use client";

import {
  ArrowLeft,
  BrainCircuit,
  Check,
  Database,
  FileScan,
  HardDrive,
  LoaderCircle,
  LogOut,
  PlugZap,
  Save,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { BrandMark, BrandName } from "@/components/brand";
import { api, ApiError } from "@/lib/api";
import type {
  AdminOverview,
  IntegrationKind,
  Locale,
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
    title: "平台控制台",
    subtitle: "集中管理学习 Agent 的数据库、模型、识别与文件能力。密钥只在服务端加密保存。",
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
  },
  en: {
    title: "Platform console",
    subtitle: "Manage the learning Agent database, models, recognition, and files in one place.",
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

function errorMessage(caught: unknown): string {
  if (caught instanceof ApiError) return `${caught.code}: ${caught.message}`;
  return caught instanceof Error ? caught.message : "Request failed";
}

function IntegrationCard({
  token,
  definition,
  setting,
  locale,
  onChange,
}: {
  token: string;
  definition: IntegrationDefinition;
  setting: PublicIntegrationSettings;
  locale: Locale;
  onChange: (setting: PublicIntegrationSettings) => void;
}) {
  const c = copy[locale];
  const Icon = definition.icon;
  const [enabled, setEnabled] = useState(setting.enabled);
  const [config, setConfig] = useState(setting.config);
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<"save" | "test" | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy("save");
    setError("");
    setNotice("");
    try {
      const updated = await api.updateIntegration(token, definition.kind, {
        enabled,
        config,
        secrets,
      });
      setSecrets({});
      setNotice(c.saved);
      onChange(updated);
    } catch (caught) {
      setError(errorMessage(caught));
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
      if (result.status === "failed") setError(result.message);
      else setNotice(result.message);
    } catch (caught) {
      setError(errorMessage(caught));
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

  return (
    <article
      className={`integration-card integration-${definition.kind}`}
      data-testid={`integration-card-${definition.kind}`}
    >
      <form onSubmit={save}>
        <header className="integration-card-header">
          <div className="integration-icon"><Icon size={23} /></div>
          <div>
            <span className="kicker">{definition.eyebrow}</span>
            <h2>{definition.title}</h2>
          </div>
          <label className="integration-switch">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(event) => setEnabled(event.target.checked)}
            />
            <span>{enabled ? c.active : c.inactive}</span>
          </label>
        </header>
        <p className="integration-description">{definition.description}</p>
        <div className="integration-health-row">
          <span className={setting.configured ? "healthy" : "waiting"}>
            {setting.configured ? <Check size={13} /> : <TriangleAlert size={13} />}
            {setting.configured ? c.ready : c.missing}
          </span>
          {setting.last_test_status && (
            <span className={setting.last_test_status === "ok" ? "healthy" : "failed"}>
              <PlugZap size={13} /> {setting.last_test_message}
            </span>
          )}
        </div>
        <div className="integration-fields">
          {definition.configFields.map((field) => (
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
          ))}
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
        {(notice || error) && (
          <p className={error ? "integration-notice error" : "integration-notice"} role="status">
            {error || notice}
          </p>
        )}
        <footer className="integration-actions">
          <button
            type="button"
            className="quiet-button"
            onClick={() => void testConnection()}
            disabled={busy !== null || !setting.configured}
          >
            {busy === "test" ? <LoaderCircle className="spin" size={15} /> : <PlugZap size={15} />}
            {busy === "test" ? c.testing : c.test}
          </button>
          <button className="primary-action" disabled={busy !== null}>
            {busy === "save" ? <LoaderCircle className="spin" size={15} /> : <Save size={15} />}
            {busy === "save" ? c.saving : c.save}
          </button>
        </footer>
      </form>
    </article>
  );
}

export function AdminConsole({
  token,
  locale,
  onClose,
  onLogout,
}: {
  token: string;
  locale: Locale;
  onClose: () => void;
  onLogout: () => void;
}) {
  const c = copy[locale];
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [integrations, setIntegrations] = useState(defaults);
  const [error, setError] = useState("");
  const byKind = useMemo(
    () => new Map(integrations.map((integration) => [integration.kind, integration])),
    [integrations],
  );

  useEffect(() => {
    let active = true;
    Promise.all([api.getAdminOverview(token), api.listIntegrations(token)])
      .then(([nextOverview, nextIntegrations]) => {
        if (!active) return;
        setOverview(nextOverview);
        setIntegrations(nextIntegrations);
      })
      .catch((caught: unknown) => {
        if (active) setError(errorMessage(caught));
      });
    return () => { active = false; };
  }, [token]);

  function updateIntegration(updated: PublicIntegrationSettings) {
    setIntegrations((current) => current.map((item) => (
      item.kind === updated.kind ? updated : item
    )));
  }

  return (
    <main className="admin-console">
      <header className="admin-topbar">
        <div className="admin-brand"><BrandMark size={34} /><BrandName /></div>
        <div className="admin-topbar-actions">
          <button className="quiet-button" onClick={onClose}>
            <ArrowLeft size={16} /> {c.back}
          </button>
          <button data-testid="admin-logout" className="quiet-button" onClick={onLogout}>
            <LogOut size={16} /> {c.logout}
          </button>
        </div>
      </header>
      <section className="admin-stage">
        <div className="admin-hero">
          <div>
            <span className="kicker">REFINEQ / SYSTEM CONTROL</span>
            <h1>{c.title}</h1>
            <p>{c.subtitle}</p>
          </div>
          <div className="admin-security-note">
            <ShieldCheck size={22} />
            <span>SERVER-SIDE ENCRYPTION</span>
          </div>
        </div>
        {error && <div className="error-banner" role="alert">{error}</div>}
        <section className="admin-summary" aria-label={c.loading}>
          <article><span>{c.users}</span><strong>{overview?.users ?? "—"}</strong></article>
          <article><span>{c.database}</span><strong>{overview?.database ?? "—"}</strong></article>
          <article><span>{c.vector}</span><strong>{overview?.pgvector ? "pgvector" : "fallback"}</strong></article>
          <article><span>{c.configured}</span><strong>{overview?.integrations_configured ?? 0}/4</strong></article>
        </section>
        <section className="integration-grid">
          {definitions[locale].map((definition) => (
            <IntegrationCard
              key={`${definition.kind}-${byKind.get(definition.kind)?.enabled}-${JSON.stringify(
                byKind.get(definition.kind)?.config,
              )}`}
              token={token}
              definition={definition}
              setting={byKind.get(definition.kind) ?? defaults[0]}
              locale={locale}
              onChange={updateIntegration}
            />
          ))}
        </section>
      </section>
    </main>
  );
}
