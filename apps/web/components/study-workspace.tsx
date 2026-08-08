"use client";

import {
  Archive,
  BookOpen,
  CalendarDays,
  ChartNoAxesColumnIncreasing,
  House,
  Languages,
  LogOut,
  Settings2,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AuthPanel } from "@/components/auth-panel";
import { BrandMark, BrandName } from "@/components/brand";
import { EvidenceLedger } from "@/components/evidence-ledger";
import { LearningHome } from "@/components/learning-home";
import { LearningSessionCanvas } from "@/components/learning-session-canvas";
import { MaterialDropzone } from "@/components/material-dropzone";
import { PlanSettings } from "@/components/plan-settings";
import { PlanTimeline } from "@/components/plan-timeline";
import { ProgressInsights } from "@/components/progress-insights";
import { WorkspaceSwitcher } from "@/components/workspace-switcher";
import { api, ApiError } from "@/lib/api";
import { localizeApiError } from "@/lib/error-messages";
import { translator } from "@/lib/i18n";
import { learningPath, type LearningSection } from "@/lib/learning-routes";
import { inferLearningMode } from "@/lib/learning-session";
import { loadModelCapability } from "@/lib/model-capability";
import { loadNextQuestion } from "@/lib/practice-flow";
import {
  clearLearningSession,
  loadLearningSession,
  saveLearningLocale,
  saveLearningSession,
} from "@/lib/session";
import type {
  AnswerResult,
  AuthResponse,
  LearningEvidence,
  LearningMode,
  LearningWorkspace,
  Locale,
  MaterialRecord,
  PlanUpdateInput,
  PracticeQuestion,
  PracticeRequest,
  Progress,
  SavedPracticeQuestion,
  StudySession,
  StudyPlan,
  SearchSource,
  WorkspaceRoute,
  WorkspaceSnapshot,
} from "@/lib/types";
import { resolveRequestedWorkspace } from "@/lib/workspace-route-state";

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
  const [modelConfigured, setModelConfigured] = useState<boolean | null>(null);
  const [workspaces, setWorkspaces] = useState<LearningWorkspace[]>([]);
  const [workspace, setWorkspace] = useState<LearningWorkspace | null>(null);
  const [plan, setPlan] = useState<StudyPlan | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [evidence, setEvidence] = useState<LearningEvidence[]>([]);
  const [materials, setMaterials] = useState<MaterialRecord[]>([]);
  const [question, setQuestion] = useState<PracticeQuestion | null>(null);
  const [savedQuestions, setSavedQuestions] = useState<SavedPracticeQuestion[]>([]);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [learningMode, setLearningMode] = useState<LearningMode>("concept");
  const [coachSessionId, setCoachSessionId] = useState<string | undefined>();
  const section = initialSection;
  const [homeBusy, setHomeBusy] = useState(false);
  const [practiceBusy, setPracticeBusy] = useState(false);
  const [busySessionId, setBusySessionId] = useState<string | null>(null);
  const [planSettingsBusy, setPlanSettingsBusy] = useState(false);
  const [error, setError] = useState("");
  const [route, setRoute] = useState<WorkspaceRoute | null>(null);
  const [previousWorkspaceId, setPreviousWorkspaceId] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const questionRequestIdRef = useRef<string | null>(null);
  const attemptIdRef = useRef<string | null>(null);

  function reportError(caught: unknown) {
    setError(localizeApiError(caught, locale));
  }

  function applySnapshot(snapshot: WorkspaceSnapshot) {
    setWorkspace(snapshot.workspace);
    setProgress(snapshot.progress);
    setPlan(snapshot.plan);
    setEvidence(snapshot.evidence);
    setMaterials(snapshot.materials);
    setSavedQuestions(snapshot.saved_questions ?? []);
    const activeQuestion = snapshot.active_question ?? null;
    setLearningMode(
      activeQuestion?.learning_mode
      ?? inferLearningMode(snapshot.workspace.subject, snapshot.workspace.goal),
    );
    setCoachSessionId(undefined);
    setQuestion(activeQuestion);
    setResult(snapshot.last_answer ?? null);
    const draftKey = activeQuestion
      ? `refineq.practice-draft:${snapshot.workspace.id}:${activeQuestion.id}`
      : null;
    setAnswer(
      snapshot.last_answer || !draftKey
        ? ""
        : window.sessionStorage.getItem(draftKey) ?? "",
    );
    questionRequestIdRef.current = null;
    attemptIdRef.current = null;
  }

  const redirectUnavailableWorkspace = useCallback(() => {
    window.sessionStorage.removeItem(ROUTE_NOTICE_KEY);
    setWorkspace(null);
    setRoute(null);
    setPreviousWorkspaceId(null);
    router.replace("/");
  }, [router]);

  useEffect(() => {
    let active = true;
    async function restore() {
      const saved = loadLearningSession(window.sessionStorage);
      if (!saved) {
        if (active) setRestoring(false);
        return;
      }
      try {
        if (saved.locale) {
          setLocale(saved.locale);
          document.documentElement.lang = saved.locale === "zh" ? "zh-CN" : "en";
        }
        const [user, configured] = await Promise.all([
          api.getProfile(saved.token),
          loadModelCapability(() => api.getModelSettings(saved.token)),
        ]);
        const restoredAuth: AuthResponse = {
          access_token: saved.token,
          token_type: "bearer",
          user,
        };
        const recent = await api.listWorkspaces(saved.token);
        if (!active) return;
        setAuth(restoredAuth);
        setModelConfigured(configured);
        setWorkspaces(recent);
        const selectedId = initialWorkspaceId;
        const resolution = resolveRequestedWorkspace(selectedId, recent);
        if (resolution.kind === "home") {
          saveLearningSession(window.sessionStorage, {
            token: saved.token,
            workspaceId: saved.workspaceId,
            locale: saved.locale ?? "zh",
          });
          setWorkspace(null);
          return;
        }
        if (resolution.kind === "unavailable") {
          redirectUnavailableWorkspace();
          return;
        }
        if (resolution.kind === "workspace") {
          const selected = resolution.workspace;
          const snapshot = await api.getWorkspaceSnapshot(saved.token, selected.id);
          if (!active) return;
          applySnapshot(snapshot);
          saveLearningSession(window.sessionStorage, {
            token: saved.token,
            workspaceId: selected.id,
            locale: saved.locale ?? "zh",
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
      } catch (caught) {
        if (!active) return;
        if (caught instanceof ApiError && (caught.status === 401 || caught.status === 403)) {
          clearLearningSession(window.sessionStorage);
          router.replace("/");
        } else if (caught instanceof ApiError && caught.status === 404 && initialWorkspaceId) {
          redirectUnavailableWorkspace();
        } else {
          setError(localizeApiError(caught, saved.locale ?? "zh"));
        }
      } finally {
        if (active) setRestoring(false);
      }
    }
    void restore();
    return () => { active = false; };
  }, [initialWorkspaceId, redirectUnavailableWorkspace, router]);

  useEffect(() => {
    if (!route) return;
    const timeout = window.setTimeout(() => {
      window.sessionStorage.removeItem(ROUTE_NOTICE_KEY);
      setRoute(null);
      setPreviousWorkspaceId(null);
    }, 7000);
    return () => window.clearTimeout(timeout);
  }, [route]);

  async function authenticated(response: AuthResponse) {
    if (initialWorkspaceId) setHomeBusy(true);
    setAuth(response);
    setError("");
    saveLearningSession(window.sessionStorage, {
      token: response.access_token,
      locale,
    });
    try {
      const [recent, configured] = await Promise.all([
        api.listWorkspaces(response.access_token),
        loadModelCapability(() => api.getModelSettings(response.access_token)),
      ]);
      setWorkspaces(recent);
      setModelConfigured(configured);
      const selected = recent.find((item) => item.id === initialWorkspaceId);
      if (initialWorkspaceId && !selected) {
        redirectUnavailableWorkspace();
        return;
      }
      if (selected) await openWorkspace(selected, response.access_token, initialSection, "replace");
    } catch (caught) {
      reportError(caught);
    } finally {
      if (initialWorkspaceId) setHomeBusy(false);
    }
  }

  async function openWorkspace(
    target: LearningWorkspace,
    token = auth?.access_token,
    targetSection: LearningSection = "today",
    navigation: "push" | "replace" = "push",
  ) {
    if (!token) return;
    setHomeBusy(true);
    setError("");
    try {
      const snapshot = await api.getWorkspaceSnapshot(token, target.id);
      applySnapshot(snapshot);
      saveLearningSession(window.sessionStorage, {
        token,
        workspaceId: target.id,
        locale,
      });
      if (navigation === "replace") {
        router.replace(learningPath(target.id, targetSection));
      } else {
        router.push(learningPath(target.id, targetSection));
      }
    } catch (caught) {
      reportError(caught);
    } finally {
      setHomeBusy(false);
    }
  }

  async function resolveIntent(intent: string) {
    if (!auth) return;
    setHomeBusy(true);
    setError("");
    try {
      const route = await api.resolveWorkspace(auth.access_token, intent);
      const saved = loadLearningSession(window.sessionStorage);
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
      saveLearningSession(window.sessionStorage, {
        token: auth.access_token,
        workspaceId: route.workspace.id,
        locale,
      });
      router.push(learningPath(route.workspace.id, "today"));
    } catch (caught) {
      reportError(caught);
    } finally {
      setHomeBusy(false);
    }
  }

  async function getQuestion(request: PracticeRequest = {}) {
    if (!auth || !workspace) return;
    setPracticeBusy(true);
    setError("");
    questionRequestIdRef.current ??= crypto.randomUUID().replaceAll("-", "");
    try {
      await loadNextQuestion(
        () => api.createWorkspaceQuestion(auth.access_token, workspace.id, {
          requestId: questionRequestIdRef.current ?? undefined,
          learningMode,
          ...request,
        }),
        (nextQuestion) => {
          if (question) {
            window.sessionStorage.removeItem(
              `refineq.practice-draft:${workspace.id}:${question.id}`,
            );
          }
          setQuestion(nextQuestion);
          setResult(null);
          setAnswer("");
          questionRequestIdRef.current = null;
          attemptIdRef.current = null;
        },
      );
    } catch (caught) {
      reportError(caught);
    } finally {
      setPracticeBusy(false);
    }
  }

  async function submitAnswer() {
    if (!auth || !workspace || !question) return;
    setPracticeBusy(true);
    attemptIdRef.current ??= crypto.randomUUID().replaceAll("-", "");
    try {
      const graded = await api.submitWorkspaceAnswer(
          auth.access_token,
          workspace.id,
          question.id,
          answer,
          attemptIdRef.current,
        );
      setResult(graded);
      attemptIdRef.current = null;
      window.sessionStorage.removeItem(
        `refineq.practice-draft:${workspace.id}:${question.id}`,
      );
      const snapshot = await api.getWorkspaceSnapshot(auth.access_token, workspace.id);
      setProgress(snapshot.progress);
      setEvidence(snapshot.evidence);
      setPlan(snapshot.plan);
    } catch (caught) {
      reportError(caught);
    } finally {
      setPracticeBusy(false);
    }
  }

  async function toggleSavedQuestion(target: PracticeQuestion, saved: boolean) {
    if (!auth || !workspace) return;
    setPracticeBusy(true);
    setError("");
    try {
      const updated = await api.setWorkspaceQuestionSaved(
        auth.access_token,
        workspace.id,
        target.id,
        saved,
      );
      setQuestion((current) => current?.id === updated.id
        ? { ...current, saved: updated.saved }
        : current);
      setSavedQuestions((current) => updated.saved
        ? [updated, ...current.filter((item) => item.id !== updated.id)]
        : current.filter((item) => item.id !== updated.id));
    } catch (caught) {
      reportError(caught);
    } finally {
      setPracticeBusy(false);
    }
  }

  async function practiceTopic(topicId: string, difficulty?: number) {
    if (!workspace) return;
    router.push(learningPath(workspace.id, "today"));
    await getQuestion({
      topicId,
      difficulty,
      learningMode,
      replace: question !== null,
    });
    window.requestAnimationFrame(() => {
      document.getElementById("active-practice")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
  }

  async function uploadMaterials(files: File[], signal?: AbortSignal): Promise<MaterialRecord[]> {
    if (!auth || !workspace) return [];
    setError("");
    try {
      const uploaded = await api.uploadWorkspaceMaterials(
        auth.access_token,
        workspace.id,
        files,
        signal,
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

  async function searchMaterials(query: string): Promise<SearchSource[]> {
    if (!auth || !workspace) return [];
    try {
      return await api.searchWorkspaceMaterials(auth.access_token, workspace.id, query);
    } catch (caught) {
      reportError(caught);
      return [];
    }
  }

  async function downloadMaterial(material: MaterialRecord) {
    if (!auth || !workspace) return;
    try {
      const blob = await api.downloadWorkspaceMaterial(auth.access_token, workspace.id, material.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = material.filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      reportError(caught);
    }
  }

  async function deleteMaterial(material: MaterialRecord) {
    if (!auth || !workspace) return;
    try {
      await api.deleteWorkspaceMaterial(auth.access_token, workspace.id, material.id);
      setMaterials((current) => current.filter((item) => item.id !== material.id));
    } catch (caught) {
      reportError(caught);
    }
  }

  async function askSessionCoach(message: string) {
    if (!auth || !workspace) throw new Error(t("error"));
    const reply = await api.chatWorkspace(
      auth.access_token,
      workspace.id,
      message,
      coachSessionId,
      crypto.randomUUID(),
      undefined,
      {
        learning_mode: learningMode,
        stage: result ? "reflect" : question ? "practice" : "learn",
        question: question?.prompt,
        draft: answer || undefined,
        feedback: result?.feedback,
      },
    );
    setCoachSessionId(reply.session_id);
    return reply;
  }

  function changeLearningMode(mode: LearningMode) {
    setLearningMode(mode);
    if (question) {
      void getQuestion({ learningMode: mode, replace: true });
    }
  }

  async function updateLearningWorkspace(
    target: LearningWorkspace,
    input: { title?: string; archived?: boolean },
  ) {
    if (!auth) return;
    setHomeBusy(true);
    setError("");
    try {
      const updated = await api.updateWorkspace(auth.access_token, target.id, input);
      setWorkspaces((current) => updated.archived && !showArchived
        ? current.filter((item) => item.id !== target.id)
        : current.map((item) => item.id === target.id ? updated : item));
    } catch (caught) {
      reportError(caught);
    } finally {
      setHomeBusy(false);
    }
  }

  async function deleteLearningWorkspace(target: LearningWorkspace) {
    if (!auth) return;
    setHomeBusy(true);
    setError("");
    try {
      await api.deleteWorkspace(auth.access_token, target.id);
      setWorkspaces((current) => current.filter((item) => item.id !== target.id));
    } catch (caught) {
      reportError(caught);
    } finally {
      setHomeBusy(false);
    }
  }

  async function toggleArchivedWorkspaces(show: boolean) {
    if (!auth) return;
    setHomeBusy(true);
    setError("");
    try {
      setWorkspaces(await api.listWorkspaces(auth.access_token, show));
      setShowArchived(show);
    } catch (caught) {
      reportError(caught);
    } finally {
      setHomeBusy(false);
    }
  }

  async function updatePlanSession(
    session: StudySession,
    input: { status?: "planned" | "completed"; planned_at?: string },
  ) {
    if (!auth || !workspace) return;
    setBusySessionId(session.id);
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
    } finally {
      setBusySessionId(null);
    }
  }

  async function updatePlanSettings(input: PlanUpdateInput) {
    if (!auth || !workspace) return;
    setPlanSettingsBusy(true);
    setError("");
    try {
      const updated = await api.updateWorkspacePlan(
        auth.access_token,
        workspace.id,
        input,
      );
      setPlan(updated);
      setWorkspace((current) => current ? { ...current, goal: input.goal } : current);
      setWorkspaces((current) => current.map((item) => (
        item.id === workspace.id ? { ...item, goal: input.goal } : item
      )));
      setProgress((current) => current ? {
        ...current,
        goal: input.goal,
        plan_id: updated.id,
        topic_order: [...input.topic_order],
      } : current);
    } catch (caught) {
      reportError(caught);
      throw caught;
    } finally {
      setPlanSettingsBusy(false);
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

  function prepareRouteNavigation() {
    window.sessionStorage.removeItem(ROUTE_NOTICE_KEY);
    setRoute(null);
    setPreviousWorkspaceId(null);
  }

  function prepareHomeNavigation() {
    prepareRouteNavigation();
    if (auth) {
      saveLearningSession(window.sessionStorage, {
        token: auth.access_token,
        workspaceId: workspace?.id,
        locale,
      });
    }
    setWorkspace(null);
  }

  function logout() {
    clearLearningSession(window.sessionStorage);
    setAuth(null);
    setModelConfigured(null);
    setWorkspace(null);
    setWorkspaces([]);
    router.replace("/");
  }

  function returnHome() {
    prepareHomeNavigation();
    router.push("/");
  }

  function toggleLocale() {
    const next = locale === "zh" ? "en" : "zh";
    setLocale(next);
    if (auth) {
      saveLearningLocale(window.sessionStorage, auth.access_token, next, workspace?.id);
    }
    document.documentElement.lang = next === "zh" ? "zh-CN" : "en";
  }

  if (restoring) return <main className="loading-stage"><BrandMark size={44} /><span>{t("loading")}</span></main>;
  if (!auth) return <AuthPanel t={t} locale={locale} onAuthenticated={authenticated} />;
  if (!workspace && initialWorkspaceId) {
    const retryTarget = workspaces.find((item) => item.id === initialWorkspaceId);
    return (
      <main id="main-content" className="workspace-route-state" data-testid="workspace-route-state">
        <BrandMark size={48} />
        <span className="kicker">REFINEQ / LEARNING SPACE</span>
        <h1>{homeBusy && !error ? t("loading") : t("workspaceOpenFailed")}</h1>
        <p>{error || (locale === "zh" ? "正在恢复这个空间的资料与学习进度。" : "Restoring this space, its sources, and progress.")}</p>
        <div>
          {retryTarget && !homeBusy && (
            <button
              type="button"
              className="secondary-action"
              onClick={() => void openWorkspace(retryTarget, auth.access_token, initialSection, "replace")}
            >
              {t("retry")}
            </button>
          )}
          <Link className="primary-action" href="/">{t("backLearningHome")}</Link>
        </div>
      </main>
    );
  }
  if (!workspace) {
    return (
      <>
        {error && <div className="error-banner" role="alert"><strong>{t("error")}</strong><span>{error}</span></div>}
        <LearningHome
          t={t}
          busy={homeBusy}
          workspaces={workspaces}
          onResolve={resolveIntent}
          onOpen={openWorkspace}
          onUpdate={updateLearningWorkspace}
          onDelete={deleteLearningWorkspace}
          showArchived={showArchived}
          onToggleArchived={toggleArchivedWorkspaces}
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
    { id: "path", icon: CalendarDays },
    { id: "materials", icon: Archive },
    { id: "progress", icon: ChartNoAxesColumnIncreasing },
  ];

  return (
    <main id="main-content" className="workspace-shell">
      <aside className="workspace-sidebar">
        <Link className="sidebar-brand wordmark-button" href="/" onClick={prepareRouteNavigation} aria-label="RefineQ">
          <BrandMark className="brand-mark" size={36} />
          <BrandName />
        </Link>
        <Link
          data-testid="workspace-home-link"
          className="workspace-home-link"
          href="/"
          onClick={prepareRouteNavigation}
        >
          <House size={18} />
          <span>{t("learningHome")}</span>
        </Link>
        <WorkspaceSwitcher
          locale={locale}
          current={workspace}
          workspaces={workspaces}
          currentProgress={Math.round(averageMastery * 100)}
          onSelect={(target) => openWorkspace(target)}
          onAllSpaces={returnHome}
        />
        <span className="workspace-nav-label">{t("workspaceSections")}</span>
        <nav className="workspace-nav" aria-label={t("workspaceSections")}>
          {nav.map(({ id, icon: Icon }) => (
            <Link
              key={id}
              data-testid={`nav-${id}`}
              className={section === id ? "active" : ""}
              href={learningPath(workspace.id, id)}
              onClick={prepareRouteNavigation}
              aria-label={t(id)}
              aria-current={section === id ? "page" : undefined}
            >
              <Icon size={19} />
              <span>{t(id)}</span>
            </Link>
          ))}
          {auth.user.role === "admin" && (
            <Link
              data-testid="nav-admin"
              href="/admin"
              aria-label={t("administration")}
            >
              <Settings2 size={19} />
              <span>{t("administration")}</span>
            </Link>
          )}
        </nav>
        <div className="sidebar-actions">
          <button className="quiet-button" onClick={toggleLocale}><Languages size={16} /> {t("language")}</button>
          <button className="quiet-button" onClick={logout}><LogOut size={16} /> {t("logout")}</button>
        </div>
      </aside>
      <section className="workspace-stage">
        {section !== "today" && (
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
        )}
        <section className={`workspace-content workspace-content-${section}`}>
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
          {error && <div className="error-banner" role="alert" aria-live="polite"><strong>{t("error")}</strong><span>{error}</span><button aria-label={t("routingDismiss")} onClick={() => setError("")}>×</button></div>}
          {section === "today" && (
            <LearningSessionCanvas
              locale={locale}
              t={t}
              workspace={workspace}
              plan={plan}
              progress={progress}
              materials={materials}
              question={question}
              answer={answer}
              result={result}
              busy={practiceBusy}
              learningMode={learningMode}
              savedQuestions={savedQuestions}
              agentToken={auth.access_token}
              modelConfigured={modelConfigured}
              onModelUnavailable={() => setModelConfigured(false)}
              isAdmin={auth.user.role === "admin"}
              onOpenAgentSettings={() => router.push("/admin/integrations/chat")}
              onLearningModeChange={changeLearningMode}
              onAnswerChange={(value) => {
                setAnswer(value);
                if (question) {
                  window.sessionStorage.setItem(
                    `refineq.practice-draft:${workspace.id}:${question.id}`,
                    value,
                  );
                }
              }}
              onStartTask={() => getQuestion({ learningMode })}
              onSubmit={submitAnswer}
              onNextTask={() => getQuestion({ learningMode, replace: true })}
              onToggleSaved={toggleSavedQuestion}
              onOpenLibrary={() => router.push(learningPath(workspace.id, "materials"))}
              onAskCoach={askSessionCoach}
            />
          )}
          {section === "path" && (
            <div className="learning-path-view" data-testid="learning-path-view">
              <div className="page-section-heading">
                <span className="kicker">PATH / ADAPTIVE</span>
                <h2>{t("path")}</h2>
                <p>{locale === "zh" ? "围绕能力目标组织每次学习，而不是堆积重复日程。" : "Each session advances the capability goal without a wall of repeated dates."}</p>
              </div>
              {plan && progress && (
                <PlanSettings
                  locale={locale}
                  plan={plan}
                  topics={progress.topics}
                  topicOrder={progress.topic_order}
                  busy={planSettingsBusy}
                  onSave={updatePlanSettings}
                />
              )}
              <PlanTimeline
                plan={plan}
                locale={locale}
                t={t}
                onUpdateSession={updatePlanSession}
                onStartSession={(session) => practiceTopic(session.topic_id)}
                busySessionId={busySessionId}
                topicLabels={progress?.topics}
              />
            </div>
          )}
          {section === "materials" && (
            <MaterialDropzone
              key={workspace.id}
               t={t}
               locale={locale}
               materials={materials}
              onUpload={uploadMaterials}
              onSearch={searchMaterials}
              onDownload={downloadMaterial}
              onDelete={deleteMaterial}
            />
          )}
          {section === "progress" && (
            <div className="learning-progress-view" data-testid="learning-progress-view">
              <div className="page-section-heading">
                <span className="kicker">PROGRESS / CAPABILITY</span>
                <h2>{t("progress")}</h2>
                <p>{locale === "zh" ? "把能力变化、实践反馈和下一步安排放在一起。" : "Capability change, task feedback, and next actions in one place."}</p>
              </div>
              <ProgressInsights
                progress={progress}
                t={t}
                onPracticeTopic={practiceTopic}
                topicLabels={progress?.topics}
              />
              <EvidenceLedger evidence={evidence} locale={locale} t={t} />
            </div>
          )}
        </section>
      </section>
    </main>
  );
}
