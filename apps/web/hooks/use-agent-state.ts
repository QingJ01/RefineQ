"use client";

import { useCallback, useState } from "react";

import { api } from "@/lib/api";
import type { AnswerResult, LearningMode, PracticeQuestion } from "@/lib/types";


type CoachContext = {
  token?: string;
  workspaceId?: string;
  learningMode: LearningMode;
  question: PracticeQuestion | null;
  result: AnswerResult | null;
  answer: string;
  errorMessage: string;
};


export function useAgentState() {
  const [coachSessionId, setCoachSessionId] = useState<string | undefined>();

  const askCoach = useCallback(async (message: string, context: CoachContext) => {
    if (!context.token || !context.workspaceId) throw new Error(context.errorMessage);
    const reply = await api.chatWorkspace(
      context.token,
      context.workspaceId,
      message,
      coachSessionId,
      crypto.randomUUID(),
      undefined,
      {
        learning_mode: context.learningMode,
        stage: context.result ? "reflect" : context.question ? "practice" : "learn",
        question: context.question?.prompt,
        draft: context.answer || undefined,
        feedback: context.result?.feedback,
      },
    );
    setCoachSessionId(reply.session_id);
    return reply;
  }, [coachSessionId]);

  const resetAgent = useCallback(() => setCoachSessionId(undefined), []);

  return { askCoach, resetAgent };
}
