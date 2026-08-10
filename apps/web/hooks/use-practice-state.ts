"use client";

import { useCallback, useRef, useState } from "react";

import { inferLearningMode } from "@/lib/learning-session";
import type {
  AnswerResult,
  LearningMode,
  PracticeQuestion,
  WorkspaceSnapshot,
} from "@/lib/types";


export function usePracticeState() {
  const [question, setQuestion] = useState<PracticeQuestion | null>(null);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [learningMode, setLearningMode] = useState<LearningMode>("concept");
  const [practiceBusy, setPracticeBusy] = useState(false);
  const practiceGenerationRef = useRef(0);
  const questionLoadSeqRef = useRef(0);
  const questionRequestIdRef = useRef<string | null>(null);
  const attemptIdRef = useRef<string | null>(null);

  const hydratePractice = useCallback((snapshot: WorkspaceSnapshot) => {
    practiceGenerationRef.current += 1;
    questionLoadSeqRef.current += 1;
    const activeQuestion = snapshot.active_question ?? null;
    setLearningMode(
      activeQuestion?.learning_mode
      ?? inferLearningMode(snapshot.workspace.subject, snapshot.workspace.goal),
    );
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
    setPracticeBusy(false);
  }, []);

  const clearPracticeState = useCallback(() => {
    practiceGenerationRef.current += 1;
    questionLoadSeqRef.current += 1;
    setQuestion(null);
    setAnswer("");
    setResult(null);
    setLearningMode("concept");
    setPracticeBusy(false);
    questionRequestIdRef.current = null;
    attemptIdRef.current = null;
  }, []);

  const capturePracticeGeneration = useCallback(
    () => practiceGenerationRef.current,
    [],
  );

  const isPracticeGenerationCurrent = useCallback(
    (generation: number) => practiceGenerationRef.current === generation,
    [],
  );

  const beginQuestionLoad = useCallback(() => {
    questionLoadSeqRef.current += 1;
    return questionLoadSeqRef.current;
  }, []);

  const isQuestionLoadCurrent = useCallback(
    (seq: number) => questionLoadSeqRef.current === seq,
    [],
  );

  return {
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
  };
}
