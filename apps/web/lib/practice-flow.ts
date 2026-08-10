import { ApiError } from "./api";
import type { PracticeQuestion } from "./types";


export async function loadNextQuestion(
  load: () => Promise<PracticeQuestion>,
  apply: (question: PracticeQuestion) => void,
  isCurrent?: () => boolean,
): Promise<void> {
  const question = await load();
  // A newer question request (e.g. a learning-mode switch) may have started
  // while this one was loading; a late response must not overwrite the
  // question the learner is now looking at.
  if (isCurrent && !isCurrent()) return;
  apply(question);
}

export function shouldRetainQuestionRequestId(error: unknown): boolean {
  return !(error instanceof ApiError) || error.status === 408 || error.status >= 500;
}
