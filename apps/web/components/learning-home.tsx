"use client";

import {
  ArrowRight,
  Archive,
  ArchiveRestore,
  Clock3,
  History,
  Languages,
  LogOut,
  MessageSquarePlus,
  Pencil,
  Settings2,
  Sparkles,
  Trash2,
} from "lucide-react";
import { FormEvent, useState } from "react";

import { BrandMark, BrandName } from "@/components/brand";
import type { Translator } from "@/lib/i18n";
import type { LearningWorkspace } from "@/lib/types";


export function LearningHome({
  t,
  busy,
  workspaces,
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

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!intent.trim()) return;
    await onResolve(intent.trim());
  }

  return (
    <main id="main-content" className="home-shell">
      <aside className="home-sidebar">
        <div className="sidebar-brand">
          <BrandMark className="brand-mark" size={36} />
          <BrandName />
        </div>
        <a className="home-nav-item active" href="#learning-composer"><MessageSquarePlus size={19} /><span>{t("startLearning")}</span></a>
        <a className="home-nav-item" href="#recent-learning"><History size={19} /><span>{t("recentLearning")}</span></a>
        {isAdmin && (
          <button
            data-testid="home-admin"
            className="home-nav-item home-admin-link"
            onClick={onAdmin}
          >
            <Settings2 size={19} /><span>平台控制台</span>
          </button>
        )}
        <div className="home-sidebar-actions">
          <button
            data-testid="home-language"
            className="home-nav-item home-admin-link"
            onClick={onToggleLocale}
          >
            <Languages size={19} /><span>{t("language")}</span>
          </button>
          <button
            data-testid="home-logout"
            className="home-nav-item home-admin-link"
            onClick={onLogout}
          >
            <LogOut size={19} /><span>{t("logout")}</span>
          </button>
          <p className="sidebar-footnote">Personal learning, remembered.</p>
        </div>
      </aside>
      <section className="learning-home">
        <div className="learning-home-hero">
          <div className="learning-brand-hero" aria-hidden="true"><BrandMark size={58} /></div>
          <span className="kicker">PERSONAL LEARNING AGENT</span>
          <h1>{t("learningPrompt")}</h1>
          <p>{t("learningPromptHint")}</p>
          <form id="learning-composer" className="learning-composer" onSubmit={submit}>
            <textarea
              data-testid="learning-intent"
              value={intent}
              onChange={(event) => setIntent(event.target.value)}
              placeholder={t("learningIntentPlaceholder")}
              rows={3}
              autoFocus
            />
            <div className="composer-footer">
              <small className="routing-note"><Sparkles size={14} /> {t("autoRouting")}</small>
              <button data-testid="start-learning" className="composer-send" disabled={busy || !intent.trim()} aria-label={t("startLearning")}>
                {busy ? <span>{t("loading")}</span> : <ArrowRight size={19} />}
              </button>
            </div>
          </form>
        </div>
          <section className="recent-learning" id="recent-learning">
            <div className="section-heading compact">
              <div><span className="kicker">CONTINUE LEARNING</span><h2>{t("recentLearning")}</h2></div>
              <div className="recent-heading-actions">
                <button type="button" data-testid="archived-workspaces-toggle" aria-pressed={showArchived} onClick={() => void onToggleArchived?.(!showArchived)}>
                  {showArchived ? <Clock3 size={15} /> : <Archive size={15} />}
                  {t(showArchived ? "hideArchived" : "showArchived")}
                </button>
                <Clock3 size={20} />
              </div>
            </div>
            {workspaces.length === 0 ? <div className="empty-note">{t(showArchived ? "noArchivedWorkspaces" : "noRecentWorkspaces")}</div> : <div className="recent-grid">
              {workspaces.map((workspace) => (
                <article className={workspace.archived ? "recent-card archived" : "recent-card"} key={workspace.id}>
                  <button className="recent-card-open" onClick={() => onOpen(workspace)} disabled={workspace.archived}>
                    <span>{workspace.subject}</span>
                    <strong>{workspace.title}</strong>
                    <p>{workspace.goal}</p>
                    {workspace.archived && <small>{t("archived")}</small>}
                    <ArrowRight size={16} />
                  </button>
                  <div className="recent-card-actions" aria-label={`${workspace.title} actions`}>
                    <button
                      type="button"
                      data-testid={`workspace-rename-${workspace.id}`}
                      aria-label={`${t("renameWorkspace")} ${workspace.title}`}
                      onClick={() => {
                        const title = window.prompt(t("renameWorkspace"), workspace.title)?.trim();
                        if (title && title !== workspace.title) void onUpdate?.(workspace, { title });
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
                      onClick={() => {
                        if (window.confirm(t("deleteWorkspaceConfirm"))) void onDelete?.(workspace);
                      }}
                    ><Trash2 size={14} /></button>
                  </div>
                </article>
              ))}
            </div>}
          </section>
      </section>
    </main>
  );
}
