"use client";

import {
  BookOpen,
  House,
  Languages,
  Layers3,
  LogOut,
  Settings2,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import type { MouseEvent, ReactNode } from "react";

import { BrandMark, BrandName } from "@/components/brand";
import { workspaceColorIndex } from "@/lib/global-calendar";
import { learningPath } from "@/lib/learning-routes";
import type { LearningWorkspace, Locale } from "@/lib/types";


export type AppSidebarDestination = "home" | "calendar" | "workspace" | "account" | "admin";

const copy = {
  zh: {
    global: "全局导航",
    home: "学习首页",
    calendar: "跨空间日程",
    spaces: "最近使用",
    otherSpaces: "切换到其他空间",
    account: "账户设置",
    admin: "系统管理",
    language: "EN",
    logout: "退出登录",
  },
  en: {
    global: "Global navigation",
    home: "Learning home",
    calendar: "Cross-space schedule",
    spaces: "Recent spaces",
    otherSpaces: "Switch to another space",
    account: "Account settings",
    admin: "System admin",
    language: "中文",
    logout: "Sign out",
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
}) {
  const text = copy[locale];
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
              <Link
                key={workspace.id}
                className="app-space-link"
                href={learningPath(workspace.id, "today")}
                onClick={onNavigate}
              >
                <i data-color={workspaceColorIndex(workspace.id)} />
                <BookOpen size={16} />
                <span>{workspace.title}</span>
              </Link>
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
        <p>Personal learning, remembered.</p>
      </div>
    </aside>
  );
}
