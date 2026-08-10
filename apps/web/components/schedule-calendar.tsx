"use client";

import { CalendarDays, ChevronLeft, ChevronRight, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { ConfirmDialog } from "@/components/confirm-dialog";
import type { Locale, StudyPlan, StudySession } from "@/lib/types";

function dateKey(value: Date): string {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

function localInputValue(value: string): string {
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export function ScheduleCalendar({
  plan,
  locale,
  topicLabels = {},
  busySessionId,
  focusedSessionId,
  onUpdateSession,
  onAddSession,
  onClearPlan,
  onStartSession,
  practiceBusy = false,
}: {
  plan: StudyPlan | null;
  locale: Locale;
  topicLabels?: Record<string, string>;
  busySessionId?: string | null;
  focusedSessionId?: string | null;
  onUpdateSession: (
    session: StudySession,
    input: { planned_at?: string; minutes?: number; status?: "planned" | "completed"; topic_id?: string },
  ) => void | boolean | Promise<void | boolean>;
  onAddSession?: (input: { topic_name: string; planned_at: string; minutes: number; activity: string }) => Promise<boolean>;
  onClearPlan?: () => Promise<boolean>;
  onStartSession?: (session: StudySession) => void | Promise<void>;
  practiceBusy?: boolean;
}) {
  const zh = locale === "zh";
  const focusedSession = plan?.sessions.find((session) => session.id === focusedSessionId);
  const initial = focusedSession
    ? new Date(focusedSession.planned_at)
    : plan?.sessions[0]
      ? new Date(plan.sessions[0].planned_at)
      : new Date();
  const [month, setMonth] = useState(new Date(initial.getFullYear(), initial.getMonth(), 1));
  const [selectedDate, setSelectedDate] = useState(dateKey(initial));
  const [editingId, setEditingId] = useState<string | null>(null);
  const [plannedAt, setPlannedAt] = useState("");
  const [minutes, setMinutes] = useState(45);
  const [topicId, setTopicId] = useState("");
  const [adding, setAdding] = useState(false);
  const [newTopic, setNewTopic] = useState("");
  const [confirmingClear, setConfirmingClear] = useState(false);
  const [clearing, setClearing] = useState(false);

  const sessionsByDate = useMemo(() => {
    const result = new Map<string, StudySession[]>();
    for (const session of plan?.sessions ?? []) {
      const key = dateKey(new Date(session.planned_at));
      result.set(key, [...(result.get(key) ?? []), session]);
    }
    return result;
  }, [plan]);

  const firstWeekday = new Date(month.getFullYear(), month.getMonth(), 1).getDay();
  const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const cells = Array.from({ length: 42 }, (_, index) => {
    const day = index - firstWeekday + 1;
    return day >= 1 && day <= daysInMonth ? new Date(month.getFullYear(), month.getMonth(), day) : null;
  });
  const selectedSessions = [...(sessionsByDate.get(selectedDate) ?? [])].sort(
    (left, right) => new Date(left.planned_at).getTime() - new Date(right.planned_at).getTime(),
  );
  const monthTitle = new Intl.DateTimeFormat(zh ? "zh-CN" : "en-US", { year: "numeric", month: "long" }).format(month);
  const weekdays = zh ? ["日", "一", "二", "三", "四", "五", "六"] : ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const activityLabel = (activity: StudySession["activity"]) => ({
    learn: zh ? "学习" : "Learn",
    practice: zh ? "练习" : "Practice",
    apply: zh ? "应用" : "Apply",
    review: zh ? "复习" : "Review",
  }[activity ?? "learn"]);
  const topicLabel = (topicId: string) => topicLabels[topicId] ?? (zh ? "未命名主题" : "Untitled topic");

  function beginEdit(session: StudySession) {
    setEditingId(session.id);
    setPlannedAt(localInputValue(session.planned_at));
    setMinutes(session.minutes);
    setTopicId(session.topic_id);
  }

  function showToday() {
    const today = new Date();
    setMonth(new Date(today.getFullYear(), today.getMonth(), 1));
    setSelectedDate(dateKey(today));
  }

  async function save(session: StudySession) {
    const saved = await onUpdateSession(session, {
      planned_at: new Date(plannedAt).toISOString(),
      minutes,
      topic_id: topicId,
    });
    if (saved === false) return;
    setSelectedDate(dateKey(new Date(plannedAt)));
    setEditingId(null);
  }

  if (!plan) return (
    <section className="content-card guided-empty-state" data-testid="schedule-empty-guide">
      <CalendarDays size={28} strokeWidth={1.5} />
      <span className="kicker">SCHEDULE / READY</span>
      <h2>{zh ? "还没有可安排的学习日程" : "No study schedule yet"}</h2>
      <p>{zh ? "计划尚未生成。生成后，每次学习与复习都会自动排进这里，并可随时调整。" : "The plan is not ready yet. Once generated, learning and review sessions will appear here and remain editable."}</p>
    </section>
  );

  return (
    <section className="schedule-page" data-testid="schedule-calendar">
      <header className="calendar-toolbar">
        <div className="calendar-product-title">
          <span className="calendar-product-icon"><CalendarDays size={24} /></span>
          <div><span>{zh ? "计划日历" : "Plan calendar"}</span><h2>{monthTitle}</h2></div>
        </div>
        <div className="calendar-toolbar-actions">
          <button type="button" className="calendar-clear-button" onClick={() => setConfirmingClear(true)}><Trash2 size={15} />{zh ? "一键清除" : "Clear plan"}</button>
          <button type="button" className="calendar-today-button" onClick={showToday}>{zh ? "今天" : "Today"}</button>
          <div className="calendar-navigation">
            <button type="button" aria-label={zh ? "上个月" : "Previous month"} onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}><ChevronLeft size={18} /></button>
            <button type="button" aria-label={zh ? "下个月" : "Next month"} onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}><ChevronRight size={18} /></button>
          </div>
        </div>
      </header>
      <div className="calendar-layout">
        <div className="month-calendar">
          <div className="calendar-weekdays">{weekdays.map((day) => <span key={day}>{day}</span>)}</div>
          <div className="calendar-grid">
            {cells.map((date, index) => {
              if (!date) return <span className="calendar-day empty" key={`empty-${index}`} />;
              const key = dateKey(date);
              const events = sessionsByDate.get(key) ?? [];
              return (
                <button type="button" key={key} className={selectedDate === key ? "calendar-day selected" : "calendar-day"} onClick={() => setSelectedDate(key)}>
                  <span>{date.getDate()}</span>
                  <div>{events.slice(0, 3).map((session, eventIndex) => <i className={`calendar-event color-${eventIndex % 4} activity-${session.activity ?? "learn"}${session.id === focusedSessionId ? " focused" : ""}${session.status === "completed" ? " completed" : ""}`} data-activity={session.activity ?? "learn"} data-session-id={session.id} data-focused={session.id === focusedSessionId ? "true" : undefined} data-status={session.status} key={session.id}><time>{new Intl.DateTimeFormat(zh ? "zh-CN" : "en-US", { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(session.planned_at))}</time>{activityLabel(session.activity)} · {topicLabel(session.topic_id)}</i>)}</div>
                </button>
              );
            })}
          </div>
        </div>
        <aside className="day-agenda">
          <span className="kicker">{selectedDate}</span>
          <h3>{zh ? "当天安排" : "Day schedule"}</h3>
          <button type="button" className="calendar-add-button" onClick={() => {
            setAdding(true);
            setPlannedAt(`${selectedDate}T19:00`);
          }}><Plus size={14} />{zh ? "添加日程" : "Add event"}</button>
          {adding && <div className="calendar-editor calendar-add-editor">
            <label>{zh ? "学习内容" : "Topic"}<input value={newTopic} onChange={(event) => setNewTopic(event.target.value)} /></label>
            <label>{zh ? "日期与时间" : "Date and time"}<input type="datetime-local" value={plannedAt} onChange={(event) => setPlannedAt(event.target.value)} /></label>
            <label>{zh ? "时长（分钟）" : "Minutes"}<input type="number" min={5} max={480} value={minutes} onChange={(event) => setMinutes(Number(event.target.value))} /></label>
            <div><button type="button" disabled={!newTopic.trim() || !plannedAt} onClick={async () => {
              const ok = await onAddSession?.({ topic_name: newTopic.trim(), planned_at: new Date(plannedAt).toISOString(), minutes, activity: "practice" });
              if (ok !== false) { setAdding(false); setNewTopic(""); }
            }}>{zh ? "添加" : "Add"}</button><button type="button" onClick={() => setAdding(false)}>{zh ? "取消" : "Cancel"}</button></div>
          </div>}
          {editingId && (() => {
            const session = selectedSessions.find((item) => item.id === editingId);
            return session ? <div className="calendar-editor calendar-edit-panel">
              <label>{zh ? "学习知识点" : "Topic"}<select value={topicId} onChange={(event) => setTopicId(event.target.value)}>{Object.entries(topicLabels).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
              <label>{zh ? "日期与时间" : "Date and time"}<input type="datetime-local" value={plannedAt} onChange={(event) => setPlannedAt(event.target.value)} /></label>
              <label>{zh ? "时长（分钟）" : "Minutes"}<input type="number" min={5} max={480} value={minutes} onChange={(event) => setMinutes(Number(event.target.value))} /></label>
              <div><button type="button" disabled={busySessionId === session.id || !plannedAt} onClick={() => void save(session)}>{zh ? "保存" : "Save"}</button><button type="button" onClick={() => setEditingId(null)}>{zh ? "取消" : "Cancel"}</button></div>
            </div> : null;
          })()}
          <div className="day-timeline" aria-label={zh ? "24 小时日程" : "24-hour schedule"}>
            <div className="day-timeline-hours">
              {Array.from({ length: 24 }, (_, hour) => <div className="day-timeline-hour" key={hour}><time>{String(hour).padStart(2, "0")}:00</time><span /></div>)}
            </div>
            <div className="day-timeline-events">
              {selectedSessions.map((session, index) => {
                const start = new Date(session.planned_at);
                const top = start.getHours() * 60 + start.getMinutes();
                const height = Math.max(34, session.minutes);
                const end = new Date(start.getTime() + session.minutes * 60_000);
                const timeFormat = new Intl.DateTimeFormat(zh ? "zh-CN" : "en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
                return <div
                  className={`timeline-event color-${index % 4}${session.id === focusedSessionId ? " focused" : ""}${session.status === "completed" ? " completed" : ""}`}
                  key={session.id}
                  data-session-id={session.id}
                  data-focused={session.id === focusedSessionId ? "true" : undefined}
                  data-status={session.status}
                  style={{ top: `${top}px`, minHeight: `${height}px` }}
                >
                  <strong>{activityLabel(session.activity)} · {topicLabel(session.topic_id)}</strong>
                  <small>{timeFormat.format(start)}–{timeFormat.format(end)} · {session.minutes} {zh ? "分钟" : "min"}</small>
                  <div className="timeline-event-actions">
                    <button type="button" data-testid={`start-calendar-session-${session.id}`} disabled={!onStartSession || practiceBusy || busySessionId === session.id} onClick={() => void onStartSession?.(session)}>{zh ? "开始" : "Start"}</button>
                    <button type="button" data-testid={`complete-calendar-session-${session.id}`} disabled={busySessionId === session.id} onClick={() => void onUpdateSession(session, { status: session.status === "completed" ? "planned" : "completed" })}>{session.status === "completed" ? (zh ? "重新打开" : "Reopen") : (zh ? "完成" : "Complete")}</button>
                    <button type="button" data-testid={`defer-calendar-session-${session.id}`} disabled={busySessionId === session.id} onClick={() => {
                      const deferredAt = new Date(session.planned_at);
                      // Advance by one LOCAL calendar day so the session lands on
                      // the day the learner sees, matching the server's local buckets.
                      deferredAt.setDate(deferredAt.getDate() + 1);
                      void onUpdateSession(session, { planned_at: deferredAt.toISOString() });
                    }}>{zh ? "顺延一天" : "Defer one day"}</button>
                    <button type="button" data-testid={`edit-calendar-session-${session.id}`} disabled={busySessionId === session.id} onClick={() => beginEdit(session)}>{zh ? "编辑" : "Edit"}</button>
                  </div>
                </div>;
              })}
              {selectedSessions.length === 0 && <p className="timeline-empty">{zh ? "这一天没有学习任务，可以点击上方添加日程。" : "No sessions. Add one above."}</p>}
            </div>
          </div>
        </aside>
      </div>
      <ConfirmDialog
        open={confirmingClear}
        title={zh ? "清空当前学习计划？" : "Clear this study plan?"}
        description={zh ? "所有日历日程都会被清除，但资料、知识点、答题记录和掌握度会保留。" : "All calendar sessions will be removed. Materials and learning progress will be kept."}
        confirmLabel={clearing ? (zh ? "正在清除…" : "Clearing…") : (zh ? "确认清除" : "Clear plan")}
        cancelLabel={zh ? "取消" : "Cancel"}
        tone="danger"
        busy={clearing}
        onCancel={() => setConfirmingClear(false)}
        onConfirm={async () => {
          setClearing(true);
          try {
            const cleared = await onClearPlan?.();
            if (cleared !== false) setConfirmingClear(false);
          } finally {
            setClearing(false);
          }
        }}
      />
    </section>
  );
}
