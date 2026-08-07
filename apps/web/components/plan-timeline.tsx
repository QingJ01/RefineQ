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
  topicLabels?: Record<string, string>;
}) {
  const [expanded, setExpanded] = useState(false);

  if (!plan) {
    return <div className="empty-note">{t("noPlan")}</div>;
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
                disabled={busySessionId === session.id}
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
