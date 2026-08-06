import { ArrowRight, CheckCircle2, RotateCcw } from "lucide-react";

import type { Translator } from "@/lib/i18n";
import type { AnswerResult, PracticeQuestion } from "@/lib/types";
import { practiceStatus } from "@/lib/view-models";


export function PracticeCard({
  question,
  answer,
  result,
  busy,
  onAnswerChange,
  onGetQuestion,
  onSubmit,
  t,
}: {
  question: PracticeQuestion | null;
  answer: string;
  result: AnswerResult | null;
  busy: boolean;
  onAnswerChange: (answer: string) => void;
  onGetQuestion: () => void;
  onSubmit: () => void;
  t: Translator;
}) {
  const status = result ? practiceStatus(result) : null;
  return (
    <section className="paper-card practice-card" aria-labelledby="practice-heading">
      <div className="section-heading">
        <div>
          <span className="kicker">RETRIEVAL / ACTIVE</span>
          <h2 id="practice-heading">{t("practice")}</h2>
        </div>
        <span className="practice-glyph" aria-hidden="true">Q</span>
      </div>
      {!question ? (
        <button className="primary-action wide" onClick={onGetQuestion} disabled={busy}>
          {t("getQuestion")} <ArrowRight size={18} />
        </button>
      ) : (
        <div className="question-sheet">
          <span className="topic-label">{question.topic_id}</span>
          <h3>{question.prompt}</h3>
          <textarea
            value={answer}
            onChange={(event) => onAnswerChange(event.target.value)}
            placeholder={t("answerPlaceholder")}
            rows={6}
          />
          <button
            className="primary-action"
            onClick={onSubmit}
            disabled={busy || answer.trim().length === 0}
          >
            {t("submitAnswer")} <ArrowRight size={18} />
          </button>
        </div>
      )}
      {result && status && (
        <div className={`practice-result ${status}`} role="status">
          {status === "mastered" ? <CheckCircle2 size={19} /> : <RotateCcw size={19} />}
          <div>
            <strong>{t(status === "mastered" ? "correct" : status)}</strong>
            <span>{t("mastery")}: {Math.round(result.mastery * 100)}%</span>
          </div>
        </div>
      )}
    </section>
  );
}
