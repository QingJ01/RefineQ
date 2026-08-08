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
  Layers3,
  Lightbulb,
  RotateCcw,
  Target,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";

import { AgentPanel } from "@/components/agent-panel";
import { SessionCoach } from "@/components/session-coach";
import { SourceDrawer } from "@/components/source-drawer";
import type { Translator } from "@/lib/i18n";
import { buildSessionSteps, sessionStage } from "@/lib/learning-session";
import type {
  AgentReply,
  AnswerResult,
  LearningMode,
  LearningWorkspace,
  Locale,
  MaterialRecord,
  PracticeQuestion,
  Progress,
  SavedPracticeQuestion,
  SearchSource,
  StudyPlan,
} from "@/lib/types";


const modeCopy: Record<Locale, Record<LearningMode, string>> = {
  zh: { concept: "概念学习", case: "案例拆解", project: "项目实战", exam: "模拟考试" },
  en: { concept: "Concept", case: "Case study", project: "Project", exam: "Mock exam" },
};

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
    submit: "提交分析，查看反馈",
    answerPlaceholder: "写下你的分析、步骤或可交付成果…",
    save: "收藏任务",
    saved: "取消收藏",
    replace: "换一个任务",
    next: "开始下一项任务",
    score: "本次评价",
    strength: "做得好的地方",
    gap: "下一步改进",
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
    submit: "Submit for feedback",
    answerPlaceholder: "Write your analysis, steps, or deliverable…",
    save: "Save task",
    saved: "Remove saved task",
    replace: "Try another task",
    next: "Start next task",
    score: "Evaluation",
    strength: "What worked",
    gap: "Improve next",
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

function lessonTitle(mode: LearningMode, locale: Locale, topic: string) {
  const prefix = locale === "zh"
    ? { concept: "建立可迁移的理解", case: "从真实场景拆解问题", project: "先定义可交付成果", exam: "梳理考点与解题条件" }[mode]
    : { concept: "Build transferable understanding", case: "Analyze a real situation", project: "Define a useful deliverable", exam: "Map the tested idea and conditions" }[mode];
  return `${prefix}：${topic}`;
}

export function LearningSessionCanvas({
  locale,
  t,
  workspace,
  plan,
  progress,
  materials,
  question,
  answer,
  result,
  busy,
  learningMode,
  savedQuestions,
  agentToken,
  modelConfigured,
  onModelUnavailable,
  isAdmin = false,
  onOpenAgentSettings,
  onLearningModeChange,
  onAnswerChange,
  onStartTask,
  onSubmit,
  onNextTask,
  onToggleSaved,
  onOpenLibrary,
  onAskCoach,
}: {
  locale: Locale;
  t: Translator;
  workspace: LearningWorkspace;
  plan: StudyPlan | null;
  progress: Progress | null;
  materials: MaterialRecord[];
  question: PracticeQuestion | null;
  answer: string;
  result: AnswerResult | null;
  busy: boolean;
  learningMode: LearningMode;
  savedQuestions: SavedPracticeQuestion[];
  agentToken?: string;
  modelConfigured?: boolean | null;
  onModelUnavailable?: () => void;
  isAdmin?: boolean;
  onOpenAgentSettings?: () => void;
  onLearningModeChange: (mode: LearningMode) => void;
  onAnswerChange: (answer: string) => void;
  onStartTask: () => void | Promise<void>;
  onSubmit: () => void | Promise<void>;
  onNextTask: () => void | Promise<void>;
  onToggleSaved: (question: PracticeQuestion, saved: boolean) => void | Promise<void>;
  onOpenLibrary: () => void;
  onAskCoach: (message: string) => Promise<AgentReply>;
}) {
  const text = interfaceCopy[locale];
  const steps = buildSessionSteps(learningMode, locale);
  const stage = sessionStage(question, result);
  const activeIndex = stage === "learn" ? 1 : stage === "practice" ? 2 : 3;
  const nextSession = useMemo(
    () => plan?.sessions.find((item) => item.status !== "completed"),
    [plan],
  );
  const activeTopicId = question?.topic_id ?? nextSession?.topic_id;
  const topic = activeTopicId
    ? progress?.topics?.[activeTopicId] ?? activeTopicId
    : workspace.topics[0] ?? workspace.title;
  const [selectedSources, setSelectedSources] = useState<SearchSource[]>([]);
  const agentRef = useRef<HTMLDetailsElement>(null);
  const sourceRecords = materials.slice(0, 2);
  const taskSources = result?.sources?.length ? result.sources : question?.sources ?? [];
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
        <span className="session-time"><Clock3 size={16} /> {plan?.daily_minutes ?? 45} {text.minutes}</span>
      </header>

      <div className="session-layout">
        <main className="session-main">
          <ol className="session-steps" aria-label={text.sessionProgress}>
            {steps.map((step, index) => (
              <li key={step.id} className={index < activeIndex ? "complete" : index === activeIndex ? "active" : ""}>
                <span>{index < activeIndex ? <Check size={16} /> : index + 1}</span>
                <div><strong>{step.label}</strong><small>{step.minutes} {text.minutes}</small></div>
              </li>
            ))}
          </ol>
          <div className="session-progress-line"><span style={{ width: `${(activeIndex + 1) * 25}%` }} /></div>

          <div className="session-mode-bar" aria-label={text.learningMode}>
            <span>{text.learningMode}</span>
            {(Object.keys(modeCopy[locale]) as LearningMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                data-testid={`learning-mode-${mode}`}
                aria-pressed={learningMode === mode}
                onClick={() => onLearningModeChange(mode)}
                disabled={busy}
              >
                {modeCopy[locale][mode]}
              </button>
            ))}
          </div>

          {stage === "learn" && (
            <article className="session-lesson" data-testid="session-learning-stage">
              <span className="session-section-label"><Lightbulb size={15} /> {modeCopy[locale][learningMode]}</span>
              <h2>{lessonTitle(learningMode, locale, topic)}</h2>
              <p>{workspace.goal}</p>
              <div className="session-framework" aria-label={locale === "zh" ? "学习框架" : "Learning framework"}>
                {framework(learningMode, locale).map((item, index) => (
                  <div key={item}><span>{index + 1}</span><strong>{item}</strong></div>
                ))}
              </div>
              <section className="session-brief">
                <div><Target size={17} /><span>{text.capability}</span><strong>{workspace.goal}</strong></div>
                <div><Layers3 size={17} /><span>{text.currentOutput}</span><strong>{text.outputHint}</strong></div>
              </section>
              <button
                type="button"
                className="primary-action session-primary"
                data-testid="session-start-task"
                disabled={busy}
                onClick={() => void onStartTask()}
              >
                {text.startTask} <ArrowRight size={18} />
              </button>
            </article>
          )}

          {stage === "practice" && question && (
            <article className="session-task" data-testid="session-practice-stage" data-question-id={question.id}>
              <span className="session-section-label"><Target size={15} /> {steps[2].label}</span>
              <span className={`session-grounding-badge ${taskGrounding}`} data-testid="practice-grounding">
                {groundingLabel}
              </span>
              <h2>{question.prompt}</h2>
              {taskSources[0]?.text && (
                <blockquote className="session-case-evidence">
                  <span>{locale === "zh" ? "真实材料线索" : "Source evidence"}</span>
                  <p>{taskSources[0].text}</p>
                </blockquote>
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
            </article>
          )}

          {stage === "reflect" && result && question && (
            <article className="session-feedback" data-testid="session-reflect-stage" role="status">
              <div className="feedback-score"><CheckCircle2 size={22} /><span>{text.score}</span><strong>{result.score}<small>/100</small></strong></div>
              <span className={`session-grounding-badge ${taskGrounding}`} data-testid="feedback-grounding">
                {groundingLabel}
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
              </div>
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
              <button type="button" className="primary-action session-primary" data-testid="next-question" disabled={busy} onClick={() => void onNextTask()}>
                {text.next} <ArrowRight size={18} />
              </button>
            </article>
          )}
        </main>

        <aside className="session-context">
          <section className="session-sources" aria-labelledby="session-sources-heading">
            <div className="context-heading"><FileText size={18} /><h2 id="session-sources-heading">{text.sources}</h2></div>
            {sourceRecords.length > 0 ? (
              <ul>{sourceRecords.map((material) => <li key={material.id}><FileText size={18} /><div><strong>{material.filename}</strong><span>{locale === "zh" ? `${material.chunk_count} 个片段 · 已索引` : `${material.chunk_count} chunks · indexed`}</span></div></li>)}</ul>
            ) : <p className="context-empty">{text.noSources}</p>}
            <button type="button" className="context-link" onClick={onOpenLibrary}>{text.openLibrary} <ArrowRight size={15} /></button>
          </section>
          <section className="session-method-summary">
            <span>{text.learningMode}</span>
            <strong>{modeCopy[locale][learningMode]}</strong>
            <p>{locale === "zh" ? "Agent 会按当前方式组织内容、任务与反馈。" : "The Agent adapts content, tasks, and feedback to this method."}</p>
          </section>
          <SessionCoach
            locale={locale}
            onAsk={onAskCoach}
            modelConfigured={modelConfigured}
            onModelUnavailable={onModelUnavailable}
            isAdmin={isAdmin}
            onConfigure={onOpenAgentSettings}
            onOpenFullCoach={agentToken ? openFullCoach : undefined}
          />
          <section className="session-next-review">
            <Clock3 size={18} />
            <div><span>{text.review}</span><strong>{nextReview ? new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", { month: "short", day: "numeric", weekday: "short" }).format(new Date(nextReview)) : text.reviewHint}</strong></div>
          </section>
        </aside>
      </div>
      {agentToken && (
        <details ref={agentRef} className="workspace-agent-disclosure" data-testid="workspace-agent" tabIndex={-1}>
          <summary>{locale === "zh" ? "完整对话、历史与资料引用" : "Full conversation, history, and sources"}</summary>
          <AgentPanel
            token={agentToken}
            workspaceId={workspace.id}
            t={t}
            locale={locale}
            modelConfigured={modelConfigured}
            onModelUnavailable={onModelUnavailable}
            isAdmin={isAdmin}
            onOpenSettings={onOpenAgentSettings}
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
