"use client";

import { CalendarPlus } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";

import type { Locale, TargetedPlanInput } from "@/lib/types";

export const MAX_TARGETED_PLAN_TOPICS = 30;

export function initialTargetedPlanTopics(topics: string[]): string[] {
  return Array.from(new Set(topics)).slice(0, MAX_TARGETED_PLAN_TOPICS);
}

const weekdayLabels = {
  zh: ["一", "二", "三", "四", "五", "六", "日"],
  en: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
};

function dateInputValue(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function initialExamDate(initialExamAt?: string): string {
  const configured = initialExamAt ? new Date(initialExamAt) : null;
  if (configured && Number.isFinite(configured.getTime()) && configured > new Date()) {
    return dateInputValue(configured);
  }
  const fallback = new Date();
  fallback.setDate(fallback.getDate() + 14);
  return dateInputValue(fallback);
}

export function TargetedPlanBuilder({
  locale,
  materialId,
  topics,
  initialExamAt,
  disabled = false,
  onCreate,
}: {
  locale: Locale;
  materialId: string;
  topics: string[];
  initialExamAt?: string;
  disabled?: boolean;
  onCreate: (input: TargetedPlanInput) => void | Promise<void>;
}) {
  const labels = locale === "zh" ? {
    title: "按这份资料生成计划",
    description: "只使用有引用依据的知识点，并按你的时间约束加入日历。",
    topics: "重点知识点",
    exam: "考试或目标日期",
    minutes: "每天分钟数",
    hour: "开始时间",
    weekdays: "学习日",
    routine: "其他固定安排（可选）",
    routinePlaceholder: "例如：周三晚有课，周末只复习",
    submit: "生成定向计划",
    submitting: "正在生成…",
    required: "至少选择一个知识点，并填写未来日期。",
    topicLimit: "一次最多选择 30 个知识点。",
  } : {
    title: "Build a plan from this material",
    description: "Use only cited topics and place them on your calendar within your constraints.",
    topics: "Focus topics",
    exam: "Exam or target date",
    minutes: "Minutes per day",
    hour: "Start hour",
    weekdays: "Study days",
    routine: "Other routine constraints (optional)",
    routinePlaceholder: "For example: class on Wednesday evening",
    submit: "Generate targeted plan",
    submitting: "Generating…",
    required: "Select at least one topic and a future target date.",
    topicLimit: "Select up to 30 focus topics at a time.",
  };
  const uniqueTopics = useMemo(() => Array.from(new Set(topics)), [topics]);
  const [selectedTopics, setSelectedTopics] = useState(
    () => new Set(initialTargetedPlanTopics(topics)),
  );
  const [examDate, setExamDate] = useState(() => initialExamDate(initialExamAt));
  const [dailyMinutes, setDailyMinutes] = useState(45);
  const [preferredHour, setPreferredHour] = useState(19);
  const [studyWeekdays, setStudyWeekdays] = useState(() => new Set([0, 1, 2, 3, 4]));
  const [routineNotes, setRoutineNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function toggleTopic(topic: string) {
    setSelectedTopics((current) => {
      const next = new Set(current);
      if (next.has(topic)) next.delete(topic);
      else if (next.size < MAX_TARGETED_PLAN_TOPICS) next.add(topic);
      else setError(labels.topicLimit);
      return next;
    });
  }

  function toggleWeekday(day: number) {
    setStudyWeekdays((current) => {
      const next = new Set(current);
      if (next.has(day)) next.delete(day);
      else next.add(day);
      return next;
    });
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled || busy) return;
    const examAt = new Date(`${examDate}T23:59:00`);
    if (
      selectedTopics.size === 0
      || studyWeekdays.size === 0
      || !Number.isFinite(examAt.getTime())
      || examAt <= new Date()
    ) {
      setError(labels.required);
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onCreate({
        material_id: materialId,
        focus_topics: Array.from(selectedTopics),
        exam_at: examAt.toISOString(),
        daily_minutes: dailyMinutes,
        study_weekdays: Array.from(studyWeekdays).toSorted(),
        preferred_hour: preferredHour,
        timezone_offset_minutes: -new Date().getTimezoneOffset(),
        routine_notes: routineNotes.trim(),
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : labels.required);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="targeted-plan-builder" data-testid="targeted-plan-builder" onSubmit={submit}>
      <div className="targeted-plan-heading">
        <CalendarPlus size={18} />
        <div><strong>{labels.title}</strong><p>{labels.description}</p></div>
      </div>
      <fieldset>
        <legend>{labels.topics}</legend>
        <div className="targeted-plan-topics">
          {uniqueTopics.map((topic) => (
            <label key={topic}>
              <input
                type="checkbox"
                checked={selectedTopics.has(topic)}
                disabled={disabled || busy}
                onChange={() => toggleTopic(topic)}
              />
              <span>{topic}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <div className="targeted-plan-grid">
        <label><span>{labels.exam}</span><input required disabled={disabled || busy} type="date" value={examDate} onChange={(event) => setExamDate(event.target.value)} /></label>
        <label><span>{labels.minutes}</span><input required disabled={disabled || busy} type="number" min={10} max={480} value={dailyMinutes} onChange={(event) => setDailyMinutes(Number(event.target.value))} /></label>
        <label><span>{labels.hour}</span><input required disabled={disabled || busy} type="number" min={0} max={23} value={preferredHour} onChange={(event) => setPreferredHour(Number(event.target.value))} /></label>
      </div>
      <fieldset>
        <legend>{labels.weekdays}</legend>
        <div className="targeted-plan-weekdays">
          {weekdayLabels[locale].map((label, day) => (
            <label key={label}>
              <input type="checkbox" disabled={disabled || busy} checked={studyWeekdays.has(day)} onChange={() => toggleWeekday(day)} />
              <span>{label}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <label className="targeted-plan-routine">
        <span>{labels.routine}</span>
        <textarea disabled={disabled || busy} maxLength={1000} value={routineNotes} placeholder={labels.routinePlaceholder} onChange={(event) => setRoutineNotes(event.target.value)} />
      </label>
      {error && <span className="targeted-plan-error" role="alert">{error}</span>}
      <button type="submit" disabled={disabled || busy || uniqueTopics.length === 0}>
        <CalendarPlus size={16} />{busy ? labels.submitting : labels.submit}
      </button>
    </form>
  );
}
