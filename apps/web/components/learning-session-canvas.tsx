"use client";

import {
  ArrowRight,
  Bookmark,
  BookmarkCheck,
  Check,
  CheckCircle2,
  Clock3,
  ExternalLink,
  FileText,
  Lightbulb,
  RotateCcw,
  Target,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { AgentPanel } from "@/components/agent-panel";
import { RichText } from "@/components/rich-text";
import { SessionCoach } from "@/components/session-coach";
import { SourceDrawer } from "@/components/source-drawer";
import type { CoachActionOutcome } from "@/lib/coach-actions";
import type { Translator } from "@/lib/i18n";
import {
  buildLessonHighlights,
  buildSessionSteps,
  remainingSessionMinutes,
  selectTodayPlanSession,
  selectYesterdayEvidence,
} from "@/lib/learning-session";
import type {
  AgentReply,
  AnswerResult,
  ExecutableActionProposal,
  LearningMode,
  LearningEvidence,
  LearningWorkspace,
  Locale,
  MaterialRecord,
  PracticeQuestion,
  Progress,
  SavedPracticeQuestion,
  SearchSource,
  StudyPlan,
} from "@/lib/types";


const SESSION_RENDERED_AT = Date.now();

function localMidnight(value: Date): number {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
}

const interfaceCopy = {
  zh: {
    today: "今日学习",
    minutes: "分钟",
    sessionProgress: "本节进度",
    learningMode: "学习方式",
    sources: "本节资料",
    openLibrary: "查看资料库",
    noSources: "还没有关联资料，Agent 会先基于学习目标组织任务。",
    capability: "能力目标",
    currentOutput: "本次产出",
    outputHint: "一份可复用的分析或实践成果",
    startTask: "进入实战任务",
    startPlannedSession: "开始今日计划",
    submit: "提交分析，查看反馈",
    answerPlaceholder: "写下你的分析、步骤或可交付成果…",
    save: "收藏任务",
    saved: "取消收藏",
    replace: "换一个任务",
    next: "开始下一项任务",
    score: "本次评价",
    strength: "做得好的地方",
    gap: "下一步改进",
    misconception: "需要纠正的误区",
    noStrengths: "这次还没有识别到明确亮点",
    noGaps: "请先补充完整回答，再生成针对性改进建议",
    review: "后续巩固",
    reviewHint: "系统会依据本次反馈安排下一次回顾。",
    sourceLabel: "参考来源",
    materialGrounding: "材料依据",
    generalGrounding: "通用生成",
  },
  en: {
    today: "Today",
    minutes: "min",
    sessionProgress: "Session progress",
    learningMode: "Learning method",
    sources: "Session sources",
    openLibrary: "Open library",
    noSources: "No sources are linked yet. The Agent will begin from your learning goal.",
    capability: "Capability goal",
    currentOutput: "Session output",
    outputHint: "A reusable analysis or practical artifact",
    startTask: "Start applied task",
    startPlannedSession: "Start today’s plan",
    submit: "Submit for feedback",
    answerPlaceholder: "Write your analysis, steps, or deliverable…",
    save: "Save task",
    saved: "Remove saved task",
    replace: "Try another task",
    next: "Start next task",
    score: "Evaluation",
    strength: "What worked",
    gap: "Improve next",
    misconception: "Misconceptions to correct",
    noStrengths: "No clear strength was identified in this response yet",
    noGaps: "Add a complete response to receive a focused improvement suggestion",
    review: "Follow-up review",
    reviewHint: "The next review will be scheduled from this feedback.",
    sourceLabel: "Sources",
    materialGrounding: "Material-grounded",
    generalGrounding: "General practice",
  },
} as const;

function framework(mode: LearningMode, locale: Locale) {
  const zh = {
    concept: ["定义", "原理", "例子", "迁移"],
    case: ["场景", "核心问题", "现有替代", "行为证据"],
    project: ["目标", "约束", "实现", "验证"],
    exam: ["考点", "条件", "方法", "易错点"],
  } as const;
  const en = {
    concept: ["Definition", "Principle", "Example", "Transfer"],
    case: ["Context", "Core problem", "Alternative", "Evidence"],
    project: ["Goal", "Constraints", "Build", "Validate"],
    exam: ["Topic", "Conditions", "Method", "Pitfall"],
  } as const;
  return locale === "zh" ? zh[mode] : en[mode];
}

export function LearningSessionCanvas({
  locale,
  t,
  workspace,
  plan,
  progress,
  evidence = [],
  beginWithReview = false,
  materials,
  question,
  answer,
  result,
  masteryBefore = null,
  busy,
  learningMode,
  savedQuestions,
  agentToken,
  modelConfigured,
  onModelUnavailable,
  onRecheckModel,
  isAdmin = false,
  onOpenAgentSettings,
  onAnswerChange,
  onStartTask,
  preferredSessionId,
  sessionStartedAt,
  onSubmit,
  onNextTask,
  onRetryTask,
  onViewProgress,
  onToggleSaved,
  onPracticeSaved,
  onOpenLibrary,
  onAskCoach,
  onApplyCoachAction,
  onCoachTurnHandled,
}: {
  locale: Locale;
  t: Translator;
  workspace: LearningWorkspace;
  plan: StudyPlan | null;
  progress: Progress | null;
  evidence?: LearningEvidence[];
  beginWithReview?: boolean;
  materials: MaterialRecord[];
  question: PracticeQuestion | null;
  answer: string;
  result: AnswerResult | null;
  masteryBefore?: number | null;
  busy: boolean;
  learningMode: LearningMode;
  savedQuestions: SavedPracticeQuestion[];
  agentToken?: string;
  modelConfigured?: boolean | null;
  onModelUnavailable?: () => void;
  onRecheckModel?: () => Promise<boolean | null>;
  isAdmin?: boolean;
  onOpenAgentSettings?: () => void;
  onLearningModeChange: (mode: LearningMode) => void;
  onAnswerChange: (answer: string) => void;
  onStartTask: () => void | Promise<void>;
  preferredSessionId?: string | null;
  sessionStartedAt?: number;
  onSubmit: () => void | Promise<void>;
  onNextTask: () => void | Promise<void>;
  onRetryTask?: () => void | Promise<void>;
  onViewProgress?: () => void;
  onToggleSaved: (question: PracticeQuestion, saved: boolean) => void | Promise<void>;
  onPracticeSaved?: (question: SavedPracticeQuestion) => void | Promise<void>;
  onOpenLibrary: () => void;
  onAskCoach: (message: string) => Promise<AgentReply>;
  onApplyCoachAction?: (
    proposal: ExecutableActionProposal,
    options?: { confirmed?: boolean },
  ) => Promise<CoachActionOutcome>;
  onCoachTurnHandled?: () => void;
}) {
  const text = interfaceCopy[locale];
  const yesterdayEvidence = useMemo(
    () => selectYesterdayEvidence(evidence),
    [evidence],
  );
  const hasYesterdayLearning = yesterdayEvidence.length > 0;
  const [stage, setStage] = useState<"review" | "learn" | "practice" | "reflect">(
    result
      ? result.session_decision && result.session_decision.action !== "summary"
        ? "practice"
        : "reflect"
      : beginWithReview
        ? hasYesterdayLearning ? "review" : "learn"
        : question ? "practice" : "learn",
  );
  const isInterimFeedback = Boolean(
    result?.session_decision && result.session_decision.action !== "summary",
  );
  const visibleStage = result && !isInterimFeedback
    ? "reflect"
    : stage === "review" && !hasYesterdayLearning
      ? "learn"
      : stage;
  const activeIndex = visibleStage === "review" ? 0 : visibleStage === "learn" ? 1 : visibleStage === "practice" ? 2 : 3;
  const nextSession = useMemo(() => {
    const sessions = plan?.sessions ?? [];
    const preferred = preferredSessionId
      ? sessions.find((item) => item.id === preferredSessionId && item.status !== "completed")
      : undefined;
    return preferred ?? selectTodayPlanSession(sessions);
  }, [plan, preferredSessionId]);
  const sessionMinutes = nextSession?.minutes ?? plan?.daily_minutes ?? 45;
  const steps = buildSessionSteps(
    learningMode,
    locale,
    sessionMinutes,
    hasYesterdayLearning,
  );
  const [clockNow, setClockNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setClockNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  const remainingMinutes = remainingSessionMinutes(
    sessionStartedAt ?? clockNow,
    sessionMinutes,
    clockNow,
  );
  const activeTopicId = question?.topic_id ?? nextSession?.topic_id;
  const topic = activeTopicId
    ? progress?.topics?.[activeTopicId] ?? (locale === "zh" ? "未命名主题" : "Untitled topic")
    : workspace.topics[0] ?? workspace.title;
  const [selectedSources, setSelectedSources] = useState<SearchSource[]>([]);
  const agentRef = useRef<HTMLDetailsElement>(null);
  const sourceRecords = materials.slice(0, 2);
  const taskSources = result?.sources?.length ? result.sources : question?.sources ?? [];
  const primarySourceText = taskSources[0]?.text ?? "";
  const lessonHighlights = useMemo(
    () => buildLessonHighlights(primarySourceText),
    [primarySourceText],
  );
  const taskGrounding = result?.grounding
    ?? question?.grounding
    ?? (taskSources.length > 0 ? "material" : "general");
  const groundingLabel = taskGrounding === "material"
    ? text.materialGrounding
    : text.generalGrounding;
  const nextReview = result?.next_review_at
    ?? plan?.sessions.find(
      (item) => item.activity === "review" && item.status !== "completed",
    )?.planned_at;
  const isSaved = question
    ? Boolean(question.saved || savedQuestions.some((saved) => saved.id === question.id))
    : false;
  const daysUntilExam = plan?.exam_at
    ? Math.max(0, Math.round((localMidnight(new Date(plan.exam_at)) - localMidnight(new Date(SESSION_RENDERED_AT))) / 86_400_000))
    : null;
  const reviewPrompts = useMemo(() => {
    const topicNames = new Map<string, string>();
    for (const item of yesterdayEvidence) {
      const topicId = typeof item.details?.topic_id === "string" ? item.details.topic_id : "";
      if (!topicId || topicNames.has(topicId)) continue;
      topicNames.set(topicId, progress?.topics?.[topicId] ?? topicId);
    }
    const prompts = Array.from(topicNames.entries()).slice(0, 3).map(([topicId, topicName]) => {
      const topicEvidence = yesterdayEvidence.filter((item) => item.details?.topic_id === topicId);
      const weakPoint = topicEvidence
        .flatMap((item) => [
          ...(Array.isArray(item.details?.misconceptions) ? item.details.misconceptions : []),
          ...(Array.isArray(item.details?.gaps) ? item.details.gaps : []),
        ])
        .find((item): item is string => typeof item === "string" && item.trim().length > 0);
      if (weakPoint) {
        return locale === "zh"
          ? `昨天学习了“${topicName}”：请重新说明 ${weakPoint}`
          : `Yesterday you studied “${topicName}”. Revisit: ${weakPoint}`;
      }
      return locale === "zh"
        ? `昨天学习了“${topicName}”：请回忆它的核心概念，并举一个例子。`
        : `Yesterday you studied “${topicName}”. Recall its core idea and one example.`;
    });
    return prompts;
  }, [locale, progress?.topics, yesterdayEvidence]);

  function openFullCoach() {
    if (!agentRef.current) return;
    agentRef.current.open = true;
    agentRef.current.focus({ preventScroll: true });
    agentRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <section className="learning-session-canvas" data-testid="learning-session-canvas">
      <header className="session-titlebar">
        <div>
          <span className="kicker">REFINEQ / SESSION</span>
          <h1>{topic} · {text.today}</h1>
        </div>
        <div className="session-title-meta">
          {daysUntilExam !== null && (
            <span className="session-exam-countdown" data-testid="exam-countdown">
              <Target size={16} /> {daysUntilExam} {t("daysLeft")}
            </span>
          )}
          <span className="session-time" data-testid="session-time-remaining">
            <Clock3 size={16} />
            {locale === "zh" ? `剩余约 ${remainingMinutes} 分钟` : `About ${remainingMinutes} min left`}
          </span>
        </div>
      </header>

      <div className="session-layout">
        <main className="session-main">
          <ol className="session-steps" aria-label={text.sessionProgress}>
            {steps.map((step, index) => (
              <li key={step.id} className={index < activeIndex ? "complete" : index === activeIndex ? "active" : ""}>
                <span>{index < activeIndex ? <Check size={16} /> : index + 1}</span>
                <div><strong>{step.label}</strong><small>{step.minutes === 0 ? (locale === "zh" ? "今天跳过" : "Skipped today") : `${step.minutes} ${text.minutes}`}</small></div>
              </li>
            ))}
          </ol>
          <div className="session-progress-line"><span style={{ width: `${(activeIndex + 1) * 25}%` }} /></div>

          {visibleStage === "review" && (
            <article className="session-lesson session-review-stage" data-testid="session-review-stage">
              <span className="session-section-label"><RotateCcw size={15} /> {steps[0].label}</span>
              <h2>{locale === "zh" ? "先花几分钟回想一下" : "Take a few minutes to recall"}</h2>
              <p>{locale === "zh" ? "不用查资料，试着在心里回答。不会也没关系，Agent 会把薄弱点带进今天的学习。" : "Try without looking anything up. It is okay not to know yet."}</p>
              <ol className="session-review-questions">
                {reviewPrompts.map((prompt) => <li key={prompt}>{prompt}</li>)}
              </ol>
              <button
                type="button"
                className="primary-action session-primary"
                data-testid="session-finish-review"
                disabled={busy}
                onClick={async () => {
                  if (!question) await onStartTask();
                  setStage("learn");
                }}
              >
                {locale === "zh" ? "完成回顾，开始今天学习" : "Finish review and start learning"} <ArrowRight size={18} />
              </button>
            </article>
          )}

          {visibleStage === "learn" && (
            <article className="session-lesson" data-testid="session-learning-stage">
              <span className="session-section-label"><Lightbulb size={15} /> {steps[1].label}</span>
              <h2>{topic}</h2>
              <p>{locale === "zh" ? "以下内容来自今天的学习计划和相关资料。" : "This content follows today's plan and its related sources."}</p>
              {lessonHighlights.length > 0 ? (
                <section className="session-learning-content" data-testid="session-learning-content">
                  <strong>{locale === "zh" ? "资料要点" : "Key points from your material"}</strong>
                  <ul>
                    {lessonHighlights.map((highlight) => (
                      <li key={highlight}><RichText>{highlight}</RichText></li>
                    ))}
                  </ul>
                  <details>
                    <summary>{locale === "zh" ? "查看资料原文" : "View source excerpt"}</summary>
                    <RichText>{taskSources[0].text}</RichText>
                  </details>
                </section>
              ) : (
                <div className="session-brief">
                  <div><Target size={17} /><span>{text.capability}</span><strong>{workspace.goal}</strong></div>
                </div>
              )}
              {taskSources.length > 0 && (
                <button type="button" className="session-source-link" onClick={() => setSelectedSources(taskSources)}>
                  <ExternalLink size={15} /> {text.sourceLabel} · {taskSources[0].filename}
                </button>
              )}
              {materials.length === 0 && (
                <div className="session-upload-prompt" data-testid="session-upload-prompt">
                  <div>
                    <strong>{t("uploadFirstSourceTitle")}</strong>
                    <p>{t("uploadFirstSourceHint")}</p>
                  </div>
                  <button type="button" className="secondary-action" onClick={onOpenLibrary}>
                    {t("uploadFirstSourceAction")} <ArrowRight size={16} />
                  </button>
                </div>
              )}
              <div className="mobile-sticky-task-action" data-testid="mobile-sticky-task-action">
                <button
                  type="button"
                  className="primary-action session-primary"
                  data-testid="session-start-task"
                  disabled={busy}
                  onClick={() => setStage("practice")}
                >
                  {locale === "zh" ? "开始练习" : "Start practice"} <ArrowRight size={18} />
                </button>
              </div>
            </article>
          )}

          {visibleStage === "practice" && question && !result && (
            <article className="session-task" data-testid="session-practice-stage" data-question-id={question.id}>
              <span className="session-section-label"><Target size={15} /> {steps[2].label}</span>
              <span className={`session-grounding-badge ${taskGrounding}`} data-testid="practice-grounding">
                {groundingLabel}
              </span>
              {question.mode && (
                <span className="session-grounding-badge" data-testid="question-generation-mode">
                  {question.mode === "ai" ? t("aiQuestion") : t("fallbackQuestion")}
                </span>
              )}
              <span className="session-grounding-badge" data-testid="question-difficulty">
                {locale === "zh" ? `难度 ${question.difficulty_level ?? 2}/5` : `Difficulty ${question.difficulty_level ?? 2}/5`}
              </span>
              <RichText className="session-question-prompt">{question.prompt}</RichText>
              {question.explanation && (
                <div className="question-explanation" data-testid="question-explanation">
                  <strong>{locale === "zh" ? "为什么考这道题" : "Why this task matters"}</strong>
                  <RichText>{question.explanation}</RichText>
                </div>
              )}
              {lessonHighlights.length > 0 && (
                <details className="session-practice-source" data-testid="session-practice-source">
                  <summary>
                    {locale === "zh" ? "需要提示？查看相关资料" : "Need a hint? View related material"}
                  </summary>
                  <div>
                    <ul>
                      {lessonHighlights.slice(0, 3).map((highlight) => (
                        <li key={highlight}><RichText>{highlight}</RichText></li>
                      ))}
                    </ul>
                  </div>
                </details>
              )}
              <div className="session-task-framework" aria-label={locale === "zh" ? "作答框架" : "Answer framework"}>
                {framework(learningMode, locale).map((item, index) => (
                  <span key={item}><b>{index + 1}</b>{item}</span>
                ))}
              </div>
              {taskSources.length > 0 && (
                <button type="button" className="session-source-link" data-testid="practice-sources" onClick={() => setSelectedSources(taskSources)}>
                  <ExternalLink size={15} /> {text.sourceLabel} · {taskSources[0].filename}
                </button>
              )}
              <label htmlFor="session-answer">{locale === "zh" ? "你的作答或产出" : "Your answer or artifact"}</label>
              <textarea
                id="session-answer"
                data-testid="practice-answer"
                value={answer}
                disabled={busy}
                onChange={(event) => onAnswerChange(event.target.value)}
                placeholder={text.answerPlaceholder}
                rows={6}
              />
              <div className="session-task-actions">
                <button
                  type="button"
                  className="secondary-action"
                  data-testid="save-question"
                  aria-pressed={isSaved}
                  disabled={busy}
                  onClick={() => void onToggleSaved(question, !isSaved)}
                >
                  {isSaved ? <BookmarkCheck size={16} /> : <Bookmark size={16} />}
                  {isSaved ? text.saved : text.save}
                </button>
                <button type="button" className="secondary-action" data-testid="skip-question" disabled={busy} onClick={() => void onNextTask()}>
                  <RotateCcw size={16} /> {text.replace}
                </button>
                <div className="mobile-sticky-task-action" data-testid="mobile-sticky-task-action">
                  <button
                    type="button"
                    className="primary-action"
                    data-testid="submit-answer"
                    disabled={busy || !answer.trim()}
                    onClick={() => void onSubmit()}
                  >
                    {text.submit} <ArrowRight size={18} />
                  </button>
                </div>
              </div>
            </article>
          )}

          {(visibleStage === "reflect" || isInterimFeedback) && result && question && (
            <article
              className="session-feedback"
              data-testid={isInterimFeedback ? "session-task-feedback" : "session-reflect-stage"}
              role="status"
            >
              <div className="feedback-score"><CheckCircle2 size={22} /><span>{text.score}</span><strong>{result.score}<small>/100</small></strong></div>
              <span className={`session-grounding-badge ${taskGrounding}`} data-testid="feedback-grounding">
                {groundingLabel}
              </span>
              <span className="session-grounding-badge" data-testid="grading-mode">
                {result.grading_mode === "ai" ? t("aiGrading") : t("fallbackGrading")}
              </span>
              <h2>{result.feedback}</h2>
              {taskSources.length > 0 && (
                <button
                  type="button"
                  className="session-source-link"
                  data-testid="feedback-sources"
                  onClick={() => setSelectedSources(taskSources)}
                >
                  <ExternalLink size={15} /> {text.sourceLabel} · {taskSources[0].filename}
                </button>
              )}
              <div className="feedback-columns">
                <section>
                  <h3>{text.strength}</h3>
                  {result.strengths.length > 0
                    ? <ul>{result.strengths.map((item) => <li key={item}>{item}</li>)}</ul>
                    : <p className="feedback-empty">{text.noStrengths}</p>}
                </section>
                <section>
                  <h3>{text.gap}</h3>
                  {result.gaps.length > 0
                    ? <ul>{result.gaps.map((item) => <li key={item}>{item}</li>)}</ul>
                    : <p className="feedback-empty">{text.noGaps}</p>}
                </section>
                {result.misconceptions.length > 0 && (
                  <section data-testid="feedback-misconceptions">
                    <h3>{text.misconception}</h3>
                    <ul>{result.misconceptions.map((item) => <li key={item}>{item}</li>)}</ul>
                  </section>
                )}
              </div>
              {result.mastery_updated && masteryBefore !== null ? (
                <div className="session-mastery-change" data-testid="mastery-change">
                  <span>{locale === "zh" ? "掌握度" : "Mastery"}</span>
                  <strong>{Math.round(masteryBefore * 100)}%</strong>
                  <ArrowRight size={16} />
                  <strong>{Math.round(result.mastery * 100)}%</strong>
                </div>
              ) : !result.mastery_updated ? (
                <p className="session-mastery-unchanged" data-testid="mastery-unchanged">
                  {t("masteryNotUpdated")}
                </p>
              ) : null}
              <div className="session-review-note">
                <Clock3 size={17} />
                <div>
                  <strong>{text.review}</strong>
                  <span>{nextReview
                    ? new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", {
                      dateStyle: "medium",
                      timeStyle: "short",
                    }).format(new Date(nextReview))
                    : text.reviewHint}</span>
                </div>
              </div>
              {result.session_decision && (
                <div className={`session-adaptive-decision ${result.session_decision.action}`} data-testid="session-decision">
                  <strong>{result.session_decision.action === "continue_topic"
                    ? (locale === "zh" ? "再巩固一下当前知识点" : "Reinforce this topic")
                    : result.session_decision.action === "next_topic"
                      ? (locale === "zh" ? "可以进入下一个知识点" : "Ready for the next topic")
                      : (locale === "zh" ? "现在进入总结复盘" : "Wrap up now")}</strong>
                  <span>{result.session_decision.reason === "time_low"
                    ? (locale === "zh" ? "剩余时间不足以完成一道新题，已为总结预留时间。" : "Time is reserved for reflection instead of starting another task.")
                    : result.session_decision.action === "continue_topic"
                      ? (locale === "zh" ? `当前掌握度 ${Math.round(result.mastery * 100)}%，达到 ${Math.round(result.session_decision.target_mastery * 100)}% 后再推进。` : `Current mastery is ${Math.round(result.mastery * 100)}%; target is ${Math.round(result.session_decision.target_mastery * 100)}%.`)
                      : (locale === "zh" ? "系统根据掌握度和剩余时间给出这一步。" : "This step reflects mastery and remaining time.")}</span>
                  {result.session_decision.action !== "summary" && (
                    <span data-testid="next-difficulty">
                      {locale === "zh"
                        ? `下一题预计难度 ${result.difficulty_level}/5，约需 ${result.session_decision.estimated_minutes} 分钟。`
                        : `Next difficulty: ${result.difficulty_level}/5, about ${result.session_decision.estimated_minutes} minutes.`}
                    </span>
                  )}
                </div>
              )}
              <div className="mobile-sticky-task-action" data-testid="mobile-sticky-task-action">
                <button type="button" className="primary-action session-primary" data-testid="next-question" disabled={busy} onClick={() => result.session_decision?.action === "summary" ? onViewProgress?.() : void onNextTask()}>
                  {result.session_decision?.action === "summary"
                    ? (locale === "zh" ? "完成今日学习" : "Finish session")
                    : result.session_decision?.action === "next_topic"
                      ? (locale === "zh" ? "学习下一个知识点" : "Learn next topic")
                      : (locale === "zh" ? "继续巩固" : "Keep practicing")} <ArrowRight size={18} />
                </button>
              </div>
              <div className="session-reflect-actions">
                <button type="button" className="secondary-action" data-testid="reflect-view-progress" disabled={!onViewProgress} onClick={onViewProgress}>
                  {locale === "zh" ? "看进步" : "View progress"}
                </button>
                <button type="button" className="secondary-action" data-testid="reflect-retry-question" disabled={busy || !onRetryTask} onClick={() => void onRetryTask?.()}>
                  <RotateCcw size={16} /> {locale === "zh" ? "重做这题" : "Retry this task"}
                </button>
                <button type="button" className="secondary-action" data-testid="reflect-save-question" aria-pressed={isSaved} disabled={busy} onClick={() => void onToggleSaved(question, !isSaved)}>
                  {isSaved ? <BookmarkCheck size={16} /> : <Bookmark size={16} />}
                  {isSaved ? text.saved : text.save}
                </button>
              </div>
            </article>
          )}
          {result && !question && (
            <article className="session-feedback" data-testid="reflect-recovery" role="status">
              <div className="feedback-score"><CheckCircle2 size={22} /><span>{text.score}</span><strong>{result.score}<small>/100</small></strong></div>
              <h2>{result.feedback}</h2>
              <p>{locale === "zh" ? "原题题面暂时无法恢复，你仍可继续下一题或查看已保存的进度。" : "The original prompt could not be restored, but you can continue or review your saved progress."}</p>
              <div className="session-reflect-actions">
                <button type="button" className="secondary-action" data-testid="reflect-view-progress" disabled={!onViewProgress} onClick={onViewProgress}>
                  {locale === "zh" ? "看进步" : "View progress"}
                </button>
                <button type="button" className="primary-action" data-testid="next-question" disabled={busy} onClick={() => void onNextTask()}>
                  {text.next} <ArrowRight size={18} />
                </button>
              </div>
            </article>
          )}
          <section className="session-saved-questions" aria-labelledby="saved-question-heading">
            <div className="session-saved-heading">
              <h2 id="saved-question-heading">{t("savedQuestions")}</h2>
              <span>{savedQuestions.length}</span>
            </div>
            {savedQuestions.length > 0 ? (
              <ul data-testid="saved-question-list">
                {savedQuestions.map((saved) => (
                  <li key={saved.id}>
                    <div>
                      <span>{progress?.topics?.[saved.topic_id] ?? (locale === "zh" ? "未命名主题" : "Untitled topic")}</span>
                      <strong>{saved.prompt}</strong>
                    </div>
                    <button
                      type="button"
                      className="secondary-action"
                      data-testid="practice-saved-question"
                      disabled={busy || !onPracticeSaved}
                      onClick={() => void onPracticeSaved?.(saved)}
                    >
                      {t("practiceSavedTopic")} <ArrowRight size={14} />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="context-empty" data-testid="saved-question-empty">
                {t("savedQuestionsEmpty")}
              </p>
            )}
          </section>
        </main>

        <aside className="session-context">
          <section className="session-sources" aria-labelledby="session-sources-heading">
            <div className="context-heading"><FileText size={18} /><h2 id="session-sources-heading">{text.sources}</h2></div>
            {sourceRecords.length > 0 ? (
              <ul>{sourceRecords.map((material) => <li key={material.id}><FileText size={18} /><div><strong>{material.filename}</strong><span>{locale === "zh" ? `${material.chunk_count} 个片段 · 已索引` : `${material.chunk_count} chunks · indexed`}</span></div></li>)}</ul>
            ) : <p className="context-empty">{text.noSources}</p>}
            <button type="button" className="context-link" onClick={onOpenLibrary}>{text.openLibrary} <ArrowRight size={15} /></button>
          </section>
          <details open className="session-coach-disclosure" data-testid="session-coach-disclosure">
            <summary>
              <span><Lightbulb size={17} /></span>
              <div>
                <strong>{locale === "zh" ? "遇到困难？问 Agent" : "Need help? Ask the Agent"}</strong>
                <small>{locale === "zh" ? "解释题目、给提示或换个思路" : "Get an explanation, hint, or another approach"}</small>
              </div>
            </summary>
            <SessionCoach
              locale={locale}
              onAsk={onAskCoach}
              modelConfigured={modelConfigured}
              onModelUnavailable={onModelUnavailable}
              onRecheck={onRecheckModel}
              isAdmin={isAdmin}
              onConfigure={onOpenAgentSettings}
              onOpenFullCoach={agentToken ? openFullCoach : undefined}
              onApplyAction={onApplyCoachAction}
              onTurnHandled={onCoachTurnHandled}
            />
          </details>
          <section className="session-next-review">
            <Clock3 size={18} />
            <div><span>{text.review}</span><strong>{nextReview ? new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", { month: "short", day: "numeric", weekday: "short" }).format(new Date(nextReview)) : text.reviewHint}</strong></div>
          </section>
        </aside>
      </div>
      {agentToken && (
        <details open ref={agentRef} className="workspace-agent-disclosure" data-testid="workspace-agent" tabIndex={-1}>
          <summary>{locale === "zh" ? "完整对话、历史与资料引用" : "Full conversation, history, and sources"}</summary>
          <AgentPanel
            token={agentToken}
            workspaceId={workspace.id}
            t={t}
            locale={locale}
            modelConfigured={modelConfigured}
            onModelUnavailable={onModelUnavailable}
            onRecheck={onRecheckModel}
            isAdmin={isAdmin}
            onOpenSettings={onOpenAgentSettings}
            onApplyAction={onApplyCoachAction}
          />
        </details>
      )}
      {selectedSources.length > 0 && (
        <SourceDrawer
          title={text.sourceLabel}
          sources={selectedSources}
          t={t}
          onClose={() => setSelectedSources([])}
        />
      )}
    </section>
  );
}
