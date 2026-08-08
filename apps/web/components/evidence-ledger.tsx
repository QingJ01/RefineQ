"use client";

import { BookOpenCheck, Flag, RotateCcw, Save } from "lucide-react";
import { useState } from "react";

import type { Translator } from "@/lib/i18n";
import type {
  AttemptFeedbackInput,
  AttemptInsight,
  LearningEvidence,
  Locale,
} from "@/lib/types";
import { evidenceTone } from "@/lib/view-models";


const visibleDetailKeys = ["score", "feedback", "strengths", "gaps", "misconceptions"] as const;

const detailCopy = {
  zh: {
    attempt: "实践反馈",
    diagnostic: "初始诊断",
    review: "复习记录",
    self_explanation: "自我解释",
    material: "资料记录",
    score: "评分",
    feedback: "总体反馈",
    strengths: "做得好的地方",
    gaps: "下一步改进",
    misconceptions: "需要纠正",
    question: "练习题",
    answer: "我的回答",
    sources: "评分来源",
    retry: "重做同题",
    note: "学习者备注",
    saveNote: "保存备注",
    appeal: "申请复核",
    appealed: "已申请复核",
  },
  en: {
    attempt: "Task feedback",
    diagnostic: "Initial check",
    review: "Review",
    self_explanation: "Self-explanation",
    material: "Source record",
    score: "Score",
    feedback: "Feedback",
    strengths: "Strengths",
    gaps: "Improve next",
    misconceptions: "Correct next",
    question: "Question",
    answer: "My answer",
    sources: "Grading sources",
    retry: "Retry same question",
    note: "Learner note",
    saveNote: "Save note",
    appeal: "Request review",
    appealed: "Review requested",
  },
} as const;

function hasDisplayValue(value: unknown) {
  if (Array.isArray(value)) return value.length > 0;
  return value !== null && value !== undefined && String(value).trim().length > 0;
}

function displayValue(value: unknown) {
  return Array.isArray(value) ? value.join(" · ") : String(value);
}

function localizedSummary(item: LearningEvidence, locale: Locale) {
  if (locale !== "zh") return item.summary;
  if (item.kind === "attempt") {
    const modeNames: Record<string, string> = {
      concept: "概念",
      case: "案例",
      project: "项目",
      exam: "考试",
    };
    const rawMode = typeof item.details.learning_mode === "string"
      ? item.details.learning_mode
      : "";
    const mode = modeNames[rawMode] ?? "当前";
    return `完成一次${mode}学习任务；回答${item.details.is_correct ? "达到" : "暂未达到"}本次标准。`;
  }
  if (item.kind === "diagnostic") {
    return `完成一次初始诊断；表现${item.details.is_correct ? "达到" : "暂未达到"}当前标准。`;
  }
  return item.summary;
}

export function EvidenceLedger({
  evidence,
  locale,
  t,
  attempts = [],
  onRetryAttempt,
  onUpdateFeedback,
}: {
  evidence: LearningEvidence[];
  locale: Locale;
  t: Translator;
  attempts?: AttemptInsight[];
  onRetryAttempt?: (attempt: AttemptInsight) => void | Promise<void>;
  onUpdateFeedback?: (
    attempt: AttemptInsight,
    input: AttemptFeedbackInput,
  ) => void | Promise<void>;
}) {
  return (
    <section className="content-card ledger" aria-labelledby="ledger-heading">
      <div className="section-heading">
        <div>
          <span className="kicker">EVIDENCE / {String(evidence.length).padStart(2, "0")}</span>
          <h2 id="ledger-heading">{t("evidenceLedger")}</h2>
        </div>
        <BookOpenCheck size={22} strokeWidth={1.5} />
      </div>
      {evidence.length === 0 ? (
        <div className="empty-note">{t("noEvidence")}</div>
      ) : (
        <ol className="evidence-timeline">
          {evidence.map((item) => {
            const visibleDetails = visibleDetailKeys
              .filter((key) => hasDisplayValue(item.details[key]))
              .map((key) => [key, item.details[key]] as const);
            const attempt = item.kind === "attempt"
              ? attempts.find((candidate) => candidate.attempt_id === item.source_id)
              : undefined;
            return (
              <li key={item.id} data-tone={evidenceTone(item.kind)}>
                <div className="ledger-date">
                  {new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  }).format(new Date(item.observed_at))}
                </div>
                <div className="ledger-mark" aria-hidden="true" />
                <div>
                  <span className="evidence-kind">{detailCopy[locale][item.kind]}</span>
                  <p>{localizedSummary(item, locale)}</p>
                  {visibleDetails.length > 0 && (
                    <details className="evidence-details">
                      <summary>{t("viewDetails")}</summary>
                      <dl>
                        {visibleDetails.map(([key, value]) => (
                          <div key={key}>
                            <dt>{detailCopy[locale][key]}</dt>
                            <dd>{displayValue(value)}</dd>
                          </div>
                        ))}
                      </dl>
                    </details>
                  )}
                  {attempt && (
                    <AttemptEvidenceActions
                      locale={locale}
                      attempt={attempt}
                      onRetry={() => onRetryAttempt?.(attempt)}
                      onUpdate={(input) => onUpdateFeedback?.(attempt, input)}
                    />
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

function AttemptEvidenceActions({
  locale,
  attempt,
  onRetry,
  onUpdate,
}: {
  locale: Locale;
  attempt: AttemptInsight;
  onRetry: () => void | Promise<void>;
  onUpdate: (input: AttemptFeedbackInput) => void | Promise<void>;
}) {
  const text = detailCopy[locale];
  const [note, setNote] = useState(attempt.learner_note ?? "");
  const [busy, setBusy] = useState(false);

  async function update(input: AttemptFeedbackInput) {
    setBusy(true);
    try {
      await onUpdate(input);
    } catch {
      // The workspace-level error banner owns the localized failure message.
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="attempt-rubric" data-testid={`attempt-rubric-${attempt.attempt_id}`}>
      <summary>{text.feedback} · {attempt.score}/100</summary>
      <dl>
        <div><dt>{text.question}</dt><dd data-testid={`attempt-question-${attempt.attempt_id}`}>{attempt.question_prompt}</dd></div>
        <div><dt>{text.answer}</dt><dd>{attempt.answer}</dd></div>
        {attempt.strengths.length > 0 && (
          <div><dt>{text.strengths}</dt><dd>{attempt.strengths.join(" · ")}</dd></div>
        )}
        {attempt.gaps.length > 0 && (
          <div><dt>{text.gaps}</dt><dd>{attempt.gaps.join(" · ")}</dd></div>
        )}
        {attempt.misconceptions.length > 0 && (
          <div><dt>{text.misconceptions}</dt><dd>{attempt.misconceptions.join(" · ")}</dd></div>
        )}
      </dl>
      {attempt.sources.length > 0 && (
        <div className="attempt-sources">
          <strong>{text.sources}</strong>
          <ul>
            {attempt.sources.map((source) => (
              <li key={source.citation_id}><span>{source.filename}</span><p>{source.text}</p></li>
            ))}
          </ul>
        </div>
      )}
      <label htmlFor={`attempt-note-${attempt.attempt_id}`}>{text.note}</label>
      <textarea
        id={`attempt-note-${attempt.attempt_id}`}
        data-testid={`attempt-note-${attempt.attempt_id}`}
        rows={2}
        maxLength={2000}
        value={note}
        disabled={busy}
        onChange={(event) => setNote(event.target.value)}
      />
      <div className="attempt-feedback-actions">
        <button type="button" data-testid={`retry-attempt-${attempt.attempt_id}`} disabled={busy} onClick={() => void onRetry()}><RotateCcw size={14} /> {text.retry}</button>
        <button type="button" data-testid={`save-attempt-note-${attempt.attempt_id}`} disabled={busy} onClick={() => void update({ learner_note: note })}><Save size={14} /> {text.saveNote}</button>
        <button type="button" data-testid={`appeal-attempt-${attempt.attempt_id}`} aria-pressed={attempt.appealed} disabled={busy} onClick={() => void update({ appealed: !attempt.appealed })}><Flag size={14} /> {attempt.appealed ? text.appealed : text.appeal}</button>
      </div>
    </details>
  );
}
