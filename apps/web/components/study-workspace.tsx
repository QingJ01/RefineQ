"use client";

import {
  Archive,
  Bot,
  BookOpen,
  Languages,
  LogOut,
  NotebookTabs,
  Settings2,
  Sparkles,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { AgentPanel } from "@/components/agent-panel";
import { AuthPanel } from "@/components/auth-panel";
import { BrandMark, BrandName } from "@/components/brand";
import { EvidenceLedger } from "@/components/evidence-ledger";
import { LearningHome } from "@/components/learning-home";
import { MaterialDropzone } from "@/components/material-dropzone";
import { PlanTimeline } from "@/components/plan-timeline";
import { PracticeCard } from "@/components/practice-card";
import { api, ApiError } from "@/lib/api";
import { translator } from "@/lib/i18n";
import { learningPath, type LearningSection } from "@/lib/learning-routes";
import { loadNextQuestion } from "@/lib/practice-flow";
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
  StudySession,
  StudyPlan,
  WorkspaceRoute,
  WorkspaceSnapshot,
} from "@/lib/types";

const ROUTE_NOTICE_KEY = "refineq.workspace-route-notice";


export function StudyWorkspace({
  initialWorkspaceId,
  initialSection = "today",
}: {
  initialWorkspaceId?: string;
  initialSection?: LearningSection;
} = {}) {
  const router = useRouter();
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
  const [section, setSection] = useState<LearningSection>(initialSection);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [route, setRoute] = useState<WorkspaceRoute | null>(null);
  const [previousWorkspaceId, setPreviousWorkspaceId] = useState<string | null>(null);

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
        if (saved.locale) setLocale(saved.locale);
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
        const selectedId = initialWorkspaceId ?? (saved.home ? undefined : saved.workspaceId);
        const selected = recent.find((item) => item.id === selectedId);
        if (selected) {
          const snapshot = await api.getWorkspaceSnapshot(saved.token, selected.id);
          if (!active) return;
          applySnapshot(snapshot);
          saveLearningSession(window.localStorage, {
            token: saved.token,
            workspaceId: selected.id,
            locale: saved.locale ?? "zh",
            home: false,
          });
          const rawNotice = window.sessionStorage.getItem(ROUTE_NOTICE_KEY);
          if (rawNotice) {
            try {
              const notice = JSON.parse(rawNotice) as {
                route: WorkspaceRoute;
                previousWorkspaceId: string | null;
              };
              if (notice.route.workspace.id === selected.id) {
                setRoute(notice.route);
                setPreviousWorkspaceId(notice.previousWorkspaceId);
              }
            } catch {
              window.sessionStorage.removeItem(ROUTE_NOTICE_KEY);
            }
          }
        }
      } catch {
        clearLearningSession(window.localStorage);
      } finally {
        if (active) setRestoring(false);
      }
    }
    void restore();
    return () => { active = false; };
  }, [initialWorkspaceId]);

  async function authenticated(response: AuthResponse) {
    setAuth(response);
    setError("");
    saveLearningSession(window.localStorage, {
      token: response.access_token,
      locale,
      home: !initialWorkspaceId,
    });
    try {
      const recent = await api.listWorkspaces(response.access_token);
      setWorkspaces(recent);
      const selected = recent.find((item) => item.id === initialWorkspaceId);
      if (selected) await openWorkspace(selected, response.access_token, initialSection);
    } catch (caught) {
      reportError(caught);
    }
  }

  async function openWorkspace(
    target: LearningWorkspace,
    token = auth?.access_token,
    targetSection: LearningSection = "today",
  ) {
    if (!token) return;
    setBusy(true);
    setError("");
    try {
      const snapshot = await api.getWorkspaceSnapshot(token, target.id);
      applySnapshot(snapshot);
      saveLearningSession(window.localStorage, {
        token,
        workspaceId: target.id,
        locale,
        home: false,
      });
      setSection(targetSection);
      router.push(learningPath(target.id, targetSection));
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
      const saved = loadLearningSession(window.localStorage);
      const previousId = workspace?.id ?? saved?.workspaceId ?? null;
      const snapshot = await api.getWorkspaceSnapshot(auth.access_token, route.workspace.id);
      applySnapshot(snapshot);
      setRoute(route);
      setPreviousWorkspaceId(previousId === route.workspace.id ? null : previousId);
      window.sessionStorage.setItem(ROUTE_NOTICE_KEY, JSON.stringify({
        route,
        previousWorkspaceId: previousId === route.workspace.id ? null : previousId,
      }));
      setWorkspaces(await api.listWorkspaces(auth.access_token));
      saveLearningSession(window.localStorage, {
        token: auth.access_token,
        workspaceId: route.workspace.id,
        locale,
        home: false,
      });
      setSection("today");
      router.push(learningPath(route.workspace.id, "today"));
    } catch (caught) {
      reportError(caught);
    } finally {
      setBusy(false);
    }
  }

  async function getQuestion() {
    if (!auth || !workspace) return;
    setBusy(true);
    setError("");
    try {
      await loadNextQuestion(
        () => api.getWorkspaceQuestion(auth.access_token, workspace.id),
        (nextQuestion) => {
          setQuestion(nextQuestion);
          setResult(null);
          setAnswer("");
        },
      );
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

  async function updateLearningWorkspace(
    target: LearningWorkspace,
    input: { title?: string; archived?: boolean },
  ) {
    if (!auth) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api.updateWorkspace(auth.access_token, target.id, input);
      setWorkspaces((current) => input.archived
        ? current.filter((item) => item.id !== target.id)
        : current.map((item) => item.id === target.id ? updated : item));
    } catch (caught) {
      reportError(caught);
    } finally {
      setBusy(false);
    }
  }

  async function deleteLearningWorkspace(target: LearningWorkspace) {
    if (!auth) return;
    setBusy(true);
    setError("");
    try {
      await api.deleteWorkspace(auth.access_token, target.id);
      setWorkspaces((current) => current.filter((item) => item.id !== target.id));
    } catch (caught) {
      reportError(caught);
    } finally {
      setBusy(false);
    }
  }

  async function updatePlanSession(
    session: StudySession,
    input: { status?: "planned" | "completed"; planned_at?: string },
  ) {
    if (!auth || !workspace) return;
    setError("");
    try {
      const updated = await api.updateWorkspacePlanSession(
        auth.access_token,
        workspace.id,
        session.id,
        input,
      );
      setPlan((current) => current ? {
        ...current,
        sessions: current.sessions.map((item) => item.id === updated.id ? updated : item),
      } : current);
    } catch (caught) {
      reportError(caught);
    }
  }

  async function undoWorkspaceRoute() {
    window.sessionStorage.removeItem(ROUTE_NOTICE_KEY);
    setRoute(null);
    const previous = workspaces.find((item) => item.id === previousWorkspaceId);
    setPreviousWorkspaceId(null);
    if (previous) await openWorkspace(previous);
    else returnHome();
  }

  function dismissWorkspaceRoute() {
    window.sessionStorage.removeItem(ROUTE_NOTICE_KEY);
    setRoute(null);
    setPreviousWorkspaceId(null);
  }

  function logout() {
    clearLearningSession(window.localStorage);
    setAuth(null);
    setWorkspace(null);
    setWorkspaces([]);
  }

  function returnHome() {
    if (auth) {
      saveLearningSession(window.localStorage, {
        token: auth.access_token,
        workspaceId: workspace?.id,
        locale,
        home: true,
      });
    }
    setWorkspace(null);
    router.push("/");
  }

  function toggleLocale() {
    const next = locale === "zh" ? "en" : "zh";
    setLocale(next);
    if (auth) {
      saveLearningSession(window.localStorage, {
        token: auth.access_token,
        workspaceId: workspace?.id,
        locale: next,
        home: !workspace,
      });
    }
    document.documentElement.lang = next === "zh" ? "zh-CN" : "en";
  }

  if (restoring) return <main className="loading-stage"><BrandMark size={44} /><span>{t("loading")}</span></main>;
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
          onUpdate={updateLearningWorkspace}
          onDelete={deleteLearningWorkspace}
          isAdmin={auth.user.role === "admin"}
          onAdmin={() => router.push("/admin")}
          onLogout={logout}
          onToggleLocale={toggleLocale}
        />
      </>
    );
  }

  const masteryValues = progress ? Object.values(progress.mastery) : [];
  const averageMastery = masteryValues.reduce((sum, value) => sum + value, 0)
    / Math.max(1, masteryValues.length);
  const nav: Array<{ id: LearningSection; icon: typeof BookOpen }> = [
    { id: "today", icon: BookOpen },
    { id: "materials", icon: Archive },
    { id: "evidence", icon: NotebookTabs },
    { id: "coach", icon: Bot },
  ];

  return (
    <main className="workspace-shell">
      <aside className="workspace-sidebar">
        <button className="sidebar-brand wordmark-button" onClick={returnHome} aria-label="RefineQ">
          <BrandMark className="brand-mark" size={36} />
          <BrandName />
        </button>
        <nav className="workspace-nav" aria-label="Study sections">
          {nav.map(({ id, icon: Icon }) => (
            <button
              key={id}
              data-testid={`nav-${id}`}
              className={section === id ? "active" : ""}
              onClick={() => {
                setSection(id);
                router.push(`/learn/${workspace.id}/${id}`);
              }}
              aria-label={t(id)}
              aria-current={section === id ? "page" : undefined}
            >
              <Icon size={19} />
              <span>{t(id)}</span>
            </button>
          ))}
          {auth.user.role === "admin" && (
            <button
              data-testid="nav-admin"
              onClick={() => router.push("/admin")}
              aria-label="管理"
            >
              <Settings2 size={19} />
              <span>管理</span>
            </button>
          )}
        </nav>
        <div className="sidebar-learning">
          <span className="kicker">CURRENT LEARNING</span>
          <strong>{workspace.title}</strong>
          <p>{workspace.goal}</p>
          <button className="quiet-button switch-learning" onClick={returnHome}>
            <Sparkles size={15} /> {t("recentLearning")}
          </button>
        </div>
        <div className="sidebar-actions">
          <button className="quiet-button" onClick={toggleLocale}><Languages size={16} /> {t("language")}</button>
          <button className="quiet-button" onClick={logout}><LogOut size={16} /> {t("logout")}</button>
        </div>
      </aside>
      <section className="workspace-stage">
        <header className="workspace-header">
          <div>
            <span className="kicker">{t("workspaceEyebrow")}</span>
            <h1>{workspace.title}</h1>
            <p>{workspace.goal}</p>
          </div>
          <span className="workspace-date">
            {new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", {
              weekday: "long",
              month: "long",
              day: "numeric",
            }).format(new Date())}
          </span>
        </header>
        <div className="workspace-progress">
          <div className="progress-copy">
            <strong>{Math.round(averageMastery * 100)}%</strong>
            <span>{t("mastery")}</span>
          </div>
          <div
            className="progress-track"
            role="progressbar"
            aria-label={t("mastery")}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(averageMastery * 100)}
          >
            <span style={{ width: `${Math.round(averageMastery * 100)}%` }} />
          </div>
          <dl className="progress-stats">
            <div><dt>{t("attempts")}</dt><dd>{progress?.attempt_count ?? 0}</dd></div>
            <div><dt>{t("diagnostic")}</dt><dd>{progress?.diagnostic_count ?? 0}</dd></div>
          </dl>
        </div>
        <section className="workspace-content">
          {route && (
            <div className="workspace-route-notice" data-testid="workspace-route-notice" role="status">
              <Sparkles size={18} />
              <div>
                <strong>{t(route.action === "created" ? "routingCreated" : route.action === "switched" ? "routingSwitched" : "routingReused")}</strong>
                <span>{route.reason} · {t("confidence")} {Math.round(route.confidence * 100)}%</span>
              </div>
              <button type="button" onClick={undoWorkspaceRoute}>{t("routingUndo")}</button>
              <button type="button" aria-label={t("routingDismiss")} onClick={dismissWorkspaceRoute}>×</button>
            </div>
          )}
          {error && <div className="error-banner"><strong>{t("error")}</strong><span>{error}</span><button onClick={() => setError("")}>×</button></div>}
          {section === "today" && (
            <div className="today-grid">
              <div className="daily-heading"><span className="kicker">TODAY&apos;S FOCUS</span><h2>{t("today")}</h2></div>
              <PlanTimeline plan={plan} locale={locale} t={t} onUpdateSession={updatePlanSession} />
              <PracticeCard question={question} answer={answer} result={result} busy={busy} onAnswerChange={setAnswer} onGetQuestion={getQuestion} onSubmit={submitAnswer} t={t} />
            </div>
          )}
          {section === "materials" && <MaterialDropzone key={workspace.id} t={t} materials={materials} onUpload={uploadMaterials} />}
          {section === "evidence" && <EvidenceLedger evidence={evidence} locale={locale} t={t} />}
          {section === "coach" && <AgentPanel token={auth.access_token} workspaceId={workspace.id} t={t} />}
        </section>
      </section>
    </main>
  );
}
