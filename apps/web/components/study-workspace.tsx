"use client";

import { Archive, Bot, BookOpen, Languages, LogOut, NotebookTabs, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { AgentPanel } from "@/components/agent-panel";
import { AuthPanel } from "@/components/auth-panel";
import { EvidenceLedger } from "@/components/evidence-ledger";
import { LearningHome } from "@/components/learning-home";
import { MaterialDropzone } from "@/components/material-dropzone";
import { PlanTimeline } from "@/components/plan-timeline";
import { PracticeCard } from "@/components/practice-card";
import { api, ApiError } from "@/lib/api";
import { translator } from "@/lib/i18n";
import {
  clearLearningSession,
  loadLearningSession,
  saveLearningSession,
} from "@/lib/session";
import type {
  AnswerResult,
  AuthResponse,
  LearningEvidence,
  LearningWorkspace,
  Locale,
  MaterialRecord,
  PracticeQuestion,
  Progress,
  StudyPlan,
  WorkspaceSnapshot,
} from "@/lib/types";


type Section = "today" | "materials" | "evidence" | "coach";

export function StudyWorkspace() {
  const [locale, setLocale] = useState<Locale>("zh");
  const t = useMemo(() => translator(locale), [locale]);
  const [restoring, setRestoring] = useState(true);
  const [auth, setAuth] = useState<AuthResponse | null>(null);
  const [workspaces, setWorkspaces] = useState<LearningWorkspace[]>([]);
  const [workspace, setWorkspace] = useState<LearningWorkspace | null>(null);
  const [plan, setPlan] = useState<StudyPlan | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [evidence, setEvidence] = useState<LearningEvidence[]>([]);
  const [materials, setMaterials] = useState<MaterialRecord[]>([]);
  const [question, setQuestion] = useState<PracticeQuestion | null>(null);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [section, setSection] = useState<Section>("today");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function reportError(caught: unknown) {
    setError(
      caught instanceof ApiError
        ? `${caught.code}: ${caught.message}`
        : caught instanceof Error
          ? caught.message
          : t("error"),
    );
  }

  function applySnapshot(snapshot: WorkspaceSnapshot) {
    setWorkspace(snapshot.workspace);
    setProgress(snapshot.progress);
    setPlan(snapshot.plan);
    setEvidence(snapshot.evidence);
    setMaterials(snapshot.materials);
    setQuestion(null);
    setResult(null);
    setAnswer("");
  }

  useEffect(() => {
    let active = true;
    async function restore() {
      const saved = loadLearningSession(window.localStorage);
      if (!saved) {
        if (active) setRestoring(false);
        return;
      }
      try {
        const user = await api.getProfile(saved.token);
        const restoredAuth: AuthResponse = {
          access_token: saved.token,
          token_type: "bearer",
          user,
        };
        const recent = await api.listWorkspaces(saved.token);
        if (!active) return;
        setAuth(restoredAuth);
        setWorkspaces(recent);
        const selected = recent.find((item) => item.id === saved.workspaceId) ?? recent[0];
        if (selected) {
          const snapshot = await api.getWorkspaceSnapshot(saved.token, selected.id);
          if (!active) return;
          applySnapshot(snapshot);
          saveLearningSession(window.localStorage, {
            token: saved.token,
            workspaceId: selected.id,
          });
        }
      } catch {
        clearLearningSession(window.localStorage);
      } finally {
        if (active) setRestoring(false);
      }
    }
    void restore();
    return () => { active = false; };
  }, []);

  async function authenticated(response: AuthResponse) {
    setAuth(response);
    setError("");
    saveLearningSession(window.localStorage, { token: response.access_token });
    try {
      const recent = await api.listWorkspaces(response.access_token);
      setWorkspaces(recent);
      if (recent[0]) await openWorkspace(recent[0], response.access_token);
    } catch (caught) {
      reportError(caught);
    }
  }

  async function openWorkspace(target: LearningWorkspace, token = auth?.access_token) {
    if (!token) return;
    setBusy(true);
    setError("");
    try {
      const snapshot = await api.getWorkspaceSnapshot(token, target.id);
      applySnapshot(snapshot);
      saveLearningSession(window.localStorage, { token, workspaceId: target.id });
      setSection("today");
    } catch (caught) {
      reportError(caught);
    } finally {
      setBusy(false);
    }
  }

  async function resolveIntent(intent: string) {
    if (!auth) return;
    setBusy(true);
    setError("");
    try {
      const route = await api.resolveWorkspace(auth.access_token, intent);
      const snapshot = await api.getWorkspaceSnapshot(auth.access_token, route.workspace.id);
      applySnapshot(snapshot);
      setWorkspaces(await api.listWorkspaces(auth.access_token));
      saveLearningSession(window.localStorage, {
        token: auth.access_token,
        workspaceId: route.workspace.id,
      });
    } catch (caught) {
      reportError(caught);
    } finally {
      setBusy(false);
    }
  }

  async function getQuestion() {
    if (!auth || !workspace) return;
    setBusy(true);
    setResult(null);
    setAnswer("");
    try {
      setQuestion(await api.getWorkspaceQuestion(auth.access_token, workspace.id));
    } catch (caught) {
      reportError(caught);
    } finally {
      setBusy(false);
    }
  }

  async function submitAnswer() {
    if (!auth || !workspace || !question) return;
    setBusy(true);
    try {
      setResult(
        await api.submitWorkspaceAnswer(
          auth.access_token,
          workspace.id,
          question.id,
          answer,
        ),
      );
      const snapshot = await api.getWorkspaceSnapshot(auth.access_token, workspace.id);
      setProgress(snapshot.progress);
      setEvidence(snapshot.evidence);
    } catch (caught) {
      reportError(caught);
    } finally {
      setBusy(false);
    }
  }

  async function uploadMaterials(files: File[]): Promise<MaterialRecord[]> {
    if (!auth || !workspace) return [];
    setError("");
    try {
      const uploaded = await api.uploadWorkspaceMaterials(
        auth.access_token,
        workspace.id,
        files,
      );
      setMaterials((current) => {
        const byId = new Map(current.map((item) => [item.id, item]));
        uploaded.forEach((item) => byId.set(item.id, item));
        return Array.from(byId.values());
      });
      return uploaded;
    } catch (caught) {
      reportError(caught);
      return [];
    }
  }

  function logout() {
    clearLearningSession(window.localStorage);
    setAuth(null);
    setWorkspace(null);
    setWorkspaces([]);
  }

  if (restoring) return <main className="loading-stage">{t("loading")}</main>;
  if (!auth) return <AuthPanel t={t} onAuthenticated={authenticated} />;
  if (!workspace) {
    return (
      <>
        {error && <div className="error-banner"><strong>{t("error")}</strong><span>{error}</span></div>}
        <LearningHome
          t={t}
          busy={busy}
          workspaces={workspaces}
          onResolve={resolveIntent}
          onOpen={openWorkspace}
        />
      </>
    );
  }

  const masteryValues = progress ? Object.values(progress.mastery) : [];
  const averageMastery = masteryValues.reduce((sum, value) => sum + value, 0)
    / Math.max(1, masteryValues.length);
  const nav: Array<{ id: Section; icon: typeof BookOpen }> = [
    { id: "today", icon: BookOpen },
    { id: "materials", icon: Archive },
    { id: "evidence", icon: NotebookTabs },
    { id: "coach", icon: Bot },
  ];

  return (
    <main className="workspace-shell">
      <header className="topbar">
        <button className="wordmark wordmark-button" onClick={() => setWorkspace(null)}>
          <span>R</span><div><strong>RefineQ</strong><small>{t("workspaceEyebrow")}</small></div>
        </button>
        <div className="top-actions">
          <button className="quiet-button" onClick={() => setLocale(locale === "zh" ? "en" : "zh")}><Languages size={16} /> {t("language")}</button>
          <button className="quiet-button" onClick={logout}><LogOut size={16} /> {t("logout")}</button>
        </div>
      </header>
      <aside className="dossier-rail">
        <span className="vertical-label">PERSONAL MEMORY · ACTIVE</span>
        <div className="rail-learning"><span className="kicker">CURRENT LEARNING</span><h1>{workspace.title}</h1><p>{workspace.goal}</p></div>
        <div className="mastery-dial" style={{ "--mastery": `${Math.round(averageMastery * 360)}deg` } as React.CSSProperties}><div><strong>{Math.round(averageMastery * 100)}</strong><span>% {t("mastery")}</span></div></div>
        <dl className="rail-stats"><div><dt>{t("attempts")}</dt><dd>{String(progress?.attempt_count ?? 0).padStart(2, "0")}</dd></div><div><dt>{t("diagnostic")}</dt><dd>{String(progress?.diagnostic_count ?? 0).padStart(2, "0")}</dd></div></dl>
        <button className="quiet-button switch-learning" onClick={() => setWorkspace(null)}><Sparkles size={15} /> {t("recentLearning")}</button>
      </aside>
      <nav className="study-nav" aria-label="Study sections">{nav.map(({ id, icon: Icon }, index) => <button key={id} data-testid={`nav-${id}`} className={section === id ? "active" : ""} onClick={() => setSection(id)}><span>{String(index + 1).padStart(2, "0")}</span><Icon size={18} />{t(id)}</button>)}</nav>
      <section className="workspace-main">
        {error && <div className="error-banner"><strong>{t("error")}</strong><span>{error}</span><button onClick={() => setError("")}>×</button></div>}
        {section === "today" && <div className="today-grid"><div className="daily-heading"><span className="kicker">TODAY / FOCUS</span><h2>{new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", { weekday: "long", month: "long", day: "numeric" }).format(new Date())}</h2></div><PlanTimeline plan={plan} locale={locale} t={t} /><PracticeCard question={question} answer={answer} result={result} busy={busy} onAnswerChange={setAnswer} onGetQuestion={getQuestion} onSubmit={submitAnswer} t={t} /></div>}
        {section === "materials" && <MaterialDropzone key={workspace.id} t={t} materials={materials} onUpload={uploadMaterials} />}
        {section === "evidence" && <EvidenceLedger evidence={evidence} locale={locale} t={t} />}
        {section === "coach" && <AgentPanel token={auth.access_token} workspaceId={workspace.id} t={t} />}
      </section>
    </main>
  );
}
