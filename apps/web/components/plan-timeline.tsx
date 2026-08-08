"use client";

import { useState } from "react";
import type { Translator } from "@/lib/i18n";
import type { Locale, StudyPlan, StudySession } from "@/lib/types";
import { buildPlanRows } from "@/lib/view-models";


export function PlanTimeline({
  plan,
  locale,
  t,
  onUpdateSession,
  onStartSession,
  busySessionId,
  practiceBusy = false,
  topicLabels = {},
}: {
  plan: StudyPlan | null;
  locale: Locale;
  t: Translator;
  onUpdateSession?: (
    session: StudySession,
    input: { status?: "planned" | "completed"; planned_at?: string },
  ) => void | Promise<void>;
  onStartSession?: (session: StudySession) => void | Promise<void>;
  busySessionId?: string | null;
  practiceBusy?: boolean;
  topicLabels?: Record<string, string>;
}) {
  const [expanded, setExpanded] = useState(false);

  if (!plan) {
    return (
      <section className="content-card guided-empty-state" data-testid="plan-empty-guide">
        <span className="kicker">PATH / READY</span>
        <h2>{t("noPlan")}</h2>
        <p>{locale === "zh" ? "先回到今日学习确认目标与学习范围，RefineQ 会据此生成可调整的学习路径。" : "Return to Today to confirm the goal and learning scope. RefineQ will then create an adjustable study path."}</p>
        <ol>
          <li>{locale === "zh" ? "确认想获得的能力或考试目标" : "Confirm the capability or exam goal"}</li>
          <li>{locale === "zh" ? "补充截止日期与每日投入" : "Add a target date and daily commitment"}</li>
          <li>{locale === "zh" ? "生成后可在这里改期、完成或重新规划" : "Reschedule, complete, or regenerate sessions here"}</li>
        </ol>
      </section>
    );
  }
  const rows = buildPlanRows(plan, locale === "zh" ? "zh-CN" : "en-US", topicLabels);
  const visibleRows = expanded ? rows : rows.slice(0, 7);
  const activityLabels = locale === "zh"
    ? { learn: "学习", practice: "练习", apply: "实战", review: "复盘" }
    : { learn: "Learn", practice: "Practice", apply: "Apply", review: "Review" };
  return (
    <section className="content-card plan-card" aria-labelledby="plan-heading">
      <div className="section-heading">
        <div>
          <span className="kicker">PLAN / {String(rows.length).padStart(2, "0")}</span>
          <h2 id="plan-heading">{t("plan")}</h2>
        </div>
        <span className="minute-badge">{plan.daily_minutes} {t("minutes")}</span>
      </div>
      <ol className="plan-timeline" id="study-plan-sessions">
        {visibleRows.map((row) => {
          const session = plan.sessions.find((item) => item.id === row.id)!;
          const deferredAt = new Date(session.planned_at);
          deferredAt.setUTCDate(deferredAt.getUTCDate() + 1);
          return (
          <li key={row.id} className={session.status === "completed" ? "plan-session completed" : "plan-session"}>
            <span className="sequence">{String(row.sequence).padStart(2, "0")}</span>
            <span className="timeline-rule" aria-hidden="true" />
            <div className="plan-topic">
              <div>
                <strong>{row.topic}</strong>
                <span className={`plan-activity plan-activity-${session.activity ?? "practice"}`}>
                  {activityLabels[session.activity ?? "practice"]}
                </span>
              </div>
              <span>{row.dateLabel}</span>
            </div>
            <span className="plan-minutes">{row.minutesLabel}</span>
            <div className="plan-session-actions">
              <button
                type="button"
                className="plan-start-action"
                data-testid={`start-session-${session.id}`}
                disabled={practiceBusy || busySessionId === session.id}
                onClick={() => void onStartSession?.(session)}
              >{t("startSession")}</button>
              <button
                type="button"
                data-testid={`complete-session-${session.id}`}
                disabled={busySessionId === session.id}
                onClick={() => void onUpdateSession?.(session, {
                  status: session.status === "completed" ? "planned" : "completed",
                })}
              >{t(session.status === "completed" ? "reopenSession" : "completeSession")}</button>
              <button
                type="button"
                data-testid={`defer-session-${session.id}`}
                disabled={busySessionId === session.id}
                onClick={() => void onUpdateSession?.(session, { planned_at: deferredAt.toISOString() })}
              >{t("deferSession")}</button>
            </div>
          </li>
          );
        })}
      </ol>
      {rows.length > 7 ? (
        <button
          type="button"
          className="plan-toggle"
          data-testid="toggle-plan-sessions"
          aria-expanded={expanded}
          aria-controls="study-plan-sessions"
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded
            ? t("collapsePlan")
            : `${t("showAll")} ${rows.length} ${t("sessions")}`}
        </button>
      ) : null}
    </section>
  );
}
