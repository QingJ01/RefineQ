"use client";

import {
  ArrowUpRight,
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  RotateCcw,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import {
  calendarDateKey,
  calendarGridRange,
  filterCalendarTasks,
  groupCalendarTasks,
  summarizeCalendarTasks,
  workspaceColorIndex,
} from "@/lib/global-calendar";
import { learningPath } from "@/lib/learning-routes";
import type { CalendarTask, LearningWorkspace, Locale } from "@/lib/types";


const copy = {
  zh: {
    eyebrow: "跨空间学习安排",
    title: "总日历",
    description: "在一处查看所有学习空间的任务；调整和执行仍回到任务所属空间。",
    today: "今天",
    previous: "上个月",
    next: "下个月",
    tasks: "项任务",
    minutes: "分钟",
    spaces: "个空间",
    filters: "空间筛选",
    allSpaces: "全部空间",
    includeArchived: "包含归档空间",
    dayAgenda: "当日安排",
    noDayTasks: "这一天没有学习任务。",
    emptyMonth: "本月没有学习任务",
    emptyMonthHint: "可以进入任一学习空间生成学习路径，任务会自动汇总到这里。",
    noSpaces: "还没有学习空间",
    noSpacesHint: "先从学习首页描述目标，RefineQ 会创建合适的学习空间。",
    noMatches: "当前筛选下没有任务",
    open: "进入对应空间",
    retry: "重试",
    loading: "正在汇总学习安排……",
    planned: "待完成",
    completed: "已完成",
    archived: "已归档",
    activities: { learn: "学习", practice: "练习", apply: "应用", review: "复习" },
  },
  en: {
    eyebrow: "Cross-space learning schedule",
    title: "Global calendar",
    description: "See every learning-space task here; return to its space to adjust or complete it.",
    today: "Today",
    previous: "Previous month",
    next: "Next month",
    tasks: "tasks",
    minutes: "min",
    spaces: "spaces",
    filters: "Space filters",
    allSpaces: "All spaces",
    includeArchived: "Include archived spaces",
    dayAgenda: "Day agenda",
    noDayTasks: "No learning tasks on this day.",
    emptyMonth: "No tasks this month",
    emptyMonthHint: "Create a study path in any learning space and its tasks will appear here.",
    noSpaces: "No learning spaces yet",
    noSpacesHint: "Describe a goal on Learning home to create your first space.",
    noMatches: "No tasks match these filters",
    open: "Open in learning space",
    retry: "Retry",
    loading: "Gathering your learning schedule…",
    planned: "Planned",
    completed: "Completed",
    archived: "Archived",
    activities: { learn: "Learn", practice: "Practice", apply: "Apply", review: "Review" },
  },
} as const;

export function GlobalCalendar({
  locale,
  month,
  selectedDate,
  tasks,
  workspaces,
  includeArchived,
  loading,
  error,
  onMonthChange,
  onSelectedDateChange,
  onIncludeArchivedChange,
  onRetry,
}: {
  locale: Locale;
  month: Date;
  selectedDate: string;
  tasks: CalendarTask[];
  workspaces: LearningWorkspace[];
  includeArchived: boolean;
  loading: boolean;
  error: string;
  onMonthChange: (month: Date) => void;
  onSelectedDateChange: (date: string) => void;
  onIncludeArchivedChange: (include: boolean) => void;
  onRetry: () => void;
}) {
  const text = copy[locale];
  const localeCode = locale === "zh" ? "zh-CN" : "en-US";
  const [workspaceIds, setWorkspaceIds] = useState<Set<string>>(new Set());
  const filteredTasks = useMemo(
    () => filterCalendarTasks(tasks, workspaceIds),
    [tasks, workspaceIds],
  );
  const tasksByDate = useMemo(() => groupCalendarTasks(filteredTasks), [filteredTasks]);
  const monthTasks = filteredTasks.filter((task) => {
    const date = new Date(task.planned_at);
    return date.getFullYear() === month.getFullYear() && date.getMonth() === month.getMonth();
  });
  const summary = summarizeCalendarTasks(monthTasks);
  const selectedTasks = tasksByDate.get(selectedDate) ?? [];
  const monthTitle = new Intl.DateTimeFormat(localeCode, { year: "numeric", month: "long" }).format(month);
  const weekdays = locale === "zh"
    ? ["日", "一", "二", "三", "四", "五", "六"]
    : ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const { startsAt } = calendarGridRange(month);
  const days = Array.from({ length: 42 }, (_, index) => {
    const date = new Date(startsAt);
    date.setDate(date.getDate() + index);
    return date;
  });

  function moveMonth(offset: number) {
    const next = new Date(month.getFullYear(), month.getMonth() + offset, 1);
    onMonthChange(next);
    onSelectedDateChange(calendarDateKey(next));
  }

  function showToday() {
    const today = new Date();
    onMonthChange(new Date(today.getFullYear(), today.getMonth(), 1));
    onSelectedDateChange(calendarDateKey(today));
  }

  function toggleWorkspace(workspaceId: string) {
    setWorkspaceIds((current) => {
      const next = new Set(current);
      if (next.has(workspaceId)) next.delete(workspaceId);
      else next.add(workspaceId);
      return next;
    });
  }

  return (
    <section className="global-calendar" data-testid="global-calendar">
      <header className="global-calendar-header">
        <div>
          <span className="kicker">CALENDAR / OVERVIEW</span>
          <p className="global-calendar-eyebrow">{text.eyebrow}</p>
          <h1>{text.title}</h1>
          <p>{text.description}</p>
        </div>
        <dl className="calendar-summary" aria-label={monthTitle}>
          <div><dt>{text.tasks}</dt><dd>{summary.tasks} {text.tasks}</dd></div>
          <div><dt>{text.minutes}</dt><dd>{summary.minutes} {text.minutes}</dd></div>
          <div><dt>{text.spaces}</dt><dd>{summary.workspaces} {text.spaces}</dd></div>
        </dl>
      </header>

      <div className="global-calendar-toolbar">
        <div className="global-calendar-month">
          <span className="calendar-product-icon"><CalendarDays size={22} /></span>
          <h2>{monthTitle}</h2>
        </div>
        <div className="calendar-toolbar-actions">
          <button type="button" className="calendar-today-button" onClick={showToday}>{text.today}</button>
          <div className="calendar-navigation">
            <button type="button" aria-label={text.previous} onClick={() => moveMonth(-1)}><ChevronLeft size={18} /></button>
            <button type="button" aria-label={text.next} onClick={() => moveMonth(1)}><ChevronRight size={18} /></button>
          </div>
        </div>
      </div>

      <div className="global-calendar-filters" aria-label={text.filters}>
        <button
          type="button"
          className={workspaceIds.size === 0 ? "active" : ""}
          aria-pressed={workspaceIds.size === 0}
          onClick={() => setWorkspaceIds(new Set())}
        >
          {text.allSpaces}
        </button>
        {workspaces.map((workspace) => (
          <button
            type="button"
            key={workspace.id}
            data-testid={`calendar-workspace-filter-${workspace.id}`}
            data-color={workspaceColorIndex(workspace.id)}
            className={workspaceIds.has(workspace.id) ? "active" : ""}
            aria-pressed={workspaceIds.has(workspace.id)}
            onClick={() => toggleWorkspace(workspace.id)}
          >
            <i /> {workspace.title}{workspace.archived ? ` · ${text.archived}` : ""}
          </button>
        ))}
        <label className="calendar-archived-toggle">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(event) => onIncludeArchivedChange(event.target.checked)}
          />
          <span>{text.includeArchived}</span>
        </label>
      </div>

      {error && (
        <div className="global-calendar-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={onRetry}><RotateCcw size={15} /> {text.retry}</button>
        </div>
      )}

      {loading ? (
        <div className="global-calendar-loading" aria-live="polite"><CalendarDays size={28} /><span>{text.loading}</span></div>
      ) : workspaces.length === 0 ? (
        <div className="global-calendar-empty"><CalendarDays size={30} /><h2>{text.noSpaces}</h2><p>{text.noSpacesHint}</p><Link href="/">{text.allSpaces}<ArrowUpRight size={15} /></Link></div>
      ) : tasks.length === 0 ? (
        <div className="global-calendar-empty"><CalendarDays size={30} /><h2>{text.emptyMonth}</h2><p>{text.emptyMonthHint}</p></div>
      ) : filteredTasks.length === 0 ? (
        <div className="global-calendar-empty compact"><h2>{text.noMatches}</h2></div>
      ) : (
        <div className="global-calendar-layout">
          <div className="global-month-calendar">
            <div className="calendar-weekdays">{weekdays.map((day) => <span key={day}>{day}</span>)}</div>
            <div className="global-calendar-grid">
              {days.map((date) => {
                const key = calendarDateKey(date);
                const events = tasksByDate.get(key) ?? [];
                const outside = date.getMonth() !== month.getMonth();
                return (
                  <button
                    type="button"
                    key={key}
                    className={`global-calendar-day${selectedDate === key ? " selected" : ""}${outside ? " outside" : ""}`}
                    onClick={() => onSelectedDateChange(key)}
                    aria-label={new Intl.DateTimeFormat(localeCode, { month: "long", day: "numeric" }).format(date)}
                  >
                    <span>{date.getDate()}</span>
                    <div>
                      {events.slice(0, 3).map((task) => (
                        <i key={task.id} data-color={workspaceColorIndex(task.workspace_id)}>
                          {task.workspace_title} · {task.topic_label}
                        </i>
                      ))}
                      {events.length > 3 && <small>+{events.length - 3}</small>}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <aside className="global-day-agenda">
            <span className="kicker">{selectedDate}</span>
            <h2>{text.dayAgenda}</h2>
            {selectedTasks.length === 0 ? <p className="global-day-empty">{text.noDayTasks}</p> : (
              <ol>
                {selectedTasks.map((task) => (
                  <li key={task.id} data-color={workspaceColorIndex(task.workspace_id)}>
                    <div className="global-agenda-meta">
                      <span><i />{task.workspace_title}</span>
                      <span className={`calendar-task-status ${task.status}`}>
                        {task.status === "completed" ? <CheckCircle2 size={14} /> : <Clock3 size={14} />}
                        {task.status === "completed" ? text.completed : text.planned}
                      </span>
                    </div>
                    <h3>{task.topic_label}</h3>
                    <p>{text.activities[task.activity]} · {new Intl.DateTimeFormat(localeCode, { hour: "2-digit", minute: "2-digit" }).format(new Date(task.planned_at))} · {task.minutes} {text.minutes}</p>
                    <Link href={`${learningPath(task.workspace_id, "calendar")}?session=${encodeURIComponent(task.id)}`}>
                      {text.open}<ArrowUpRight size={15} />
                    </Link>
                  </li>
                ))}
              </ol>
            )}
          </aside>
        </div>
      )}
    </section>
  );
}
