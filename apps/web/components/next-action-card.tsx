"use client";

import { ArrowRight, BookOpen, CalendarClock, TriangleAlert, Upload } from "lucide-react";

import type { Locale, NextAction } from "@/lib/types";


export interface NextActionHandlers {
  onUpload: () => void;
  onStartReview: (sessionId: string, topicId: string | null) => void;
  onStartSession: (sessionId: string) => void;
  onRepairPlan: () => void;
  onStartPractice: (topicId: string | null) => void;
}

export function executeNextAction(action: NextAction, handlers: NextActionHandlers): void {
  if (action.action_type === "upload_material") handlers.onUpload();
  else if (action.action_type === "start_review" && action.target_id) {
    handlers.onStartReview(action.target_id, action.topic_id);
  } else if (action.action_type === "start_session" && action.target_id) {
    handlers.onStartSession(action.target_id);
  } else if (action.action_type === "repair_pace") handlers.onRepairPlan();
  else if (action.action_type === "start_practice") handlers.onStartPractice(action.topic_id);
}

export function NextActionCard({
  locale,
  action,
  busy,
  ...handlers
}: {
  locale: Locale;
  action: NextAction;
  busy: boolean;
} & NextActionHandlers) {
  const zh = locale === "zh";
  const copy = {
    upload_material: {
      eyebrow: zh ? "开始前准备" : "Before you begin",
      title: zh ? "先上传一份学习资料" : "Upload one study source",
      cta: zh ? "上传资料" : "Upload material",
      icon: Upload,
    },
    start_review: {
      eyebrow: zh ? "最优先" : "Highest priority",
      title: zh ? "完成已到期复习" : "Complete the due review",
      cta: zh ? "开始复习" : "Start review",
      icon: CalendarClock,
    },
    start_session: {
      eyebrow: zh ? "今日计划" : "Today's plan",
      title: zh ? "完成下一场学习" : "Complete the next session",
      cta: zh ? "开始学习" : "Start session",
      icon: BookOpen,
    },
    repair_pace: {
      eyebrow: zh ? "进度风险" : "Pace risk",
      title: zh ? "先修正计划约束" : "Repair the plan first",
      cta: zh ? "检查计划" : "Review plan",
      icon: TriangleAlert,
    },
    start_practice: {
      eyebrow: zh ? "下一步" : "Next step",
      title: zh ? "练习当前最弱主题" : "Practice the weakest topic",
      cta: zh ? "开始练习" : "Start practice",
      icon: ArrowRight,
    },
  }[action.action_type];
  const Icon = copy.icon;

  return (
    <article className="content-card next-action-card" data-testid="next-action-card">
      <div className="next-action-icon" aria-hidden="true"><Icon size={22} /></div>
      <div className="next-action-copy">
        <span>{copy.eyebrow}</span>
        <h2>{copy.title}</h2>
        <p>{action.reason}</p>
        <small>{action.expected_outcome}</small>
      </div>
      <button
        type="button"
        className="primary-action"
        data-testid={`next-action-${action.action_type}`}
        data-target-id={action.target_id ?? undefined}
        disabled={busy}
        onClick={() => executeNextAction(action, handlers)}
      >
        {busy ? (zh ? "正在准备…" : "Preparing…") : copy.cta}
        <ArrowRight size={16} />
      </button>
    </article>
  );
}
