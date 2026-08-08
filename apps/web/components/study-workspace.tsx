"use client";

import {
  Archive,
  BookOpen,
  CalendarDays,
  ChartNoAxesColumnIncreasing,
  Route,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { AuthPanel } from "@/components/auth-panel";
import { AppSidebar } from "@/components/app-sidebar";
import { BrandMark } from "@/components/brand";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { EvidenceLedger } from "@/components/evidence-ledger";
import { InitialDiagnostic } from "@/components/initial-diagnostic";
import { LearningHome } from "@/components/learning-home";
import { LearningReport } from "@/components/learning-report";
import { LearningSessionCanvas } from "@/components/learning-session-canvas";
import { MaterialDropzone } from "@/components/material-dropzone";
import { PlanSettings } from "@/components/plan-settings";
import { PlanTimeline } from "@/components/plan-timeline";
import { ScheduleCalendar } from "@/components/schedule-calendar";
import { ProgressInsights } from "@/components/progress-insights";
import { ProgressTopicDetail } from "@/components/progress-topic-detail";
import { ReviewQueue } from "@/components/review-queue";
import { WorkspaceSwitcher } from "@/components/workspace-switcher";
import { useAgentState } from "@/hooks/use-agent-state";
import { useLearningAuth } from "@/hooks/use-learning-auth";
import { usePracticeState } from "@/hooks/use-practice-state";
import { useWorkspaceState } from "@/hooks/use-workspace-state";
import { api, ApiError } from "@/lib/api";
import {
  executeCoachAction,
  pendingCoachTurn,
  type PendingCoachTurn,
} from "@/lib/coach-actions";
import { localizeApiError } from "@/lib/error-messages";
import { learningPath, type LearningSection } from "@/lib/learning-routes";
import { learningModeForActivity } from "@/lib/learning-session";
import { loadModelCapability, refreshModelCapability } from "@/lib/model-capability";
import { loadNextQuestion } from "@/lib/practice-flow";
import {
  guardPracticeNavigation,
  hasUnsavedPracticeDraft,
  type PracticeNavigationAction,
} from "@/lib/practice-navigation";
import { isAbortError } from "@/lib/upload-flow";
import {
  clearLearningSession,
  installSessionHandoff,
  loadLearningSession,
  requestSessionHandoff,
  saveLearningSession,
} from "@/lib/session";
import type {
  AttemptFeedbackInput,
  AttemptInsight,
  ExecutableActionProposal,
  AuthResponse,
  DueReviewInsight,
  DiagnosticResultInput,
  LearningMode,
  LearningWorkspace,
  MaterialRecord,
  MaterialUpdateInput,
  PlanUpdateInput,
  PracticeQuestion,
  PracticeRequest,
  SearchSource,
  StudySession,
  TopicSuggestion,
  WorkspaceRoute,
  WorkspaceSnapshot,
} from "@/lib/types";
import { resolveRequestedWorkspace } from "@/lib/workspace-route-state";
import {
  clearWorkspaceSnapshots,
  consumeWorkspaceSnapshot,
  removeWorkspaceSnapshot,
  saveWorkspaceSnapshot,
} from "@/lib/workspace-snapshot-handoff";

const ROUTE_NOTICE_KEY = "refineq.workspace-route-notice";
const SECTION_FOCUS_KEY = "refineq.section-focus";


export function StudyWorkspace({
  initialWorkspaceId,
  initialSection = "today",
}: {
  initialWorkspaceId?: string;
  initialSection?: LearningSection;
} = {}) {
  const router = useRouter();
  const {
    auth,
    error,
    locale,
    modelConfigured,
    reportError,
    resetAuthentication,
    restoring,
    setAuth,
    setError,
    setLocale,
    setModelConfigured,
    setRestoring,
    t,
    toggleLocale: toggleLearningLocale,
  } = useLearningAuth();
  const {
    applySnapshot: applyWorkspaceSnapshot,
    clearWorkspaceState,
    evidence,
    insights,
    materials,
    plan,
    previousWorkspaceId,
    progress,
    route,
    savedQuestions,
    selectedTopicId,
    setEvidence,
    setInsights,
    setMaterials,
    setTopicSuggestions,
    setPlan,
    setPreviousWorkspaceId,
    setProgress,
    setRoute,
    setSavedQuestions,
    setSelectedTopicId,
    setShowArchived,
    setWorkspace,
    setWorkspaces,
    showArchived,
    workspace,
    workspaces,
    topicSuggestions,
  } = useWorkspaceState();
  const {
    answer,
    attemptIdRef,
    capturePracticeGeneration,
    clearPracticeState,
    hydratePractice,
    isPracticeGenerationCurrent,
    learningMode,
    practiceBusy,
    question,
    questionRequestIdRef,
    result,
    setAnswer,
    setLearningMode,
    setPracticeBusy,
    setQuestion,
    setResult,
  } = usePracticeState();
  const { askCoach, resetAgent } = useAgentState();
  const section = initialSection;
  const [homeBusy, setHomeBusy] = useState(false);
  const [busySessionId, setBusySessionId] = useState<string | null>(null);
  const [planSettingsBusy, setPlanSettingsBusy] = useState(false);
  const [insightsLoading, setInsightsLoading] = useState(false);
  const [snapshotConflict, setSnapshotConflict] = useState(false);
  const [masteryBefore, setMasteryBefore] = useState<number | null>(null);
  const [acceptingTopicSuggestionId, setAcceptingTopicSuggestionId] = useState<string | null>(null);
  const sectionHeadingRef = useRef<HTMLHeadingElement>(null);
  const pendingTurnIdRef = useRef<PendingCoachTurn | null>(null);
  const appliedActionIdsRef = useRef(new Set<string>());
  const activeCoachWorkspaceIdRef = useRef<string | null>(null);
  const pendingPracticeActionRef = useRef<PracticeNavigationAction | null>(null);
  const [draftConfirmOpen, setDraftConfirmOpen] = useState(false);
  const authRef = useRef(auth);
  const workspaceRef = useRef(workspace);
  const localeRef = useRef(locale);
  authRef.current = auth;
  workspaceRef.current = workspace;
  localeRef.current = locale;

  const applySnapshot = useCallback((snapshot: WorkspaceSnapshot) => {
    if (activeCoachWorkspaceIdRef.current !== snapshot.workspace.id) {
      pendingTurnIdRef.current = null;
      appliedActionIdsRef.current.clear();
      resetAgent();
    }
    activeCoachWorkspaceIdRef.current = snapshot.workspace.id;
    applyWorkspaceSnapshot(snapshot);
    hydratePractice(snapshot);
  }, [applyWorkspaceSnapshot, hydratePractice, resetAgent]);

  const recheckModelCapability = useCallback(async (): Promise<boolean | null> => {
    const token = auth?.access_token;
    if (!token) return null;
    return refreshModelCapability(
      () => api.getModelSettings(token),
      setModelConfigured,
    );
  }, [auth?.access_token, setModelConfigured]);

  useEffect(() => installSessionHandoff(window.sessionStorage), []);

  function runGuardedPracticeAction(action: PracticeNavigationAction): boolean {
    return guardPracticeNavigation(
      hasUnsavedPracticeDraft(answer, Boolean(question), Boolean(result)),
      action,
      (pending) => {
        pendingPracticeActionRef.current = pending;
        setDraftConfirmOpen(true);
      },
    );
  }

  function confirmDraftReplacement() {
    const pending = pendingPracticeActionRef.current;
    pendingPracticeActionRef.current = null;
    setDraftConfirmOpen(false);
    if (pending) void pending();
  }

  function cancelDraftReplacement() {
    pendingPracticeActionRef.current = null;
    setDraftConfirmOpen(false);
  }

  useEffect(() => {
    const token = auth?.access_token;
    const workspaceId = workspace?.id;
    if ((section !== "progress" && section !== "today") || !token || !workspaceId) return;
    let active = true;
    void Promise.resolve()
      .then(() => {
        if (active) setInsightsLoading(true);
        return api.getWorkspaceInsights(token, workspaceId);
      })
      .then((loaded) => {
        if (active) setInsights(loaded);
      })
      .catch((caught) => {
        if (active) setError(localizeApiError(caught, locale));
      })
      .finally(() => {
        if (active) setInsightsLoading(false);
      });
    return () => { active = false; };
  }, [auth?.access_token, locale, section, setError, setInsights, workspace?.id]);

  useEffect(() => {
    if (window.sessionStorage.getItem(SECTION_FOCUS_KEY) !== "1") return;
    if (restoring || !workspace || !sectionHeadingRef.current) return;
    window.sessionStorage.removeItem(SECTION_FOCUS_KEY);
    const timeout = window.setTimeout(() => {
      sectionHeadingRef.current?.focus({ preventScroll: true });
    }, 0);
    return () => window.clearTimeout(timeout);
  }, [restoring, section, workspace]);

  const redirectUnavailableWorkspace = useCallback(() => {
    window.sessionStorage.removeItem(ROUTE_NOTICE_KEY);
    setHomeBusy(true);
    setWorkspace(null);
    setRoute(null);
    setPreviousWorkspaceId(null);
    router.replace("/");
  }, [router, setPreviousWorkspaceId, setRoute, setWorkspace]);

  useEffect(() => {
    let active = true;
    async function restore() {
      const currentAuth = authRef.current;
      if (currentAuth) {
        if (!initialWorkspaceId) {
          setWorkspace(null);
          if (active) setRestoring(false);
          return;
        }
        if (workspaceRef.current?.id === initialWorkspaceId) {
          removeWorkspaceSnapshot(window.sessionStorage, initialWorkspaceId);
          if (active) setRestoring(false);
          return;
        }
        clearWorkspaceState();
        clearPracticeState();
        resetAgent();
        setError("");
        setRestoring(true);
        try {
          const snapshot = consumeWorkspaceSnapshot(window.sessionStorage, initialWorkspaceId)
            ?? await api.getWorkspaceSnapshot(currentAuth.access_token, initialWorkspaceId);
          if (!active) return;
          applySnapshot(snapshot);
          saveLearningSession(window.sessionStorage, {
            token: currentAuth.access_token,
            workspaceId: initialWorkspaceId,
            locale: localeRef.current,
          });
        } catch (caught) {
          if (!active) return;
          if (caught instanceof ApiError && (caught.status === 401 || caught.status === 403)) {
            clearWorkspaceSnapshots(window.sessionStorage);
            resetAuthentication();
            clearWorkspaceState();
            clearPracticeState();
            resetAgent();
            setWorkspaces([]);
            router.replace("/");
          } else if (caught instanceof ApiError && caught.status === 404) {
            redirectUnavailableWorkspace();
          } else {
            setError(localizeApiError(caught, localeRef.current));
          }
        } finally {
          if (active) setRestoring(false);
        }
        return;
      }
      const saved = loadLearningSession(window.sessionStorage)
        ?? await requestSessionHandoff(window.sessionStorage);
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
          const snapshot = consumeWorkspaceSnapshot(window.sessionStorage, selected.id)
            ?? await api.getWorkspaceSnapshot(saved.token, selected.id);
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
          clearWorkspaceSnapshots(window.sessionStorage);
          clearLearningSession(window.sessionStorage);
          clearWorkspaceState();
          clearPracticeState();
          resetAgent();
          setWorkspaces([]);
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
  }, [
    applySnapshot,
    clearPracticeState,
    clearWorkspaceState,
    initialWorkspaceId,
    redirectUnavailableWorkspace,
    resetAuthentication,
    resetAgent,
    router,
    setAuth,
    setError,
    setLocale,
    setModelConfigured,
    setPreviousWorkspaceId,
    setRestoring,
    setRoute,
    setWorkspace,
    setWorkspaces,
  ]);

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
    removeWorkspaceSnapshot(window.sessionStorage, target.id);
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
      removeWorkspaceSnapshot(window.sessionStorage, route.workspace.id);
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

  async function getQuestion(request: PracticeRequest = {}): Promise<boolean> {
    if (!auth || !workspace) return false;
    const generation = capturePracticeGeneration();
    setPracticeBusy(true);
    setError("");
    const requestId = request.requestId
      ?? questionRequestIdRef.current
      ?? crypto.randomUUID().replaceAll("-", "");
    if (!request.requestId) questionRequestIdRef.current = requestId;
    try {
      await loadNextQuestion(
        () => api.createWorkspaceQuestion(auth.access_token, workspace.id, {
          learningMode,
          ...request,
          requestId,
        }),
        (nextQuestion) => {
          if (!isPracticeGenerationCurrent(generation)) return;
          if (question) {
            window.sessionStorage.removeItem(
              `refineq.practice-draft:${workspace.id}:${question.id}`,
            );
          }
          setQuestion(nextQuestion);
          setResult(null);
          setMasteryBefore(null);
          setAnswer("");
          questionRequestIdRef.current = null;
          attemptIdRef.current = null;
        },
      );
      return isPracticeGenerationCurrent(generation);
    } catch (caught) {
      if (isPracticeGenerationCurrent(generation)) reportError(caught);
      return false;
    } finally {
      if (isPracticeGenerationCurrent(generation)) setPracticeBusy(false);
    }
  }

  async function submitInitialDiagnostic(results: DiagnosticResultInput[]) {
    if (!auth || !workspace) return;
    const generation = capturePracticeGeneration();
    setPracticeBusy(true);
    setError("");
    try {
      await api.submitWorkspaceDiagnostic(auth.access_token, workspace.id, results);
      if (!isPracticeGenerationCurrent(generation)) return;
      const snapshot = await api.getWorkspaceSnapshot(auth.access_token, workspace.id);
      if (!isPracticeGenerationCurrent(generation)) return;
      setProgress(snapshot.progress);
      setEvidence(snapshot.evidence);
      setPlan(snapshot.plan);
    } catch (caught) {
      if (isPracticeGenerationCurrent(generation)) reportError(caught);
    } finally {
      if (isPracticeGenerationCurrent(generation)) setPracticeBusy(false);
    }
  }

  async function submitAnswer() {
    if (!auth || !workspace || !question) return;
    const generation = capturePracticeGeneration();
    setPracticeBusy(true);
    setError("");
    setSnapshotConflict(false);
    setMasteryBefore(progress?.mastery?.[question.topic_id] ?? null);
    attemptIdRef.current ??= crypto.randomUUID().replaceAll("-", "");
    const attemptId = attemptIdRef.current;
    try {
      const graded = await api.submitWorkspaceAnswer(
          auth.access_token,
          workspace.id,
          question.id,
          answer,
          attemptId,
        );
      if (!isPracticeGenerationCurrent(generation)) return;
      setResult(graded);
      attemptIdRef.current = null;
      window.sessionStorage.removeItem(
        `refineq.practice-draft:${workspace.id}:${question.id}`,
      );
      const snapshot = await api.getWorkspaceSnapshot(auth.access_token, workspace.id);
      if (!isPracticeGenerationCurrent(generation)) return;
      setProgress(snapshot.progress);
      setEvidence(snapshot.evidence);
      setPlan(snapshot.plan);
    } catch (caught) {
      if (isPracticeGenerationCurrent(generation)) {
        if (caught instanceof ApiError && caught.status === 409) setSnapshotConflict(true);
        reportError(caught);
      }
    } finally {
      if (isPracticeGenerationCurrent(generation)) setPracticeBusy(false);
    }
  }

  async function toggleSavedQuestion(target: PracticeQuestion, saved: boolean): Promise<boolean> {
    if (!auth || !workspace) return false;
    const generation = capturePracticeGeneration();
    setPracticeBusy(true);
    setError("");
    try {
      const updated = await api.setWorkspaceQuestionSaved(
        auth.access_token,
        workspace.id,
        target.id,
        saved,
      );
      if (!isPracticeGenerationCurrent(generation)) return false;
      setQuestion((current) => current?.id === updated.id
        ? { ...current, saved: updated.saved }
        : current);
      setSavedQuestions((current) => updated.saved
        ? [updated, ...current.filter((item) => item.id !== updated.id)]
        : current.filter((item) => item.id !== updated.id));
      return true;
    } catch (caught) {
      if (isPracticeGenerationCurrent(generation)) reportError(caught);
      return false;
    } finally {
      if (isPracticeGenerationCurrent(generation)) setPracticeBusy(false);
    }
  }

  function practiceTopic(topicId: string, difficulty?: number) {
    runGuardedPracticeAction(async () => {
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
    });
  }

  function startReviewSession(topicId: string, sessionId: string) {
    runGuardedPracticeAction(async () => {
      if (!workspace) return;
      router.push(learningPath(workspace.id, "today"));
      await getQuestion({
        topicId,
        reviewSessionId: sessionId,
        learningMode,
        replace: question !== null,
      });
      window.requestAnimationFrame(() => {
        document.getElementById("active-practice")?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      });
    });
  }

  function startPlanSession(session: StudySession) {
    runGuardedPracticeAction(async () => {
      if (!workspace) return;
      const mode = learningModeForActivity(session.activity ?? "practice");
      setLearningMode(mode);
      router.push(learningPath(workspace.id, "today"));
      await getQuestion({
        topicId: session.topic_id,
        planSessionId: session.id,
        learningMode: mode,
        replace: question !== null,
      });
      window.requestAnimationFrame(() => {
        document.getElementById("active-practice")?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      });
    });
  }

  function startReview(review: DueReviewInsight) {
    startReviewSession(review.topic_id, review.session_id);
  }

  function retryAttempt(attempt: AttemptInsight) {
    runGuardedPracticeAction(async () => {
      if (!auth || !workspace) return;
      const generation = capturePracticeGeneration();
      setPracticeBusy(true);
      setError("");
      try {
        const retried = await api.retryWorkspaceQuestion(auth.access_token, workspace.id, attempt.question_id);
        if (!isPracticeGenerationCurrent(generation)) return;
        setQuestion(retried);
        setResult(null);
        setMasteryBefore(null);
        setAnswer("");
        questionRequestIdRef.current = null;
        attemptIdRef.current = null;
        router.push(learningPath(workspace.id, "today"));
      } catch (caught) {
        if (isPracticeGenerationCurrent(generation)) reportError(caught);
      } finally {
        if (isPracticeGenerationCurrent(generation)) setPracticeBusy(false);
      }
    });
  }

  function practiceSavedQuestion(saved: PracticeQuestion) {
    runGuardedPracticeAction(async () => {
      if (!auth || !workspace) return;
      const generation = capturePracticeGeneration();
      setPracticeBusy(true);
      setError("");
      try {
        const retried = await api.retryWorkspaceQuestion(auth.access_token, workspace.id, saved.id);
        if (!isPracticeGenerationCurrent(generation)) return;
        if (question) window.sessionStorage.removeItem(`refineq.practice-draft:${workspace.id}:${question.id}`);
        setQuestion(retried);
        setResult(null);
        setMasteryBefore(null);
        setAnswer("");
        questionRequestIdRef.current = null;
        attemptIdRef.current = null;
        router.push(learningPath(workspace.id, "today"));
        window.requestAnimationFrame(() => {
          document.getElementById("active-practice")?.scrollIntoView({ behavior: "smooth", block: "start" });
        });
      } catch (caught) {
        if (isPracticeGenerationCurrent(generation)) reportError(caught);
      } finally {
        if (isPracticeGenerationCurrent(generation)) setPracticeBusy(false);
      }
    });
  }

  async function updateAttemptFeedback(
    attempt: AttemptInsight,
    input: AttemptFeedbackInput,
  ) {
    if (!auth || !workspace) return;
    const generation = capturePracticeGeneration();
    setError("");
    try {
      const updated = await api.updateWorkspaceAttemptFeedback(
        auth.access_token,
        workspace.id,
        attempt.attempt_id,
        input,
      );
      if (!isPracticeGenerationCurrent(generation)) return;
      setInsights((current) => current ? {
        ...current,
        attempts: current.attempts.map((item) => item.attempt_id === updated.attempt_id
          ? { ...item, learner_note: updated.learner_note, appealed: updated.appealed }
          : item),
      } : current);
    } catch (caught) {
      if (isPracticeGenerationCurrent(generation)) reportError(caught);
      throw caught;
    }
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
      await refreshTopicSuggestions(auth.access_token, workspace.id);
      return uploaded;
    } catch (caught) {
      if (isAbortError(caught)) return [];
      reportError(caught);
      return [];
    }
  }

  async function refreshTopicSuggestions(token: string, workspaceId: string) {
    try {
      const suggestions = await api.listWorkspaceTopicSuggestions(token, workspaceId);
      if (workspaceRef.current?.id === workspaceId) setTopicSuggestions(suggestions);
    } catch (caught) {
      if (workspaceRef.current?.id === workspaceId) reportError(caught);
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
      await refreshTopicSuggestions(auth.access_token, workspace.id);
    } catch (caught) {
      reportError(caught);
    }
  }

  async function updateMaterial(material: MaterialRecord, input: MaterialUpdateInput) {
    if (!auth || !workspace) return;
    try {
      const updated = await api.updateWorkspaceMaterial(
        auth.access_token,
        workspace.id,
        material.id,
        input,
      );
      setMaterials((current) => current.map((item) => item.id === updated.id ? updated : item));
      await refreshTopicSuggestions(auth.access_token, workspace.id);
    } catch (caught) {
      reportError(caught);
      throw caught;
    }
  }

  async function acceptTopicSuggestion(suggestion: TopicSuggestion) {
    if (!auth || !workspace || acceptingTopicSuggestionId !== null) return;
    const workspaceId = workspace.id;
    setAcceptingTopicSuggestionId(suggestion.id);
    setError("");
    try {
      const snapshot = await api.acceptWorkspaceTopicSuggestion(
        auth.access_token,
        workspaceId,
        suggestion.id,
      );
      if (workspaceRef.current?.id === workspaceId) applySnapshot(snapshot);
    } catch (caught) {
      if (workspaceRef.current?.id === workspaceId) reportError(caught);
    } finally {
      if (workspaceRef.current?.id === workspaceId) setAcceptingTopicSuggestionId(null);
    }
  }

  async function bulkDeleteMaterials(selected: MaterialRecord[]) {
    if (!auth || !workspace || selected.length === 0) return;
    try {
      const ids = selected.map((material) => material.id);
      await api.bulkDeleteWorkspaceMaterials(auth.access_token, workspace.id, ids);
      const removed = new Set(ids);
      setMaterials((current) => current.filter((item) => !removed.has(item.id)));
      await refreshTopicSuggestions(auth.access_token, workspace.id);
    } catch (caught) {
      reportError(caught);
      throw caught;
    }
  }

  async function askSessionCoach(message: string) {
    const pendingTurn = pendingCoachTurn(
      pendingTurnIdRef.current,
      message,
      () => crypto.randomUUID(),
    );
    pendingTurnIdRef.current = pendingTurn;
    return askCoach(message, {
      token: auth?.access_token,
      workspaceId: workspace?.id,
      learningMode,
      question,
      result,
      answer,
      errorMessage: t("error"),
      turnId: pendingTurn.id,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    });
  }

  async function refreshWorkspaceSnapshot() {
    if (!auth || !workspace) throw new Error(t("error"));
    try {
      const snapshot = await api.getWorkspaceSnapshot(auth.access_token, workspace.id);
      applySnapshot(snapshot);
    } catch (caught) {
      reportError(caught);
      throw caught;
    }
  }

  async function resyncWorkspace() {
    try {
      await refreshWorkspaceSnapshot();
      setSnapshotConflict(false);
      setError("");
    } catch {
      // refreshWorkspaceSnapshot already reports the localized failure.
    }
  }

  async function applyCoachAction(
    proposal: ExecutableActionProposal,
    options: { confirmed?: boolean } = {},
  ) {
    const storedDraft = question
      ? window.sessionStorage.getItem(`refineq.practice-draft:${workspace?.id}:${question.id}`)
      : null;
    return executeCoachAction(proposal, {
      appliedActionIds: appliedActionIdsRef.current,
      hasDraft: Boolean((storedDraft ?? answer).trim()),
      confirmed: options.confirmed,
      applyAdjust: (action) => getQuestion({
        requestId: action.action_id,
        topicId: action.topic_id,
        difficulty: action.difficulty,
        learningMode: action.learning_mode,
        replace: action.destructive,
      }),
      applyPlanUpdate: async (action) => {
        const target = plan?.sessions.find((session) => session.id === action.session_id);
        if (!target) {
          reportError(new Error(locale === "zh" ? "找不到要调整的计划场次。" : "The plan session is no longer available."));
          return false;
        }
        return updatePlanSession(target, {
          status: action.status ?? undefined,
          planned_at: action.planned_at ?? undefined,
        });
      },
      applySaveQuestion: async (action) => {
        const target = question?.id === action.question_id
          ? question
          : savedQuestions.find((item) => item.id === action.question_id);
        if (!target) {
          reportError(new Error(locale === "zh" ? "找不到要收藏的题目。" : "The question is no longer available."));
          return false;
        }
        return toggleSavedQuestion(target, action.saved);
      },
    });
  }

  function changeLearningMode(mode: LearningMode) {
    runGuardedPracticeAction(() => {
      setLearningMode(mode);
      if (question) return getQuestion({ learningMode: mode, replace: true }).then(() => undefined);
    });
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
    input: { status?: "planned" | "completed"; planned_at?: string; minutes?: number },
  ): Promise<boolean> {
    if (!auth || !workspace) return false;
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
      return true;
    } catch (caught) {
      reportError(caught);
      return false;
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

  function prepareSectionNavigation() {
    prepareRouteNavigation();
    if (window.matchMedia("(max-width: 640px)").matches) {
      window.sessionStorage.setItem(SECTION_FOCUS_KEY, "1");
    }
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
    if (workspace && progress) {
      saveWorkspaceSnapshot(window.sessionStorage, {
        workspace,
        progress,
        plan,
        evidence,
        materials,
        saved_questions: savedQuestions,
        active_question: question,
        last_answer: result,
      });
    }
    setWorkspace(null);
  }

  function logout() {
    clearWorkspaceSnapshots(window.sessionStorage);
    resetAuthentication();
    clearWorkspaceState();
    clearPracticeState();
    resetAgent();
    setWorkspaces([]);
    router.replace("/");
  }

  function returnHome() {
    prepareHomeNavigation();
    router.push("/");
  }

  function toggleLocale() {
    toggleLearningLocale(workspace?.id);
  }

  if (restoring) return <main className="loading-stage"><BrandMark size={44} /><span>{t("loading")}</span></main>;
  if (!auth) {
    return (
      <>
        {error && (
          <div className="error-banner auth-restore-error" data-testid="auth-restore-error" role="alert">
            <strong>{t("error")}</strong>
            <span>{error}</span>
          </div>
        )}
        <AuthPanel t={t} locale={locale} onAuthenticated={authenticated} />
      </>
    );
  }
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
          locale={locale}
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
          onLogout={logout}
          onToggleLocale={toggleLocale}
        />
      </>
    );
  }

  const masteryValues = progress ? Object.values(progress.mastery) : [];
  const averageMastery = masteryValues.reduce((sum, value) => sum + value, 0)
    / Math.max(1, masteryValues.length);
  const selectedTopic = insights?.topics.find((item) => item.topic_id === selectedTopicId);
  const nav: Array<{ id: LearningSection; icon: typeof BookOpen }> = [
    { id: "today", icon: BookOpen },
    { id: "path", icon: Route },
    { id: "materials", icon: Archive },
    { id: "calendar", icon: CalendarDays },
    { id: "progress", icon: ChartNoAxesColumnIncreasing },
  ];

  return (
    <main id="main-content" className="workspace-shell">
      <div className="workspace-sidebar">
        <AppSidebar
          locale={locale}
          active="workspace"
          workspaces={workspaces}
          currentWorkspaceId={workspace.id}
          isAdmin={auth.user.role === "admin"}
          contextLabel={t("workspaceSections")}
          contextNavigation={(
            <>
              <WorkspaceSwitcher
                locale={locale}
                current={workspace}
                workspaces={workspaces}
                currentProgress={Math.round(averageMastery * 100)}
                onSelect={(target) => openWorkspace(target)}
                onAllSpaces={returnHome}
              />
              <div className="workspace-nav">
                {nav.map(({ id, icon: Icon }) => (
                  <Link
                    key={id}
                    data-testid={`nav-${id}`}
                    className={section === id ? "active" : ""}
                    href={learningPath(workspace.id, id)}
                    onClick={prepareSectionNavigation}
                    aria-label={t(id)}
                    aria-current={section === id ? "page" : undefined}
                  >
                    <Icon size={19} />
                    <span>{t(id)}</span>
                  </Link>
                ))}
              </div>
            </>
          )}
          onToggleLocale={toggleLocale}
          onLogout={logout}
          onNavigate={prepareRouteNavigation}
          onHomeNavigate={prepareHomeNavigation}
        />
      </div>
      <section className="workspace-stage">
        <header className="mobile-section-context" data-testid="mobile-section-context">
          <div>
            <span>{workspace.title}</span>
            <h1 ref={sectionHeadingRef} tabIndex={-1} data-testid="mobile-section-title">{t(section)}</h1>
          </div>
          <nav className="mobile-context-shortcuts" aria-label={t("workspaceSections")}>
            {nav.map(({ id, icon: Icon }) => (
              <Link
                key={id}
                data-testid={`mobile-shortcut-${id}`}
                className={section === id ? "active" : ""}
                href={learningPath(workspace.id, id)}
                onClick={prepareSectionNavigation}
                aria-current={section === id ? "page" : undefined}
              >
                <Icon size={15} />
                <span>{t(id)}</span>
              </Link>
            ))}
          </nav>
        </header>
        {section !== "today" && section !== "calendar" && (
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
          <div className="workspace-routing-summary" data-testid="workspace-routing-summary">
            <Sparkles size={16} />
            <span>{workspace.routing_summary}</span>
          </div>
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
          {error && <div className="error-banner" role="alert" aria-live="polite"><strong>{t("error")}</strong><span>{error}</span>{snapshotConflict && <button type="button" data-testid="resync-workspace" onClick={() => void resyncWorkspace()}>{locale === "zh" ? "重新同步" : "Resync"}</button>}<button aria-label={t("routingDismiss")} onClick={() => { setError(""); setSnapshotConflict(false); }}>×</button></div>}
          {section === "today" && progress?.diagnostic_count === 0 && (
            <InitialDiagnostic
              locale={locale}
              topics={progress.topics}
              busy={practiceBusy}
              onSubmit={submitInitialDiagnostic}
            />
          )}
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
              masteryBefore={masteryBefore}
              busy={practiceBusy}
              learningMode={learningMode}
              savedQuestions={savedQuestions}
              agentToken={auth.access_token}
              modelConfigured={modelConfigured}
              onModelUnavailable={() => setModelConfigured(false)}
              onRecheckModel={recheckModelCapability}
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
              onStartTask={() => { void getQuestion({ learningMode }); }}
              onSubmit={submitAnswer}
              onNextTask={() => { runGuardedPracticeAction(() => getQuestion({ learningMode, replace: true }).then(() => undefined)); }}
              onRetryTask={() => { if (question) void practiceSavedQuestion(question); }}
              onViewProgress={() => router.push(learningPath(workspace.id, "progress"))}
              onToggleSaved={(target, saved) => { void toggleSavedQuestion(target, saved); }}
              onPracticeSaved={(saved) => { void practiceSavedQuestion(saved); }}
              onOpenLibrary={() => router.push(learningPath(workspace.id, "materials"))}
              onAskCoach={askSessionCoach}
              onApplyCoachAction={applyCoachAction}
              onCoachTurnHandled={() => { pendingTurnIdRef.current = null; }}
            />
          )}
          {section === "today" && (insightsLoading || (insights?.due_reviews.length ?? 0) > 0) && (
            <ReviewQueue
              locale={locale}
              reviews={insights?.due_reviews ?? []}
              busy={practiceBusy}
              loading={insightsLoading}
              onStartReview={startReview}
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
                onUpdateSession={(session, input) => { void updatePlanSession(session, input); }}
                onStartSession={startPlanSession}
                practiceBusy={practiceBusy}
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
              onUpdate={updateMaterial}
              onBulkDelete={bulkDeleteMaterials}
              topicSuggestions={topicSuggestions}
              acceptingTopicSuggestionId={acceptingTopicSuggestionId}
              onAcceptTopicSuggestion={acceptTopicSuggestion}
            />
          )}
          {section === "calendar" && (
            <ScheduleCalendar
              plan={plan}
              locale={locale}
              topicLabels={progress?.topics}
              busySessionId={busySessionId}
              onUpdateSession={updatePlanSession}
            />
          )}
          {section === "progress" && (
            <div className="learning-progress-view" data-testid="learning-progress-view">
              <div className="page-section-heading">
                <span className="kicker">PROGRESS / CAPABILITY</span>
                <h2>{t("progress")}</h2>
                <p>{locale === "zh" ? "把能力变化、实践反馈和下一步安排放在一起。" : "Capability change, task feedback, and next actions in one place."}</p>
              </div>
              {insights && progress && (
                <LearningReport locale={locale} progress={progress} insights={insights} />
              )}
              <ReviewQueue
                locale={locale}
                reviews={insights?.due_reviews ?? []}
                busy={practiceBusy}
                loading={insightsLoading}
                onStartReview={startReview}
              />
              <ProgressInsights
                progress={progress}
                t={t}
                locale={locale}
                onPracticeTopic={practiceTopic}
                topicLabels={progress?.topics}
                insights={insights}
                onSelectTopic={setSelectedTopicId}
                busy={practiceBusy}
                loading={insightsLoading}
              />
              {selectedTopic && (
                <ProgressTopicDetail
                  locale={locale}
                  topic={selectedTopic}
                  history={insights?.mastery_history ?? []}
                  onClose={() => setSelectedTopicId(null)}
                />
              )}
              <EvidenceLedger
                evidence={evidence}
                locale={locale}
                t={t}
                attempts={insights?.attempts}
                onRetryAttempt={retryAttempt}
                onUpdateFeedback={updateAttemptFeedback}
              />
            </div>
          )}
        </section>
      </section>
      <ConfirmDialog
        open={draftConfirmOpen}
        title={locale === "zh" ? "放弃未提交的作答？" : "Discard the unsaved answer?"}
        description={locale === "zh" ? "继续会清空当前草稿并切换题目；取消会保留现有内容。" : "Continuing clears the current draft and changes the task. Cancel keeps your answer."}
        confirmLabel={locale === "zh" ? "放弃并继续" : "Discard and continue"}
        cancelLabel={locale === "zh" ? "保留草稿" : "Keep draft"}
        tone="danger"
        onConfirm={confirmDraftReplacement}
        onCancel={cancelDraftReplacement}
      />
    </main>
  );
}
