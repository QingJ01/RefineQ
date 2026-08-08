"use client";

import {
  ArrowRight,
  BookOpen,
  CalendarDays,
  House,
  Languages,
  LayoutGrid,
  LogOut,
  Settings2,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { BrandMark, BrandName } from "@/components/brand";
import { workspaceColorIndex } from "@/lib/global-calendar";
import { learningPath } from "@/lib/learning-routes";
import type { LearningWorkspace, Locale } from "@/lib/types";


export type AppSidebarDestination = "home" | "calendar" | "workspace" | "account" | "admin";

const copy = {
  zh: {
    global: "全局导航",
    home: "学习首页",
    calendar: "总日历",
    spaces: "学习空间",
    allSpaces: "全部学习空间",
    recent: "最近使用",
    account: "账户设置",
    admin: "系统管理",
    language: "EN",
    logout: "退出登录",
  },
  en: {
    global: "Global navigation",
    home: "Learning home",
    calendar: "Global calendar",
    spaces: "Learning spaces",
    allSpaces: "All learning spaces",
    recent: "Recent",
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
  onToggleLocale: () => void;
  onLogout: () => void;
  onNavigate?: () => void;
  onHomeNavigate?: () => void;
}) {
  const text = copy[locale];
  const recent = workspaces.filter((workspace) => !workspace.archived).slice(0, 5);

  return (
    <aside className="app-sidebar" data-testid="app-sidebar">
      <Link className="app-sidebar-brand wordmark-button" href="/" aria-label="RefineQ">
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
          <CalendarDays size={19} />
          <span>{text.calendar}</span>
        </Link>
      </nav>

      <section className="app-sidebar-spaces" aria-labelledby="app-sidebar-spaces-label">
        <span id="app-sidebar-spaces-label" className="app-sidebar-label">{text.spaces}</span>
        <Link className="app-spaces-all" href="/#recent-learning" onClick={onHomeNavigate ?? onNavigate}>
          <LayoutGrid size={17} />
          <span>{text.allSpaces}</span>
          <ArrowRight size={14} />
        </Link>
        {recent.length > 0 && (
          <div className="app-recent-spaces">
            <small>{text.recent}</small>
            {recent.map((workspace) => (
              <Link
                key={workspace.id}
                className={workspace.id === currentWorkspaceId ? "app-space-link active" : "app-space-link"}
                href={learningPath(workspace.id, "today")}
                onClick={onNavigate}
                aria-current={workspace.id === currentWorkspaceId ? "location" : undefined}
              >
                <i data-color={workspaceColorIndex(workspace.id)} />
                <BookOpen size={16} />
                <span>{workspace.title}</span>
              </Link>
            ))}
          </div>
        )}
      </section>

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
            className={active === "admin" ? "app-utility-link active" : "app-utility-link"}
            href="/admin"
            onClick={onNavigate}
            aria-current={active === "admin" ? "page" : undefined}
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
