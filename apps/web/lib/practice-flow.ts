import type { PracticeQuestion } from "./types";


export async function loadNextQuestion(
  load: () => Promise<PracticeQuestion>,
  apply: (question: PracticeQuestion) => void,
): Promise<void> {
  const question = await load();
  apply(question);
}
