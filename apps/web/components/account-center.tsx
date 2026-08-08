"use client";

import {
  ArrowLeft,
  Check,
  Download,
  KeyRound,
  LoaderCircle,
  LogOut,
  ShieldCheck,
  Trash2,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { AppSidebar } from "@/components/app-sidebar";
import { BrandMark } from "@/components/brand";
import { api, ApiError } from "@/lib/api";
import { localizeApiError } from "@/lib/error-messages";
import { learningPath } from "@/lib/learning-routes";
import {
  loadLearningSession,
  saveLearningLocale,
} from "@/lib/session";
import { clearUserScopedSessionState } from "@/lib/client-session-state";
import type { LearningWorkspace, Locale, User } from "@/lib/types";


const copy = {
  zh: {
    eyebrow: "IDENTITY / CONTROL",
    title: "账户与安全",
    subtitle: "管理你的公开资料、登录凭据与 RefineQ 中保存的学习数据。",
    back: "返回学习",
    language: "EN",
    profile: "个人资料",
    profileHint: "这个名字会出现在你的学习档案和反馈中。",
    displayName: "显示名称",
    email: "登录邮箱",
    saveProfile: "保存资料",
    savedProfile: "个人资料已更新",
    password: "修改密码",
    passwordHint: "修改后，所有已签发的登录令牌都会立即失效。",
    currentPassword: "当前密码",
    newPassword: "新密码",
    passwordRule: "至少 12 个 UTF-8 字节",
    changePassword: "更新密码",
    passwordChanged: "密码已更新，请重新登录",
    data: "数据与会话",
    dataHint: "下载账户、学习状态与资料元数据的 JSON 副本（不含资料原文件），或让所有设备退出登录。",
    export: "导出我的数据",
    exporting: "正在整理导出",
    logoutAll: "退出所有设备",
    logoutAllHint: "包括当前浏览器在内的全部会话都会失效。",
    danger: "危险区域",
    dangerHint: "删除后，账户、学习空间、资料索引、练习和对话无法恢复。",
    typeToConfirm: (email: string) => `请输入 ${email} 以确认`,
    confirmation: "确认邮箱",
    deletePassword: "当前密码",
    delete: "永久删除账户",
    deleting: "正在安全删除",
    working: "处理中…",
    genericError: "操作没有完成，请稍后重试。",
  },
  en: {
    eyebrow: "IDENTITY / CONTROL",
    title: "Account & security",
    subtitle: "Manage your public profile, sign-in credentials, and the learning data stored in RefineQ.",
    back: "Back to learning",
    language: "中文",
    profile: "Profile",
    profileHint: "This name appears across your learning record and feedback.",
    displayName: "Display name",
    email: "Sign-in email",
    saveProfile: "Save profile",
    savedProfile: "Profile updated",
    password: "Change password",
    passwordHint: "Changing it immediately invalidates every issued access token.",
    currentPassword: "Current password",
    newPassword: "New password",
    passwordRule: "At least 12 UTF-8 bytes",
    changePassword: "Update password",
    passwordChanged: "Password updated. Sign in again",
    data: "Data & sessions",
    dataHint: "Download account, learning-state, and material metadata as JSON (original files are not included), or sign every device out at once.",
    export: "Export my data",
    exporting: "Preparing export",
    logoutAll: "Sign out everywhere",
    logoutAllHint: "Every session, including this browser, will become invalid.",
    danger: "Danger zone",
    dangerHint: "Your account, learning spaces, material index, practice, and conversations cannot be recovered.",
    typeToConfirm: (email: string) => `Type ${email} to confirm`,
    confirmation: "Confirmation email",
    deletePassword: "Current password",
    delete: "Delete account permanently",
    deleting: "Deleting safely",
    working: "Working…",
    genericError: "The action did not finish. Try again shortly.",
  },
} as const;

export function shouldClearAccountSession(caught: unknown): boolean {
  return caught instanceof ApiError && (caught.status === 401 || caught.status === 403);
}

type Action = "profile" | "password" | "export" | "sessions" | "delete";

export function AccountCenter({
  locale,
  user,
  workspaces = [],
  busy,
  backHref = "/",
  onToggleLocale,
  onUpdateProfile,
  onChangePassword,
  onExport,
  onLogoutAll,
  onDeleteAccount,
  onLogout,
}: {
  locale: Locale;
  user: User;
  workspaces?: LearningWorkspace[];
  busy: boolean;
  backHref?: string;
  onToggleLocale?: () => void;
  onUpdateProfile: (displayName: string) => void | Promise<void>;
  onChangePassword: (currentPassword: string, newPassword: string) => void | Promise<void>;
  onExport: () => void | Promise<void>;
  onLogoutAll: () => void | Promise<void>;
  onDeleteAccount: (currentPassword: string, confirmation: string) => void | Promise<void>;
  onLogout?: () => void;
}) {
  const text = copy[locale];
  const [displayName, setDisplayName] = useState(user.display_name);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [deletePassword, setDeletePassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [pending, setPending] = useState<Action | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  async function run(action: Action, task: () => void | Promise<void>, success = "") {
    setPending(action);
    setNotice("");
    setError("");
    try {
      await task();
      setNotice(success);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : text.genericError);
    } finally {
      setPending(null);
    }
  }

  async function submitProfile(event: FormEvent) {
    event.preventDefault();
    const normalized = displayName.trim();
    if (!normalized || normalized === user.display_name) return;
    await run("profile", () => onUpdateProfile(normalized), text.savedProfile);
  }

  async function submitPassword(event: FormEvent) {
    event.preventDefault();
    if (!currentPassword || !newPassword) return;
    await run("password", async () => {
      await onChangePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
    }, text.passwordChanged);
  }

  async function submitDelete(event: FormEvent) {
    event.preventDefault();
    if (confirmation.trim().toLowerCase() !== user.email.toLowerCase() || !deletePassword) return;
    await run("delete", () => onDeleteAccount(deletePassword, confirmation.trim()));
  }

  const disabled = busy || pending !== null;
  const deletionConfirmed = confirmation.trim().toLowerCase() === user.email.toLowerCase();

  return (
    <main id="main-content" className="account-shell" data-testid="account-center">
      <AppSidebar
        locale={locale}
        active="account"
        workspaces={workspaces}
        isAdmin={user.role === "admin"}
        contextLabel={text.title}
        contextNavigation={(
          <>
            <a href="#profile"><UserRound size={17} /> <span>{text.profile}</span></a>
            <a href="#security"><KeyRound size={17} /> <span>{text.password}</span></a>
            <a href="#data-sessions"><Download size={17} /> <span>{text.data}</span></a>
            <a href="#danger-zone"><Trash2 size={17} /> <span>{text.danger}</span></a>
          </>
        )}
        onToggleLocale={onToggleLocale ?? (() => undefined)}
        onLogout={onLogout ?? (() => undefined)}
      />
      <section className="account-main">
      <header className="account-header">
        <div className="account-header-actions">
          <Link className="secondary-action" href={backHref}>
            <ArrowLeft size={16} /> {text.back}
          </Link>
        </div>
      </header>

      <section className="account-intro">
        <span className="kicker">{text.eyebrow}</span>
        <h1>{text.title}</h1>
        <p>{text.subtitle}</p>
        <div className="account-identity-stamp" aria-label={`${user.display_name}, ${user.email}`}>
          <span><UserRound size={18} /></span>
          <strong>{user.display_name}</strong>
          <small>{user.email}</small>
        </div>
      </section>

      {(notice || error) && (
        <div className={`account-message ${error ? "error" : "success"}`} role="status" aria-live="polite">
          {error ? null : <Check size={16} />}{error || notice}
        </div>
      )}

      <div className="account-grid">
        <section id="profile" className="account-panel account-profile-panel">
          <div className="account-panel-heading">
            <span><UserRound size={19} /></span>
            <div><h2>{text.profile}</h2><p>{text.profileHint}</p></div>
          </div>
          <form data-testid="account-profile-form" onSubmit={(event) => void submitProfile(event)}>
            <label>{text.displayName}
              <input value={displayName} maxLength={100} onChange={(event) => setDisplayName(event.target.value)} />
            </label>
            <label>{text.email}
              <input value={user.email} disabled readOnly />
            </label>
            <button className="primary-action" disabled={disabled || !displayName.trim() || displayName.trim() === user.display_name}>
              {pending === "profile" ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}
              {pending === "profile" ? text.working : text.saveProfile}
            </button>
          </form>
        </section>

        <section id="security" className="account-panel account-password-panel">
          <div className="account-panel-heading">
            <span><KeyRound size={19} /></span>
            <div><h2>{text.password}</h2><p>{text.passwordHint}</p></div>
          </div>
          <form data-testid="account-password-form" onSubmit={(event) => void submitPassword(event)}>
            <label>{text.currentPassword}
              <input type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} />
            </label>
            <label>{text.newPassword}
              <input type="password" autoComplete="new-password" minLength={12} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} />
              <small>{text.passwordRule}</small>
            </label>
            <button className="primary-action" disabled={disabled || !currentPassword || !newPassword}>
              {pending === "password" ? <LoaderCircle className="spin" size={16} /> : <ShieldCheck size={16} />}
              {pending === "password" ? text.working : text.changePassword}
            </button>
          </form>
        </section>

        <section id="data-sessions" className="account-panel account-data-panel">
          <div className="account-panel-heading">
            <span><Download size={19} /></span>
            <div><h2>{text.data}</h2><p>{text.dataHint}</p></div>
          </div>
          <div className="account-data-actions">
            <button data-testid="account-export" className="secondary-action" type="button" disabled={disabled} onClick={() => void run("export", onExport)}>
              {pending === "export" ? <LoaderCircle className="spin" size={16} /> : <Download size={16} />}
              {pending === "export" ? text.exporting : text.export}
            </button>
            <div className="account-session-row">
              <div><strong>{text.logoutAll}</strong><small>{text.logoutAllHint}</small></div>
              <button data-testid="account-logout-all" className="secondary-action" type="button" disabled={disabled} onClick={() => void run("sessions", onLogoutAll)}>
                {pending === "sessions" ? <LoaderCircle className="spin" size={16} /> : <LogOut size={16} />}
                {pending === "sessions" ? text.working : text.logoutAll}
              </button>
            </div>
          </div>
        </section>

        <section id="danger-zone" className="account-panel account-danger-panel">
          <div className="account-panel-heading">
            <span><Trash2 size={19} /></span>
            <div><h2>{text.danger}</h2><p>{text.dangerHint}</p></div>
          </div>
          <form onSubmit={(event) => void submitDelete(event)}>
            <p className="account-confirm-copy">{text.typeToConfirm(user.email)}</p>
            <label>{text.confirmation}
              <input data-testid="account-delete-confirmation" autoComplete="off" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
            </label>
            <label>{text.deletePassword}
              <input type="password" autoComplete="current-password" value={deletePassword} onChange={(event) => setDeletePassword(event.target.value)} />
            </label>
            <button className="danger-action" disabled={disabled || !deletionConfirmed || !deletePassword}>
              {pending === "delete" ? <LoaderCircle className="spin" size={16} /> : <Trash2 size={16} />}
              {pending === "delete" ? text.deleting : text.delete}
            </button>
          </form>
        </section>
      </div>
      </section>
    </main>
  );
}

export function AccountRoute() {
  const router = useRouter();
  const [locale, setLocale] = useState<Locale>("zh");
  const [token, setToken] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [workspaces, setWorkspaces] = useState<LearningWorkspace[]>([]);
  const [backHref, setBackHref] = useState("/");
  const [loadError, setLoadError] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let active = true;
    const saved = loadLearningSession(window.sessionStorage);
    if (!saved) {
      router.replace("/");
      return;
    }
    const savedLocale = saved.locale ?? "zh";
    void Promise.resolve().then(() => {
      if (active) {
        setLocale(savedLocale);
        setLoadError("");
      }
      return Promise.all([
        api.getProfile(saved.token),
        api.listWorkspaces(saved.token).catch(() => []),
      ]);
    }).then(([profile, nextWorkspaces]) => {
      if (!active) return;
      setToken(saved.token);
      setWorkspaces(nextWorkspaces);
      setBackHref(saved.workspaceId ? learningPath(saved.workspaceId, "today") : "/");
      setUser(profile);
    }).catch((caught) => {
      if (shouldClearAccountSession(caught)) {
        api.clearReadCache(saved.token);
        clearUserScopedSessionState(window.sessionStorage);
        router.replace("/");
        return;
      }
      if (active) setLoadError(localizeApiError(caught, savedLocale));
    });
    return () => { active = false; };
  }, [reload, router]);

  function localized<T>(task: Promise<T>): Promise<T> {
    return task.catch((caught) => {
      throw new Error(localizeApiError(caught, locale));
    });
  }

  function exitAccount() {
    api.clearReadCache(token);
    clearUserScopedSessionState(window.sessionStorage);
    router.replace("/");
  }

  if (!user || !token) {
    return (
      <main id="main-content" className="account-loading" aria-live="polite">
        <BrandMark size={42} />
        {loadError ? (
          <div role="alert">
            <p>{loadError}</p>
            <button type="button" onClick={() => setReload((value) => value + 1)}>{locale === "zh" ? "重试" : "Retry"}</button>
            <Link href="/">{locale === "zh" ? "返回学习首页" : "Back to learning"}</Link>
          </div>
        ) : <LoaderCircle className="spin" size={22} />}
      </main>
    );
  }

  return (
    <AccountCenter
      locale={locale}
      user={user}
      workspaces={workspaces}
      busy={false}
      backHref={backHref}
      onToggleLocale={() => {
        const next = locale === "zh" ? "en" : "zh";
        setLocale(next);
        saveLearningLocale(window.sessionStorage, token, next);
      }}
      onLogout={exitAccount}
      onUpdateProfile={async (displayName) => {
        setUser(await localized(api.updateProfile(token, displayName)));
      }}
      onChangePassword={async (currentPassword, newPassword) => {
        await localized(api.changePassword(token, currentPassword, newPassword));
        exitAccount();
      }}
      onExport={async () => {
        const exported = await localized(api.exportAccount(token));
        const url = URL.createObjectURL(new Blob(
          [JSON.stringify(exported, null, 2)],
          { type: "application/json" },
        ));
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `refineq-account-${new Date().toISOString().slice(0, 10)}.json`;
        anchor.click();
        window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
      }}
      onLogoutAll={async () => {
        await localized(api.revokeSessions(token));
        exitAccount();
      }}
      onDeleteAccount={async (currentPassword, confirmation) => {
        await localized(api.deleteAccount(token, currentPassword, confirmation));
        exitAccount();
      }}
    />
  );
}
