"use client";

import {
  BookOpen,
  House,
  Languages,
  Layers3,
  LibraryBig,
  LogOut,
  MoreHorizontal,
  Settings2,
  Trash2,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { useState, type MouseEvent, type ReactNode } from "react";

import { BrandMark, BrandName } from "@/components/brand";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { workspaceColorIndex } from "@/lib/global-calendar";
import { learningPath } from "@/lib/learning-routes";
import type { LearningWorkspace, Locale } from "@/lib/types";


export type AppSidebarDestination = "home" | "library" | "calendar" | "workspace" | "account" | "admin";

const copy = {
  zh: {
    global: "全局导航",
    home: "学习首页",
    library: "总资料库",
    calendar: "全部日程",
    spaces: "最近使用",
    otherSpaces: "切换到其他空间",
    account: "账户设置",
    admin: "系统管理",
    language: "EN",
    logout: "退出登录",
    delete: "删除学习空间",
    deleteConfirm: "删除后，该空间的学习进度、计划和记录将无法恢复。是否确定删除？",
    cancel: "取消",
  },
  en: {
    global: "Global navigation",
    home: "Learning home",
    library: "Material library",
    calendar: "All schedules",
    spaces: "Recent spaces",
    otherSpaces: "Switch to another space",
    account: "Account settings",
    admin: "System admin",
    language: "中文",
    logout: "Sign out",
    delete: "Delete learning space",
    deleteConfirm: "This permanently removes the space, its progress, plan, and records. Delete it?",
    cancel: "Cancel",
  },
} as const;

export function AppSidebar({
  locale,
  active,
  workspaces,
  currentWorkspaceId,
  isAdmin = false,
  contextLabel,
  contextNavigation,
  contextOwnsActive = false,
  onToggleLocale,
  onLogout,
  onNavigate,
  onHomeNavigate,
  onDeleteWorkspace,
}: {
  locale: Locale;
  active: AppSidebarDestination;
  workspaces: LearningWorkspace[];
  currentWorkspaceId?: string;
  isAdmin?: boolean;
  contextLabel?: string;
  contextNavigation?: ReactNode;
  /** Set when the context navigation already marks the current route, so the
   *  utility entry point stays a plain link instead of a second highlight. */
  contextOwnsActive?: boolean;
  onToggleLocale: () => void;
  onLogout: () => void;
  onNavigate?: (event: MouseEvent<HTMLAnchorElement>) => void;
  onHomeNavigate?: (event: MouseEvent<HTMLAnchorElement>) => void;
  onDeleteWorkspace?: (workspace: LearningWorkspace) => void | Promise<void>;
}) {
  const text = copy[locale];
  const [menuWorkspaceId, setMenuWorkspaceId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<LearningWorkspace | null>(null);
  const [deleting, setDeleting] = useState(false);
  // Settings areas own the context slot; stacking the learner space list there
  // would show two unrelated navigations at once.
  const showSpaces = active === "home" || active === "calendar" || active === "workspace";
  const recent = workspaces
    .filter((workspace) => !workspace.archived && workspace.id !== currentWorkspaceId)
    .slice(0, 5);

  return (
    <aside className="app-sidebar" data-testid="app-sidebar">
      <Link
        className="app-sidebar-brand wordmark-button"
        href="/"
        aria-label="RefineQ"
        onClick={onHomeNavigate ?? onNavigate}
      >
        <BrandMark className="brand-mark" size={36} />
        <BrandName />
      </Link>

      <nav className="app-sidebar-global" aria-label={text.global}>
        <Link
          data-testid="app-nav-library"
          className={active === "library" ? "app-nav-item active" : "app-nav-item"}
          href="/library"
          onClick={onNavigate}
          aria-current={active === "library" ? "page" : undefined}
        >
          <LibraryBig size={19} />
          <span>{text.library}</span>
        </Link>
        <Link
          data-testid="app-nav-home"
          className={active === "home" ? "app-nav-item active" : "app-nav-item"}
          href="/"
          onClick={onHomeNavigate ?? onNavigate}
          aria-current={active === "home" ? "page" : undefined}
        >
          <House size={19} />
          <span>{text.home}</span>
        </Link>
        <Link
          data-testid="app-nav-calendar"
          className={active === "calendar" ? "app-nav-item active" : "app-nav-item"}
          href="/calendar"
          onClick={onNavigate}
          aria-current={active === "calendar" ? "page" : undefined}
        >
          <Layers3 size={19} />
          <span>{text.calendar}</span>
        </Link>
      </nav>

      {showSpaces && recent.length > 0 && (
        <section
          className="app-sidebar-spaces"
          data-testid="app-sidebar-spaces"
          aria-labelledby="app-sidebar-spaces-label"
        >
          <span id="app-sidebar-spaces-label" className="app-sidebar-label">
            {active === "workspace" ? text.otherSpaces : text.spaces}
          </span>
          <div className="app-recent-spaces">
            {recent.map((workspace) => (
              <div className="app-space-row" key={workspace.id}>
                <Link
                  className="app-space-link"
                  href={learningPath(workspace.id, "today")}
                  onClick={onNavigate}
                >
                  <i data-color={workspaceColorIndex(workspace.id)} />
                  <BookOpen size={16} />
                  <span>{workspace.title}</span>
                </Link>
                {onDeleteWorkspace && (
                  <div className="app-space-menu">
                    <button
                      type="button"
                      className="app-space-menu-trigger"
                      data-testid={`workspace-menu-${workspace.id}`}
                      aria-label={`${workspace.title} ${locale === "zh" ? "更多操作" : "More actions"}`}
                      aria-expanded={menuWorkspaceId === workspace.id}
                      onClick={() => setMenuWorkspaceId((current) => current === workspace.id ? null : workspace.id)}
                    ><MoreHorizontal size={17} /></button>
                    {menuWorkspaceId === workspace.id && (
                      <div className="app-space-menu-popover">
                        <button
                          type="button"
                          data-testid={`workspace-menu-delete-${workspace.id}`}
                          onClick={() => {
                            setMenuWorkspaceId(null);
                            setDeleteTarget(workspace);
                          }}
                        ><Trash2 size={15} />{text.delete}</button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {contextNavigation && (
        <section className="app-sidebar-context">
          {contextLabel && <span className="app-sidebar-label">{contextLabel}</span>}
          <nav aria-label={contextLabel}>{contextNavigation}</nav>
        </section>
      )}

      <div className="app-sidebar-utilities">
        <Link
          data-testid="app-nav-account"
          className={active === "account" ? "app-utility-link active" : "app-utility-link"}
          href="/account"
          onClick={onNavigate}
          aria-current={active === "account" ? "page" : undefined}
        >
          <UserRound size={18} /> <span>{text.account}</span>
        </Link>
        {isAdmin && (
          <Link
            data-testid="app-nav-admin"
            className={
              active === "admin" && !contextOwnsActive ? "app-utility-link active" : "app-utility-link"
            }
            href="/admin"
            onClick={onNavigate}
            aria-current={active === "admin" && !contextOwnsActive ? "page" : undefined}
          >
            <Settings2 size={18} /> <span>{text.admin}</span>
          </Link>
        )}
        <button data-testid="app-language" type="button" onClick={onToggleLocale}>
          <Languages size={18} /> <span>{text.language}</span>
        </button>
        <button data-testid="app-logout" type="button" onClick={onLogout}>
          <LogOut size={18} /> <span>{text.logout}</span>
        </button>
        <p>{locale === "zh" ? "记住进度，继续学习。" : "Your progress, remembered."}</p>
      </div>
      <ConfirmDialog
        open={deleteTarget !== null}
        title={deleteTarget ? `${text.delete} · ${deleteTarget.title}` : text.delete}
        description={text.deleteConfirm}
        confirmLabel={text.delete}
        cancelLabel={text.cancel}
        tone="danger"
        busy={deleting}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={async () => {
          if (!deleteTarget || !onDeleteWorkspace) return;
          setDeleting(true);
          try {
            await onDeleteWorkspace(deleteTarget);
            setDeleteTarget(null);
          } finally {
            setDeleting(false);
          }
        }}
      />
    </aside>
  );
}
