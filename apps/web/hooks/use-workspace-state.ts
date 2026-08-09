"use client";

import { useCallback, useState } from "react";

import type {
  LearningEvidence,
  LearningInsights,
  LearningWorkspace,
  MaterialRecord,
  NextAction,
  Progress,
  SavedPracticeQuestion,
  StudyPlan,
  TopicSuggestion,
  WorkspaceRoute,
  WorkspaceSnapshot,
} from "@/lib/types";


export function useWorkspaceState() {
  const [workspaces, setWorkspaces] = useState<LearningWorkspace[]>([]);
  const [workspace, setWorkspace] = useState<LearningWorkspace | null>(null);
  const [plan, setPlan] = useState<StudyPlan | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [evidence, setEvidence] = useState<LearningEvidence[]>([]);
  const [insights, setInsights] = useState<LearningInsights | null>(null);
  const [selectedTopicId, setSelectedTopicId] = useState<string | null>(null);
  const [materials, setMaterials] = useState<MaterialRecord[]>([]);
  const [nextAction, setNextAction] = useState<NextAction | null>(null);
  const [topicSuggestions, setTopicSuggestions] = useState<TopicSuggestion[]>([]);
  const [savedQuestions, setSavedQuestions] = useState<SavedPracticeQuestion[]>([]);
  const [route, setRoute] = useState<WorkspaceRoute | null>(null);
  const [previousWorkspaceId, setPreviousWorkspaceId] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);

  const applySnapshot = useCallback((snapshot: WorkspaceSnapshot) => {
    setWorkspace(snapshot.workspace);
    setProgress(snapshot.progress);
    setPlan(snapshot.plan);
    setEvidence(snapshot.evidence);
    setInsights(null);
    setSelectedTopicId(null);
    setMaterials(snapshot.materials);
    setNextAction(snapshot.next_action);
    setTopicSuggestions(snapshot.topic_suggestions ?? []);
    setSavedQuestions(snapshot.saved_questions ?? []);
  }, []);

  const clearWorkspaceState = useCallback(() => {
    setWorkspace(null);
    setPlan(null);
    setProgress(null);
    setEvidence([]);
    setInsights(null);
    setSelectedTopicId(null);
    setMaterials([]);
    setNextAction(null);
    setTopicSuggestions([]);
    setSavedQuestions([]);
    setRoute(null);
    setPreviousWorkspaceId(null);
  }, []);

  return {
    applySnapshot,
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
    topicSuggestions,
    workspace,
    workspaces,
  };
}
