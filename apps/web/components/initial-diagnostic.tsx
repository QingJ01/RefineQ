"use client";

import { ClipboardCheck } from "lucide-react";
import { useState } from "react";

import type { DiagnosticResultInput, Locale } from "@/lib/types";


export function InitialDiagnostic({
  locale,
  topics,
  busy,
  onSubmit,
}: {
  locale: Locale;
  topics: Record<string, string>;
  busy: boolean;
  onSubmit: (results: DiagnosticResultInput[]) => void | Promise<void>;
}) {
  const [answers, setAnswers] = useState<Record<string, boolean>>({});
  const entries = Object.entries(topics);
  const complete = entries.length > 0 && entries.every(([topicId]) => topicId in answers);
  const copy = locale === "zh"
    ? {
      eyebrow: "起点校准",
      title: "先确认你目前能独立完成什么",
      description: "不要查资料，按当前真实状态作答。结果只用于调整起点，不是考试成绩。",
      prompt: "我能不看资料解释并应用这个主题",
      yes: "可以",
      notYet: "还不行",
      submit: "保存起点",
      saving: "正在保存…",
    }
    : {
      eyebrow: "Starting point",
      title: "Confirm what you can do independently",
      description: "Answer without checking sources. This adjusts your starting point; it is not a grade.",
      prompt: "I can explain and apply this topic without notes",
      yes: "Yes",
      notYet: "Not yet",
      submit: "Save starting point",
      saving: "Saving…",
    };

  return (
    <details className="content-card initial-diagnostic" data-testid="initial-diagnostic">
      <summary>
        <span><ClipboardCheck size={18} /> {copy.eyebrow}</span>
        <strong id="initial-diagnostic-title">{copy.title}</strong>
        <small>{copy.description}</small>
      </summary>
      <form
        aria-labelledby="initial-diagnostic-title"
        onSubmit={(event) => {
          event.preventDefault();
          if (!complete || busy) return;
          void onSubmit(entries.map(([topicId]) => ({
            topic_id: topicId,
            is_correct: answers[topicId],
          })));
        }}
      >
        <div className="initial-diagnostic-topics">
          {entries.map(([topicId, topicName]) => (
            <fieldset key={topicId}>
              <legend><strong>{topicName}</strong><span>{copy.prompt}</span></legend>
              <label>
                <input
                  type="radio"
                  name={`diagnostic-${topicId}`}
                  value="yes"
                  checked={answers[topicId] === true}
                  onChange={() => setAnswers((current) => ({ ...current, [topicId]: true }))}
                />
                {copy.yes}
              </label>
              <label>
                <input
                  type="radio"
                  name={`diagnostic-${topicId}`}
                  value="not-yet"
                  checked={answers[topicId] === false}
                  onChange={() => setAnswers((current) => ({ ...current, [topicId]: false }))}
                />
                {copy.notYet}
              </label>
            </fieldset>
          ))}
        </div>
        <button
          type="submit"
          className="primary-action"
          data-testid="submit-initial-diagnostic"
          disabled={!complete || busy}
        >
          {busy ? copy.saving : copy.submit}
        </button>
      </form>
    </details>
  );
}
