"use client";

import { Archive, Bot, BookOpen, Languages, LogOut, NotebookTabs } from "lucide-react";
import { useMemo, useState } from "react";

import { AgentPanel } from "@/components/agent-panel";
import { AuthPanel } from "@/components/auth-panel";
import { EvidenceLedger } from "@/components/evidence-ledger";
import { GoalDraft, GoalWizard } from "@/components/goal-wizard";
import { MaterialDropzone } from "@/components/material-dropzone";
import { PlanTimeline } from "@/components/plan-timeline";
import { PracticeCard } from "@/components/practice-card";
import { api, ApiError } from "@/lib/api";
import { translator } from "@/lib/i18n";
import type { AnswerResult, AuthResponse, LearningEvidence, Locale, PracticeQuestion, Progress, Project, StudyPlan } from "@/lib/types";


type Section = "today" | "materials" | "evidence" | "coach";

export function StudyWorkspace() {
  const [locale, setLocale] = useState<Locale>("zh");
  const t = useMemo(() => translator(locale), [locale]);
  const [auth, setAuth] = useState<AuthResponse | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [plan, setPlan] = useState<StudyPlan | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [evidence, setEvidence] = useState<LearningEvidence[]>([]);
  const [question, setQuestion] = useState<PracticeQuestion | null>(null);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [section, setSection] = useState<Section>("today");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function reportError(caught: unknown) {
    setError(caught instanceof ApiError ? `${caught.code}: ${caught.message}` : caught instanceof Error ? caught.message : t("error"));
  }

  async function createDossier(draft: GoalDraft) {
    if (!auth) return;
    setBusy(true); setError("");
    try {
      const created = await api.createProject(auth.access_token, draft.projectName);
      const seeded = await api.seedProject(auth.access_token, created.id, { goal: draft.goal, exam_at: draft.examAt, daily_minutes: draft.dailyMinutes, topics: draft.topics });
      const generatedPlan = await api.createPlan(auth.access_token, created.id);
      setProject(created); setProgress(seeded); setPlan(generatedPlan);
    } catch (caught) { reportError(caught); } finally { setBusy(false); }
  }

  async function getQuestion() {
    if (!auth || !project) return;
    setBusy(true); setResult(null); setAnswer("");
    try { setQuestion(await api.getQuestion(auth.access_token, project.id)); } catch (caught) { reportError(caught); } finally { setBusy(false); }
  }

  async function submitAnswer() {
    if (!auth || !project || !question) return;
    setBusy(true);
    try {
      setResult(await api.submitAnswer(auth.access_token, project.id, question.id, answer));
      setProgress(await api.getProgress(auth.access_token, project.id));
      setEvidence(await api.getEvidence(auth.access_token, project.id));
    } catch (caught) { reportError(caught); } finally { setBusy(false); }
  }

  if (!auth) return <AuthPanel t={t} onAuthenticated={setAuth} />;
  if (!project) return <GoalWizard t={t} busy={busy} onCreate={createDossier} />;

  const averageMastery = progress ? Object.values(progress.mastery).reduce((sum, value) => sum + value, 0) / Math.max(1, Object.keys(progress.mastery).length) : 0;
  const nav: Array<{ id: Section; icon: typeof BookOpen }> = [{ id: "today", icon: BookOpen }, { id: "materials", icon: Archive }, { id: "evidence", icon: NotebookTabs }, { id: "coach", icon: Bot }];

  return (
    <main className="workspace-shell">
      <header className="topbar"><div className="wordmark"><span>R</span><div><strong>RefineQ</strong><small>{t("workspaceEyebrow")}</small></div></div><div className="top-actions"><button className="quiet-button" onClick={() => setLocale(locale === "zh" ? "en" : "zh")}><Languages size={16} /> {t("language")}</button><button className="quiet-button" onClick={() => { setAuth(null); setProject(null); }}><LogOut size={16} /> {t("logout")}</button></div></header>
      <aside className="dossier-rail"><span className="vertical-label">STUDY DOSSIER · 2026</span><div className="rail-project"><span className="kicker">CURRENT FILE</span><h1>{project.name}</h1><p>{progress?.goal}</p></div><div className="mastery-dial" style={{ "--mastery": `${Math.round(averageMastery * 360)}deg` } as React.CSSProperties}><div><strong>{Math.round(averageMastery * 100)}</strong><span>% {t("mastery")}</span></div></div><dl className="rail-stats"><div><dt>{t("attempts")}</dt><dd>{String(progress?.attempt_count ?? 0).padStart(2, "0")}</dd></div><div><dt>{t("diagnostic")}</dt><dd>{String(progress?.diagnostic_count ?? 0).padStart(2, "0")}</dd></div></dl></aside>
      <nav className="study-nav" aria-label="Study sections">{nav.map(({ id, icon: Icon }, index) => <button key={id} className={section === id ? "active" : ""} onClick={() => setSection(id)}><span>{String(index + 1).padStart(2, "0")}</span><Icon size={18} />{t(id)}</button>)}</nav>
      <section className="workspace-main">{error && <div className="error-banner"><strong>{t("error")}</strong><span>{error}</span><button onClick={() => setError("")}>×</button></div>}{section === "today" && <div className="today-grid"><div className="daily-heading"><span className="kicker">TODAY / FOCUS</span><h2>{new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", { weekday: "long", month: "long", day: "numeric" }).format(new Date())}</h2></div><PlanTimeline plan={plan} locale={locale} t={t} /><PracticeCard question={question} answer={answer} result={result} busy={busy} onAnswerChange={setAnswer} onGetQuestion={getQuestion} onSubmit={submitAnswer} t={t} /></div>}{section === "materials" && <MaterialDropzone t={t} onUpload={(files) => api.uploadMaterials(auth.access_token, project.id, files)} />}{section === "evidence" && <EvidenceLedger evidence={evidence} locale={locale} t={t} />}{section === "coach" && <AgentPanel token={auth.access_token} projectId={project.id} t={t} />}</section>
    </main>
  );
}
