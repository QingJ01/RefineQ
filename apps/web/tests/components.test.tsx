import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { EvidenceLedger } from "../components/evidence-ledger";
import { AuthPanel } from "../components/auth-panel";
import { AgentPanel } from "../components/agent-panel";
import { AdminConsole } from "../components/admin-console";
import { LearningHome } from "../components/learning-home";
import { MaterialDropzone } from "../components/material-dropzone";
import { PlanTimeline } from "../components/plan-timeline";
import { PracticeCard } from "../components/practice-card";
import { ProgressInsights } from "../components/progress-insights";
import { SourceDrawer } from "../components/source-drawer";
import { translator } from "../lib/i18n";


const t = translator("en");

describe("focused learning components", () => {
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

    expect(html).toContain('href="#recent-learning"');
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
            },
          ],
        }}
        onUpdateSession={() => undefined}
      />,
    );

    expect(html).toContain("limits");
    expect(html).toContain("01");
    expect(html).toContain("45 min");
    expect(html).toContain("content-card plan-card");
    expect(html).toContain('data-testid="complete-session-session-1"');
    expect(html).toContain('data-testid="defer-session-session-1"');
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
            details: { score: 88, feedback: "Strong explanation" },
          },
        ]}
      />,
    );

    expect(html).toContain("Learning evidence ledger");
    expect(html).toContain("Practice response for limits was correct.");
    expect(html).toContain("data-tone=\"jade\"");
    expect(html).toContain('class="evidence-timeline"');
    expect(html).toContain("Strong explanation");
    expect(html).toContain("<details");
  });

  it("turns mastery into an actionable progress recommendation", () => {
    const html = renderToStaticMarkup(
      <ProgressInsights
        t={t}
        progress={{
          goal: "Pass calculus",
          mastery: { limits: 0.72, derivatives: 0.34 },
          diagnostic_count: 1,
          attempt_count: 4,
          plan_id: "plan-1",
        }}
      />,
    );

    expect(html).toContain("derivatives");
    expect(html).toContain("34%");
    expect(html).toContain('data-testid="progress-recommendation"');
  });

  it("renders source evidence in a focused disclosure drawer", () => {
    const html = renderToStaticMarkup(
      <SourceDrawer
        title="Evidence sources"
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

    expect(html).toContain("notes#0");
    expect(html).toContain("notes.md");
    expect(html).toContain('role="dialog"');
  });

  it("never renders an expected answer in the practice card", () => {
    const html = renderToStaticMarkup(
      <PracticeCard
        t={t}
        question={{ id: "question-1", topic_id: "limits", prompt: "Explain a limit" }}
        answer=""
        result={null}
        busy={false}
        onAnswerChange={() => undefined}
        onGetQuestion={() => undefined}
        onSubmit={() => undefined}
      />,
    );

    expect(html).toContain("Explain a limit");
    expect(html).not.toContain("expected_answer");
    expect(html).toContain("content-card practice-card");
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
          grading_mode: "ai",
          mastery_updated: true,
          replayed: false,
        }}
        busy={false}
        onAnswerChange={() => undefined}
        onGetQuestion={() => undefined}
        onSubmit={() => undefined}
      />,
    );

    expect(html).toContain("88");
    expect(html).toContain("核心概念正确");
    expect(html).toContain("说明了趋近");
    expect(html).toContain("缺少形式化定义");
    expect(html).toContain("难度 3");
    expect(html).toContain("AI 判分");
    expect(html).toContain("notes#0");
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
        onAnswerChange={() => undefined}
        onGetQuestion={() => undefined}
        onSubmit={() => undefined}
      />,
    );

    expect(html).toContain('data-testid="next-question"');
    expect(html).not.toContain('data-testid="submit-answer"');
  });

  it("renders materials from the controlled workspace snapshot", () => {
    const html = renderToStaticMarkup(
      <MaterialDropzone
        t={t}
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
  });

  it("renders the learning Agent with a focused chat composer", () => {
    const html = renderToStaticMarkup(
      <AgentPanel token="token" workspaceId="workspace-1" t={t} />,
    );

    expect(html).toContain("content-card agent-card");
    expect(html).toContain('class="chat-composer"');
    expect(html).toContain('data-testid="agent-new-conversation"');
    expect(html).toContain('data-testid="agent-history"');
  });
});
