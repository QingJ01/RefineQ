"use client";

import { useState } from "react";
import type { Translator } from "@/lib/i18n";
import type { Locale, StudyPlan, StudySession } from "@/lib/types";
import { buildPlanRows } from "@/lib/view-models";

function localInputValue(value: string): string {
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

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
    input: { status?: "planned" | "completed"; planned_at?: string; minutes?: number; topic_id?: string },
  ) => void | boolean | Promise<void | boolean>;
  onStartSession?: (session: StudySession) => void | Promise<void>;
  busySessionId?: string | null;
  practiceBusy?: boolean;
  topicLabels?: Record<string, string>;
}) {
  const [expanded, setExpanded] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [plannedAt, setPlannedAt] = useState("");
  const [minutes, setMinutes] = useState(45);
  const [topicId, setTopicId] = useState("");

  function beginEdit(session: StudySession) {
    setEditingId(session.id);
    setPlannedAt(localInputValue(session.planned_at));
    setMinutes(session.minutes);
    setTopicId(session.topic_id);
  }

  async function save(session: StudySession) {
    if (!plannedAt) return;
    const saved = await onUpdateSession?.(session, {
      planned_at: new Date(plannedAt).toISOString(),
      minutes,
      topic_id: topicId,
    });
    if (saved === false) return;
    setEditingId(null);
  }

  if (!plan) {
    return (
      <section className="content-card guided-empty-state" data-testid="plan-empty-guide">
        <span className="kicker">PATH / READY</span>
        <h2>{t("noPlan")}</h2>
        <p>{locale === "zh" ? "计划尚未生成。请重试打开学习空间，或在今日向 Agent 请求重新规划。" : "The plan is not ready yet. Reopen this learning space or ask the Agent on Today to replan."}</p>
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
            {editingId === session.id ? (
              <div className="plan-session-editor">
                <label>
                  <span>{locale === "zh" ? "学习知识点" : "Topic"}</span>
                  <select value={topicId} onChange={(event) => setTopicId(event.target.value)}>
                    {Object.entries(topicLabels).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
                  </select>
                </label>
                <label>
                  <span>{locale === "zh" ? "日期与时间" : "Date and time"}</span>
                  <input type="datetime-local" value={plannedAt} onChange={(event) => setPlannedAt(event.target.value)} />
                </label>
                <label>
                  <span>{locale === "zh" ? "分钟" : "Minutes"}</span>
                  <input type="number" min={5} max={480} value={minutes} onChange={(event) => setMinutes(Number(event.target.value))} />
                </label>
                <button type="button" disabled={busySessionId === session.id || !plannedAt || minutes < 5 || minutes > 480} onClick={() => void save(session)}>
                  {locale === "zh" ? "保存" : "Save"}
                </button>
                <button type="button" onClick={() => setEditingId(null)}>
                  {locale === "zh" ? "取消" : "Cancel"}
                </button>
              </div>
            ) : (
            <div className="plan-session-actions">
              <button
                type="button"
                className="plan-start-action"
                data-testid={`start-session-${session.id}`}
                disabled={!onStartSession || practiceBusy || busySessionId === session.id}
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
              <button
                type="button"
                data-testid={`edit-session-${session.id}`}
                disabled={busySessionId === session.id}
                onClick={() => beginEdit(session)}
              >{locale === "zh" ? "编辑" : "Edit"}</button>
            </div>
            )}
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
