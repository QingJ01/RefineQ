"use client";

import {
  Archive,
  BookOpen,
  CalendarDays,
  ChartNoAxesColumnIncreasing,
  List,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { MouseEvent, useCallback, useEffect, useRef, useState } from "react";

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
import { NextActionCard } from "@/components/next-action-card";
import { PlanSettings } from "@/components/plan-settings";
import { PlanTimeline } from "@/components/plan-timeline";
import { ScheduleCalendar } from "@/components/schedule-calendar";
import { ProgressInsights } from "@/components/progress-insights";
import { ProgressTopicDetail } from "@/components/progress-topic-detail";
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
import { describePlanCapacityError, localizeApiError } from "@/lib/error-messages";
import {
  browserHistoryNavigation,
  browserHistoryTraversalTarget,
  installHistoryNavigationGuard,
} from "@/lib/history-navigation-guard";
import { learningPath, type LearningSection } from "@/lib/learning-routes";
import { learningModeForActivity } from "@/lib/learning-session";
import { loadModelCapability, refreshModelCapability } from "@/lib/model-capability";
import { loadNextQuestion } from "@/lib/practice-flow";
import {
  guardPracticeNavigation,
  hasUnsavedPracticeDraft,
  navigationBlockReason,
  type NavigationBlockReason,
  type PracticeNavigationAction,
} from "@/lib/practice-navigation";
import { isAbortError } from "@/lib/upload-flow";
import {
  installSessionHandoff,
  loadLearningSession,
  requestSessionHandoff,
  saveLearningSession,
} from "@/lib/session";
import {
  clearUserScopedSessionState,
  clearWorkspaceRouteNotice,
  readWorkspaceRouteNotice,
  writeWorkspaceRouteNotice,
} from "@/lib/client-session-state";
import type {
  AttemptFeedbackInput,
  AttemptInsight,
  ExecutableActionProposal,
  AuthResponse,
  DiagnosticResultInput,
  HomeActionReceipt,
  HomeDispatchResult,
  HomeWorkspaceProposal,
  LearningMode,
  LearningWorkspace,
  MaterialAnalysis,
  MaterialRecord,
  MaterialUpdateInput,
  PlanUpdateInput,
  PracticeQuestion,
  PracticeRequest,
  SearchSource,
  StudySession,
  TargetedPlanInput,
  TopicSuggestion,
} from "@/lib/types";
import { resolveRequestedWorkspace } from "@/lib/workspace-route-state";
import { chooseWorkspacePrimaryAction } from "@/lib/workspace-primary-action";
import {
  clearWorkspaceSnapshots,
  consumeWorkspaceSnapshot,
  removeWorkspaceSnapshot,
  saveWorkspaceSnapshot,
  type WorkspaceSnapshotHandoff,
} from "@/lib/workspace-snapshot-handoff";

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
    nextAction,
    plan,
    previousWorkspaceId,
    progress,
    route,
    savedQuestions,
    selectedTopicId,
    setEvidence,
    setInsights,
    setMaterials,
    setNextAction,
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
    beginQuestionLoad,
    capturePracticeGeneration,
    clearPracticeState,
    hydratePractice,
    isPracticeGenerationCurrent,
    isQuestionLoadCurrent,
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
  const [focusedPlanSessionId, setFocusedPlanSessionId] = useState<string | null>(null);
  const [planView, setPlanView] = useState<"list" | "calendar">("list");
  const [planSettingsBusy, setPlanSettingsBusy] = useState(false);
  const [targetedPlanBusy, setTargetedPlanBusy] = useState(false);
  const [insightsLoading, setInsightsLoading] = useState(false);
  const [snapshotConflict, setSnapshotConflict] = useState(false);
  const [masteryBefore, setMasteryBefore] = useState<number | null>(null);
  const [acceptingTopicSuggestionId, setAcceptingTopicSuggestionId] = useState<string | null>(null);
  const sectionHeadingRef = useRef<HTMLHeadingElement>(null);
  const pendingTurnIdRef = useRef<PendingCoachTurn | null>(null);
  const appliedActionIdsRef = useRef(new Set<string>());
  const activeCoachWorkspaceIdRef = useRef<string | null>(null);
  const insightsPrefetchedForRef = useRef<string | null>(null);
  const pendingPracticeActionRef = useRef<PracticeNavigationAction | null>(null);
  const [draftConfirmOpen, setDraftConfirmOpen] = useState(false);
  const [navigationConfirmReason, setNavigationConfirmReason] = useState<NavigationBlockReason | null>(null);
  const [uploadInProgress, setUploadInProgress] = useState(false);
  const [libraryMaterials, setLibraryMaterials] = useState<MaterialRecord[]>([]);
  const [linkingLibraryMaterialId, setLinkingLibraryMaterialId] = useState<string | null>(null);
  const pendingRouteActionRef = useRef<PracticeNavigationAction | null>(null);
  const persistWorkspaceHandoffRef = useRef<() => void>(() => undefined);
  const navigationBlockRef = useRef<() => NavigationBlockReason | null>(() => null);
  const historyBlockRef = useRef<(
    reason: NavigationBlockReason,
    resume: PracticeNavigationAction,
  ) => void>(() => undefined);
  const latestHomeRequestIdRef = useRef<string | null>(null);
  const workspaceOpenGenerationRef = useRef(0);
  const targetedPlanGenerationRef = useRef(0);
  const targetedPlanBusyRef = useRef(false);
  const authRef = useRef(auth);
  const workspaceRef = useRef(workspace);
  const localeRef = useRef(locale);
  const sectionRef = useRef(section);
  authRef.current = auth;
  workspaceRef.current = workspace;
  localeRef.current = locale;
  sectionRef.current = section;
  persistWorkspaceHandoffRef.current = persistWorkspaceHandoff;
  navigationBlockRef.current = currentNavigationBlock;
  historyBlockRef.current = (reason, resume) => {
    pendingRouteActionRef.current = resume;
    setNavigationConfirmReason(reason);
  };

  const applySnapshot = useCallback((snapshot: WorkspaceSnapshotHandoff) => {
    if (activeCoachWorkspaceIdRef.current !== snapshot.workspace.id) {
      pendingTurnIdRef.current = null;
      appliedActionIdsRef.current.clear();
      resetAgent();
    }
    activeCoachWorkspaceIdRef.current = snapshot.workspace.id;
    applyWorkspaceSnapshot(snapshot);
    hydratePractice(snapshot);
    if (snapshot.client_state) {
      setMasteryBefore(snapshot.client_state.masteryBefore);
      setLearningMode(snapshot.client_state.learningMode);
    } else {
      setMasteryBefore(null);
    }
  }, [applyWorkspaceSnapshot, hydratePractice, resetAgent, setLearningMode]);

  const recheckModelCapability = useCallback(async (): Promise<boolean | null> => {
    const token = auth?.access_token;
    if (!token) return null;
    return refreshModelCapability(
      () => api.getModelSettings(token),
      setModelConfigured,
    );
  }, [auth?.access_token, setModelConfigured]);

  useEffect(() => installSessionHandoff(window.sessionStorage), []);

  useEffect(() => {
    if (
      !auth?.access_token
      || !workspace?.id
      || !result?.attempt_id
      || result.grounding !== "material"
    ) return;
    void api.markWorkspaceGradeShown(
      auth.access_token,
      workspace.id,
      result.attempt_id,
    ).catch(() => undefined);
  }, [auth?.access_token, result?.attempt_id, result?.grounding, workspace?.id]);

  useEffect(() => installHistoryNavigationGuard(
    browserHistoryNavigation(window),
    () => navigationBlockRef.current(),
    (reason, resume) => historyBlockRef.current(reason, resume),
    browserHistoryTraversalTarget(window),
  ), []);

  useEffect(() => () => {
    const activeToken = authRef.current?.access_token;
    const savedSession = loadLearningSession(window.sessionStorage);
    if (!activeToken || savedSession?.token !== activeToken) return;
    persistWorkspaceHandoffRef.current();
  }, []);

  useEffect(() => {
    void Promise.resolve().then(() => {
      const requestedSessionId = new URLSearchParams(window.location.search).get("session");
      setFocusedPlanSessionId(
        section === "today" || section === "plan"
          ? requestedSessionId
          : null,
      );
      if (section === "plan" && /\/calendar\/?$/.test(window.location.pathname)) {
        setPlanView("calendar");
      }
    });
  }, [initialWorkspaceId, section]);

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

  function currentNavigationBlock(): NavigationBlockReason | null {
    return navigationBlockReason({
      uploadActive: uploadInProgress,
      unsavedDraft: hasUnsavedPracticeDraft(answer, Boolean(question), Boolean(result)),
    });
  }

  function deferRouteAction(action: PracticeNavigationAction): boolean {
    const reason = currentNavigationBlock();
    if (!reason) return false;
    pendingRouteActionRef.current = action;
    setNavigationConfirmReason(reason);
    return true;
  }

  function confirmRouteNavigation() {
    const pending = pendingRouteActionRef.current;
    pendingRouteActionRef.current = null;
    setNavigationConfirmReason(null);
    if (pending) void pending();
  }

  function cancelRouteNavigation() {
    pendingRouteActionRef.current = null;
    setNavigationConfirmReason(null);
  }

  useEffect(() => {
    const token = auth?.access_token;
    const workspaceId = workspace?.id;
    if ((section !== "progress" && section !== "today") || !token || !workspaceId) return;
    if (insightsPrefetchedForRef.current === workspaceId) {
      insightsPrefetchedForRef.current = null;
      return;
    }
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
        if (active) setError(localizeApiError(caught, localeRef.current));
      })
      .finally(() => {
        if (active) setInsightsLoading(false);
      });
    return () => { active = false; };
  }, [auth?.access_token, section, setError, setInsights, workspace?.id]);

  useEffect(() => {
    if (!auth || !workspace || section !== "materials") return;
    let active = true;
    api.listLibraryMaterials(auth.access_token)
      .then((records) => { if (active) setLibraryMaterials(records); })
      .catch((caught) => { if (active) reportError(caught); });
    return () => { active = false; };
  }, [auth, reportError, section, workspace]);

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
    clearWorkspaceRouteNotice(window.sessionStorage);
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
          const savedSession = loadLearningSession(window.sessionStorage);
          if (
            workspaceRef.current
            && savedSession?.token === currentAuth.access_token
          ) persistWorkspaceHandoffRef.current();
          setWorkspace(null);
          setHomeBusy(false);
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
          const cachedSnapshot = consumeWorkspaceSnapshot(window.sessionStorage, initialWorkspaceId);
          const [snapshot, restoredInsights] = await Promise.all([
            cachedSnapshot
              ? Promise.resolve(cachedSnapshot)
              : api.getWorkspaceSnapshot(currentAuth.access_token, initialWorkspaceId),
            sectionRef.current === "today" || sectionRef.current === "progress"
              ? api.getWorkspaceInsights(currentAuth.access_token, initialWorkspaceId).catch(() => null)
              : Promise.resolve(null),
          ]);
          if (!active) return;
          applySnapshot(snapshot);
          if (restoredInsights) {
            insightsPrefetchedForRef.current = initialWorkspaceId;
            setInsights(restoredInsights);
          }
          saveLearningSession(window.sessionStorage, {
            token: currentAuth.access_token,
            workspaceId: initialWorkspaceId,
            locale: localeRef.current,
          });
        } catch (caught) {
          if (!active) return;
          if (caught instanceof ApiError && (caught.status === 401 || caught.status === 403)) {
            clearWorkspaceSnapshots(window.sessionStorage);
            authRef.current = null;
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
        const [user, configured, recent] = await Promise.all([
          api.getProfile(saved.token),
          loadModelCapability(() => api.getModelSettings(saved.token)),
          api.listWorkspaces(saved.token),
        ]);
        const restoredAuth: AuthResponse = {
          access_token: saved.token,
          token_type: "bearer",
          user,
        };
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
          const cachedSnapshot = consumeWorkspaceSnapshot(window.sessionStorage, selected.id);
          const [snapshot, restoredInsights] = await Promise.all([
            cachedSnapshot
              ? Promise.resolve(cachedSnapshot)
              : api.getWorkspaceSnapshot(saved.token, selected.id),
            sectionRef.current === "today" || sectionRef.current === "progress"
              ? api.getWorkspaceInsights(saved.token, selected.id).catch(() => null)
              : Promise.resolve(null),
          ]);
          if (!active) return;
          applySnapshot(snapshot);
          if (restoredInsights) {
            insightsPrefetchedForRef.current = selected.id;
            setInsights(restoredInsights);
          }
          saveLearningSession(window.sessionStorage, {
            token: saved.token,
            workspaceId: selected.id,
            locale: saved.locale ?? "zh",
          });
          const notice = readWorkspaceRouteNotice(window.sessionStorage);
          if (notice?.route.workspace.id === selected.id) {
            setRoute(notice.route);
            setPreviousWorkspaceId(notice.previousWorkspaceId);
          }
        }
      } catch (caught) {
        if (!active) return;
        if (caught instanceof ApiError && (caught.status === 401 || caught.status === 403)) {
          clearWorkspaceSnapshots(window.sessionStorage);
          clearUserScopedSessionState(window.sessionStorage);
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
    setInsights,
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
    authRef.current = response;
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
    expectedHomeRequestId?: string,
  ) {
    if (!token) return;
    if (expectedHomeRequestId === undefined) latestHomeRequestIdRef.current = null;
    const openGeneration = workspaceOpenGenerationRef.current + 1;
    workspaceOpenGenerationRef.current = openGeneration;
    removeWorkspaceSnapshot(window.sessionStorage, target.id);
    setHomeBusy(true);
    setError("");
    try {
      const snapshot = await api.getWorkspaceSnapshot(token, target.id);
      if (
        authRef.current?.access_token !== token
        || workspaceOpenGenerationRef.current !== openGeneration
        || (
          expectedHomeRequestId !== undefined
          && latestHomeRequestIdRef.current !== expectedHomeRequestId
        )
      ) return;
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
      if (
        authRef.current?.access_token !== token
        || workspaceOpenGenerationRef.current !== openGeneration
        || (
          expectedHomeRequestId !== undefined
          && latestHomeRequestIdRef.current !== expectedHomeRequestId
        )
      ) return;
      reportError(caught);
    } finally {
      if (
        authRef.current?.access_token === token
        && workspaceOpenGenerationRef.current === openGeneration
      ) setHomeBusy(false);
    }
  }

  async function dispatchHome(
    input: {
      request_id: string;
      text: string;
      timezone_offset_minutes: number;
      clarification?: { continuation_token: string; option_id: string } | null;
    },
    signal: AbortSignal,
  ): Promise<HomeDispatchResult | null> {
    const token = auth?.access_token;
    if (!token) return null;
    latestHomeRequestIdRef.current = input.request_id;
    const result = await api.dispatchHome(token, input, signal);
    if (signal.aborted || authRef.current?.access_token !== token) return null;
    if (result.kind !== "open_workspace" || !result.workspace_target.auto_navigate) {
      return result;
    }
    const recent = await api.listWorkspaces(token, true);
    if (signal.aborted || authRef.current?.access_token !== token) return null;
    const target = recent.find((item) => item.id === result.workspace_target.workspace_id);
    if (!target) {
      throw new Error(localeRef.current === "zh"
        ? "目标学习空间已不存在，请重新选择。"
        : "That learning space no longer exists. Choose again.");
    }
    const saved = loadLearningSession(window.sessionStorage);
    const previousId = workspaceRef.current?.id ?? saved?.workspaceId ?? null;
    const routeForNotice = {
      action: result.workspace_target.route_action,
      confidence: result.confidence,
      reason: result.reason,
      workspace: target,
      requestId: result.request_id,
      undoToken: result.workspace_target.undo_token ?? undefined,
      undoExpiresAt: result.workspace_target.undo_expires_at ?? undefined,
    };
    setRoute(routeForNotice);
    setPreviousWorkspaceId(previousId === target.id ? null : previousId);
    setWorkspaces(recent);
    writeWorkspaceRouteNotice(window.sessionStorage, {
      route: routeForNotice,
      previousWorkspaceId: previousId === target.id ? null : previousId,
    });
    await openWorkspace(target, token, "today", "push", input.request_id);
    return null;
  }

  async function reviseHomeResult(
    result: HomeDispatchResult,
    proposalChanges: {
      title?: string;
      goal?: string;
      exam_at?: string;
      daily_minutes?: number;
    },
  ): Promise<HomeWorkspaceProposal> {
    const token = auth?.access_token;
    if (!token) throw new Error("Authentication required");
    if (latestHomeRequestIdRef.current !== result.request_id) {
      throw new Error("This proposal is no longer the active home request");
    }
    if (result.kind !== "propose_workspace") {
      throw new Error("This result has no revisable workspace proposal");
    }
    const proposal = await api.reviseHomeWorkspaceProposal(token, {
      request_id: result.request_id,
      confirmation_token: result.workspace_proposal.confirmation_token,
      original_proposal: result.workspace_proposal,
      changes: proposalChanges,
    });
    if (
      authRef.current?.access_token !== token
      || latestHomeRequestIdRef.current !== result.request_id
    ) {
      throw new Error("User session changed before proposal review");
    }
    return proposal;
  }

  async function confirmHomeResult(
    result: HomeDispatchResult,
  ): Promise<HomeActionReceipt> {
    const token = auth?.access_token;
    if (!token) throw new Error("Authentication required");
    if (latestHomeRequestIdRef.current !== result.request_id) {
      throw new Error("This proposal is no longer the active home request");
    }
    const proposal = result.kind === "workspace_action"
      ? result.action_proposal
      : result.kind === "propose_workspace"
        ? result.workspace_proposal
        : null;
    if (!proposal) throw new Error("This result has no confirmable action");
    const receipt = await api.confirmHomeAction(token, {
      request_id: result.request_id,
      confirmation_token: proposal.confirmation_token,
      proposal: proposal as unknown as Record<string, unknown>,
      idempotency_key: proposal.idempotency_key,
    });
    if (
      authRef.current?.access_token !== token
      || latestHomeRequestIdRef.current !== result.request_id
    ) return receipt;
    if (receipt.route?.auto_navigate) {
      const recent = await api.listWorkspaces(token);
      if (
        authRef.current?.access_token !== token
        || latestHomeRequestIdRef.current !== result.request_id
      ) return receipt;
      const target = recent.find((item) => item.id === receipt.workspace_id);
      if (target) {
        const routeForNotice = {
          action: receipt.route.route_action,
          confidence: 1,
          reason: receipt.route.reason,
          workspace: target,
          requestId: receipt.request_id,
          undoToken: receipt.route.undo_token ?? undefined,
          undoExpiresAt: receipt.route.undo_expires_at ?? undefined,
        };
        setWorkspaces(recent);
        setRoute(routeForNotice);
        writeWorkspaceRouteNotice(window.sessionStorage, {
          route: routeForNotice,
          previousWorkspaceId: null,
        });
        await openWorkspace(target, token, "today", "push", result.request_id);
      }
    }
    return receipt;
  }

  async function cancelHomeResult(result: HomeDispatchResult): Promise<void> {
    const token = auth?.access_token;
    if (!token) return;
    await api.cancelHomeAction(token, result.request_id);
  }

  async function getQuestion(request: PracticeRequest = {}): Promise<boolean> {
    if (!auth || !workspace) return false;
    const generation = capturePracticeGeneration();
    const loadSeq = beginQuestionLoad();
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
        () => isPracticeGenerationCurrent(generation) && isQuestionLoadCurrent(loadSeq),
      );
      return isPracticeGenerationCurrent(generation) && isQuestionLoadCurrent(loadSeq);
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
      setNextAction(snapshot.next_action);
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
          {
            expectedStateVersion: question.state_version,
            promptHash: question.prompt_hash,
          },
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
      setNextAction(snapshot.next_action);
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
    const targetWorkspaceId = workspace.id;
    setError("");
    try {
      const uploaded = await api.uploadWorkspaceMaterials(
        auth.access_token,
        targetWorkspaceId,
        files,
        signal,
      );
      if (workspaceRef.current?.id === targetWorkspaceId) {
        setMaterials((current) => {
          const byId = new Map(current.map((item) => [item.id, item]));
          uploaded.forEach((item) => byId.set(item.id, item));
          return Array.from(byId.values());
        });
      }
      await Promise.all([
        refreshTopicSuggestions(auth.access_token, targetWorkspaceId),
        refreshNextAction(auth.access_token, targetWorkspaceId),
      ]);
      return uploaded;
    } catch (caught) {
      if (isAbortError(caught)) return [];
      if (workspaceRef.current?.id === targetWorkspaceId) reportError(caught);
      throw caught;
    }
  }

  async function linkLibraryMaterial(material: MaterialRecord): Promise<void> {
    if (!auth || !workspace || !material.project_id) return;
    setLinkingLibraryMaterialId(material.id);
    setError("");
    try {
      const linked = await api.attachLibraryMaterial(
        auth.access_token,
        material.project_id,
        material.id,
        workspace.id,
      );
      setMaterials((current) => current.some((item) => item.id === linked.id)
        ? current
        : [linked, ...current]);
    } catch (caught) {
      reportError(caught);
      throw caught;
    } finally {
      setLinkingLibraryMaterialId(null);
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

  async function refreshNextAction(token: string, workspaceId: string) {
    try {
      const refreshed = await api.getWorkspaceNextAction(token, workspaceId);
      if (workspaceRef.current?.id === workspaceId) setNextAction(refreshed);
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

  async function analyzeMaterial(material: MaterialRecord): Promise<MaterialAnalysis> {
    if (!auth || !workspace) throw new Error(t("error"));
    const requestedAt = new Date().toISOString();
    try {
      return await api.analyzeWorkspaceMaterial(
        auth.access_token,
        workspace.id,
        material.id,
      );
    } catch (analysisError) {
      try {
        return await api.waitForWorkspaceMaterialAnalysis(
          auth.access_token,
          workspace.id,
          material.id,
          requestedAt,
        );
      } catch {
        reportError(analysisError);
        throw analysisError;
      }
    }
  }

  async function createTargetedPlan(input: TargetedPlanInput) {
    if (!auth || !workspace || targetedPlanBusyRef.current) return;
    const targetWorkspaceId = workspace.id;
    const targetToken = auth.access_token;
    const generation = ++targetedPlanGenerationRef.current;
    targetedPlanBusyRef.current = true;
    setTargetedPlanBusy(true);
    setError("");
    // One stable idempotency key for this whole user action. The endpoint is
    // synchronous and commits even if the request times out, so a retry must
    // reuse this exact key to replay the committed plan instead of forging a
    // fresh-key plan that overwrites the one the learner never got to see.
    const request: TargetedPlanInput = {
      ...input,
      idempotency_key: input.idempotency_key ?? crypto.randomUUID().replaceAll("-", ""),
    };
    try {
      const created = await (async () => {
        try {
          return await api.createTargetedPlan(targetToken, targetWorkspaceId, request);
        } catch (caught) {
          // A client-side timeout (408) is not proof the server failed to commit.
          // Retry once with the SAME key so the committed plan is reconciled back
          // rather than surfaced as a terminal error that invites an overwrite.
          if (
            !(caught instanceof ApiError && caught.status === 408)
            || targetedPlanGenerationRef.current !== generation
            || workspaceRef.current?.id !== targetWorkspaceId
            || authRef.current?.access_token !== targetToken
          ) throw caught;
          return api.createTargetedPlan(targetToken, targetWorkspaceId, request);
        }
      })();
      if (
        targetedPlanGenerationRef.current !== generation
        || workspaceRef.current?.id !== targetWorkspaceId
        || authRef.current?.access_token !== targetToken
      ) return;
      const snapshot = await api.getWorkspaceSnapshot(targetToken, targetWorkspaceId);
      if (
        targetedPlanGenerationRef.current !== generation
        || workspaceRef.current?.id !== targetWorkspaceId
        || authRef.current?.access_token !== targetToken
      ) return;
      setPlan(created);
      setProgress(snapshot.progress);
      setEvidence(snapshot.evidence);
      setNextAction(snapshot.next_action);
      setPlanView("calendar");
      router.push(`/learn/${encodeURIComponent(targetWorkspaceId)}/calendar`);
    } catch (caught) {
      if (
        targetedPlanGenerationRef.current === generation
        && workspaceRef.current?.id === targetWorkspaceId
      ) reportError(caught);
      throw caught;
    } finally {
      if (targetedPlanGenerationRef.current === generation) {
        targetedPlanBusyRef.current = false;
        setTargetedPlanBusy(false);
      }
    }
  }

  async function addCalendarSession(input: { topic_name: string; planned_at: string; minutes: number; activity: string }) {
    if (!auth || !workspace) return false;
    await api.addWorkspacePlanSession(auth.access_token, workspace.id, input);
    await refreshWorkspaceSnapshot();
    return true;
  }

  async function clearCalendarPlan() {
    if (!auth || !workspace) return false;
    await api.clearWorkspacePlan(auth.access_token, workspace.id);
    setPlan(null);
    await refreshWorkspaceSnapshot();
    return true;
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
      await Promise.all([
        refreshTopicSuggestions(auth.access_token, workspace.id),
        refreshNextAction(auth.access_token, workspace.id),
      ]);
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
      await Promise.all([
        refreshTopicSuggestions(auth.access_token, workspace.id),
        refreshNextAction(auth.access_token, workspace.id),
      ]);
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
      await refreshNextAction(auth.access_token, workspace.id);
      return true;
    } catch (caught) {
      // A daily-budget conflict gets a specific message (with the next open day)
      // instead of the generic error banner.
      setError(describePlanCapacityError(caught, locale));
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
      if (input.regenerate) setPlanView("calendar");
      await refreshNextAction(auth.access_token, workspace.id);
    } catch (caught) {
      reportError(caught);
      throw caught;
    } finally {
      setPlanSettingsBusy(false);
    }
  }

  async function undoWorkspaceRoute() {
    if (!route) return;
    if (route.action === "created") {
      const token = auth?.access_token;
      if (!token || !route.requestId || !route.undoToken) {
        setError(locale === "zh"
          ? "撤销凭证已失效；你仍可在首页手动删除这个学习空间。"
          : "The undo proof expired. You can still delete this learning space from home.");
        return;
      }
      setHomeBusy(true);
      setError("");
      try {
        await api.undoHomeCreation(token, {
          request_id: route.requestId,
          workspace_id: route.workspace.id,
          undo_token: route.undoToken,
        });
        if (authRef.current?.access_token !== token) return;
        const previous = workspaces.find((item) => item.id === previousWorkspaceId);
        clearWorkspaceRouteNotice(window.sessionStorage);
        removeWorkspaceSnapshot(window.sessionStorage, route.workspace.id);
        setRoute(null);
        setPreviousWorkspaceId(null);
        setWorkspaces((current) => current.filter((item) => item.id !== route.workspace.id));
        workspaceRef.current = null;
        clearWorkspaceState();
        clearPracticeState();
        resetAgent();
        if (previous) {
          await openWorkspace(previous, token);
        } else {
          saveLearningSession(window.sessionStorage, { token, locale });
          router.push("/");
        }
      } catch (caught) {
        if (authRef.current?.access_token === token) reportError(caught);
      } finally {
        if (authRef.current?.access_token === token) setHomeBusy(false);
      }
      return;
    }
    clearWorkspaceRouteNotice(window.sessionStorage);
    setRoute(null);
    const previous = workspaces.find((item) => item.id === previousWorkspaceId);
    setPreviousWorkspaceId(null);
    if (previous) await openWorkspace(previous);
    else returnHome();
  }

  function dismissWorkspaceRoute() {
    clearWorkspaceRouteNotice(window.sessionStorage);
    setRoute(null);
    setPreviousWorkspaceId(null);
  }

  function persistWorkspaceHandoff() {
    if (auth) {
      saveLearningSession(window.sessionStorage, {
        token: auth.access_token,
        workspaceId: workspace?.id,
        locale,
      });
    }
    if (workspace && progress && nextAction) {
      saveWorkspaceSnapshot(window.sessionStorage, {
        workspace,
        progress,
        plan,
        evidence,
        materials,
        saved_questions: savedQuestions,
        active_question: question,
        last_answer: result,
        topic_suggestions: topicSuggestions,
        next_action: nextAction,
        client_state: {
          learningMode,
          masteryBefore,
        },
      });
    }
  }

  function commitRouteNavigation() {
    clearWorkspaceRouteNotice(window.sessionStorage);
    setRoute(null);
    setPreviousWorkspaceId(null);
    persistWorkspaceHandoff();
  }

  function commitSectionNavigation() {
    clearWorkspaceRouteNotice(window.sessionStorage);
    setRoute(null);
    setPreviousWorkspaceId(null);
    if (window.matchMedia("(max-width: 640px)").matches) {
      window.sessionStorage.setItem(SECTION_FOCUS_KEY, "1");
    }
  }

  function commitHomeNavigation() {
    setHomeBusy(true);
    commitRouteNavigation();
    setWorkspace(null);
  }

  function prepareRouteNavigation(event: MouseEvent<HTMLAnchorElement>) {
    const href = event.currentTarget.getAttribute("href") ?? "/";
    if (deferRouteAction(() => {
      commitRouteNavigation();
      router.push(href);
    })) {
      event.preventDefault();
      return;
    }
    commitRouteNavigation();
  }

  function prepareSectionNavigation(event: MouseEvent<HTMLAnchorElement>) {
    const href = event.currentTarget.getAttribute("href") ?? "/";
    if (deferRouteAction(() => {
      commitSectionNavigation();
      router.push(href);
    })) {
      event.preventDefault();
      return;
    }
    commitSectionNavigation();
  }

  function prepareHomeNavigation(event: MouseEvent<HTMLAnchorElement>) {
    if (deferRouteAction(() => {
      commitHomeNavigation();
      router.push("/");
    })) {
      event.preventDefault();
      return;
    }
    commitHomeNavigation();
  }

  function logout() {
    api.clearReadCache(auth?.access_token);
    clearUserScopedSessionState(window.sessionStorage);
    authRef.current = null;
    latestHomeRequestIdRef.current = null;
    workspaceOpenGenerationRef.current += 1;
    setHomeBusy(false);
    resetAuthentication();
    clearWorkspaceState();
    clearPracticeState();
    resetAgent();
    setWorkspaces([]);
    router.replace("/");
  }

  function returnHome() {
    const action = () => {
      commitHomeNavigation();
      router.push("/");
    };
    if (!deferRouteAction(action)) action();
  }

  function navigateWithinWorkspace(href: string) {
    const action = () => {
      commitSectionNavigation();
      router.push(href);
    };
    if (!deferRouteAction(action)) action();
  }

  function navigateOutsideWorkspace(href: string) {
    const action = () => {
      commitRouteNavigation();
      router.push(href);
    };
    if (!deferRouteAction(action)) action();
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
            onDispatch={dispatchHome}
            onRevise={reviseHomeResult}
            onConfirm={confirmHomeResult}
            onCancel={cancelHomeResult}
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
  const primaryAction = progress ? chooseWorkspacePrimaryAction({
    diagnosticCount: progress.diagnostic_count,
    attemptCount: progress.attempt_count,
    nextActionType: nextAction?.action_type ?? null,
  }) : "none";
  const nav: Array<{ id: LearningSection; icon: typeof BookOpen }> = [
    { id: "today", icon: BookOpen },
    { id: "plan", icon: CalendarDays },
    { id: "materials", icon: Archive },
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
                onSelect={(target) => {
                  const action = () => openWorkspace(target);
                  if (!deferRouteAction(action)) void action();
                }}
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
          onDeleteWorkspace={deleteLearningWorkspace}
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
        {section !== "today" && (
          <header className="workspace-header">
            <div>
              <span className="kicker">{t("workspaceEyebrow")}</span>
              <h1>{workspace.title}</h1>
              <p>{plan?.goal ?? progress?.goal ?? workspace.goal}</p>
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
          {!route && (
            <div className="workspace-routing-summary" data-testid="workspace-routing-summary">
              <Sparkles size={16} />
              <span>{workspace.routing_summary}</span>
            </div>
          )}
          {route && (
            <div className="workspace-route-notice" data-testid="workspace-route-notice" role="status">
              <Sparkles size={18} />
              <div>
                <strong>{t(route.action === "created" ? "routingCreated" : route.action === "switched" ? "routingSwitched" : "routingReused")}</strong>
                <span>{route.reason}</span>
              </div>
              <button type="button" onClick={undoWorkspaceRoute}>{t("routingUndo")}</button>
              <button type="button" aria-label={t("routingDismiss")} onClick={dismissWorkspaceRoute}>×</button>
            </div>
          )}
          {error && <div className="error-banner" role="alert" aria-live="polite"><strong>{t("error")}</strong><span>{error}</span>{snapshotConflict && <button type="button" data-testid="resync-workspace" onClick={() => void resyncWorkspace()}>{locale === "zh" ? "重新同步" : "Resync"}</button>}<button aria-label={t("routingDismiss")} onClick={() => { setError(""); setSnapshotConflict(false); }}>×</button></div>}
          {section === "today" && !question && !result && nextAction
            && primaryAction === "next_action" && (
            <NextActionCard
              locale={locale}
              action={nextAction}
              busy={practiceBusy}
              onUpload={() => navigateWithinWorkspace(learningPath(workspace.id, "materials"))}
              onStartReview={(sessionId, topicId) => {
                if (topicId) startReviewSession(topicId, sessionId);
              }}
              onStartSession={(sessionId) => {
                const session = plan?.sessions.find((item) => item.id === sessionId);
                if (session) startPlanSession(session);
              }}
              onRepairPlan={() => navigateWithinWorkspace(learningPath(workspace.id, "plan"))}
              onStartPractice={(topicId) => {
                if (topicId) practiceTopic(topicId);
                else void getQuestion({ learningMode });
              }}
            />
          )}
          {section === "today"
            && primaryAction === "diagnostic"
            && progress
            && (
            <InitialDiagnostic
              locale={locale}
              topics={progress.topics}
              busy={practiceBusy}
              onSubmit={submitInitialDiagnostic}
            />
          )}
          {section === "today" && (question || result) && (
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
              onOpenAgentSettings={() => navigateOutsideWorkspace("/admin/integrations/chat")}
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
              onStartPlanSession={startPlanSession}
              preferredSessionId={focusedPlanSessionId}
              onSubmit={submitAnswer}
              onNextTask={() => { runGuardedPracticeAction(() => getQuestion({ learningMode, replace: true }).then(() => undefined)); }}
              onRetryTask={() => { if (question) void practiceSavedQuestion(question); }}
              onViewProgress={() => navigateWithinWorkspace(learningPath(workspace.id, "progress"))}
              onToggleSaved={(target, saved) => { void toggleSavedQuestion(target, saved); }}
              onPracticeSaved={(saved) => { void practiceSavedQuestion(saved); }}
              onOpenLibrary={() => navigateWithinWorkspace(learningPath(workspace.id, "materials"))}
              onAskCoach={askSessionCoach}
              onApplyCoachAction={applyCoachAction}
              onCoachTurnHandled={() => { pendingTurnIdRef.current = null; }}
            />
          )}
          {section === "plan" && (
            <div className="learning-path-view" data-testid="learning-path-view">
              <div className="page-section-heading">
                <span className="kicker">学习安排</span>
                <h2>{t("plan")}</h2>
                <p>{locale === "zh" ? "查看或调整当前学习空间的任务。列表和日历会自动同步。" : "View or adjust tasks in this learning space. List and calendar stay in sync."}</p>
                <div className="plan-view-toggle" aria-label={locale === "zh" ? "计划视图" : "Plan view"}>
                  <button type="button" data-testid="plan-view-list" aria-pressed={planView === "list"} onClick={() => setPlanView("list")}><List size={16} />{locale === "zh" ? "列表" : "List"}</button>
                  <button type="button" data-testid="plan-view-calendar" aria-pressed={planView === "calendar"} onClick={() => setPlanView("calendar")}><CalendarDays size={16} />{locale === "zh" ? "日历" : "Calendar"}</button>
                </div>
              </div>
              {progress && (
                <PlanSettings
                  locale={locale}
                  plan={plan}
                  topics={progress.topics}
                  topicOrder={progress.topic_order}
                  originalGoal={workspace.original_goal ?? workspace.goal}
                  busy={planSettingsBusy}
                  onSave={updatePlanSettings}
                />
              )}
              {planView === "list" ? (
                <PlanTimeline
                  plan={plan}
                  locale={locale}
                  t={t}
                  onUpdateSession={updatePlanSession}
                  onStartSession={startPlanSession}
                  practiceBusy={practiceBusy}
                  busySessionId={busySessionId}
                  topicLabels={progress?.topics}
                />
              ) : (
                <ScheduleCalendar
                  key={focusedPlanSessionId ?? "workspace-calendar"}
                  plan={plan}
                  locale={locale}
                  topicLabels={progress?.topics}
                  busySessionId={busySessionId}
                  focusedSessionId={focusedPlanSessionId}
                  onUpdateSession={updatePlanSession}
                  onStartSession={startPlanSession}
                  practiceBusy={practiceBusy}
                  onAddSession={addCalendarSession}
                  onClearPlan={clearCalendarPlan}
                />
              )}
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
              onAnalyze={analyzeMaterial}
              onCreateTargetedPlan={createTargetedPlan}
              targetedPlanBusy={targetedPlanBusy}
              targetExamAt={plan?.exam_at}
              onDownload={downloadMaterial}
              onDelete={deleteMaterial}
              onUpdate={updateMaterial}
              onBulkDelete={bulkDeleteMaterials}
              topicSuggestions={topicSuggestions}
              acceptingTopicSuggestionId={acceptingTopicSuggestionId}
              onAcceptTopicSuggestion={acceptTopicSuggestion}
              onUploadActivityChange={setUploadInProgress}
               libraryMaterials={libraryMaterials}
               linkingLibraryMaterialId={linkingLibraryMaterialId}
               onLinkLibraryMaterial={linkLibraryMaterial}
             />
          )}
          {section === "progress" && (
            <div className="learning-progress-view" data-testid="learning-progress-view">
              <div className="page-section-heading">
                <h2>{t("progress")}</h2>
                <p>{locale === "zh" ? "掌握学习状态，找到下一步重点。" : "See your learning status and what to focus on next."}</p>
                <a href="#learning-record">{locale === "zh" ? "查看学习记录" : "View learning record"}</a>
              </div>
              <div className="progress-overview-grid">
                {insights && progress && (
                  <LearningReport locale={locale} progress={progress} insights={insights} />
                )}
                <ProgressInsights
                  progress={progress}
                  t={t}
                  locale={locale}
                  topicLabels={progress?.topics}
                  insights={insights}
                  onSelectTopic={setSelectedTopicId}
                  busy={practiceBusy}
                  loading={insightsLoading}
                />
              </div>
              {selectedTopic && (
                <ProgressTopicDetail
                  locale={locale}
                  topic={selectedTopic}
                  history={insights?.mastery_history ?? []}
                  onClose={() => setSelectedTopicId(null)}
                />
              )}
              <section id="learning-record" className="learning-record">
                <div className="page-section-heading compact">
                  <span className="kicker">历史记录</span>
                  <h2>{locale === "zh" ? "学习记录" : "Learning record"}</h2>
                </div>
                <EvidenceLedger
                  evidence={evidence}
                  locale={locale}
                  t={t}
                  attempts={insights?.attempts}
                  onRetryAttempt={retryAttempt}
                  onUpdateFeedback={updateAttemptFeedback}
                />
              </section>
            </div>
          )}
        </section>
      </section>
      <ConfirmDialog
        open={navigationConfirmReason !== null}
        title={navigationConfirmReason === "upload"
          ? (locale === "zh" ? "上传仍在进行，确定离开？" : "Leave while files are uploading?")
          : (locale === "zh" ? "当前作答尚未提交，确定离开？" : "Leave with an unsaved answer?")}
        description={navigationConfirmReason === "upload"
          ? (locale === "zh" ? "离开当前学习空间会取消排队中和正在进行的上传。" : "Leaving this learning space cancels queued and active uploads.")
          : (locale === "zh" ? "草稿会保存在当前标签页；返回这道题时可以继续。" : "The draft stays in this tab so you can continue when you return.")}
        confirmLabel={locale === "zh" ? "仍然离开" : "Leave anyway"}
        cancelLabel={locale === "zh" ? "留在这里" : "Stay here"}
        tone="danger"
        onConfirm={confirmRouteNavigation}
        onCancel={cancelRouteNavigation}
      />
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
