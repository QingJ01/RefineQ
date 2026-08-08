export type PracticeNavigationAction = () => void | Promise<void>;

export function hasUnsavedPracticeDraft(
  answer: string,
  hasQuestion: boolean,
  hasResult: boolean,
): boolean {
  return hasQuestion && !hasResult && answer.trim().length > 0;
}

export function guardPracticeNavigation(
  hasDraft: boolean,
  action: PracticeNavigationAction,
  defer: (action: PracticeNavigationAction) => void,
): boolean {
  if (hasDraft) {
    defer(action);
    return false;
  }
  void action();
  return true;
}
