"use client";

import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";

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
  onUpdateSession,
}: {
  plan: StudyPlan | null;
  locale: Locale;
  topicLabels?: Record<string, string>;
  busySessionId?: string | null;
  onUpdateSession: (
    session: StudySession,
    input: { planned_at?: string; minutes?: number; status?: "planned" | "completed" },
  ) => void | boolean | Promise<void | boolean>;
}) {
  const zh = locale === "zh";
  const initial = plan?.sessions[0] ? new Date(plan.sessions[0].planned_at) : new Date();
  const [month, setMonth] = useState(new Date(initial.getFullYear(), initial.getMonth(), 1));
  const [selectedDate, setSelectedDate] = useState(dateKey(initial));
  const [editingId, setEditingId] = useState<string | null>(null);
  const [plannedAt, setPlannedAt] = useState("");
  const [minutes, setMinutes] = useState(45);

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
  const selectedSessions = sessionsByDate.get(selectedDate) ?? [];
  const monthTitle = new Intl.DateTimeFormat(zh ? "zh-CN" : "en-US", { year: "numeric", month: "long" }).format(month);
  const weekdays = zh ? ["日", "一", "二", "三", "四", "五", "六"] : ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  function beginEdit(session: StudySession) {
    setEditingId(session.id);
    setPlannedAt(localInputValue(session.planned_at));
    setMinutes(session.minutes);
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
    });
    if (saved === false) return;
    setSelectedDate(dateKey(new Date(plannedAt)));
    setEditingId(null);
  }

  if (!plan) return <div className="empty-note">{zh ? "确认学习范围后，时间表会出现在这里。" : "Confirm your learning scope to create a schedule."}</div>;

  return (
    <section className="schedule-page" data-testid="schedule-calendar">
      <header className="calendar-toolbar">
        <div className="calendar-product-title">
          <span className="calendar-product-icon"><CalendarDays size={24} /></span>
          <div><span>{zh ? "RefineQ 学习时间表" : "RefineQ Study Schedule"}</span><h2>{monthTitle}</h2></div>
        </div>
        <div className="calendar-toolbar-actions">
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
                  <div>{events.slice(0, 3).map((session, eventIndex) => <i className={`calendar-event color-${eventIndex % 4}`} key={session.id}>{topicLabels[session.topic_id] ?? session.topic_id}</i>)}</div>
                </button>
              );
            })}
          </div>
        </div>
        <aside className="day-agenda">
          <span className="kicker">{selectedDate}</span>
          <h3>{zh ? "当天安排" : "Day schedule"}</h3>
          {selectedSessions.length === 0 ? <p>{zh ? "这一天没有学习任务。" : "No study sessions on this day."}</p> : (
            <ol>{selectedSessions.map((session) => (
              <li key={session.id}>
                {editingId === session.id ? (
                  <div className="calendar-editor">
                    <label>{zh ? "日期与时间" : "Date and time"}<input type="datetime-local" value={plannedAt} onChange={(event) => setPlannedAt(event.target.value)} /></label>
                    <label>{zh ? "时长（分钟）" : "Minutes"}<input type="number" min={5} max={480} value={minutes} onChange={(event) => setMinutes(Number(event.target.value))} /></label>
                    <div><button type="button" disabled={busySessionId === session.id || !plannedAt} onClick={() => void save(session)}>{zh ? "保存" : "Save"}</button><button type="button" onClick={() => setEditingId(null)}>{zh ? "取消" : "Cancel"}</button></div>
                  </div>
                ) : (
                  <button type="button" className="agenda-event" onClick={() => beginEdit(session)}>
                    <i /><span><strong>{topicLabels[session.topic_id] ?? session.topic_id}</strong><small>{new Intl.DateTimeFormat(zh ? "zh-CN" : "en-US", { hour: "2-digit", minute: "2-digit" }).format(new Date(session.planned_at))} · {session.minutes} {zh ? "分钟" : "min"}</small></span>
                  </button>
                )}
              </li>
            ))}</ol>
          )}
        </aside>
      </div>
    </section>
  );
}
