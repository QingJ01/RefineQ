"use client";

import Image from "next/image";
import {
  ArrowUp,
  Check,
  CircleAlert,
  LoaderCircle,
  MessageCircleMore,
  RotateCcw,
  Settings2,
  Sparkles,
  X,
} from "lucide-react";
import { FormEvent, useState } from "react";

import { ApiError } from "@/lib/api";
import { RichText } from "@/components/rich-text";
import type { CoachActionOutcome } from "@/lib/coach-actions";
import type {
  AgentReply,
  CoachActionProposal,
  ExecutableActionProposal,
  Locale,
} from "@/lib/types";


const copy = {
  zh: {
    title: "RefineQ 教练 · 当前步骤",
    intro: "我会结合当前目标、资料和你的回答，帮助你完成这一步。",
    suggestions: ["给我一点提示", "换种方式解释", "回看相关内容", "为什么问这道题？"],
    placeholder: "向教练提问…",
    send: "发送",
    error: "暂时无法连接教练，你仍可以继续当前学习任务。",
    modelMissing: "学习 Agent 尚未配置模型。练习、资料和进度仍可继续使用。",
    modelUnknown: "暂时无法确认学习 Agent 状态。本地练习、资料和进度仍可继续使用。",
    configure: "前往配置",
    recheck: "重新检测",
    contactAdmin: "请联系管理员配置学习 Agent 模型。",
    fullCoach: "完整对话与历史",
    applied: "已执行",
    confirm: "这个动作会清空当前题的未提交内容，是否继续？",
    confirmAction: "继续执行",
    cancel: "先不执行",
    failed: "动作执行失败，你可以用同一请求安全重试。",
    retry: "重试",
  },
  en: {
    title: "RefineQ coach · Current step",
    intro: "I use your goal, sources, and answers to help with this step.",
    suggestions: ["Give me a hint", "Explain it another way", "Review the related content", "Why ask this question?"],
    placeholder: "Ask your coach…",
    send: "Send",
    error: "The coach is temporarily unavailable. You can continue the current task.",
    modelMissing: "The learning Agent has not been configured. Practice, material, and progress remain available.",
    modelUnknown: "The learning Agent status is unavailable. Local practice, material, and progress remain available.",
    configure: "Open settings",
    recheck: "Check again",
    contactAdmin: "Please contact an administrator to configure the learning Agent model.",
    fullCoach: "Full conversation and history",
    applied: "Applied",
    confirm: "This action will clear the unsubmitted draft for the current question. Continue?",
    confirmAction: "Continue",
    cancel: "Keep current question",
    failed: "The action failed. You can safely retry the same request.",
    retry: "Retry",
  },
} as const;

export type CoachActionCardState =
  | { status: "applied" | "confirmation_required" | "failed" | "executing"; proposal: ExecutableActionProposal }
  | { status: "rejected"; proposal: Extract<CoachActionProposal, { type: "rejected" }> };

function proposalSummary(proposal: ExecutableActionProposal, locale: Locale) {
  if (proposal.type === "adjust_practice") {
    return locale === "zh"
      ? `换题：「${proposal.topic_name}」· 难度 ${proposal.difficulty}`
      : `Replace question: ${proposal.topic_name} · Difficulty ${proposal.difficulty}`;
  }
  if (proposal.type === "update_plan_session") {
    if (proposal.status === "completed") {
      return locale === "zh" ? `已完成：${proposal.session_label}` : `Completed: ${proposal.session_label}`;
    }
    return locale === "zh" ? `调整计划：${proposal.session_label}` : `Update plan: ${proposal.session_label}`;
  }
  return proposal.saved
    ? (locale === "zh" ? "收藏当前题目" : "Save current question")
    : (locale === "zh" ? "取消收藏当前题目" : "Unsave current question");
}

function rejectedSummary(
  proposal: Extract<CoachActionProposal, { type: "rejected" }>,
  locale: Locale,
) {
  if (locale === "en") return proposal.summary;
  const summaries: Record<string, string> = {
    no_topics: "当前学习空间还没有可练习的主题。",
    unknown_topic: "当前学习空间没有匹配的主题。",
    difficulty_at_bound: "当前难度已经到达可调整的边界。",
    no_pending_question: "当前没有可收藏的待答题目。",
    no_study_plan: "当前学习空间还没有学习计划。",
    no_matching_session: "没有找到匹配的学习场次。",
    ambiguous_session: "有多个学习场次符合描述，请说得更具体一些。",
    date_before_today: "不能把学习场次移到今天之前。",
    date_after_exam: "不能把学习场次移到考试日期之后。",
    invalid_timezone: "无法识别浏览器时区，请刷新后重试。",
    invalid_plan: "当前学习计划包含无效场次。",
    invalid_exam_date: "当前考试日期无效，暂时不能改期。",
    stale_action_proposal: "这条旧建议已经过期，请重新向 Agent 提问。",
  };
  return summaries[proposal.reason_code] ?? proposal.summary;
}

export function CoachActionCard({
  locale,
  state,
  onConfirm,
  onCancel,
  onRetry,
}: {
  locale: Locale;
  state: CoachActionCardState;
  onConfirm: () => void;
  onCancel: () => void;
  onRetry: () => void;
}) {
  const text = copy[locale];
  if (state.status === "rejected") {
    return (
      <div className="coach-action-card is-rejected" data-testid="coach-action-rejected" role="status">
        <CircleAlert size={15} />
        <div>
          <strong>{rejectedSummary(state.proposal, locale)}</strong>
          {state.proposal.candidates.length > 0 && <p>{state.proposal.candidates.join(" · ")}</p>}
        </div>
      </div>
    );
  }

  const summary = proposalSummary(state.proposal, locale);
  return (
    <div
      className={`coach-action-card is-${state.status}`}
      data-testid={`coach-action-${state.status}`}
      role="status"
    >
      {state.status === "applied"
        ? <Check size={15} />
        : state.status === "executing"
          ? <LoaderCircle className="spin" size={15} />
          : state.status === "failed"
            ? <CircleAlert size={15} />
            : <Sparkles size={15} />}
      <div>
        <strong>{state.status === "applied" ? `${text.applied} · ${summary}` : summary}</strong>
        {state.status === "confirmation_required" && <p>{text.confirm}</p>}
        {state.status === "failed" && <p>{text.failed}</p>}
        {state.status === "confirmation_required" && (
          <div className="coach-action-buttons">
            <button type="button" data-testid="coach-action-confirm" onClick={onConfirm}>{text.confirmAction}</button>
            <button type="button" data-testid="coach-action-cancel" className="is-secondary" onClick={onCancel}>
              <X size={12} /> {text.cancel}
            </button>
          </div>
        )}
        {state.status === "failed" && (
          <div className="coach-action-buttons">
            <button type="button" data-testid="coach-action-retry" onClick={onRetry}>{text.retry}</button>
          </div>
        )}
      </div>
    </div>
  );
}

export function SessionCoach({
  locale,
  onAsk,
  modelConfigured = true,
  isAdmin = false,
  onConfigure,
  onRecheck,
  onOpenFullCoach,
  onModelUnavailable,
  onApplyAction,
  onTurnHandled,
}: {
  locale: Locale;
  onAsk: (message: string) => Promise<AgentReply>;
  modelConfigured?: boolean | null;
  isAdmin?: boolean;
  onConfigure?: () => void;
  onRecheck?: () => void | Promise<boolean | null>;
  onOpenFullCoach?: () => void;
  onModelUnavailable?: () => void;
  onApplyAction?: (
    proposal: ExecutableActionProposal,
    options?: { confirmed?: boolean },
  ) => Promise<CoachActionOutcome>;
  onTurnHandled?: () => void;
}) {
  const text = copy[locale];
  const [message, setMessage] = useState("");
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [actionState, setActionState] = useState<CoachActionCardState | null>(null);
  const actionBusy = actionState?.status === "executing";

  async function applyAction(
    proposal: ExecutableActionProposal,
    options?: { confirmed?: boolean },
  ) {
    setActionState({ status: "executing", proposal });
    if (!onApplyAction) {
      setActionState({ status: "failed", proposal });
      return;
    }
    try {
      const outcome = await onApplyAction(proposal, options);
      setActionState({
        status: outcome.status === "confirmation_required"
          ? "confirmation_required"
          : outcome.status === "applied"
              ? "applied"
              : "failed",
        proposal,
      });
    } catch {
      setActionState({ status: "failed", proposal });
    }
  }

  async function ask(value: string) {
    const normalized = value.trim();
    if (!normalized || busy || actionBusy) return;
    setBusy(true);
    setError("");
    let chatSucceeded = false;
    try {
      const response = await onAsk(normalized);
      chatSucceeded = true;
      setReply(response.message);
      setMessage("");
      const proposal = response.action_proposal;
      if (!proposal) {
        setActionState(null);
      } else if (proposal.type === "rejected") {
        setActionState({ status: "rejected", proposal });
      } else {
        await applyAction(proposal);
      }
    } catch (caught) {
      if (!chatSucceeded) {
        if (caught instanceof ApiError && caught.code === "model_not_configured") {
          onModelUnavailable?.();
        }
        setError(text.error);
      }
    } finally {
      if (chatSucceeded) onTurnHandled?.();
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void ask(message);
  }

  return (
    <section className="session-coach" data-testid="session-coach" aria-labelledby="session-coach-title">
      <div className="session-coach-heading">
        <span className="coach-avatar">
          <Image
            src="/assets/refineq-coach-avatar.png"
            alt=""
            aria-hidden="true"
            width={56}
            height={56}
          />
        </span>
        <div>
          <span className="coach-kicker"><Sparkles size={13} /> COACH</span>
          <h3 id="session-coach-title">{text.title}</h3>
        </div>
      </div>
      <RichText className="coach-intro">{reply || text.intro}</RichText>
      {onOpenFullCoach && (
        <button
          type="button"
          className="coach-full-link"
          data-testid="open-full-coach"
          onClick={onOpenFullCoach}
        >
          <MessageCircleMore size={14} /> {text.fullCoach}
        </button>
      )}
      {modelConfigured !== true && (
        <div className="coach-capability-notice" role="status">
          <p>{modelConfigured === false ? text.modelMissing : text.modelUnknown}</p>
          {modelConfigured === false && !isAdmin && <p>{text.contactAdmin}</p>}
          {isAdmin && onConfigure && (
            <button
              type="button"
              data-testid="coach-configure-model"
              onClick={onConfigure}
            >
              <Settings2 size={14} /> {text.configure}
            </button>
          )}
          {modelConfigured === null && onRecheck && (
            <button
              type="button"
              data-testid="coach-recheck"
              onClick={() => void onRecheck()}
            >
              <RotateCcw size={14} /> {text.recheck}
            </button>
          )}
        </div>
      )}
      {actionState && (
        <CoachActionCard
          locale={locale}
          state={actionState}
          onConfirm={() => {
            if (actionState.status !== "rejected") {
              void applyAction(actionState.proposal, { confirmed: true });
            }
          }}
          onCancel={() => setActionState(null)}
          onRetry={() => {
            if (actionState.status !== "rejected") {
              void applyAction(actionState.proposal, { confirmed: true });
            }
          }}
        />
      )}
      <div className="coach-suggestions" aria-label={locale === "zh" ? "教练快捷问题" : "Coach suggestions"}>
        {text.suggestions.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            data-testid="session-coach-suggestion"
            disabled={busy || actionBusy || modelConfigured === false}
            onClick={() => void ask(suggestion)}
          >
            {suggestion}
          </button>
        ))}
      </div>
      {error && <p className="coach-error" role="status">{error}</p>}
      <form className="session-coach-form" onSubmit={submit}>
        <label className="sr-only" htmlFor="session-coach-input">{text.placeholder}</label>
        <input
          id="session-coach-input"
          data-testid="session-coach-input"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder={text.placeholder}
          disabled={busy || actionBusy || modelConfigured === false}
        />
        <button
          type="submit"
          aria-label={text.send}
          disabled={busy || actionBusy || !message.trim() || modelConfigured === false}
        >
          {busy ? <LoaderCircle className="spin" size={17} /> : <ArrowUp size={17} />}
        </button>
      </form>
    </section>
  );
}
