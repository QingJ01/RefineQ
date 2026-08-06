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
    <section className="content-card practice-card" aria-labelledby="practice-heading">
      <div className="section-heading">
        <div>
          <span className="kicker">RETRIEVAL / ACTIVE</span>
          <h2 id="practice-heading">{t("practice")}</h2>
        </div>
        <span className="practice-glyph" aria-hidden="true">Q</span>
      </div>
      {!question ? (
        <button data-testid="get-question" className="primary-action wide" onClick={onGetQuestion} disabled={busy}>
          {t("getQuestion")} <ArrowRight size={18} />
        </button>
      ) : !result ? (
        <div className="question-sheet">
          <span className="topic-label">{question.topic_id}</span>
          <h3>{question.prompt}</h3>
          <textarea
            data-testid="practice-answer"
            value={answer}
            onChange={(event) => onAnswerChange(event.target.value)}
            placeholder={t("answerPlaceholder")}
            rows={6}
          />
          <button
            data-testid="submit-answer"
            className="primary-action"
            onClick={onSubmit}
            disabled={busy || answer.trim().length === 0}
          >
            {t("submitAnswer")} <ArrowRight size={18} />
          </button>
        </div>
      ) : null}
      {result && status && (
        <div className={`practice-result ${status}`} role="status">
          {status === "mastered" ? <CheckCircle2 size={19} /> : <RotateCcw size={19} />}
          <div>
            <strong>{t(status === "mastered" ? "correct" : status)}</strong>
            <span>{t("score")}: {result.score} / 100 · {t("mastery")}: {Math.round(result.mastery * 100)}%</span>
            {!result.mastery_updated && <p>{t("masteryNotUpdated")}</p>}
            {result.feedback && <p>{result.feedback}</p>}
            {result.strengths.length > 0 && <section><b>{t("strengths")}</b><ul>{result.strengths.map((item) => <li key={item}>{item}</li>)}</ul></section>}
            {result.gaps.length > 0 && <section><b>{t("gaps")}</b><ul>{result.gaps.map((item) => <li key={item}>{item}</li>)}</ul></section>}
            {result.misconceptions.length > 0 && <section><b>{t("misconceptions")}</b><ul>{result.misconceptions.map((item) => <li key={item}>{item}</li>)}</ul></section>}
          </div>
        </div>
      )}
      {result && (
        <button
          data-testid="next-question"
          className="primary-action wide"
          onClick={onGetQuestion}
          disabled={busy}
        >
          {t("nextQuestion")} <ArrowRight size={18} />
        </button>
      )}
    </section>
  );
}
