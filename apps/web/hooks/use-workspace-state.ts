"use client";

import { useCallback, useState } from "react";

import type {
  LearningEvidence,
  LearningInsights,
  LearningWorkspace,
  MaterialRecord,
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
    topicSuggestions,
    workspace,
    workspaces,
  };
}
