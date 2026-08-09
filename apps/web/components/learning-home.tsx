"use client";

import {
  ArrowRight,
  Archive,
  ArchiveRestore,
  Check,
  Clock3,
  Pencil,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { FormEvent, useState } from "react";

import { AppSidebar } from "@/components/app-sidebar";
import { BrandMark } from "@/components/brand";
import { ConfirmDialog } from "@/components/confirm-dialog";
import type { Translator } from "@/lib/i18n";
import type { LearningWorkspace, Locale } from "@/lib/types";

export function LearningHome({
  locale = "zh",
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
  onLogout,
  onToggleLocale,
}: {
  locale?: Locale;
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
  onLogout: () => void;
  onToggleLocale: () => void;
}) {
  const [intent, setIntent] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<LearningWorkspace | null>(null);
  const [deleting, setDeleting] = useState(false);
  const activeWorkspaces = workspaces.filter((item) => !item.archived);

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
      <div className="home-sidebar">
        <AppSidebar
          locale={locale}
          active="home"
          workspaces={activeWorkspaces}
          isAdmin={isAdmin}
          onToggleLocale={onToggleLocale}
          onLogout={onLogout}
        />
      </div>
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
                    <button className="recent-card-open" onClick={() => onOpen(workspace)} disabled={workspace.archived}>
                      <span>{workspace.subject}</span>
                      <strong>{workspace.title}</strong>
                      <p>{workspace.goal}</p>
                      {workspace.archived && <small>{t("archived")}</small>}
                      <ArrowRight size={16} />
                    </button>
                  )}
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
                </article>
              ))}
            </div>}
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
