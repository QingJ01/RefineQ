"use client";

import {
  ArrowRight,
  Bookmark,
  BookmarkCheck,
  CheckCircle2,
  ExternalLink,
  RefreshCw,
  RotateCcw,
} from "lucide-react";
import { useState } from "react";

import { SourceDrawer } from "@/components/source-drawer";
import type { Translator } from "@/lib/i18n";
import type {
  AnswerResult,
  PracticeQuestion,
  PracticeRequest,
  SavedPracticeQuestion,
  SearchSource,
} from "@/lib/types";
import { practiceStatus } from "@/lib/view-models";


export function PracticeCard({
  question,
  answer,
  result,
  busy,
  difficulty,
  savedQuestions,
  onAnswerChange,
  onGetQuestion,
  onSubmit,
  onDifficultyChange,
  onToggleSaved,
  t,
}: {
  question: PracticeQuestion | null;
  answer: string;
  result: AnswerResult | null;
  busy: boolean;
  difficulty: number | null;
  savedQuestions: SavedPracticeQuestion[];
  onAnswerChange: (answer: string) => void;
  onGetQuestion: (request?: PracticeRequest) => void | Promise<void>;
  onSubmit: () => void;
  onDifficultyChange: (difficulty: number | null) => void;
  onToggleSaved: (question: PracticeQuestion, saved: boolean) => void | Promise<void>;
  t: Translator;
}) {
  const status = result ? practiceStatus(result) : null;
  const [selectedSources, setSelectedSources] = useState<SearchSource[]>([]);
  const availableSources = result?.sources?.length ? result.sources : question?.sources ?? [];

  function requestOptions(extra: PracticeRequest = {}): PracticeRequest {
    return {
      ...(difficulty === null ? {} : { difficulty }),
      ...extra,
    };
  }

  return (
    <section
      id="active-practice"
      className="content-card practice-card"
      aria-labelledby="practice-heading"
      aria-busy={busy}
    >
      <div className="section-heading">
        <div>
          <span className="kicker">RETRIEVAL / ACTIVE</span>
          <h2 id="practice-heading">{t("practice")}</h2>
        </div>
        <span className="practice-glyph" aria-hidden="true">Q</span>
      </div>

      <div className="practice-toolbar">
        <label htmlFor="practice-difficulty">{t("difficultyLevel")}</label>
        <select
          id="practice-difficulty"
          data-testid="practice-difficulty"
          value={difficulty ?? "adaptive"}
          disabled={busy}
          onChange={(event) => onDifficultyChange(
            event.target.value === "adaptive" ? null : Number(event.target.value),
          )}
        >
          <option value="adaptive">{t("adaptiveDifficulty")}</option>
          {[1, 2, 3, 4, 5].map((level) => (
            <option key={level} value={level}>{t("difficulty")} {level}</option>
          ))}
        </select>
      </div>

      {!question ? (
        <button
          data-testid="get-question"
          className="primary-action wide"
          onClick={() => void onGetQuestion(requestOptions())}
          disabled={busy}
        >
          {t("getQuestion")} <ArrowRight size={18} />
        </button>
      ) : !result ? (
        <div className="question-sheet">
          <div className="practice-meta">
            <span className="topic-label">{question.topic_id}</span>
            {question.difficulty_level ? <span>{t("difficulty")} {question.difficulty_level}</span> : null}
            <span>{t(question.mode === "ai" ? "aiQuestion" : "fallbackQuestion")}</span>
          </div>
          <h3>{question.prompt}</h3>
          <div className="practice-question-actions">
            <button
              type="button"
              data-testid="save-question"
              disabled={busy}
              aria-pressed={question.saved ?? false}
              onClick={() => void onToggleSaved(question, !(question.saved ?? false))}
            >
              {question.saved ? <BookmarkCheck size={15} /> : <Bookmark size={15} />}
              {t(question.saved ? "unsaveQuestion" : "saveQuestion")}
            </button>
            {availableSources.length > 0 && (
              <button
                type="button"
                data-testid="practice-sources"
                onClick={() => setSelectedSources(availableSources)}
              ><ExternalLink size={15} /> {t("viewSources")}</button>
            )}
            <button
              type="button"
              data-testid="skip-question"
              disabled={busy}
              onClick={() => void onGetQuestion(requestOptions({ replace: true }))}
            ><RefreshCw size={15} /> {t("skipQuestion")}</button>
          </div>
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

      {result && status && question && (
        <>
          <div className={`practice-result ${status}`} role="status">
            {status === "mastered" ? <CheckCircle2 size={19} /> : <RotateCcw size={19} />}
            <div>
              <strong>{t(status === "mastered" ? "correct" : status)}</strong>
              <span>{t("score")}: {result.score} / 100 · {t("mastery")}: {Math.round(result.mastery * 100)}%</span>
              <div className="practice-meta result-meta">
                <span>{t("difficulty")} {result.difficulty_level}</span>
                <span>{t(result.grading_mode === "ai" ? "aiGrading" : "fallbackGrading")}</span>
              </div>
              {!result.mastery_updated && <p>{t("masteryNotUpdated")}</p>}
              {result.feedback && <p>{result.feedback}</p>}
              {result.strengths.length > 0 && <section><b>{t("strengths")}</b><ul>{result.strengths.map((item) => <li key={item}>{item}</li>)}</ul></section>}
              {result.gaps.length > 0 && <section><b>{t("gaps")}</b><ul>{result.gaps.map((item) => <li key={item}>{item}</li>)}</ul></section>}
              {result.misconceptions.length > 0 && <section><b>{t("misconceptions")}</b><ul>{result.misconceptions.map((item) => <li key={item}>{item}</li>)}</ul></section>}
            </div>
          </div>
          <div className="practice-result-actions">
            <button
              type="button"
              data-testid="save-question"
              className="secondary-action"
              disabled={busy}
              aria-pressed={question.saved ?? false}
              onClick={() => void onToggleSaved(question, !(question.saved ?? false))}
            >
              {question.saved ? <BookmarkCheck size={15} /> : <Bookmark size={15} />}
              {t(question.saved ? "unsaveQuestion" : "saveQuestion")}
            </button>
            {availableSources.length > 0 && (
              <button type="button" data-testid="practice-sources" className="secondary-action" onClick={() => setSelectedSources(availableSources)}>
                <ExternalLink size={15} /> {t("viewSources")}
              </button>
            )}
            <button
              type="button"
              data-testid="retry-topic"
              className="secondary-action"
              disabled={busy}
              onClick={() => void onGetQuestion({
                topicId: question.topic_id,
                difficulty: question.difficulty_level,
                replace: true,
              })}
            ><RotateCcw size={15} /> {t("retryTopic")}</button>
            <button
              data-testid="next-question"
              className="primary-action"
              onClick={() => void onGetQuestion(requestOptions())}
              disabled={busy}
            >
              {t("nextQuestion")} <ArrowRight size={18} />
            </button>
          </div>
        </>
      )}

      {savedQuestions.length > 0 && (
        <details className="saved-question-list">
          <summary>{t("savedQuestions")} <span>{savedQuestions.length}</span></summary>
          <ul>
            {savedQuestions.map((saved) => (
              <li key={saved.id} data-testid="practice-saved-question">
                <div><span>{saved.topic_id}</span><strong>{saved.prompt}</strong></div>
                <button
                  type="button"
                  data-testid="practice-saved-topic"
                  disabled={busy}
                  onClick={() => void onGetQuestion({
                    topicId: saved.topic_id,
                    difficulty: saved.difficulty_level,
                    replace: true,
                  })}
                >{t("practiceSavedTopic")} <ArrowRight size={14} /></button>
              </li>
            ))}
          </ul>
        </details>
      )}

      {selectedSources.length > 0 && (
        <SourceDrawer
          title={t("sources")}
          sources={selectedSources}
          t={t}
          onClose={() => setSelectedSources([])}
        />
      )}
    </section>
  );
}
