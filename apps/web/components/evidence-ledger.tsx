import { BookOpenCheck } from "lucide-react";

import type { Translator } from "@/lib/i18n";
import type { LearningEvidence, Locale } from "@/lib/types";
import { evidenceTone } from "@/lib/view-models";


const visibleDetailKeys = ["score", "feedback", "strengths", "gaps", "misconceptions"] as const;

const detailCopy = {
  zh: {
    attempt: "实践反馈",
    diagnostic: "初始诊断",
    review: "复盘记录",
    self_explanation: "自我解释",
    material: "资料记录",
    score: "评分",
    feedback: "总体反馈",
    strengths: "做得好的地方",
    gaps: "下一步改进",
    misconceptions: "需要纠正",
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
}: {
  evidence: LearningEvidence[];
  locale: Locale;
  t: Translator;
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
                        <div key={key}><dt>{detailCopy[locale][key]}</dt><dd>{displayValue(value)}</dd></div>
                      ))}
                    </dl>
                  </details>
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
