import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { EvidenceLedger } from "../components/evidence-ledger";
import { AuthPanel } from "../components/auth-panel";
import { AgentPanel } from "../components/agent-panel";
import { AdminConsole } from "../components/admin-console";
import { LearningHome } from "../components/learning-home";
import { LearningSessionCanvas } from "../components/learning-session-canvas";
import { MaterialDropzone } from "../components/material-dropzone";
import { PlanTimeline } from "../components/plan-timeline";
import { PracticeCard } from "../components/practice-card";
import { ProgressInsights } from "../components/progress-insights";
import { SourceDrawer } from "../components/source-drawer";
import { ConfirmDialog } from "../components/confirm-dialog";
import { SessionCoach } from "../components/session-coach";
import { translator } from "../lib/i18n";
import type { SearchSource } from "../lib/types";


const t = translator("en");

describe("focused learning components", () => {
  it("renders one coherent capability session with contextual sources and coach", () => {
    const html = renderToStaticMarkup(
      <LearningSessionCanvas
        locale="zh"
        t={t}
        workspace={{
          id: "product-thinking",
          title: "产品思维",
          subject: "product",
          goal: "学会验证真实用户需求",
          topics: ["用户需求验证"],
          keywords: ["需求验证"],
          routing_summary: "能力学习",
          archived: false,
          created_at: "2026-08-07T00:00:00Z",
          last_active_at: "2026-08-07T00:00:00Z",
        }}
        plan={null}
        progress={null}
        materials={[{
          id: "interview",
          filename: "用户访谈原文.md",
          content_type: "text/markdown",
          size: 1200,
          status: "indexed",
          chunk_count: 3,
          content_sha256: "abc",
          indexed_at: "2026-08-07T00:00:00Z",
        }]}
        question={null}
        answer=""
        result={null}
        busy={false}
        learningMode="case"
        savedQuestions={[]}
        onLearningModeChange={() => undefined}
        onAnswerChange={() => undefined}
        onStartTask={() => undefined}
        onSubmit={() => undefined}
        onNextTask={() => undefined}
        onToggleSaved={() => undefined}
        onOpenLibrary={() => undefined}
        onAskCoach={async () => ({
          session_id: "session-1",
          message: "我们从真实行为证据开始。",
          citations: [],
          sources: [],
        })}
      />,
    );

    expect(html).toContain('data-testid="learning-session-canvas"');
    expect(html).toContain('data-testid="learning-mode-case"');
    expect(html).toContain("目标校准");
    expect(html).toContain("案例拆解");
    expect(html).toContain("实战任务");
    expect(html).toContain("反馈复盘");
    expect(html).toContain("用户访谈原文.md");
    expect(html).toContain('data-testid="session-coach"');
    expect(html).not.toContain("证据账本");
  });

  it("distinguishes material-grounded practice from general generation", () => {
    const source: SearchSource = {
      citation_id: "interview#0",
      material_id: "interview",
      filename: "用户访谈原文.md",
      chunk_index: 0,
      text: "用户会先把访谈记录复制到表格，再逐条打标签。",
      score: 0.92,
    };
    const renderGrounding = (
      grounding: "material" | "general",
      sources: SearchSource[],
      reflect = false,
    ) => renderToStaticMarkup(
      <LearningSessionCanvas
        locale="zh"
        t={translator("zh")}
        workspace={{
          id: "product-thinking",
          title: "产品思维",
          subject: "product",
          goal: "识别真实用户需求",
          topics: ["用户需求验证"],
          keywords: ["需求验证"],
          routing_summary: "能力学习",
          archived: false,
          created_at: "2026-08-07T00:00:00Z",
          last_active_at: "2026-08-07T00:00:00Z",
        }}
        plan={null}
        progress={null}
        materials={[]}
        question={{
          id: "question-1",
          topic_id: "user-needs",
          prompt: "分析用户当前的替代方案",
          grounding,
          sources,
        }}
        answer=""
        result={reflect ? {
          attempt_id: "attempt-1",
          question_id: "question-1",
          topic_id: "user-needs",
          is_correct: true,
          mastery: 0.6,
          difficulty_level: 2,
          evidence_id: "evidence-1",
          score: 80,
          feedback: "已经区分了表面诉求与行为证据。",
          strengths: ["引用了行为证据"],
          gaps: [],
          misconceptions: [],
          citations: [],
          sources,
          grounding,
          grading_mode: "ai",
          mastery_updated: true,
          replayed: false,
        } : null}
        busy={false}
        learningMode="case"
        savedQuestions={[]}
        onLearningModeChange={() => undefined}
        onAnswerChange={() => undefined}
        onStartTask={() => undefined}
        onSubmit={() => undefined}
        onNextTask={() => undefined}
        onToggleSaved={() => undefined}
        onOpenLibrary={() => undefined}
        onAskCoach={async () => ({ session_id: "session-1", message: "", citations: [], sources: [] })}
      />,
    );

    const materialHtml = renderGrounding("material", [source]);
    const generalHtml = renderGrounding("general", []);
    const feedbackHtml = renderGrounding("material", [source], true);

    expect(materialHtml).toContain('data-testid="practice-grounding"');
    expect(materialHtml).toContain("材料依据");
    expect(materialHtml).toContain('data-testid="practice-sources"');
    expect(generalHtml).toContain("通用生成");
    expect(generalHtml).not.toContain("真实材料线索");
    expect(feedbackHtml).toContain('data-testid="feedback-grounding"');
    expect(feedbackHtml).toContain("材料依据");
    expect(feedbackHtml).toContain('data-testid="feedback-sources"');
    expect(feedbackHtml).toContain("用户访谈原文.md");
  });

  it("keeps empty grading dimensions explicit instead of rendering blank cards", () => {
    const html = renderToStaticMarkup(
      <LearningSessionCanvas
        locale="zh"
        t={translator("zh")}
        workspace={{
          id: "math-space",
          title: "高等数学",
          subject: "mathematics",
          goal: "掌握导数",
          topics: ["链式法则"],
          keywords: ["导数"],
          routing_summary: "考试学习",
          archived: false,
          created_at: "2026-08-07T00:00:00Z",
          last_active_at: "2026-08-07T00:00:00Z",
        }}
        plan={null}
        progress={null}
        materials={[]}
        question={{ id: "question-1", topic_id: "chain-rule", prompt: "解释链式法则" }}
        answer=""
        result={{
          attempt_id: "attempt-1",
          question_id: "question-1",
          topic_id: "chain-rule",
          is_correct: false,
          mastery: 0,
          difficulty_level: 2,
          evidence_id: "evidence-1",
          score: 0,
          feedback: "回答信息不足，请用完整句子说明原理。",
          strengths: [],
          gaps: [],
          misconceptions: [],
          citations: [],
          grading_mode: "ai",
          mastery_updated: false,
          replayed: false,
        }}
        busy={false}
        learningMode="concept"
        savedQuestions={[]}
        onLearningModeChange={() => undefined}
        onAnswerChange={() => undefined}
        onStartTask={() => undefined}
        onSubmit={() => undefined}
        onNextTask={() => undefined}
        onToggleSaved={() => undefined}
        onOpenLibrary={() => undefined}
        onAskCoach={async () => ({ session_id: "session-1", message: "", citations: [], sources: [] })}
      />,
    );

    expect(html).toContain("这次还没有识别到明确亮点");
    expect(html).toContain("请先补充完整回答，再生成针对性改进建议");
  });

  it("renders a reusable accessible confirmation dialog", () => {
    const html = renderToStaticMarkup(
      <ConfirmDialog
        open
        title="Delete material?"
        description="This also removes its search index."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        tone="danger"
        onConfirm={() => undefined}
        onCancel={() => undefined}
      />,
    );

    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
    expect(html).toContain('data-testid="confirm-dialog-confirm"');
    expect(html).toContain('data-testid="confirm-dialog-cancel"');
    expect(html).toContain("Delete material?");
  });

  it("renders a concise administrator overview without full configuration forms", () => {
    const html = renderToStaticMarkup(
      <AdminConsole
        token="admin-token"
        locale="zh"
        onLogout={() => undefined}
        onToggleLocale={() => undefined}
      />,
    );

    expect(html).toContain('class="admin-console"');
    expect(html).toContain('data-testid="admin-overview"');
    expect(html).toContain('data-testid="admin-system-status"');
    expect(html).toContain('data-testid="admin-next-action"');
    expect(html).toContain('data-testid="admin-principles"');
    expect(html).not.toContain('data-testid="admin-integration-link-');
    expect(html).not.toContain('data-testid="integration-card-');
    expect(html).toContain('data-testid="admin-logout"');
  });

  it("renders only the selected integration on a detail route", () => {
    const html = renderToStaticMarkup(
      <AdminConsole
        token="admin-token"
        locale="en"
        activeKind="chat"
        onLogout={() => undefined}
        onToggleLocale={() => undefined}
      />,
    );

    expect(html).toContain('data-testid="admin-integration-detail"');
    expect(html).toContain('data-testid="integration-card-chat"');
    expect(html).toContain('data-testid="admin-form-section-basic"');
    expect(html).toContain('data-testid="admin-form-section-credentials"');
    expect(html).toContain('data-testid="admin-form-section-network"');
    expect(html).toContain('data-testid="admin-save-test"');
    expect(html.match(/data-testid="integration-card-/g)).toHaveLength(1);
    expect(html).not.toContain('data-testid="integration-card-embedding"');
  });

  it("presents authentication as a calm RefineQ welcome card", () => {
    const html = renderToStaticMarkup(
      <AuthPanel t={translator("zh")} onAuthenticated={() => undefined} />,
    );

    expect(html).toContain('class="auth-brand"');
    expect(html).toContain("RefineQ");
    expect(html).toContain('class="auth-welcome"');
    expect(html).toContain('class="auth-form-side"');
    expect(html).not.toContain("auth-orbit");
    expect(html).toContain('data-brand-mark="refineq-q-page"');
    expect(html).toContain('data-brand-fold="true"');
    expect(html).toContain('data-brand-progress="true"');
    expect(html).toContain('data-brand-name="RefineQ"');
    expect(html).toContain('translate="no"');
    expect(html).not.toContain('<span aria-hidden="true">Q</span>');
    expect(html).not.toContain(">R</span>");
    expect(html).not.toContain("auth-memory-track");
    expect(html).not.toContain("auth-memory-step");
    expect(html).toContain('class="auth-illustration"');
    expect(html).toContain("refineq-learning-illustration.png");
    expect(html).toMatch(/<img(?=[^>]*class="auth-illustration")(?=[^>]*aria-hidden="true")[^>]*>/);
    expect(html).toContain("目标");
    expect(html).toContain("资料");
    expect(html).toContain("练习");
    expect(html).toContain("进步");
    expect(html).toContain('autoComplete="email"');
    expect(html).toContain('autoComplete="current-password"');
    expect(html).toContain('data-testid="toggle-password"');
    expect(html).toContain('data-testid="forgot-password"');
  });

  it("starts with one personal Agent prompt instead of a project form", () => {
    const html = renderToStaticMarkup(
      <LearningHome
        t={translator("zh")}
        busy={false}
        workspaces={[]}
        onResolve={() => undefined}
        onOpen={() => undefined}
        onLogout={() => undefined}
        onToggleLocale={() => undefined}
      />,
    );

    expect(html).toContain("今天想学什么");
    expect(html).not.toContain("项目名称");
    expect(html).toContain('class="home-shell"');
    expect(html).toContain('class="home-sidebar"');
    expect(html).toContain('class="learning-composer"');
    expect(html).toContain("RefineQ");
    expect(html).toContain('data-testid="home-logout"');
    expect(html).toContain('data-testid="home-language"');
  });

  it("makes recent learning and workspace correction actions operable", () => {
    const html = renderToStaticMarkup(
      <LearningHome
        t={translator("zh")}
        busy={false}
        workspaces={[{
          id: "math-space",
          title: "高等数学",
          subject: "数学",
          goal: "准备期末考试",
          topics: ["极限"],
          keywords: ["高数"],
          routing_summary: "数学学习",
          archived: false,
          created_at: "2026-08-07T00:00:00Z",
          last_active_at: "2026-08-07T00:00:00Z",
        }]}
        onResolve={() => undefined}
        onOpen={() => undefined}
        onUpdate={() => undefined}
        onDelete={() => undefined}
        showArchived={false}
        onToggleArchived={() => undefined}
        onLogout={() => undefined}
        onToggleLocale={() => undefined}
      />,
    );

    expect(html).toContain('id="recent-learning"');
    expect(html).toContain('data-testid="workspace-rename-math-space"');
    expect(html).toContain('data-testid="workspace-archive-math-space"');
    expect(html).toContain('data-testid="workspace-delete-math-space"');
    expect(html).toContain('data-testid="archived-workspaces-toggle"');
  });

  it("renders plan sessions as a numbered study path", () => {
    const html = renderToStaticMarkup(
      <PlanTimeline
        locale="en"
        t={t}
        plan={{
          id: "plan-1",
          goal: "Pass calculus",
          exam_at: "2026-08-10T08:00:00Z",
          daily_minutes: 45,
          sessions: [
            {
              id: "session-1",
              topic_id: "limits",
              planned_at: "2026-08-06T08:00:00Z",
              minutes: 45,
              activity: "learn",
            },
          ],
        }}
        onUpdateSession={() => undefined}
        onStartSession={() => undefined}
      />,
    );

    expect(html).toContain("limits");
    expect(html).toContain("01");
    expect(html).toContain("45 min");
    expect(html).toContain("Learn");
    expect(html).toContain("content-card plan-card");
    expect(html).toContain('data-testid="complete-session-session-1"');
    expect(html).toContain('data-testid="defer-session-session-1"');
    expect(html).toContain('data-testid="start-session-session-1"');
  });

  it("keeps long study paths focused until the learner expands them", () => {
    const html = renderToStaticMarkup(
      <PlanTimeline
        locale="en"
        t={t}
        plan={{
          id: "plan-long",
          goal: "Prepare for finals",
          exam_at: "2026-09-01T08:00:00Z",
          daily_minutes: 45,
          sessions: Array.from({ length: 10 }, (_, index) => ({
            id: `session-${index + 1}`,
            topic_id: `topic-${index + 1}`,
            planned_at: `2026-08-${String(index + 6).padStart(2, "0")}T08:00:00Z`,
            minutes: 45,
          })),
        }}
      />,
    );

    expect(html.match(/class="plan-session"/g)).toHaveLength(7);
    expect(html).toContain('id="study-plan-sessions"');
    expect(html).toContain('aria-controls="study-plan-sessions"');
    expect(html).toContain('data-testid="toggle-plan-sessions"');
    expect(html).toContain("Show all 10 sessions");
  });

  it("renders evidence as a dated ledger", () => {
    const html = renderToStaticMarkup(
      <EvidenceLedger
        locale="en"
        t={t}
        evidence={[
          {
            id: "evidence-1",
            kind: "attempt",
            source_id: "attempt-1",
            summary: "Practice response for limits was correct.",
            observed_at: "2026-08-06T08:00:00Z",
            details: {
              topic_id: "topic_internal",
              question_id: "question_internal",
              score: 88,
              feedback: "Strong explanation",
            },
          },
        ]}
      />,
    );

    expect(html).toContain("Learning record");
    expect(html).toContain("Practice response for limits was correct.");
    expect(html).toContain("data-tone=\"jade\"");
    expect(html).toContain('class="evidence-timeline"');
    expect(html).toContain("Strong explanation");
    expect(html).toContain("<details");
    expect(html).not.toContain("topic_internal");
    expect(html).not.toContain("question_internal");
  });

  it("turns mastery into an actionable progress recommendation", () => {
    const html = renderToStaticMarkup(
      <ProgressInsights
        t={t}
        progress={{
          goal: "Pass calculus",
          mastery: { limits: 0.72, derivatives: 0.34 },
          topics: { limits: "Function limits", derivatives: "Derivatives" },
          diagnostic_count: 1,
          attempt_count: 4,
          plan_id: "plan-1",
        }}
        onPracticeTopic={() => undefined}
      />,
    );

    expect(html).toContain("Derivatives");
    expect(html).toContain("34%");
    expect(html).toContain('data-testid="progress-recommendation"');
    expect(html).toContain('data-testid="practice-recommended-topic"');
  });

  it("renders source evidence in a focused disclosure drawer", () => {
    const html = renderToStaticMarkup(
      <SourceDrawer
        title="Evidence sources"
        t={t}
        onClose={() => undefined}
        sources={[{
          citation_id: "notes#0",
          material_id: "material-1",
          filename: "notes.md",
          chunk_index: 0,
          text: "A limit describes the value a function approaches.",
          score: 0.91,
        }]}
      />,
    );

    expect(html).not.toContain("notes#0");
    expect(html).toContain("notes.md");
    expect(html).toContain('role="dialog"');
    expect(html).toContain("91% match");
  });

  it("renders a localized empty source disclosure", () => {
    const html = renderToStaticMarkup(
      <SourceDrawer title="Evidence sources" t={t} sources={[]} onClose={() => undefined} />,
    );

    expect(html).toContain("No source excerpts are available");
    expect(html).toContain('aria-label="Close"');
  });

  it("never renders an expected answer in the practice card", () => {
    const html = renderToStaticMarkup(
      <PracticeCard
        t={t}
        question={{
          id: "question-1",
          topic_id: "limits",
          prompt: "Explain a limit",
          difficulty_level: 3,
          citations: ["notes#0"],
          sources: [{
            citation_id: "notes#0",
            material_id: "material-1",
            filename: "notes.md",
            chunk_index: 0,
            text: "A limit is an approached value.",
            score: 0.91,
          }],
          saved: false,
        }}
        answer=""
        result={null}
        busy={false}
        difficulty={null}
        savedQuestions={[]}
        onAnswerChange={() => undefined}
        onGetQuestion={() => undefined}
        onSubmit={() => undefined}
        onDifficultyChange={() => undefined}
        onToggleSaved={() => undefined}
      />,
    );

    expect(html).toContain("Explain a limit");
    expect(html).not.toContain("expected_answer");
    expect(html).toContain("content-card practice-card");
    expect(html).toContain('data-testid="practice-difficulty"');
    expect(html).toContain('data-testid="skip-question"');
    expect(html).toContain('data-testid="save-question"');
    expect(html).toContain('data-testid="practice-sources"');
  });

  it("renders explainable AI grading feedback", () => {
    const html = renderToStaticMarkup(
      <PracticeCard
        t={translator("zh")}
        question={{
          id: "question-1",
          topic_id: "limits",
          prompt: "解释函数极限",
          difficulty_level: 3,
          citations: ["notes#0"],
          mode: "ai",
        }}
        answer="函数值趋近的目标"
        result={{
          attempt_id: "attempt-1",
          question_id: "question-1",
          topic_id: "limits",
          is_correct: true,
          mastery: 0.6,
          difficulty_level: 3,
          evidence_id: "evidence-1",
          score: 88,
          feedback: "核心概念正确，可以补充形式化定义。",
          strengths: ["说明了趋近"],
          gaps: ["缺少形式化定义"],
          misconceptions: [],
          citations: ["notes#0"],
          sources: [{
            citation_id: "notes#0",
            material_id: "material-1",
            filename: "notes.md",
            chunk_index: 0,
            text: "函数极限是函数值趋近的目标。",
            score: 0.91,
          }],
          grading_mode: "ai",
          mastery_updated: true,
          replayed: false,
        }}
        busy={false}
        difficulty={3}
        savedQuestions={[]}
        onAnswerChange={() => undefined}
        onGetQuestion={() => undefined}
        onSubmit={() => undefined}
        onDifficultyChange={() => undefined}
        onToggleSaved={() => undefined}
      />,
    );

    expect(html).toContain("88");
    expect(html).toContain("核心概念正确");
    expect(html).toContain("说明了趋近");
    expect(html).toContain("缺少形式化定义");
    expect(html).toContain("难度 3");
    expect(html).toContain("AI 判分");
    expect(html).not.toContain("notes#0");
    expect(html).toContain('data-testid="practice-sources"');
  });

  it("offers a next question after grading instead of resubmitting the old one", () => {
    const html = renderToStaticMarkup(
      <PracticeCard
        t={t}
        question={{ id: "question-1", topic_id: "limits", prompt: "Explain a limit" }}
        answer="A limit is..."
        result={{
          attempt_id: "attempt-1",
          question_id: "question-1",
          topic_id: "limits",
          is_correct: false,
          mastery: 0.2,
          difficulty_level: 2,
          evidence_id: "evidence-1",
          score: 40,
          feedback: "Add an example.",
          strengths: [],
          gaps: ["example"],
          misconceptions: [],
          citations: [],
          grading_mode: "fallback",
          mastery_updated: false,
          replayed: false,
        }}
        busy={false}
        difficulty={null}
        savedQuestions={[]}
        onAnswerChange={() => undefined}
        onGetQuestion={() => undefined}
        onSubmit={() => undefined}
        onDifficultyChange={() => undefined}
        onToggleSaved={() => undefined}
      />,
    );

    expect(html).toContain('data-testid="next-question"');
    expect(html).toContain('data-testid="retry-topic"');
    expect(html).not.toContain('data-testid="submit-answer"');
  });

  it("renders durable saved questions as a reusable practice list", () => {
    const html = renderToStaticMarkup(
      <PracticeCard
        t={t}
        question={null}
        answer=""
        result={null}
        busy={false}
        difficulty={null}
        savedQuestions={[{
          id: "saved-question",
          topic_id: "limits",
          prompt: "Explain a one-sided limit",
          difficulty_level: 4,
          citations: [],
          sources: [],
          mode: "ai",
          saved: true,
          saved_at: "2026-08-07T08:00:00Z",
        }]}
        onAnswerChange={() => undefined}
        onGetQuestion={() => undefined}
        onSubmit={() => undefined}
        onDifficultyChange={() => undefined}
        onToggleSaved={() => undefined}
      />,
    );

    expect(html).toContain("Explain a one-sided limit");
    expect(html).toContain('data-testid="practice-saved-question"');
    expect(html).toContain('data-testid="practice-saved-topic"');
  });

  it("renders materials from the controlled workspace snapshot", () => {
    const html = renderToStaticMarkup(
      <MaterialDropzone
        t={t}
        locale="en"
        materials={[{
          id: "material-1",
          filename: "limits.txt",
          content_type: "text/plain",
          size: 12,
          status: "indexed",
          chunk_count: 1,
          content_sha256: "abc",
          indexed_at: "2026-08-06T00:00:00Z",
        }]}
        onUpload={async () => []}
        onSearch={async () => []}
        onDownload={() => undefined}
        onDelete={() => undefined}
      />,
    );

    expect(html).toContain("limits.txt");
    expect(html).toContain('class="upload-surface"');
    expect(html).toContain('data-testid="material-search"');
    expect(html).toContain('data-testid="material-download-material-1"');
    expect(html).toContain('data-testid="material-delete-material-1"');
    expect(html).toContain('data-testid="material-metadata-material-1"');
    expect(html).toContain("12 B");
    expect(html).toContain("text/plain");
  });

  it("renders the learning Agent with a focused chat composer", () => {
    const html = renderToStaticMarkup(
      <AgentPanel token="token" workspaceId="workspace-1" t={t} />,
    );

    expect(html).toContain("content-card agent-card");
    expect(html).toContain('class="chat-composer"');
    expect(html).toContain('data-testid="agent-new-conversation"');
    expect(html).toContain('data-testid="agent-history"');
    expect(html).toContain('data-testid="agent-suggestion"');
    expect(html).toContain("Checking model");
  });

  it("gives administrators a recovery action when the coach model is unavailable", () => {
    const html = renderToStaticMarkup(
      <SessionCoach
        locale="zh"
        modelConfigured={false}
        isAdmin
        onConfigure={() => undefined}
        onAsk={async () => ({
          session_id: "session-1",
          message: "reply",
          citations: [],
          sources: [],
        })}
      />,
    );

    expect(html).toContain("学习 Agent 尚未配置模型");
    expect(html).toContain('data-testid="coach-configure-model"');
    expect(html).toContain("前往配置");
  });

  it("keeps local learning explicit when model capability status cannot be checked", () => {
    const html = renderToStaticMarkup(
      <SessionCoach
        locale="zh"
        modelConfigured={null}
        onAsk={async () => ({
          session_id: "session-1",
          message: "reply",
          citations: [],
          sources: [],
        })}
      />,
    );

    expect(html).toContain("暂时无法确认学习 Agent 状态");
    expect(html).toContain("本地练习、资料和进度仍可继续使用");
    expect(html).toContain('data-testid="session-coach-input"');
    expect(html).toContain("disabled");
  });

  it("makes the complete conversation workspace reachable from today's session", () => {
    const html = renderToStaticMarkup(
      <LearningSessionCanvas
        locale="en"
        t={translator("en")}
        workspace={{
          id: "workspace-1",
          title: "Product thinking",
          subject: "product",
          goal: "Validate real user needs",
          topics: ["User research"],
          keywords: ["research"],
          routing_summary: "Capability learning",
          archived: false,
          created_at: "2026-08-08T00:00:00Z",
          last_active_at: "2026-08-08T00:00:00Z",
        }}
        plan={null}
        progress={null}
        materials={[]}
        question={null}
        answer=""
        result={null}
        busy={false}
        learningMode="case"
        savedQuestions={[]}
        agentToken="token"
        modelConfigured={false}
        isAdmin
        onOpenAgentSettings={() => undefined}
        onLearningModeChange={() => undefined}
        onAnswerChange={() => undefined}
        onStartTask={async () => undefined}
        onSubmit={async () => undefined}
        onNextTask={async () => undefined}
        onToggleSaved={async () => undefined}
        onOpenLibrary={() => undefined}
        onAskCoach={async () => ({ session_id: "session-1", message: "reply", citations: [], sources: [] })}
      />,
    );

    expect(html).toContain('data-testid="open-full-coach"');
    expect(html).toContain('data-testid="workspace-agent"');
    expect(html).toContain('tabindex="-1"');
    expect(html).toContain('data-testid="agent-history"');
    expect(html).toContain('data-testid="agent-new-conversation"');
    expect(html).toContain("The learning Agent has not been configured");
    expect(html).toContain('data-testid="coach-configure-model"');
  });
});
