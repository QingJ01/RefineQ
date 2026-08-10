"use client";

import { ArrowDown, ArrowUp, CalendarClock, RefreshCcw, Save, Undo2 } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { validatePlanSettings, type PlanSettingsErrors } from "@/lib/plan-settings";
import type { Locale, PlanUpdateInput, StudyPlan } from "@/lib/types";


const copy = {
  zh: {
    currentConstraints: "当前安排",
    minutesPerDay: "分钟/天",
    historicalInput: "最初目标",
    historicalNote: "这里只显示创建学习空间时填写的目标，不会改变当前日程。",
    summary: "调整学习计划",
    createSummary: "生成学习计划",
    description: "修改目标、日期、每天学习时长和内容顺序。",
    goal: "学习目标",
    examDate: "目标日期",
    dailyMinutes: "每天学习多久",
    topicOrder: "学习内容顺序",
    moveUp: "上移",
    moveDown: "下移",
    cancel: "取消修改",
    save: "保存设置",
    regenerate: "重新生成课表",
    generate: "生成课表",
    notGenerated: "尚未生成日程",
    saved: "计划设置已保存。",
    goalRequired: "请填写学习目标。",
    dateRequired: "目标日期至少应为明天。",
    minutesInvalid: "每日时长须为 5–480 分钟。",
    topicsInvalid: "每个主题必须且只能出现一次。",
    confirmTitle: "重新生成学习课表？",
    confirmDescription: "现有日程会被替换；已完成的相同主题活动会尽量保留。",
    confirm: "确认重新生成",
    untitledTopic: "未命名主题",
  },
  en: {
    currentConstraints: "Current effective plan",
    minutesPerDay: "min/day",
    historicalInput: "Historical input",
    historicalNote: "This text records the original intent and does not control the current schedule.",
    summary: "Adjust learning plan",
    createSummary: "Create learning plan",
    description: "Change the goal, target date, daily time, and topic order. Saving does not rearrange existing sessions.",
    goal: "Learning goal",
    examDate: "Target date",
    dailyMinutes: "Minutes per day",
    topicOrder: "Topic order",
    moveUp: "Move up",
    moveDown: "Move down",
    cancel: "Cancel changes",
    save: "Save settings",
    regenerate: "Regenerate schedule",
    generate: "Generate schedule",
    notGenerated: "No schedule yet",
    saved: "Plan settings saved.",
    goalRequired: "Enter a learning goal.",
    dateRequired: "Choose a target date after today.",
    minutesInvalid: "Daily time must be between 5 and 480 minutes.",
    topicsInvalid: "Every topic must appear exactly once.",
    confirmTitle: "Regenerate the learning schedule?",
    confirmDescription: "Existing sessions will be replaced. Completed matching activities are preserved when possible.",
    confirm: "Regenerate schedule",
    untitledTopic: "Untitled topic",
  },
} as const;

function toLocalDateInput(iso: string): string {
  const date = new Date(iso);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function initialOrder(topicOrder: string[], topics: Record<string, string>) {
  const available = Object.keys(topics);
  return topicOrder.length === available.length && topicOrder.every((topic) => topic in topics)
    ? [...topicOrder]
    : available;
}

export function PlanSettings({
  locale,
  plan,
  topics,
  topicOrder,
  originalGoal,
  busy = false,
  onSave,
}: {
  locale: Locale;
  plan: StudyPlan | null;
  topics: Record<string, string>;
  topicOrder: string[];
  originalGoal: string;
  busy?: boolean;
  onSave: (input: PlanUpdateInput) => void | Promise<void>;
}) {
  const text = copy[locale];
  const availableTopics = useMemo(() => Object.keys(topics), [topics]);
  const defaultExamDate = useMemo(() => {
    const date = new Date();
    date.setDate(date.getDate() + 30);
    return date.toISOString().slice(0, 10);
  }, []);
  const [goal, setGoal] = useState(plan?.goal ?? originalGoal);
  const [examDate, setExamDate] = useState(plan ? toLocalDateInput(plan.exam_at) : defaultExamDate);
  const [dailyMinutes, setDailyMinutes] = useState(plan?.daily_minutes ?? 45);
  const [order, setOrder] = useState(() => initialOrder(topicOrder, topics));
  const [errors, setErrors] = useState<PlanSettingsErrors>({});
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [confirming, setConfirming] = useState(false);

  function reset() {
    setGoal(plan?.goal ?? originalGoal);
    setExamDate(plan ? toLocalDateInput(plan.exam_at) : defaultExamDate);
    setDailyMinutes(plan?.daily_minutes ?? 45);
    setOrder(initialOrder(topicOrder, topics));
    setErrors({});
    setNotice("");
  }

  function move(topic: string, direction: -1 | 1) {
    setOrder((current) => {
      const index = current.indexOf(topic);
      const destination = index + direction;
      if (index < 0 || destination < 0 || destination >= current.length) return current;
      const next = [...current];
      [next[index], next[destination]] = [next[destination], next[index]];
      return next;
    });
    setNotice("");
  }

  async function save(regenerate: boolean) {
    const nextErrors = validatePlanSettings({
      goal,
      examDate,
      dailyMinutes,
      topicOrder: order,
      availableTopics,
    });
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;
    setSaving(true);
    setNotice("");
    try {
      const examAt = new Date(`${examDate}T23:59:59`).toISOString();
      await onSave({
        goal: goal.trim(),
        exam_at: examAt,
        daily_minutes: dailyMinutes,
        topic_order: order,
        regenerate: regenerate || !plan,
      });
      setNotice(text.saved);
      setConfirming(false);
    } catch {
      setNotice("");
    } finally {
      setSaving(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void save(false);
  }

  const errorCopy = {
    goal: text.goalRequired,
    examDate: text.dateRequired,
    dailyMinutes: text.minutesInvalid,
    topicOrder: text.topicsInvalid,
  };
  const locked = busy || saving;
  const formattedExamDate = plan ? new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(plan.exam_at)) : null;

  return (
    <details className="content-card plan-settings" data-testid="plan-settings">
      <summary data-testid="plan-settings-toggle">
        <span><CalendarClock size={18} /><strong>{plan ? text.summary : text.createSummary}</strong></span>
        <small>{text.description}</small>
        <div className="current-plan-constraints" data-testid="current-plan-constraints">
          <span>{text.currentConstraints}</span>
          <strong>{plan ? `${formattedExamDate} · ${plan.daily_minutes} ${text.minutesPerDay}` : text.notGenerated}</strong>
        </div>
      </summary>
      <form onSubmit={submit} noValidate>
        <details className="historical-plan-input" data-testid="historical-plan-input">
          <summary>{text.historicalInput}</summary>
          <blockquote>{originalGoal}</blockquote>
          <small>{text.historicalNote}</small>
        </details>
        <label htmlFor="plan-goal">{text.goal}</label>
        <textarea
          id="plan-goal"
          data-testid="plan-goal"
          rows={3}
          value={goal}
          disabled={locked}
          aria-invalid={Boolean(errors.goal)}
          onChange={(event) => { setGoal(event.target.value); setNotice(""); }}
        />
        {errors.goal && <p className="form-error" role="alert">{errorCopy.goal}</p>}

        <div className="plan-settings-grid">
          <div>
            <label htmlFor="plan-exam-date">{text.examDate}</label>
            <input
              id="plan-exam-date"
              data-testid="plan-exam-date"
              type="date"
              value={examDate}
              disabled={locked}
              aria-invalid={Boolean(errors.examDate)}
              onChange={(event) => { setExamDate(event.target.value); setNotice(""); }}
            />
            {errors.examDate && <p className="form-error" role="alert">{errorCopy.examDate}</p>}
          </div>
          <div>
            <label htmlFor="plan-daily-minutes">{text.dailyMinutes}</label>
            <input
              id="plan-daily-minutes"
              data-testid="plan-daily-minutes"
              type="number"
              min={5}
              max={480}
              value={dailyMinutes}
              disabled={locked}
              aria-invalid={Boolean(errors.dailyMinutes)}
              onChange={(event) => { setDailyMinutes(Number(event.target.value)); setNotice(""); }}
            />
            {errors.dailyMinutes && <p className="form-error" role="alert">{errorCopy.dailyMinutes}</p>}
          </div>
        </div>

        <fieldset className="plan-topic-order" disabled={locked}>
          <legend>{text.topicOrder}</legend>
          {order.map((topic, index) => (
            <div key={topic} data-testid={`plan-topic-${topic}`}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{topics[topic] ?? text.untitledTopic}</strong>
              <button
                type="button"
                data-testid={`plan-topic-up-${topic}`}
                aria-label={`${text.moveUp}: ${topics[topic] ?? text.untitledTopic}`}
                disabled={index === 0}
                onClick={() => move(topic, -1)}
              ><ArrowUp size={15} /></button>
              <button
                type="button"
                data-testid={`plan-topic-down-${topic}`}
                aria-label={`${text.moveDown}: ${topics[topic] ?? text.untitledTopic}`}
                disabled={index === order.length - 1}
                onClick={() => move(topic, 1)}
              ><ArrowDown size={15} /></button>
            </div>
          ))}
          {errors.topicOrder && <p className="form-error" role="alert">{errorCopy.topicOrder}</p>}
        </fieldset>

        {notice && <p className="form-notice" data-testid="plan-settings-notice" role="status">{notice}</p>}
        <div className="plan-settings-actions">
          <button type="button" data-testid="plan-settings-cancel" disabled={locked} onClick={reset}>
            <Undo2 size={15} /> {text.cancel}
          </button>
          {plan && <button type="submit" className="secondary-action" data-testid="plan-settings-save" disabled={locked}>
            <Save size={15} /> {text.save}
          </button>}
          <button
            type="button"
            className="danger-action"
            data-testid="plan-settings-regenerate"
            disabled={locked}
            onClick={() => {
              const nextErrors = validatePlanSettings({
                goal,
                examDate,
                dailyMinutes,
                topicOrder: order,
                availableTopics,
              });
              setErrors(nextErrors);
              if (Object.keys(nextErrors).length === 0) {
                if (plan) setConfirming(true);
                else void save(true);
              }
            }}
          ><RefreshCcw size={15} /> {plan ? text.regenerate : text.generate}</button>
        </div>
      </form>
      <ConfirmDialog
        open={confirming}
        title={text.confirmTitle}
        description={text.confirmDescription}
        confirmLabel={text.confirm}
        cancelLabel={text.cancel}
        tone="danger"
        busy={locked}
        onCancel={() => setConfirming(false)}
        onConfirm={() => save(true)}
      />
    </details>
  );
}
