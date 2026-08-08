import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { EvidenceLedger } from "../components/evidence-ledger";
import { AuthPanel } from "../components/auth-panel";
import { AgentPanel } from "../components/agent-panel";
import { AdminConsole, refreshAdminAudit } from "../components/admin-console";
import { AccountCenter } from "../components/account-center";
import { AppSidebar } from "../components/app-sidebar";
import { LearningHome } from "../components/learning-home";
import { InitialDiagnostic } from "../components/initial-diagnostic";
import { LearningReport } from "../components/learning-report";
import { LearningSessionCanvas } from "../components/learning-session-canvas";
import { MaterialDropzone } from "../components/material-dropzone";
import { PlanTimeline } from "../components/plan-timeline";
import { PlanSettings } from "../components/plan-settings";
import { ProgressInsights } from "../components/progress-insights";
import { ProgressTopicDetail } from "../components/progress-topic-detail";
import { ReviewQueue } from "../components/review-queue";
import { SourceDrawer } from "../components/source-drawer";
import { ConfirmDialog } from "../components/confirm-dialog";
import { CoachActionCard, SessionCoach } from "../components/session-coach";
import { WorkspaceSwitcher } from "../components/workspace-switcher";
import { ScheduleCalendar } from "../components/schedule-calendar";
import { translator } from "../lib/i18n";
import type { SearchSource } from "../lib/types";


const t = translator("en");

const sidebarWorkspaces = [{
  id: "math-space",
  title: "Mathematics",
  subject: "Mathematics",
  goal: "Pass the final",
  topics: ["Limits"],
  keywords: ["calculus"],
  routing_summary: "Calculus study",
  archived: false,
  created_at: "2026-08-01T00:00:00Z",
  last_active_at: "2026-08-08T00:00:00Z",
}];


describe("shared authenticated sidebar", () => {
  it("keeps global destinations, recent spaces, contextual navigation, and utilities together", () => {
    const html = renderToStaticMarkup(
      <AppSidebar
        locale="en"
        active="calendar"
        workspaces={sidebarWorkspaces}
        isAdmin
        contextLabel="ACCOUNT"
        contextNavigation={<a href="#profile">Profile</a>}
        onToggleLocale={() => undefined}
        onLogout={() => undefined}
      />,
    );

    expect(html).toContain('data-testid="app-sidebar"');
    expect(html).toContain('data-testid="app-nav-home"');
    expect(html).toContain('data-testid="app-nav-calendar"');
    expect(html).toContain('href="/calendar"');
    expect(html).toContain('aria-current="page"');
    expect(html).toContain('href="/#recent-learning"');
    expect(html).toContain('href="/learn/math-space/today"');
    expect(html).toContain('data-testid="app-nav-admin"');
    expect(html).toContain('data-testid="app-nav-account"');
    expect(html).toContain("Profile");
    expect(html).toContain('data-testid="app-language"');
    expect(html).toContain('data-testid="app-logout"');
  });

  it("does not expose administrator navigation to learners", () => {
    const html = renderToStaticMarkup(
      <AppSidebar
        locale="zh"
        active="home"
        workspaces={[]}
        onToggleLocale={() => undefined}
        onLogout={() => undefined}
      />,
    );

    expect(html).not.toContain('data-testid="app-nav-admin"');
    expect(html).toContain("学习首页");
    expect(html).toContain("总日历");
  });
});

describe("focused learning components", () => {
  it("renders an accessible initial self-assessment for every topic", () => {
    const html = renderToStaticMarkup(
      <InitialDiagnostic
        locale="en"
        topics={{ limits: "Function limits", derivatives: "Derivatives" }}
        busy={false}
        onSubmit={async () => undefined}
      />,
    );

    expect(html).toContain('data-testid="initial-diagnostic"');
    expect(html).toContain("Function limits");
    expect(html).toContain("Derivatives");
    expect(html).toContain('name="diagnostic-limits"');
    expect(html).toContain('name="diagnostic-derivatives"');
    expect(html).toContain('type="radio"');
    expect(html).toContain('data-testid="submit-initial-diagnostic"');
    expect(html).toContain("disabled");
  });

  it("renders a complete account and security center with an explicit danger zone", () => {
    const html = renderToStaticMarkup(
      <AccountCenter
        locale="en"
        workspaces={sidebarWorkspaces}
        user={{
          id: "user-1",
          email: "learner@example.com",
          display_name: "Learner",
          role: "learner",
          created_at: "2026-08-08T00:00:00Z",
        }}
        busy={false}
        onUpdateProfile={async () => undefined}
        onChangePassword={async () => undefined}
        onExport={async () => undefined}
        onLogoutAll={async () => undefined}
        onDeleteAccount={async () => undefined}
        onLogout={() => undefined}
      />,
    );

    expect(html).toContain('data-testid="account-center"');
    expect(html).toContain('data-testid="app-sidebar"');
    expect(html).toContain('data-testid="app-nav-account"');
    expect(html).toMatch(/data-testid="app-nav-account"[^>]*aria-current="page"/);
    expect(html).toContain('data-testid="account-profile-form"');
    expect(html).toContain('data-testid="account-password-form"');
    expect(html).toContain('data-testid="account-export"');
    expect(html).toContain('data-testid="account-logout-all"');
    expect(html).toContain('data-testid="account-delete-confirmation"');
    expect(html).toContain('id="profile"');
    expect(html).toContain('id="security"');
    expect(html).toContain('id="data-sessions"');
    expect(html).toContain('id="danger-zone"');
    expect(html).toContain("Type learner@example.com to confirm");
    expect(html).toContain("Delete account permanently");
  });

  it("renders the plan as a compact calendar agenda for the sidebar", () => {
    const html = renderToStaticMarkup(
      <ScheduleCalendar
        locale="zh"
        topicLabels={{ derivatives: "导数应用" }}
        onUpdateSession={() => undefined}
        plan={{
          id: "plan-calendar",
          goal: "数学考试",
          exam_at: "2026-09-01T08:00:00Z",
          daily_minutes: 45,
          sessions: [{
            id: "session-calendar",
            topic_id: "derivatives",
            planned_at: "2026-08-10T08:00:00Z",
            minutes: 45,
          }],
        }}
      />,
    );

    expect(html).toContain("RefineQ 学习时间表");
    expect(html).toContain("导数应用");
    expect(html).toContain('data-testid="schedule-calendar"');
  });

  it("labels learning and review activities in the calendar", () => {
    const html = renderToStaticMarkup(
      <ScheduleCalendar
        locale="en"
        topicLabels={{ limits: "Limits" }}
        onUpdateSession={() => undefined}
        plan={{
          id: "plan-calendar",
          goal: "Pass calculus",
          exam_at: "2026-09-01T08:00:00Z",
          daily_minutes: 45,
          sessions: [{
            id: "session-review",
            topic_id: "limits",
            planned_at: "2026-08-10T08:00:00Z",
            minutes: 20,
            activity: "review",
          }],
        }}
      />,
    );

    expect(html).toContain('data-activity="review"');
    expect(html).toContain("Review");
  });

  it("renders guided empty cards for plans, schedules, and progress", () => {
    const planHtml = renderToStaticMarkup(
      <PlanTimeline locale="en" t={t} plan={null} />,
    );
    const scheduleHtml = renderToStaticMarkup(
      <ScheduleCalendar locale="en" plan={null} onUpdateSession={() => undefined} />,
    );
    const progressHtml = renderToStaticMarkup(
      <ProgressInsights t={t} progress={null} />,
    );

    expect(planHtml).toContain('data-testid="plan-empty-guide"');
    expect(scheduleHtml).toContain('data-testid="schedule-empty-guide"');
    expect(progressHtml).toContain('data-testid="progress-empty-guide"');
    expect(planHtml).toContain("content-card");
    expect(scheduleHtml).toContain("content-card");
    expect(progressHtml).toContain("content-card");
  });

  it("summarizes only the latest seven days and reports mastery change honestly", () => {
    const html = renderToStaticMarkup(
      <LearningReport
        locale="en"
        now={new Date("2026-08-08T12:00:00Z")}
        progress={{
          goal: "Pass calculus",
          mastery: { limits: 0.7 },
          topics: { limits: "Limits" },
          topic_order: ["limits"],
          diagnostic_count: 1,
          attempt_count: 8,
          plan_id: "plan-1",
        }}
        insights={{
          workspace_id: "workspace-1",
          due_reviews: [],
          topics: [],
          mastery_history: [
            { attempt_id: "old", topic_id: "limits", mastery: 0.4, observed_at: "2026-07-31T12:00:00Z" },
            { attempt_id: "new", topic_id: "limits", mastery: 0.7, observed_at: "2026-08-07T12:00:00Z" },
          ],
          attempts: [{
            attempt_id: "new",
            question_id: "question-1",
            topic_id: "limits",
            topic_name: "Limits",
            question_prompt: "Explain limits",
            answer: "An approached value",
            is_correct: true,
            mastery: 0.7,
            score: 90,
            feedback: "Good",
            strengths: [],
            gaps: [],
            misconceptions: [],
            citations: [],
            sources: [],
            grounding: "general",
            grading_mode: "ai",
            mastery_updated: true,
            observed_at: "2026-08-07T12:00:00Z",
            learner_note: null,
            appealed: false,
          }],
        }}
      />,
    );

    expect(html).toContain('data-testid="learning-report"');
    expect(html).toContain("1 attempt");
    expect(html).toContain("+30%");
    expect(html).not.toContain("8 attempts");
  });

  it.each([
    ["applied", "coach-action-applied"],
    ["confirmation_required", "coach-action-confirmation_required"],
    ["failed", "coach-action-failed"],
    ["executing", "coach-action-executing"],
  ] as const)("renders the %s coach action card state", (status, testId) => {
    const html = renderToStaticMarkup(
      <CoachActionCard
        locale="en"
        state={{
          status,
          proposal: {
            type: "adjust_practice",
            action_id: "action-1",
            topic_id: "limits",
            topic_name: "Limits",
            difficulty: 2,
            learning_mode: "concept",
            destructive: true,
          },
        }}
        onConfirm={() => undefined}
        onCancel={() => undefined}
        onRetry={() => undefined}
      />,
    );

    expect(html).toContain(`data-testid="${testId}"`);
  });

  it("renders rejected proposals as explanations, never as success", () => {
    const html = renderToStaticMarkup(
      <CoachActionCard
        locale="en"
        state={{
          status: "rejected",
          proposal: {
            type: "rejected",
            reason_code: "unknown_topic",
            summary: "This workspace has no topic named Operating systems.",
            candidates: [],
          },
        }}
        onConfirm={() => undefined}
        onCancel={() => undefined}
        onRetry={() => undefined}
      />,
    );

    expect(html).toContain('data-testid="coach-action-rejected"');
    expect(html).toContain("This workspace has no topic named Operating systems.");
    expect(html).not.toContain('data-testid="coach-action-applied"');
  });

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
        plan={{
          id: "plan-1",
          goal: "完成产品考试",
          exam_at: "2099-09-01T08:00:00Z",
          daily_minutes: 45,
          sessions: [],
        }}
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
        savedQuestions={[{
          id: "saved-question-1",
          topic_id: "user-needs",
          prompt: "分析已收藏的用户访谈原题",
          difficulty_level: 2,
          saved: true,
          saved_at: "2026-08-08T00:00:00Z",
        }]}
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
    expect(html).toContain('data-testid="mobile-sticky-task-action"');
    expect(html).toContain('data-testid="learning-mode-case"');
    expect(html).toContain("目标校准");
    expect(html).toContain("案例拆解");
    expect(html).toContain("实战任务");
    expect(html).toContain("反馈复盘");
    expect(html).toContain("用户访谈原文.md");
    expect(html).toContain('data-testid="session-coach"');
    expect(html).toContain('data-testid="saved-question-list"');
    expect(html).toContain("分析已收藏的用户访谈原题");
    expect(html).toContain('data-testid="practice-saved-question"');
    expect(html).toContain('data-testid="exam-countdown"');
    expect(html).not.toContain('data-testid="session-upload-prompt"');
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
      restoreQuestion = true,
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
        question={restoreQuestion ? {
          id: "question-1",
          topic_id: "user-needs",
          prompt: "分析用户当前的替代方案",
          explanation: "这道题用于检验你能否从行为证据识别真实需求。",
          grounding,
          sources,
          mode: "ai",
        } : null}
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
          misconceptions: ["misread observed behavior as stated preference"],
          citations: [],
          sources,
          grounding,
          grading_mode: "ai",
          mastery_updated: true,
          replayed: false,
        } : null}
        masteryBefore={0.42}
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
    const recoveryHtml = renderGrounding("material", [source], true, false);

    expect(materialHtml).toContain('data-testid="practice-grounding"');
    expect(materialHtml).toContain('data-testid="question-generation-mode"');
    expect(materialHtml).toContain('data-testid="question-explanation"');
    expect(materialHtml).toContain("这道题用于检验你能否从行为证据识别真实需求。");
    expect(materialHtml).toContain("材料依据");
    expect(materialHtml).toContain('data-testid="practice-sources"');
    expect(materialHtml).toContain("未命名主题");
    expect(materialHtml).not.toContain("user-needs · 今日学习");
    expect(generalHtml).toContain("通用生成");
    expect(generalHtml).not.toContain("真实材料线索");
    expect(feedbackHtml).toContain('data-testid="feedback-grounding"');
    expect(feedbackHtml).toContain('data-testid="grading-mode"');
    expect(feedbackHtml).toContain('data-testid="feedback-misconceptions"');
    expect(feedbackHtml).toContain("misread observed behavior as stated preference");
    expect(feedbackHtml).toContain("材料依据");
    expect(feedbackHtml).toContain('data-testid="feedback-sources"');
    expect(feedbackHtml).toContain("用户访谈原文.md");
    expect(feedbackHtml).toContain("42%");
    expect(feedbackHtml).toContain("60%");
    expect(feedbackHtml).toContain('data-testid="reflect-view-progress"');
    expect(feedbackHtml).toContain('data-testid="reflect-retry-question"');
    expect(feedbackHtml).toContain('data-testid="reflect-save-question"');
    expect(recoveryHtml).toContain('data-testid="reflect-recovery"');
    expect(recoveryHtml).toContain('data-testid="next-question"');
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
        masteryBefore={0.42}
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
    expect(html).toContain('data-testid="mastery-unchanged"');
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
          workspaces={sidebarWorkspaces}
        onLogout={() => undefined}
        onToggleLocale={() => undefined}
      />,
    );

      expect(html).toContain('class="admin-console"');
      expect(html).toContain('data-testid="app-sidebar"');
      expect(html).toMatch(/data-testid="app-nav-admin"[^>]*aria-current="page"/);
    expect(html).toContain('data-testid="admin-overview"');
    expect(html).toContain('data-testid="admin-system-status"');
    expect(html).toContain('data-testid="admin-next-action"');
    expect(html).toContain('data-testid="admin-principles"');
    expect(html).not.toContain('data-testid="admin-integration-link-');
    expect(html).not.toContain('data-testid="integration-card-');
    expect(html).toContain('data-testid="app-logout"');
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

  it("renders the administrator operations control plane with guarded backups", () => {
    const html = renderToStaticMarkup(
      <AdminConsole
        token="admin-token"
        locale="en"
        activeSection="operations"
        onLogout={() => undefined}
        onToggleLocale={() => undefined}
      />,
    );

    expect(html).toContain('data-testid="admin-operations"');
    expect(html).toContain('data-testid="admin-users"');
    expect(html).toContain('data-testid="admin-activity"');
    expect(html).toContain('data-testid="admin-jobs"');
    expect(html).toContain('data-testid="admin-backups"');
    expect(html).toContain('data-testid="admin-create-backup"');
    expect(html).toContain("Users and quotas");
    expect(html).toContain("Audit activity");
    expect(html).toContain("Material jobs");
  });

  it("keeps a successful admin mutation successful when audit refresh fails", async () => {
    const apply = vi.fn();

    await expect(refreshAdminAudit(
      async () => { throw new Error("audit read failed"); },
      apply,
    )).resolves.toBe(false);
    expect(apply).not.toHaveBeenCalled();
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
    expect(html).not.toContain('data-testid="forgot-password"');
  });

  it("starts with one personal Agent prompt instead of a project form", () => {
    const html = renderToStaticMarkup(
      <LearningHome
          locale="zh"
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
      expect(html).toContain('data-testid="app-sidebar"');
    expect(html).toContain('class="learning-composer"');
    expect(html).toContain("RefineQ");
    expect(html).toContain('data-testid="app-logout"');
    expect(html).toContain('data-testid="app-language"');
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

  it("renders workspace switching as an accessible menu trigger instead of a home link", () => {
    const html = renderToStaticMarkup(
      <WorkspaceSwitcher
        locale="zh"
        current={{
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
        }}
        workspaces={[]}
        currentProgress={42}
        onSelect={() => undefined}
        onAllSpaces={() => undefined}
      />,
    );

    expect(html).toContain('data-testid="workspace-switcher"');
    expect(html).toContain('aria-haspopup="menu"');
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain("高等数学");
    expect(html).toContain("42%");
    expect(html).not.toContain('href="/"');
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

    expect(html).toContain("Untitled topic");
    expect(html).toContain("01");
    expect(html).toContain("45 min");
    expect(html).toContain("Learn");
    expect(html).toContain("content-card plan-card");
    expect(html).toContain('data-testid="complete-session-session-1"');
    expect(html).toContain('data-testid="defer-session-session-1"');
    expect(html).toContain('data-testid="start-session-session-1"');
  });

  it("renders editable plan settings with save, cancel, ordering, and regeneration controls", () => {
    const html = renderToStaticMarkup(
      <PlanSettings
        locale="en"
        plan={{
          id: "plan-1",
          goal: "Pass calculus",
          exam_at: "2026-08-20T23:59:59Z",
          daily_minutes: 45,
          sessions: [{
            id: "session-1",
            topic_id: "limits",
            planned_at: "2026-08-09T08:00:00Z",
            minutes: 45,
          }],
        }}
        topics={{ limits: "Limits", derivatives: "Derivatives" }}
        topicOrder={["limits", "derivatives"]}
        onSave={() => undefined}
      />,
    );

    expect(html).toContain('data-testid="plan-settings"');
    expect(html).toContain('data-testid="plan-goal"');
    expect(html).toContain('data-testid="plan-exam-date"');
    expect(html).toContain('data-testid="plan-daily-minutes"');
    expect(html).toContain('data-testid="plan-topic-limits"');
    expect(html).toContain('data-testid="plan-topic-up-derivatives"');
    expect(html).toContain('data-testid="plan-settings-cancel"');
    expect(html).toContain('data-testid="plan-settings-save"');
    expect(html).toContain('data-testid="plan-settings-regenerate"');
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
          topic_order: ["limits", "derivatives"],
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

  it("breaks equal-mastery recommendation ties by topic id", () => {
    const html = renderToStaticMarkup(
      <ProgressInsights
        t={t}
        progress={{
          goal: "Pass calculus",
          mastery: { topic_z: 0.2, topic_a: 0.2 },
          topics: { topic_z: "Zeta", topic_a: "Alpha" },
          topic_order: ["topic_z", "topic_a"],
          diagnostic_count: 0,
          attempt_count: 0,
          plan_id: "plan-1",
        }}
        onPracticeTopic={() => undefined}
      />,
    );

    expect(html).toMatch(/progress-recommendation[\s\S]*<strong>Alpha<\/strong>/);
  });

  it("labels mastery only after the backend marks the evidence stable", () => {
    const baseProgress = {
      goal: "Pass calculus",
      mastery: { limits: 0.99 },
      topics: { limits: "Limits" },
      topic_order: ["limits"],
      diagnostic_count: 0,
      attempt_count: 1,
      plan_id: "plan-1",
    };
    const unstable = renderToStaticMarkup(
      <ProgressInsights t={t} progress={{ ...baseProgress, stable: { limits: false } }} />,
    );
    const stable = renderToStaticMarkup(
      <ProgressInsights t={t} progress={{ ...baseProgress, stable: { limits: true } }} />,
    );

    expect(unstable).not.toContain("Mastered");
    expect(stable).toContain("Mastered");
  });

  it("renders due reviews and a topic drill-down with stable empty states", () => {
    const reviewHtml = renderToStaticMarkup(
      <ReviewQueue
        locale="en"
        reviews={[{
          session_id: "review-1",
          topic_id: "limits",
          topic_name: "Limits",
          due_at: "2026-08-08T08:00:00Z",
          minutes: 20,
          overdue: true,
        }]}
        onStartReview={() => undefined}
      />,
    );
    const detailHtml = renderToStaticMarkup(
      <ProgressTopicDetail
        locale="en"
        topic={{
          topic_id: "limits",
          topic_name: "Limits",
          mastery: 0.42,
          attempt_count: 2,
          error_count: 1,
          last_practiced_at: "2026-08-08T08:00:00Z",
        }}
        history={[{
          attempt_id: "attempt-1",
          topic_id: "limits",
          mastery: 0.42,
          observed_at: "2026-08-08T08:00:00Z",
        }]}
        onClose={() => undefined}
      />,
    );
    const emptyHtml = renderToStaticMarkup(
      <ReviewQueue locale="en" reviews={[]} onStartReview={() => undefined} />,
    );

    expect(reviewHtml).toContain('data-testid="review-queue"');
    expect(reviewHtml).toContain('data-testid="start-review-review-1"');
    expect(detailHtml).toContain('data-testid="progress-topic-detail"');
    expect(detailHtml).toContain("42%");
    expect(detailHtml).toContain("1 error");
    expect(emptyHtml).toContain('data-testid="review-queue-empty"');
  });

  it("keeps insight placeholders honest and disables every practice entry while generating", () => {
    const reviewHtml = renderToStaticMarkup(
      <ReviewQueue
        locale="en"
        loading
        busy
        reviews={[{
          session_id: "review-1",
          topic_id: "limits",
          topic_name: "Limits",
          due_at: "2026-08-08T08:00:00Z",
          minutes: 20,
          overdue: true,
        }]}
        onStartReview={() => undefined}
      />,
    );
    const progressHtml = renderToStaticMarkup(
      <ProgressInsights
        t={t}
        loading
        busy
        progress={{
          goal: "Pass calculus",
          mastery: { limits: 0.3 },
          topics: { limits: "Limits" },
          topic_order: ["limits"],
          diagnostic_count: 0,
          attempt_count: 0,
          plan_id: "plan-1",
        }}
        onPracticeTopic={() => undefined}
      />,
    );
    const planHtml = renderToStaticMarkup(
      <PlanTimeline
        locale="en"
        t={t}
        practiceBusy
        plan={{
          id: "plan-1",
          goal: "Pass calculus",
          exam_at: "2026-09-01T08:00:00Z",
          daily_minutes: 45,
          sessions: [{
            id: "session-1",
            topic_id: "limits",
            planned_at: "2026-08-09T08:00:00Z",
            minutes: 45,
          }],
        }}
        onStartSession={() => undefined}
      />,
    );

    expect(reviewHtml).toContain('data-testid="review-queue-loading"');
    expect(progressHtml).toContain('data-testid="progress-insights-loading"');
    expect(planHtml.match(/data-testid="start-session-session-1"[^>]*disabled/)?.[0]).toBeTruthy();
  });

  it("adds rubric, source, retry, note, and appeal actions to attempt evidence", () => {
    const html = renderToStaticMarkup(
      <EvidenceLedger
        locale="en"
        t={t}
        evidence={[{
          id: "evidence-1",
          kind: "attempt",
          source_id: "attempt-1",
          summary: "Completed a task for Limits.",
          observed_at: "2026-08-08T08:00:00Z",
          details: { score: 72, feedback: "Good structure" },
        }]}
        attempts={[{
          attempt_id: "attempt-1",
          question_id: "question-1",
          topic_id: "limits",
          topic_name: "Limits",
          question_prompt: "Explain a limit.",
          answer: "A limit describes an approached value.",
          is_correct: true,
          mastery: 0.42,
          score: 72,
          feedback: "Good structure",
          strengths: ["Clear definition"],
          gaps: ["Add an example"],
          misconceptions: [],
          citations: ["source-1"],
          sources: [{
            citation_id: "source-1",
            material_id: "material-1",
            filename: "limits.pdf",
            chunk_index: 0,
            text: "Formal definition of a limit.",
            score: 0.9,
          }],
          grounding: "material",
          grading_mode: "fallback",
          mastery_updated: true,
          observed_at: "2026-08-08T08:00:00Z",
          learner_note: null,
          appealed: false,
        }]}
        onRetryAttempt={() => undefined}
        onUpdateFeedback={() => undefined}
      />,
    );

    expect(html).toContain("Explain a limit.");
    expect(html).toContain("Clear definition");
    expect(html).toContain("limits.pdf");
    expect(html).toContain('data-testid="retry-attempt-attempt-1"');
    expect(html).toContain('data-testid="attempt-note-attempt-1"');
    expect(html).toContain('data-testid="appeal-attempt-attempt-1"');
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

  it("renders materials from the controlled workspace snapshot", () => {
    const html = renderToStaticMarkup(
      <MaterialDropzone
        t={t}
        locale="en"
        materials={[{
          id: "material-1",
          filename: "limits.txt",
          title: "Limits handbook",
          tags: ["exam", "calculus"],
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
        onUpdate={async () => undefined}
        onBulkDelete={async () => undefined}
        topicSuggestions={[{
          id: "topic_epsilon_delta",
          name: "epsilon-delta",
          source_material_ids: ["material-1"],
        }]}
        onAcceptTopicSuggestion={async () => undefined}
      />,
    );

    expect(html).toContain("Limits handbook");
    expect(html).toContain("exam");
    expect(html).toContain('class="upload-surface"');
    expect(html).toContain('data-testid="material-search"');
    expect(html).toContain('data-testid="material-filter-status"');
    expect(html).toContain('data-testid="material-filter-tag"');
    expect(html).toContain('data-testid="material-sort"');
    expect(html).toContain('data-testid="material-select-all"');
    expect(html).toContain('data-testid="material-select-material-1"');
    expect(html).toContain('data-testid="material-edit-material-1"');
    expect(html).toContain('data-testid="material-bulk-delete"');
    expect(html).toContain('data-testid="material-download-material-1"');
    expect(html).toContain('data-testid="material-delete-material-1"');
    expect(html).toContain('data-testid="material-metadata-material-1"');
    expect(html).toContain('data-testid="material-topic-suggestions"');
    expect(html).toContain('data-testid="accept-topic-topic_epsilon_delta"');
    expect(html).toContain("Add topic");
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

  it("tells a learner who can configure an unavailable model", () => {
    const html = renderToStaticMarkup(
      <SessionCoach
        locale="en"
        modelConfigured={false}
        onAsk={async () => ({ session_id: "session-1", message: "reply", citations: [], sources: [] })}
      />,
    );

    expect(html).toContain("contact an administrator");
    expect(html).not.toContain('data-testid="coach-configure-model"');
  });

  it("keeps local learning explicit when model capability status cannot be checked", () => {
    const html = renderToStaticMarkup(
      <SessionCoach
        locale="zh"
        modelConfigured={null}
        onRecheck={async () => true}
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
    expect(html).toContain('data-testid="coach-recheck"');
    const input = html.match(/<input[^>]*data-testid="session-coach-input"[^>]*>/)?.[0];
    expect(input).not.toContain("disabled");
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
    expect(html).toContain('data-testid="session-upload-prompt"');
    expect(html).toContain('data-testid="saved-question-empty"');
  });
});
