"use client";

import {
  Archive,
  ArchiveRestore,
  ArrowRight,
  BookOpen,
  CalendarDays,
  ChartNoAxesColumnIncreasing,
  Check,
  Clock3,
  History,
  House,
  Languages,
  LogOut,
  MessageSquarePlus,
  Pencil,
  Settings2,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useState } from "react";

import { BrandMark, BrandName } from "@/components/brand";
import { ConfirmDialog } from "@/components/confirm-dialog";
import type { Translator } from "@/lib/i18n";
import { learningPath, type LearningSection } from "@/lib/learning-routes";
import type { LearningWorkspace, Locale } from "@/lib/types";

const workspaceSections: Array<{
  id: LearningSection;
  icon: typeof BookOpen;
}> = [
  { id: "today", icon: BookOpen },
  { id: "path", icon: CalendarDays },
  { id: "materials", icon: Archive },
  { id: "progress", icon: ChartNoAxesColumnIncreasing },
];

export function LearningHome({
  t,
  busy,
  workspaces,
  locale = "zh",
  onResolve,
  onOpen,
  onUpdate,
  onDelete,
  showArchived = false,
  onToggleArchived,
  isAdmin = false,
  onAdmin,
  onLogout,
  onToggleLocale,
}: {
  t: Translator;
  busy: boolean;
  workspaces: LearningWorkspace[];
  locale?: Locale;
  onResolve: (intent: string) => void | Promise<void>;
  onOpen: (workspace: LearningWorkspace) => void | Promise<void>;
  onUpdate?: (
    workspace: LearningWorkspace,
    input: { title?: string; archived?: boolean },
  ) => void | Promise<void>;
  onDelete?: (workspace: LearningWorkspace) => void | Promise<void>;
  showArchived?: boolean;
  onToggleArchived?: (show: boolean) => void | Promise<void>;
  isAdmin?: boolean;
  onAdmin?: () => void;
  onLogout: () => void;
  onToggleLocale: () => void;
}) {
  const [intent, setIntent] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<LearningWorkspace | null>(null);
  const [deleting, setDeleting] = useState(false);
  const currentWorkspace = workspaces.find((item) => !item.archived) ?? null;
  const formattedDate = new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  }).format(new Date());

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!intent.trim()) return;
    await onResolve(intent.trim());
  }

  async function submitRename(event: FormEvent, workspace: LearningWorkspace) {
    event.preventDefault();
    const title = renameValue.trim();
    if (!title || title === workspace.title) {
      setRenamingId(null);
      return;
    }
    setRenaming(true);
    try {
      await onUpdate?.(workspace, { title });
      setRenamingId(null);
    } finally {
      setRenaming(false);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await onDelete?.(deleteTarget);
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <main id="main-content" className="home-shell">
      <aside className="home-sidebar">
        <Link className="sidebar-brand wordmark-button" href="/" aria-label="RefineQ">
          <BrandMark className="brand-mark" size={36} />
          <BrandName />
        </Link>
        <nav className="home-navigation" aria-label={t("learningHome")}>
          <a className="home-nav-item active" href="#home-overview" aria-current="page">
            <House size={19} />
            <span>{t("learningHome")}</span>
          </a>
          <a className="home-nav-item" href="#learning-composer">
            <MessageSquarePlus size={19} />
            <span>{t("newLearningGoal")}</span>
          </a>
          <a className="home-nav-item" href="#recent-learning">
            <History size={19} />
            <span>{t("recentLearning")}</span>
          </a>
          {isAdmin && (
            <button
              data-testid="home-admin"
              className="home-nav-item home-admin-link"
              onClick={onAdmin}
            >
              <Settings2 size={19} />
              <span>{t("administration")}</span>
            </button>
          )}
        </nav>
        {currentWorkspace && (
          <Link
            className="home-sidebar-space"
            href={learningPath(currentWorkspace.id, "today")}
            aria-label={`${t("continueLearning")}: ${currentWorkspace.title}`}
          >
            <span className="kicker">{t("currentSpace")}</span>
            <strong>{currentWorkspace.title}</strong>
            <p>{currentWorkspace.goal}</p>
            <span>{t("continueLearning")} <ArrowRight size={14} /></span>
          </Link>
        )}
        <div className="home-sidebar-actions">
          <button
            data-testid="home-language"
            className="home-nav-item home-admin-link"
            onClick={onToggleLocale}
          >
            <Languages size={19} />
            <span>{t("language")}</span>
          </button>
          <button
            data-testid="home-logout"
            className="home-nav-item home-admin-link"
            onClick={onLogout}
          >
            <LogOut size={19} />
            <span>{t("logout")}</span>
          </button>
        </div>
      </aside>

      <section className="learning-home">
        <header id="home-overview" className="home-command-header" data-testid="home-command-header">
          <div>
            <span className="kicker">REFINEQ / PERSONAL LEARNING</span>
            <h1>{t("homeTitle")}</h1>
            <p>{t("homeSubtitle")}</p>
          </div>
          <time>{formattedDate}</time>
        </header>

        <div className="home-command-grid">
          {currentWorkspace ? (
            <article className="current-learning-space" data-testid="current-learning-space">
              <div className="current-space-heading">
                <div>
                  <span className="kicker">{t("continueLearning")}</span>
                  <span className="current-space-subject">{currentWorkspace.subject}</span>
                </div>
                <Sparkles size={22} />
              </div>
              <h2>{currentWorkspace.title}</h2>
              <p>{currentWorkspace.goal}</p>
              {currentWorkspace.topics.length > 0 && (
                <div className="current-space-topics" aria-label={t("learningGoal")}>
                  {currentWorkspace.topics.slice(0, 3).map((topic) => <span key={topic}>{topic}</span>)}
                </div>
              )}
              <nav className="current-space-shortcuts" aria-label={`${currentWorkspace.title} ${t("workspaceSections")}`}>
                {workspaceSections.map(({ id, icon: Icon }) => (
                  <Link key={id} href={learningPath(currentWorkspace.id, id)}>
                    <Icon size={18} />
                    <span>{t(id)}</span>
                  </Link>
                ))}
              </nav>
              <Link className="current-space-primary" href={learningPath(currentWorkspace.id, "today")}>
                <span>{t("continueLearning")}</span>
                <ArrowRight size={18} />
              </Link>
            </article>
          ) : (
            <article className="current-learning-space empty" data-testid="current-learning-space-empty">
              <div className="current-space-empty-mark"><BookOpen size={24} /></div>
              <span className="kicker">{t("currentSpace")}</span>
              <h2>{t("noActiveWorkspace")}</h2>
              <p>{t("noActiveWorkspaceHint")}</p>
              <a href="#learning-composer">{t("createFirstSpace")} <ArrowRight size={16} /></a>
            </article>
          )}

          <section className="agent-start-card">
            <div className="agent-start-heading">
              <div className="agent-start-mark" aria-hidden="true"><BrandMark size={38} /></div>
              <div>
                <span className="kicker">PERSONAL LEARNING AGENT</span>
                <h2>{t("learningPrompt")}</h2>
              </div>
            </div>
            <p>{t("learningPromptHint")}</p>
            <form id="learning-composer" className="learning-composer" onSubmit={submit}>
              <textarea
                data-testid="learning-intent"
                value={intent}
                onChange={(event) => setIntent(event.target.value)}
                placeholder={t("learningIntentPlaceholder")}
                rows={3}
              />
              <div className="composer-footer">
                <small className="routing-note"><Sparkles size={14} /> {t("autoRouting")}</small>
                <button
                  data-testid="start-learning"
                  className="composer-send"
                  disabled={busy || !intent.trim()}
                  aria-label={t("startLearning")}
                >
                  {busy ? <span>{t("loading")}</span> : <ArrowRight size={19} />}
                </button>
              </div>
            </form>
          </section>
        </div>

        <section className="recent-learning" id="recent-learning">
          <div className="section-heading compact">
            <div>
              <span className="kicker">LEARNING SPACES</span>
              <h2>{t("recentLearning")}</h2>
            </div>
            <div className="recent-heading-actions">
              <button
                type="button"
                data-testid="archived-workspaces-toggle"
                aria-pressed={showArchived}
                onClick={() => void onToggleArchived?.(!showArchived)}
              >
                {showArchived ? <Clock3 size={15} /> : <Archive size={15} />}
                {t(showArchived ? "hideArchived" : "showArchived")}
              </button>
            </div>
          </div>

          {workspaces.length === 0 ? (
            <div className="empty-note">{t(showArchived ? "noArchivedWorkspaces" : "noRecentWorkspaces")}</div>
          ) : (
            <div className="recent-grid">
              {workspaces.map((workspace) => (
                <article className={workspace.archived ? "recent-card archived" : "recent-card"} key={workspace.id}>
                  {renamingId === workspace.id ? (
                    <form
                      className="workspace-rename-form"
                      data-testid="workspace-rename-form"
                      onSubmit={(event) => void submitRename(event, workspace)}
                    >
                      <span>{workspace.subject}</span>
                      <input
                        autoFocus
                        value={renameValue}
                        maxLength={200}
                        aria-label={t("renameWorkspace")}
                        onChange={(event) => setRenameValue(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Escape") setRenamingId(null);
                        }}
                      />
                      <div>
                        <button type="submit" aria-label={t("saveRename")} disabled={renaming || !renameValue.trim()}><Check size={15} /></button>
                        <button type="button" aria-label={t("cancelRename")} disabled={renaming} onClick={() => setRenamingId(null)}><X size={15} /></button>
                      </div>
                    </form>
                  ) : (
                    <>
                      <div className="recent-card-heading">
                        <span>{workspace.subject}</span>
                        <div className="recent-card-actions" aria-label={`${workspace.title} actions`}>
                          <button
                            type="button"
                            data-testid={`workspace-rename-${workspace.id}`}
                            aria-label={`${t("renameWorkspace")} ${workspace.title}`}
                            onClick={() => {
                              setRenamingId(workspace.id);
                              setRenameValue(workspace.title);
                            }}
                          ><Pencil size={14} /></button>
                          <button
                            type="button"
                            data-testid={`workspace-archive-${workspace.id}`}
                            aria-label={`${t(workspace.archived ? "restoreWorkspace" : "archiveWorkspace")} ${workspace.title}`}
                            onClick={() => void onUpdate?.(workspace, { archived: !workspace.archived })}
                          >{workspace.archived ? <ArchiveRestore size={14} /> : <Archive size={14} />}</button>
                          <button
                            type="button"
                            data-testid={`workspace-delete-${workspace.id}`}
                            aria-label={`${t("deleteWorkspace")} ${workspace.title}`}
                            onClick={() => setDeleteTarget(workspace)}
                          ><Trash2 size={14} /></button>
                        </div>
                      </div>
                      <button className="recent-card-open" onClick={() => onOpen(workspace)} disabled={workspace.archived}>
                        <strong>{workspace.title}</strong>
                        <p>{workspace.goal}</p>
                        {workspace.archived && <small>{t("archived")}</small>}
                        {!workspace.archived && <ArrowRight size={16} />}
                      </button>
                      {!workspace.archived && (
                        <nav className="recent-card-shortcuts" aria-label={`${workspace.title} ${t("workspaceSections")}`}>
                          {workspaceSections.map(({ id, icon: Icon }) => (
                            <Link key={id} href={learningPath(workspace.id, id)} aria-label={`${workspace.title}: ${t(id)}`}>
                              <Icon size={15} />
                              <span>{t(id)}</span>
                            </Link>
                          ))}
                        </nav>
                      )}
                    </>
                  )}
                </article>
              ))}
            </div>
          )}
        </section>
      </section>

      <ConfirmDialog
        open={deleteTarget !== null}
        title={deleteTarget ? `${t("deleteWorkspace")} · ${deleteTarget.title}` : t("deleteWorkspace")}
        description={t("deleteWorkspaceConfirm")}
        confirmLabel={t("deleteWorkspace")}
        cancelLabel={t("cancel")}
        tone="danger"
        busy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </main>
  );
}
