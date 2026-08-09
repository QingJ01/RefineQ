"use client";

import {
  ArrowRight,
  Archive,
  ArchiveRestore,
  BookOpen,
  CalendarClock,
  Check,
  Clock3,
  Copy,
  Pencil,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";

import { AppSidebar } from "@/components/app-sidebar";
import { BrandMark } from "@/components/brand";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { ApiError } from "@/lib/api";
import type { Translator } from "@/lib/i18n";
import type {
  HomeActionReceipt,
  HomeDispatchResult,
  HomeWorkspaceProposal,
  LearningWorkspace,
  Locale,
} from "@/lib/types";

export function LearningHome({
  locale = "zh",
  t,
  busy,
  workspaces,
  onDispatch,
  onConfirm,
  onCancel,
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
  onDispatch: (
    input: {
      request_id: string;
      text: string;
      timezone_offset_minutes: number;
      clarification?: { continuation_token: string; option_id: string } | null;
    },
    signal: AbortSignal,
  ) => Promise<HomeDispatchResult | null>;
  onConfirm: (
    result: HomeDispatchResult,
    proposalChanges?: Partial<Pick<HomeWorkspaceProposal, "title" | "goal" | "exam_at" | "daily_minutes">>,
  ) => Promise<HomeActionReceipt>;
  onCancel?: (result: HomeDispatchResult) => void | Promise<void>;
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
  const [latestResult, setLatestResult] = useState<HomeDispatchResult | null>(null);
  const [dispatching, setDispatching] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [dispatchError, setDispatchError] = useState("");
  const [receiptNotice, setReceiptNotice] = useState("");
  const [proposalDraft, setProposalDraft] = useState<{
    title: string;
    goal: string;
    exam_at: string;
    daily_minutes: number;
  } | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<LearningWorkspace | null>(null);
  const [deleting, setDeleting] = useState(false);
  const requestRef = useRef<{ id: string; controller: AbortController } | null>(null);
  const resultHeadingRef = useRef<HTMLHeadingElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const activeWorkspaces = workspaces.filter((item) => !item.archived);

  useEffect(() => () => requestRef.current?.controller.abort(), []);

  function requestId(): string {
    return globalThis.crypto?.randomUUID?.()
      ?? `home-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  async function dispatchText(
    text: string,
    clarification?: { continuation_token: string; option_id: string } | null,
  ) {
    const normalized = text.trim();
    if (!normalized) return;
    if (normalized.length > 12_000) {
      setLatestResult(null);
      setDispatchError(t("homeTooLong"));
      requestAnimationFrame(() => inputRef.current?.focus());
      return;
    }
    requestRef.current?.controller.abort();
    const current = { id: requestId(), controller: new AbortController() };
    requestRef.current = current;
    setLatestResult(null);
    setReceiptNotice("");
    setDispatchError("");
    setDispatching(true);
    try {
      const result = await onDispatch({
        request_id: current.id,
        text: normalized,
        timezone_offset_minutes: -new Date().getTimezoneOffset(),
        clarification,
      }, current.controller.signal);
      if (
        requestRef.current?.id !== current.id
        || current.controller.signal.aborted
        || (result && result.request_id !== current.id)
      ) return;
      if (result) {
        setLatestResult(result);
        setProposalDraft(result.kind === "propose_workspace" ? {
          title: result.workspace_proposal.title,
          goal: result.workspace_proposal.goal,
          exam_at: result.workspace_proposal.exam_at,
          daily_minutes: result.workspace_proposal.daily_minutes,
        } : null);
        requestAnimationFrame(() => resultHeadingRef.current?.focus());
      }
    } catch (caught) {
      if (current.controller.signal.aborted) return;
      if (requestRef.current?.id !== current.id) return;
      setDispatchError(caught instanceof Error ? caught.message : "Request failed");
      requestAnimationFrame(() => inputRef.current?.focus());
    } finally {
      if (requestRef.current?.id === current.id) setDispatching(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    await dispatchText(intent);
  }

  function composerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  }

  async function confirmResult() {
    if (!latestResult) return;
    setConfirming(true);
    setDispatchError("");
    try {
      const receipt = await onConfirm(
        latestResult,
        latestResult.kind === "propose_workspace" && proposalDraft
          ? proposalDraft
          : undefined,
      );
      if (receipt.status === "succeeded") {
        setReceiptNotice(receipt.replayed ? t("homeAlreadyConfirmed") : t("homeConfirmed"))
      }
    } catch (caught) {
      if (
        caught instanceof ApiError
        && (caught.code === "invalid_home_confirmation" || caught.code === "home_action_conflict")
      ) {
        await dispatchText(intent);
        return;
      }
      setDispatchError(caught instanceof Error ? caught.message : "Confirmation failed");
    } finally {
      setConfirming(false);
    }
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

  const resultClarification = latestResult?.kind === "clarify"
    ? latestResult.clarification
    : latestResult?.kind === "out_of_scope"
      ? latestResult.manual_recovery
      : null;

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
              ref={inputRef}
              data-testid="learning-intent"
              value={intent}
              onChange={(event) => setIntent(event.target.value)}
              placeholder={t("learningIntentPlaceholder")}
              rows={3}
              onKeyDown={composerKeyDown}
              autoFocus
            />
            <div className="composer-footer">
              <small className="routing-note"><Sparkles size={14} /> {t("autoRouting")}</small>
              <button data-testid="start-learning" className="composer-send" disabled={busy || dispatching || !intent.trim()} aria-label={t("startLearning")}>
                {busy || dispatching ? <span>{t("loading")}</span> : <ArrowRight size={19} />}
              </button>
            </div>
          </form>
          <div className="home-dispatch-status" aria-live="polite" aria-atomic="true">
            {dispatching ? t("homeDispatching") : dispatchError || receiptNotice}
          </div>
          {latestResult && (
            <article className={`home-result-card result-${latestResult.kind}`} data-testid={`home-result-${latestResult.kind}`}>
              <div className="home-result-heading">
                <span className="kicker">{t("homeNextAction")}</span>
                <h2 ref={resultHeadingRef} tabIndex={-1}>
                  {latestResult.kind === "direct_answer" && t("homeDirectTitle")}
                  {latestResult.kind === "open_workspace" && latestResult.workspace_target.title}
                  {latestResult.kind === "workspace_action" && t("homeActionTitle")}
                  {latestResult.kind === "propose_workspace" && t("homeProposalTitle")}
                  {latestResult.kind === "clarify" && t("homeClarifyTitle")}
                  {latestResult.kind === "out_of_scope" && t("homeOutOfScopeTitle")}
                </h2>
                <p>{latestResult.reason}</p>
              </div>

              {latestResult.kind === "direct_answer" && (
                <div className="home-answer-body">
                  <p>{latestResult.answer.content}</p>
                  <small>
                    {latestResult.answer.basis === "pasted_text" ? t("homeBasisPasted") : t("homeBasisGeneral")}
                    {` · ${t("homeNoPersonalSources")}`}
                  </small>
                </div>
              )}

              {latestResult.kind === "open_workspace" && (
                <div className="home-target-summary">
                  <p>{latestResult.workspace_target.goal}</p>
                  {latestResult.workspace_target.next_action && (
                    <>
                      <strong>{latestResult.workspace_target.next_action.reason}</strong>
                      <span>
                        {latestResult.workspace_target.next_action.minutes
                          ? `${t("homeEstimated")} ${latestResult.workspace_target.next_action.minutes} ${t("minutes")}`
                          : t("homeOpenDetails")}
                      </span>
                    </>
                  )}
                  {(latestResult.workspace_target.exam_at || latestResult.workspace_target.pace_risk !== "low") && (
                    <small>
                      {latestResult.workspace_target.exam_at
                        ? `${t("homeDeadline")}：${new Date(latestResult.workspace_target.exam_at).toLocaleDateString(locale)}`
                        : ""}
                      {latestResult.workspace_target.exam_at && latestResult.workspace_target.pace_risk !== "low" ? " · " : ""}
                      {latestResult.workspace_target.pace_risk !== "low"
                        ? `${t("homeRisk")}：${t(latestResult.workspace_target.pace_risk === "high" ? "homeRiskHigh" : "homeRiskMedium")}`
                        : ""}
                    </small>
                  )}
                  {latestResult.workspace_target.deferred_workspace_title && (
                    <small>{t("homeDeferred")}：{latestResult.workspace_target.deferred_workspace_title}</small>
                  )}
                </div>
              )}

              {latestResult.kind === "workspace_action" && (
                <div className="home-change-preview">
                  <div><span>{t("homeBefore")}</span><code>{JSON.stringify(latestResult.action_proposal.before)}</code></div>
                  <ArrowRight size={18} aria-hidden="true" />
                  <div><span>{t("homeAfter")}</span><code>{JSON.stringify(latestResult.action_proposal.after)}</code></div>
                </div>
              )}

              {latestResult.kind === "propose_workspace" && (
                <div className="home-proposal-preview">
                  <label><span>{t("homeSpace")}</span><input maxLength={200} value={proposalDraft?.title ?? ""} onChange={(event) => setProposalDraft((current) => current ? { ...current, title: event.target.value } : current)} /></label>
                  <label><span>{t("learningGoal")}</span><textarea maxLength={500} value={proposalDraft?.goal ?? ""} onChange={(event) => setProposalDraft((current) => current ? { ...current, goal: event.target.value } : current)} /></label>
                  <label><span>{t("homeDeadline")}</span><input type="date" value={(proposalDraft?.exam_at ?? "").slice(0, 10)} onChange={(event) => setProposalDraft((current) => current ? { ...current, exam_at: new Date(`${event.target.value}T23:59:00Z`).toISOString() } : current)} /></label>
                  <label><span>{t("homeDaily")}</span><input type="number" min={5} max={480} value={proposalDraft?.daily_minutes ?? 45} onChange={(event) => setProposalDraft((current) => current ? { ...current, daily_minutes: Number(event.target.value) } : current)} /></label>
                  <small>{latestResult.workspace_proposal.material_hint}</small>
                </div>
              )}

              {resultClarification && (
                <div className="home-clarification-options">
                    {resultClarification.options.map((option, index) => (
                      <button
                        type="button"
                        key={option.id}
                        className={index === 0 ? "primary-action" : undefined}
                        onClick={() => {
                          if (option.id === "change_question") {
                            setLatestResult(null);
                            setIntent("");
                            inputRef.current?.focus();
                            return;
                          }
                          if (option.id === "configure_model") {
                            window.location.assign("/admin/integrations/chat");
                            return;
                          }
                          void dispatchText(intent, {
                            continuation_token: resultClarification.continuation_token,
                            option_id: option.id,
                          });
                        }}
                      >{option.label}</button>
                    ))}
                </div>
              )}

              {latestResult.limitations.length > 0 && (
                <ul className="home-result-limitations">
                  {latestResult.limitations.map((item) => <li key={item}>{item}</li>)}
                </ul>
              )}

              <div className="home-result-actions">
                {latestResult.kind === "direct_answer" && (
                  <>
                    <button type="button" className="primary-action" onClick={() => void navigator.clipboard.writeText(latestResult.answer.content)}><Copy size={16} />{t("homeCopy")}</button>
                    <button type="button" onClick={() => void dispatchText(`${locale === "zh" ? "我想系统学习" : "I want to study"}：${latestResult.answer.convertible_goal}`)}><BookOpen size={16} />{t("homeConvert")}</button>
                    <button type="button" onClick={() => { setLatestResult(null); setIntent(""); inputRef.current?.focus(); }}>{t("homeNewQuestion")}</button>
                  </>
                )}
                {latestResult.kind === "open_workspace" && (
                  <button
                    type="button"
                    className="primary-action"
                    onClick={() => {
                      const target = workspaces.find((item) => item.id === latestResult.workspace_target.workspace_id);
                      if (target) void onOpen(target);
                      else setDispatchError(t("workspaceOpenFailed"));
                    }}
                  ><BookOpen size={16} />{t("homeContinue")}</button>
                )}
                {(latestResult.kind === "workspace_action" || latestResult.kind === "propose_workspace") && (
                  <>
                    <button type="button" className="primary-action" disabled={confirming} onClick={() => void confirmResult()}>
                      <CalendarClock size={16} />{confirming ? t("homeConfirming") : t("homeConfirm")}
                    </button>
                    <button
                      type="button"
                      disabled={confirming}
                      onClick={() => {
                        void Promise.resolve(onCancel?.(latestResult)).catch(() => undefined);
                        setLatestResult(null);
                      }}
                    >{t("homeCancel")}</button>
                  </>
                )}
                {latestResult.kind === "out_of_scope" && !latestResult.manual_recovery && (
                  <button type="button" className="primary-action" onClick={() => { setLatestResult(null); inputRef.current?.focus(); }}>换一个问题</button>
                )}
              </div>
            </article>
          )}
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
